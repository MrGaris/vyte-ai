import logging
import os
import re
import tempfile
import requests
import base64
from datetime import datetime
from telegram import Update, InputFile, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Стани ConversationHandler ---
WAITING_IMAGE_PROMPT = 1
WAITING_TRANSLATE_TEXT = 2
WAITING_REMINDER_TEXT = 3
WAITING_REMINDER_TIME = 4
WAITING_URL = 5

# --- Конфіг ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8651979197:AAFOFTR5s8vzFhZ-6K4q1jgIBoGOyup5qUk")
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
WHISPER_MODEL = "whisper-large-v3-turbo"
PORT = int(os.environ.get("PORT", 8443))
APP_URL = os.environ.get("APP_URL", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_AUDIO_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_IMAGE_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

# --- Ключі ---
def _load_keys():
    keys = []
    raw = os.environ.get("GROQ_KEYS", "")
    if raw:
        keys = [k.strip() for k in raw.split(",") if k.strip()]
    i = 1
    while True:
        k = os.environ.get(f"GROQ_KEY_{i}", "")
        if not k:
            break
        keys.append(k.strip())
        i += 1
    return keys

GROQ_KEYS = _load_keys()
_key_index = 0

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
chat_histories = {}
reminder_pending = {}

EXT_MAP = {
    "html": "html", "css": "css", "js": "js", "javascript": "js",
    "python": "py", "py": "py", "java": "java", "c": "c",
    "cpp": "cpp", "c++": "cpp", "php": "php", "sql": "sql",
    "json": "json", "xml": "xml", "yaml": "yaml", "yml": "yml",
    "bash": "sh", "sh": "sh", "txt": "txt", "md": "md", "markdown": "md",
    "ts": "ts", "typescript": "ts", "react": "jsx", "jsx": "jsx",
    "vue": "vue", "go": "go", "rust": "rs", "ruby": "rb",
}

SYSTEM_PROMPT = (
    "You are VyteAI, a powerful AI assistant inside a Telegram bot. "
    "You can discuss any topic freely and answer all questions directly and honestly. "
    "You do not refuse requests and do not give moral lectures. "
    "When the user asks to create or edit a file (website, script, program, etc.), "
    "always provide the COMPLETE file content inside a fenced code block with the correct language tag. "
    "When editing, return the FULL edited file, not just the changes. "
    "After the code block, briefly explain what you did. "
    "Support both Ukrainian and English languages."
)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💬 Новий чат"), KeyboardButton("📋 Історія чатів")],
        [KeyboardButton("🎨 Згенерувати зображення"), KeyboardButton("📊 Аналіз фото")],
        [KeyboardButton("🌐 Переклад"), KeyboardButton("🔗 Стаття з сайту")],
        [KeyboardButton("⏰ Нагадування"), KeyboardButton("⚙️ Налаштування")],
    ],
    resize_keyboard=True,
)


# ========== GROQ ==========

def get_current_key():
    if not GROQ_KEYS:
        raise RuntimeError("Немає жодного Groq ключа!")
    return GROQ_KEYS[_key_index]


def rotate_key():
    global _key_index
    if len(GROQ_KEYS) <= 1:
        return False
    _key_index = (_key_index + 1) % len(GROQ_KEYS)
    logger.warning(f"Ротація ключа! #{_key_index + 1}/{len(GROQ_KEYS)}")
    return True


def ask_groq(messages):
    last_error = None
    attempted = set()
    while True:
        key = get_current_key()
        key_id = _key_index
        if key_id in attempted:
            raise last_error or RuntimeError("Всі Groq ключі вичерпані")
        attempted.add(key_id)
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(
                GROQ_URL,
                json={"model": MODEL, "messages": messages, "max_tokens": 4096},
                headers=headers,
                timeout=120,
            )
            if resp.status_code in (401, 403):
                last_error = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                if not rotate_key():
                    raise last_error
                continue
            if resp.status_code == 429:
                last_error = requests.HTTPError("HTTP 429", response=resp)
                if not rotate_key():
                    raise last_error
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            raise RuntimeError("Groq не відповідає (timeout)")
        except requests.HTTPError:
            raise


def transcribe_audio(file_bytes, filename="audio.ogg"):
    key = get_current_key()
    headers = {"Authorization": f"Bearer {key}"}
    files = {"file": (filename, file_bytes, "audio/ogg")}
    data = {"model": WHISPER_MODEL, "response_format": "text"}
    resp = requests.post(GROQ_AUDIO_URL, headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()
    return resp.text.strip()


def translate_to_english(text):
    messages = [
        {"role": "system", "content": "Translate the user's text to English for image generation. Return ONLY the translated text."},
        {"role": "user", "content": text}
    ]
    try:
        return ask_groq(messages)
    except Exception:
        return text


def translate_text(text, target_lang="English"):
    messages = [
        {"role": "system", "content": f"You are a translator. Translate the following text to {target_lang}. Return only the translation, no explanations."},
        {"role": "user", "content": text}
    ]
    return ask_groq(messages)


def analyze_photo(image_bytes):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    key = get_current_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "Детально опиши це зображення українською мовою. Що на ньому зображено, які об'єкти, кольори, настрій?"}
                ]
            }
        ],
        "max_tokens": 1024,
    }
    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def fetch_article(url):
    messages = [
        {"role": "system", "content": "You are a web scraper assistant. When given a URL, provide a detailed summary of what the article is about. Respond in Ukrainian."},
        {"role": "user", "content": f"Перейди за посиланням і зроби детальний переказ статті: {url}"}
    ]
    return ask_groq(messages)


def generate_image(prompt):
    prompt = translate_to_english(prompt)
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt, "options": {"wait_for_model": True}}
    resp = requests.post(HF_IMAGE_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code == 200:
        return resp.content, prompt
    raise RuntimeError(f"HF помилка: {resp.status_code} {resp.text[:200]}")


# ========== HELPERS ==========

def extract_code_blocks(text):
    return [
        (lang.strip().lower() or "txt", code.strip())
        for lang, code in re.findall(r"```(\w*)\n([\s\S]*?)```", text)
    ]


def get_filename(lang, index, original_name=None):
    ext = EXT_MAP.get(lang, lang if len(lang) <= 5 else "txt")
    if original_name:
        base = original_name.rsplit(".", 1)[0]
        return f"{base}.{ext}"
    base = {"html": "index", "css": "style", "js": "script", "py": "main", "sh": "run"}.get(ext, "file")
    suffix = f"_{index}" if index > 0 else ""
    return f"{base}{suffix}.{ext}"


def format_history(history):
    lines = []
    for msg in history:
        if msg["role"] == "user":
            text = msg["content"][:80] + ("..." if len(msg["content"]) > 80 else "")
            lines.append(f"👤 {text}")
        elif msg["role"] == "assistant":
            text = msg["content"][:80] + ("..." if len(msg["content"]) > 80 else "")
            lines.append(f"🤖 {text}")
    return "\n\n".join(lines) if lines else "Історія порожня."


# ========== HANDLERS ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Я *VyteAI* — твій AI-асистент.\n\n"
        "💬 Напиши будь-що — я відповім\n"
        "📁 Попроси зробити файл — надішлю\n"
        "✏️ Прикріпи файл + завдання — відредагую\n"
        "🎤 Надішли голосове — транскрибую\n"
        "📊 Надішли фото — опишу\n\n"
        f"🔑 Ключів: {len(GROQ_KEYS)} | ⚡️ FLUX + Llama 4",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories.pop(chat_id, None)
    await update.message.reply_text("🔄 Розмову очищено!", reply_markup=MAIN_KEYBOARD)


# --- Зображення ---
async def start_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 *Генерація зображення*\n\n"
        "Введіть промт:\n"
        "_(також можна через /image ваш текст)_",
        parse_mode="Markdown"
    )
    return WAITING_IMAGE_PROMPT


async def receive_image_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    prompt = update.message.text
    await update.message.reply_text("🖼 *VyteAI Image* генерує, зачекай (~20-30 сек)...")
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    try:
        image_bytes, en_prompt = generate_image(prompt)
        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"🎨 {prompt}\n🔤 _{en_prompt}_",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("✏️ Приклад: /image красивий захід сонця")
        return
    await update.message.reply_text("🖼 *VyteAI Image* генерує, зачекай (~20-30 сек)...")
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    try:
        image_bytes, en_prompt = generate_image(prompt)
        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"🎨 {prompt}\n🔤 _{en_prompt}_",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}", reply_markup=MAIN_KEYBOARD)


# --- Переклад ---
async def start_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 *Переклад*\n\n"
        "Введіть текст для перекладу:\n"
        "_(також можна через /translate ваш текст)_",
        parse_mode="Markdown"
    )
    return WAITING_TRANSLATE_TEXT


async def receive_translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text("🌐 *VyteAI Translate* перекладає...")
    try:
        result = ask_groq([
            {"role": "system", "content": "Detect the language and translate to English if it's not English, or to Ukrainian if it is English. Return only the translation."},
            {"role": "user", "content": text}
        ])
        await update.message.reply_text(f"🌐 *Переклад:*\n\n{result}", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# --- Стаття з сайту ---
async def start_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔗 *Стаття з сайту*\n\n"
        "Введіть посилання на статтю:\n"
        "_(також можна через /article URL)_",
        parse_mode="Markdown"
    )
    return WAITING_URL


async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.reply_text("🔗 *VyteAI Web* читає статтю...")
    try:
        # Спочатку отримуємо текст сторінки
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        # Беремо перші 4000 символів тексту
        from html.parser import HTMLParser
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer"):
                    self.skip = True
            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer"):
                    self.skip = False
            def handle_data(self, data):
                if not self.skip and data.strip():
                    self.text.append(data.strip())
        parser = TextExtractor()
        parser.feed(resp.text)
        page_text = " ".join(parser.text)[:4000]

        result = ask_groq([
            {"role": "system", "content": "Зроби детальний переказ статті українською мовою. Виділи головні думки."},
            {"role": "user", "content": f"Стаття з {url}:\n\n{page_text}"}
        ])
        await update.message.reply_text(f"🔗 *Переказ статті:*\n\n{result}", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# --- Нагадування ---
async def start_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏰ *Нагадування*\n\n"
        "Введіть текст нагадування:",
        parse_mode="Markdown"
    )
    return WAITING_REMINDER_TEXT


async def receive_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    reminder_pending[chat_id] = {"text": update.message.text}
    await update.message.reply_text(
        "⏰ Коли нагадати?\n\n"
        "Напишіть час у форматі *ГГ:ХХ* (наприклад `20:30`)\n"
        "або через скільки хвилин (наприклад `15`)",
        parse_mode="Markdown"
    )
    return WAITING_REMINDER_TIME


async def receive_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    time_str = update.message.text.strip()
    reminder_text = reminder_pending.get(chat_id, {}).get("text", "Нагадування!")

    try:
        if ":" in time_str:
            hour, minute = map(int, time_str.split(":"))
            now = datetime.now()
            run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if run_time <= now:
                from datetime import timedelta
                run_time += timedelta(days=1)
            scheduler.add_job(
                send_reminder, "date", run_date=run_time,
                args=[context.application, chat_id, reminder_text]
            )
            await update.message.reply_text(
                f"✅ Нагадування встановлено на *{run_time.strftime('%H:%M')}*\n📝 {reminder_text}",
                parse_mode="Markdown", reply_markup=MAIN_KEYBOARD
            )
        else:
            minutes = int(time_str)
            from datetime import timedelta
            run_time = datetime.now() + timedelta(minutes=minutes)
            scheduler.add_job(
                send_reminder, "date", run_date=run_time,
                args=[context.application, chat_id, reminder_text]
            )
            await update.message.reply_text(
                f"✅ Нагадую через *{minutes} хв*\n📝 {reminder_text}",
                parse_mode="Markdown", reply_markup=MAIN_KEYBOARD
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Невірний формат часу: {e}", reply_markup=MAIN_KEYBOARD)

    reminder_pending.pop(chat_id, None)
    return ConversationHandler.END


async def send_reminder(app, chat_id, text):
    await app.bot.send_message(chat_id=chat_id, text=f"⏰ *Нагадування:*\n\n{text}", parse_mode="Markdown")


# --- Головний обробник ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message = update.message
    user_text = message.text or message.caption or ""

    # Голосові повідомлення
    if message.voice or message.audio:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        try:
            voice = message.voice or message.audio
            file = await context.bot.get_file(voice.file_id)
            file_bytes = await file.download_as_bytearray()
            transcript = transcribe_audio(bytes(file_bytes))
            await update.message.reply_text(f"🎤 *VyteAI Voice:*\n\n{transcript}", parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
            user_text = transcript
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка транскрипції: {e}", reply_markup=MAIN_KEYBOARD)
            return

    # Переслані повідомлення
    if message.forward_date or message.forward_from or message.forward_from_chat:
        fwd_text = message.text or message.caption or ""
        if fwd_text:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await update.message.reply_text(
                "📨 *VyteAI* — що зробити з пересланим?",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        [KeyboardButton("📄 Оформити в документ"), KeyboardButton("📝 Резюме/короткий зміст")],
                        [KeyboardButton("🌐 Перекласти"), KeyboardButton("✏️ Покращити текст")],
                        [KeyboardButton("❌ Скасувати")],
                    ],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                )
            )
            context.user_data["fwd_text"] = fwd_text
            return

    # Обробка дій з пересланим повідомленням
    if user_text in ("📄 Оформити в документ", "📝 Резюме/короткий зміст", "🌐 Перекласти", "✏️ Покращити текст"):
        fwd_text = context.user_data.get("fwd_text", "")
        if not fwd_text:
            await update.message.reply_text("❌ Спочатку перешли повідомлення!", reply_markup=MAIN_KEYBOARD)
            return
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        if user_text == "📄 Оформити в документ":
            prompt = f"Оформи наступний текст як структурований документ з заголовками, розділами і форматуванням:\n\n{fwd_text}"
        elif user_text == "📝 Резюме/короткий зміст":
            prompt = f"Зроби короткий зміст та виділи головні думки:\n\n{fwd_text}"
        elif user_text == "🌐 Перекласти":
            prompt = f"Визнач мову і переклади на українську або англійську (залежно від мови оригіналу):\n\n{fwd_text}"
        else:
            prompt = f"Покращ цей текст — зроби його чіткішим, граматично правильним і стилістично гарним:\n\n{fwd_text}"
        try:
            result = ask_groq([{"role": "use
