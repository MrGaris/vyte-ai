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


# --- Мови ---
LANGUAGES = {
    "en": {
        "start": "👋 Hello! I'm *VyteAI* — your AI assistant.\n\n💬 Write anything — I'll respond\n📁 Ask to create a file — I'll send it\n✏️ Attach a file + task — I'll edit it\n🎤 Send a voice message — I'll transcribe\n📊 Send a photo — I'll describe it\n\n🔑 Keys: {keys} | ⚡️ VyteAI Basic",
        "new_chat": "🆕 New chat started!",
        "history_empty": "📋 History is empty.",
        "history_title": "📋 *Last conversation:*\n\n",
        "settings": "⚙️ *Settings*\n\n🤖 Model: `VyteAI Basic`\n🎤 Voice: `VyteAI Voice`\n🔑 Keys: {keys}\n🔄 Active: #{idx}\n\nCommands:\n/reset — clear chat\n/image — generate image\n/translate — translate\n/article — article from URL\n/lang — change language",
        "send_photo": "📊 Send a photo and I'll describe it!",
        "image_prompt": "🎨 *VyteAI Image*\n\nEnter image prompt:\n_(also via /image your text)_",
        "generating": "🖼 VyteAI Image generating, please wait (~20-30 sec)...",
        "translate_prompt": "🌐 *VyteAI Translate*\n\nEnter text to translate:\n_(also via /translate your text)_",
        "translating": "🌐 VyteAI Translate is working...",
        "url_prompt": "🔗 *VyteAI Web*\n\nEnter article URL:\n_(also via /article URL)_",
        "reading": "🔗 VyteAI Web is reading...",
        "reminder_text": "⏰ *Reminder*\n\nEnter reminder text:",
        "reminder_time": "⏰ When to remind?\n\nEnter time *HH:MM* (e.g. `20:30`)\nor minutes from now (e.g. `15`)",
        "reminder_set": "✅ Reminder set for *{time}*\n📝 {text}",
        "reminder_min": "✅ Reminding in *{min} min*\n📝 {text}",
        "reminder_arrived": "⏰ *Reminder:*\n\n{text}",
        "error": "❌ Error: {e}",
        "cancelled": "❌ Cancelled.",
        "no_fwd": "❌ First forward a message!",
        "fwd_menu": "📨 VyteAI — what to do with forwarded message?",
        "write_something": "✏️ Write something or ask a question!",
        "transcription": "🎤 *VyteAI Voice:*\n\n",
        "photo_analysis": "🖼 *VyteAI Vision:*\n\n",
        "article_result": "🔗 *Article summary:*\n\n",
        "translate_result": "🌐 *Translation:*\n\n",
        "choose_lang": "🌐 Choose language:",
        "lang_set": "✅ Language set to English!",
        "btn_new_chat": "💬 New Chat",
        "btn_history": "📋 Chat History",
        "btn_image": "🎨 Generate Image",
        "btn_photo": "📊 Photo Analysis",
        "btn_translate": "🌐 Translate",
        "btn_url": "🔗 Article from URL",
        "btn_reminder": "⏰ Reminder",
        "btn_settings": "⚙️ Settings",
        "btn_doc": "📄 Make Document",
        "btn_summary": "📝 Summary",
        "btn_translate2": "🌐 Translate",
        "btn_improve": "✏️ Improve Text",
        "btn_cancel": "❌ Cancel",
    },
    "uk": {
        "start": "👋 Привіт! Я *VyteAI* — твій AI-асистент.\n\n💬 Напиши будь-що — я відповім\n📁 Попроси зробити файл — надішлю\n✏️ Прикріпи файл + завдання — відредагую\n🎤 Надішли голосове — транскрибую\n📊 Надішли фото — опишу\n\n🔑 Ключів: {keys} | ⚡️ VyteAI Basic",
        "new_chat": "🆕 Новий чат розпочато!",
        "history_empty": "📋 Історія порожня.",
        "history_title": "📋 *Остання розмова:*\n\n",
        "settings": "⚙️ *Налаштування*\n\n🤖 Модель: `VyteAI Basic`\n🎤 Голос: `VyteAI Voice`\n🔑 Ключів: {keys}\n🔄 Активний: #{idx}\n\nКоманди:\n/reset — очистити розмову\n/image — генерація фото\n/translate — переклад\n/article — стаття\n/lang — змінити мову",
        "send_photo": "📊 Надішли фото — і я його опишу!",
        "image_prompt": "🎨 *VyteAI Image*\n\nВведіть промт:\n_(також можна через /image ваш текст)_",
        "generating": "🖼 VyteAI Image генерує, зачекай (~20-30 сек)...",
        "translate_prompt": "🌐 *VyteAI Translate*\n\nВведіть текст для перекладу:\n_(також можна через /translate ваш текст)_",
        "translating": "🌐 VyteAI Translate перекладає...",
        "url_prompt": "🔗 *VyteAI Web*\n\nВведіть посилання на статтю:\n_(також можна через /article URL)_",
        "reading": "🔗 VyteAI Web читає статтю...",
        "reminder_text": "⏰ *Нагадування*\n\nВведіть текст нагадування:",
        "reminder_time": "⏰ Коли нагадати?\n\nНапишіть час *ГГ:ХХ* (наприклад `20:30`)\nабо через скільки хвилин (наприклад `15`)",
        "reminder_set": "✅ Нагадування на *{time}*\n📝 {text}",
        "reminder_min": "✅ Нагадую через *{min} хв*\n📝 {text}",
        "reminder_arrived": "⏰ *Нагадування:*\n\n{text}",
        "error": "❌ Помилка: {e}",
        "cancelled": "❌ Скасовано.",
        "no_fwd": "❌ Спочатку перешли повідомлення!",
        "fwd_menu": "📨 VyteAI — що зробити з пересланим?",
        "write_something": "✏️ Напиши що зробити або задай питання!",
        "transcription": "🎤 *VyteAI Voice:*\n\n",
        "photo_analysis": "🖼 *VyteAI Vision:*\n\n",
        "article_result": "🔗 *Переказ статті:*\n\n",
        "translate_result": "🌐 *Переклад:*\n\n",
        "choose_lang": "🌐 Оберіть мову:",
        "lang_set": "✅ Мову змінено на Українську!",
        "btn_new_chat": "💬 Новий чат",
        "btn_history": "📋 Історія чатів",
        "btn_image": "🎨 Згенерувати зображення",
        "btn_photo": "📊 Аналіз фото",
        "btn_translate": "🌐 Переклад",
        "btn_url": "🔗 Стаття з сайту",
        "btn_reminder": "⏰ Нагадування",
        "btn_settings": "⚙️ Налаштування",
        "btn_doc": "📄 Оформити в документ",
        "btn_summary": "📝 Резюме",
        "btn_translate2": "🌐 Перекласти",
        "btn_improve": "✏️ Покращити текст",
        "btn_cancel": "❌ Скасувати",
    },
    "ru": {
        "start": "👋 Привет! Я *VyteAI* — твой AI-ассистент.\n\n💬 Напиши что угодно — отвечу\n📁 Попроси создать файл — пришлю\n✏️ Прикрепи файл + задание — отредактирую\n🎤 Пришли голосовое — расшифрую\n📊 Пришли фото — опишу\n\n🔑 Ключей: {keys} | ⚡️ VyteAI Basic",
        "new_chat": "🆕 Новый чат начат!",
        "history_empty": "📋 История пуста.",
        "history_title": "📋 *Последний разговор:*\n\n",
        "settings": "⚙️ *Настройки*\n\n🤖 Модель: `VyteAI Basic`\n🎤 Голос: `VyteAI Voice`\n🔑 Ключей: {keys}\n🔄 Активный: #{idx}\n\nКоманды:\n/reset — очистить чат\n/image — генерация фото\n/translate — перевод\n/article — статья\n/lang — сменить язык",
        "send_photo": "📊 Пришли фото — и я его опишу!",
        "image_prompt": "🎨 *VyteAI Image*\n\nВведи промт:\n_(также через /image твой текст)_",
        "generating": "🖼 VyteAI Image генерирует, подожди (~20-30 сек)...",
        "translate_prompt": "🌐 *VyteAI Translate*\n\nВведи текст для перевода:\n_(также через /translate твой текст)_",
        "translating": "🌐 VyteAI Translate переводит...",
        "url_prompt": "🔗 *VyteAI Web*\n\nВведи ссылку на статью:\n_(также через /article URL)_",
        "reading": "🔗 VyteAI Web читает статью...",
        "reminder_text": "⏰ *Напоминание*\n\nВведи текст напоминания:",
        "reminder_time": "⏰ Когда напомнить?\n\nНапиши время *ЧЧ:ММ* (например `20:30`)\nили через сколько минут (например `15`)",
        "reminder_set": "✅ Напоминание на *{time}*\n📝 {text}",
        "reminder_min": "✅ Напомню через *{min} мин*\n📝 {text}",
        "reminder_arrived": "⏰ *Напоминание:*\n\n{text}",
        "error": "❌ Ошибка: {e}",
        "cancelled": "❌ Отменено.",
        "no_fwd": "❌ Сначала перешли сообщение!",
        "fwd_menu": "📨 VyteAI — что сделать с пересланным?",
        "write_something": "✏️ Напиши что сделать или задай вопрос!",
        "transcription": "🎤 *VyteAI Voice:*\n\n",
        "photo_analysis": "🖼 *VyteAI Vision:*\n\n",
        "article_result": "🔗 *Пересказ статьи:*\n\n",
        "translate_result": "🌐 *Перевод:*\n\n",
        "choose_lang": "🌐 Выберите язык:",
        "lang_set": "✅ Язык изменён на Русский!",
        "btn_new_chat": "💬 Новый чат",
        "btn_history": "📋 История чатов",
        "btn_image": "🎨 Генерация изображения",
        "btn_photo": "📊 Анализ фото",
        "btn_translate": "🌐 Перевод",
        "btn_url": "🔗 Статья с сайта",
        "btn_reminder": "⏰ Напоминание",
        "btn_settings": "⚙️ Настройки",
        "btn_doc": "📄 Оформить в документ",
        "btn_summary": "📝 Резюме",
        "btn_translate2": "🌐 Перевести",
        "btn_improve": "✏️ Улучшить текст",
        "btn_cancel": "❌ Отмена",
    },
}

user_languages = {}  # chat_id -> "en"/"uk"/"ru"

def get_lang(chat_id):
    return user_languages.get(chat_id, "en")

def t(chat_id, key, **kwargs):
    lang = get_lang(chat_id)
    text = LANGUAGES[lang].get(key, LANGUAGES["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text

def get_keyboard(chat_id):
    lang = get_lang(chat_id)
    L = LANGUAGES[lang]
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(L["btn_new_chat"]), KeyboardButton(L["btn_history"])],
            [KeyboardButton(L["btn_image"]), KeyboardButton(L["btn_photo"])],
            [KeyboardButton(L["btn_translate"]), KeyboardButton(L["btn_url"])],
            [KeyboardButton(L["btn_reminder"]), KeyboardButton(L["btn_settings"])],
        ],
        resize_keyboard=True,
    )

def get_fwd_keyboard(chat_id):
    lang = get_lang(chat_id)
    L = LANGUAGES[lang]
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(L["btn_doc"]), KeyboardButton(L["btn_summary"])],
            [KeyboardButton(L["btn_translate2"]), KeyboardButton(L["btn_improve"])],
            [KeyboardButton(L["btn_cancel"])],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

# --- Стани ConversationHandler ---
WAITING_IMAGE_PROMPT = 1
WAITING_TRANSLATE_TEXT = 2
WAITING_REMINDER_TEXT = 3
WAITING_REMINDER_TIME = 4
WAITING_URL = 5

# --- Конфіг ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8651979197:AAFOFTR5s8vzFhZ-6K4q1jgIBoGOyup5qUk")
MODEL = "meta-llama/VyteAI Pro 1.0"
WHISPER_MODEL = "VyteAI Voice"
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

# MAIN_KEYBOARD замінено на get_keyboard(chat_id)


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
        "model": "meta-llama/VyteAI Pro 1.0",
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


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("🇬🇧 English"), KeyboardButton("🇺🇦 Українська")],
            [KeyboardButton("🇷🇺 Русский")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(t(chat_id, "choose_lang"), reply_markup=keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # Якщо мова ще не вибрана — показуємо вибір мови
    if chat_id not in user_languages:
        keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("🇬🇧 English"), KeyboardButton("🇺🇦 Українська")],
                [KeyboardButton("🇷🇺 Русский")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await update.message.reply_text(
            "🌐 Choose your language / Оберіть мову / Выберите язык:",
            reply_markup=keyboard,
        )
        return
    await update.message.reply_text(
        t(chat_id, "start", keys=len(GROQ_KEYS)),
        parse_mode="Markdown",
        reply_markup=get_keyboard(chat_id),
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories.pop(chat_id, None)
    await update.message.reply_text("🔄 Reset!", reply_markup=get_keyboard(chat_id))


# --- Зображення ---
async def start_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(t(chat_id, "image_prompt"), parse_mode="Markdown")
    return WAITING_IMAGE_PROMPT


async def receive_image_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    prompt = update.message.text
    await update.message.reply_text(t(chat_id, "generating"))
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    try:
        image_bytes, en_prompt = generate_image(prompt)
        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"🖼 VyteAI Image\n\n{prompt}",
            reply_markup=get_keyboard(chat_id),
        )
    except Exception as e:
        await update.message.reply_text(t(chat_id, "error", e=e), reply_markup=get_keyboard(chat_id))
    return ConversationHandler.END


async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text(t(chat_id, "image_prompt"), parse_mode="Markdown")
        return
    await update.message.reply_text(t(chat_id, "generating"))
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    try:
        image_bytes, en_prompt = generate_image(prompt)
        await update.message.reply_photo(
            photo=image_bytes,
            caption=f"🖼 VyteAI Image\n\n{prompt}",
            reply_markup=get_keyboard(chat_id),
        )
    except Exception as e:
        await update.message.reply_text(t(chat_id, "error", e=e), reply_markup=get_keyboard(chat_id))


# --- Переклад ---
async def start_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(t(chat_id, "translate_prompt"), parse_mode="Markdown")
    return WAITING_TRANSLATE_TEXT


async def receive_translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    await update.message.reply_text(t(chat_id, "translating"))
    try:
        result = ask_groq([
            {"role": "system", "content": "Detect the language and translate to English if it's not English, or to Ukrainian if it is English. Return only the translation."},
            {"role": "user", "content": text}
        ])
        await update.message.reply_text(t(chat_id, "translate_result") + result, parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
    except Exception as e:
        await update.message.reply_text(t(chat_id, "error", e=e), reply_markup=get_keyboard(chat_id))
    return ConversationHandler.END


# --- Стаття з сайту ---
async def start_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(t(chat_id, "url_prompt"), parse_mode="Markdown")
    return WAITING_URL


async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    url = update.message.text.strip()
    await update.message.reply_text(t(chat_id, "reading"))
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
            {"role": "system", "content": "Summarize this article in the same language the user prefers. Be detailed and highlight main points."},
            {"role": "user", "content": f"Article from {url}:\n\n{page_text}"}
        ])
        await update.message.reply_text(t(chat_id, "article_result") + result, parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
    except Exception as e:
        await update.message.reply_text(t(chat_id, "error", e=e), reply_markup=get_keyboard(chat_id))
    return ConversationHandler.END


# --- Нагадування ---
async def start_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(t(chat_id, "reminder_text"), parse_mode="Markdown")
    return WAITING_REMINDER_TEXT


async def receive_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    reminder_pending[chat_id] = {"text": update.message.text}
    await update.message.reply_text(t(chat_id, "reminder_time"), parse_mode="Markdown")
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
                args=[context.application, chat_id, reminder_text],
                id=f"reminder_{chat_id}_{datetime.now().timestamp()}"
            )
            await update.message.reply_text(
                t(chat_id, "reminder_set", time=run_time.strftime('%H:%M'), text=reminder_text),
                parse_mode="Markdown", reply_markup=get_keyboard(chat_id)
            )
        else:
            minutes = int(time_str)
            from datetime import timedelta
            run_time = datetime.now() + timedelta(minutes=minutes)
            scheduler.add_job(
                send_reminder, "date", run_date=run_time,
                args=[context.application, chat_id, reminder_text],
                id=f"reminder_{chat_id}_{datetime.now().timestamp()}"
            )
            await update.message.reply_text(
                t(chat_id, "reminder_min", min=minutes, text=reminder_text),
                parse_mode="Markdown", reply_markup=get_keyboard(chat_id)
            )
    except Exception as e:
        await update.message.reply_text(t(chat_id, "error", e=e), reply_markup=get_keyboard(chat_id))

    reminder_pending.pop(chat_id, None)
    return ConversationHandler.END


async def send_reminder(app, chat_id, text):
    lang = user_languages.get(chat_id, "en")
    msg = LANGUAGES[lang]["reminder_arrived"].format(text=text)
    await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")


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
            await update.message.reply_text(t(chat_id, "transcription") + transcript, parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
            user_text = transcript
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка транскрипції: {e}", reply_markup=get_keyboard(chat_id))
            return

    # Вибір мови
    if user_text in ("🇬🇧 English", "🇺🇦 Українська", "🇷🇺 Русский"):
        lang_map = {"🇬🇧 English": "en", "🇺🇦 Українська": "uk", "🇷🇺 Русский": "ru"}
        user_languages[chat_id] = lang_map[user_text]
        await update.message.reply_text(
            t(chat_id, "start", keys=len(GROQ_KEYS)),
            parse_mode="Markdown",
            reply_markup=get_keyboard(chat_id),
        )
        return

    # Кнопки меню
    btn_new_chat = [LANGUAGES[l]["btn_new_chat"] for l in LANGUAGES]
    btn_history = [LANGUAGES[l]["btn_history"] for l in LANGUAGES]
    btn_photo = [LANGUAGES[l]["btn_photo"] for l in LANGUAGES]
    btn_settings = [LANGUAGES[l]["btn_settings"] for l in LANGUAGES]
    btn_image = [LANGUAGES[l]["btn_image"] for l in LANGUAGES]
    btn_translate = [LANGUAGES[l]["btn_translate"] for l in LANGUAGES]
    btn_url = [LANGUAGES[l]["btn_url"] for l in LANGUAGES]
    btn_reminder = [LANGUAGES[l]["btn_reminder"] for l in LANGUAGES]
    btn_doc = [LANGUAGES[l]["btn_doc"] for l in LANGUAGES]
    btn_summary = [LANGUAGES[l]["btn_summary"] for l in LANGUAGES]
    btn_translate2 = [LANGUAGES[l]["btn_translate2"] for l in LANGUAGES]
    btn_improve = [LANGUAGES[l]["btn_improve"] for l in LANGUAGES]
    btn_cancel = [LANGUAGES[l]["btn_cancel"] for l in LANGUAGES]

    if user_text in btn_new_chat:
        chat_histories.pop(chat_id, None)
        await update.message.reply_text(t(chat_id, "new_chat"), reply_markup=get_keyboard(chat_id))
        return

    if user_text in btn_history:
        history = chat_histories.get(chat_id, [])
        user_msgs = [m for m in history if m["role"] != "system"]
        text = t(chat_id, "history_title") + format_history(user_msgs[-10:]) if user_msgs else t(chat_id, "history_empty")
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
        return

    if user_text in btn_photo:
        await update.message.reply_text(t(chat_id, "send_photo"), reply_markup=get_keyboard(chat_id))
        return

    if user_text in btn_settings:
        await update.message.reply_text(t(chat_id, "settings", keys=len(GROQ_KEYS), idx=_key_index+1), parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
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
            await update.message.reply_text("❌ Спочатку перешли повідомлення!", reply_markup=get_keyboard(chat_id))
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
            result = ask_groq([{"role": "user", "content": prompt}])
            context.user_data.pop("fwd_text", None)
            await update.message.reply_text(result, reply_markup=get_keyboard(chat_id))
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка: {e}", reply_markup=get_keyboard(chat_id))
        return

    if user_text == "❌ Скасувати":
        context.user_data.pop("fwd_text", None)
        await update.message.reply_text("❌ Скасовано.", reply_markup=get_keyboard(chat_id))
        return

    # Вибір мови
    if user_text in ("🇬🇧 English", "🇺🇦 Українська", "🇷🇺 Русский"):
        lang_map = {"🇬🇧 English": "en", "🇺🇦 Українська": "uk", "🇷🇺 Русский": "ru"}
        user_languages[chat_id] = lang_map[user_text]
        await update.message.reply_text(
            t(chat_id, "start", keys=len(GROQ_KEYS)),
            parse_mode="Markdown",
            reply_markup=get_keyboard(chat_id),
        )
        return

    # Кнопки меню
    btn_new_chat = [LANGUAGES[l]["btn_new_chat"] for l in LANGUAGES]
    btn_history = [LANGUAGES[l]["btn_history"] for l in LANGUAGES]
    btn_photo = [LANGUAGES[l]["btn_photo"] for l in LANGUAGES]
    btn_settings = [LANGUAGES[l]["btn_settings"] for l in LANGUAGES]
    btn_image = [LANGUAGES[l]["btn_image"] for l in LANGUAGES]
    btn_translate = [LANGUAGES[l]["btn_translate"] for l in LANGUAGES]
    btn_url = [LANGUAGES[l]["btn_url"] for l in LANGUAGES]
    btn_reminder = [LANGUAGES[l]["btn_reminder"] for l in LANGUAGES]
    btn_doc = [LANGUAGES[l]["btn_doc"] for l in LANGUAGES]
    btn_summary = [LANGUAGES[l]["btn_summary"] for l in LANGUAGES]
    btn_translate2 = [LANGUAGES[l]["btn_translate2"] for l in LANGUAGES]
    btn_improve = [LANGUAGES[l]["btn_improve"] for l in LANGUAGES]
    btn_cancel = [LANGUAGES[l]["btn_cancel"] for l in LANGUAGES]

    if user_text in btn_new_chat:
        chat_histories.pop(chat_id, None)
        await update.message.reply_text(t(chat_id, "new_chat"), reply_markup=get_keyboard(chat_id))
        return

    if user_text in btn_history:
        history = chat_histories.get(chat_id, [])
        user_msgs = [m for m in history if m["role"] != "system"]
        text = t(chat_id, "history_title") + format_history(user_msgs[-10:]) if user_msgs else t(chat_id, "history_empty")
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
        return

    if user_text in btn_photo:
        await update.message.reply_text(t(chat_id, "send_photo"), reply_markup=get_keyboard(chat_id))
        return

    if user_text in btn_settings:
        await update.message.reply_text(t(chat_id, "settings", keys=len(GROQ_KEYS), idx=_key_index+1), parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
        return

    # Переслані повідомлення
    if getattr(message, 'forward_origin', None) or getattr(message, 'forward_from', None) or getattr(message, 'forward_from_chat', None):
        fwd_text = message.text or message.caption or ""
        if fwd_text:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            fwd_keyboard = ReplyKeyboardMarkup(
                [
                    [KeyboardButton("\U0001f4c4 Оформити в документ"), KeyboardButton("\U0001f4dd Резюме")],
                    [KeyboardButton("\U0001f310 Перекласти"), KeyboardButton("\U0001f58a Покращити текст")],
                    [KeyboardButton("\u274c Скасувати")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await update.message.reply_text(t(chat_id, "fwd_menu"), reply_markup=get_fwd_keyboard(chat_id))
            context.user_data["fwd_text"] = fwd_text
            return

    # Дії з пересланим
    fwd_actions = tuple(LANGUAGES[l][k] for l in LANGUAGES for k in ["btn_doc","btn_summary","btn_translate2","btn_improve"])
    if user_text in fwd_actions:
        fwd_text = context.user_data.get("fwd_text", "")
        if not fwd_text:
            await update.message.reply_text(t(chat_id, "no_fwd"), reply_markup=get_keyboard(chat_id))
            return
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        prompts = {
            "\U0001f4c4 Оформити в документ": f"Оформи як структурований документ з заголовками:\n\n{fwd_text}",
            "\U0001f4dd Резюме": f"Зроби короткий зміст, виділи головні думки:\n\n{fwd_text}",
            "\U0001f310 Перекласти": f"Визнач мову і переклади на укр або англ:\n\n{fwd_text}",
            "\U0001f58a Покращити текст": f"Покращ текст, зроби чіткішим та граматично правильним:\n\n{fwd_text}",
        }
        try:
            result = ask_groq([{"role": "user", "content": prompts[user_text]}])
            context.user_data.pop("fwd_text", None)
            await update.message.reply_text(result, reply_markup=get_keyboard(chat_id))
        except Exception as e:
            await update.message.reply_text(f"\u274c Помилка: {e}", reply_markup=get_keyboard(chat_id))
        return

    if user_text in btn_cancel:
        context.user_data.pop("fwd_text", None)
        await update.message.reply_text(t(chat_id, "cancelled"), reply_markup=get_keyboard(chat_id))
        return

    # Аналіз фото з підписом або кнопка
    if message.photo or user_text == "📊 Аналіз фото":
        if message.photo:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            try:
                photo = message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
                file_bytes = await file.download_as_bytearray()
                result = analyze_photo(bytes(file_bytes))
                await update.message.reply_text(t(chat_id, "photo_analysis") + result, parse_mode="Markdown", reply_markup=get_keyboard(chat_id))
            except Exception as e:
                await update.message.reply_text(f"❌ Помилка аналізу: {e}", reply_markup=get_keyboard(chat_id))
            return
        else:
            await update.message.reply_text("📊 Надішли фото і я його опишу!", reply_markup=get_keyboard(chat_id))
            return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Файли
    file_content = None
    original_filename = None
    if message.document:
        doc = message.document
        original_filename = doc.file_name
        try:
            file = await context.bot.get_file(doc.file_id)
            file_bytes = await file.download_as_bytearray()
            try:
                file_content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                file_content = file_bytes.decode("latin-1")
        except Exception as e:
            await update.message.reply_text(t(chat_id, "error", e=e))
            return

    if chat_id not in chat_histories:
        chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if file_content and original_filename:
        if user_text:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nЗавдання: {user_text}"
        else:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nПроаналізуй і запитай що зробити."
    else:
        user_message = user_text

    if not user_message:
        await update.message.reply_text(t(chat_id, "write_something"), reply_markup=get_keyboard(chat_id))
        return

    chat_histories[chat_id].append({"role": "user", "content": user_message})
    if len(chat_histories[chat_id]) > 21:
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-20:]

    try:
        ai_reply = ask_groq(chat_histories[chat_id])
    except Exception as e:
        logger.error(f"Groq error: {e}")
        await update.message.reply_text(f"❌ Помилка: {e}", reply_markup=get_keyboard(chat_id))
        return

    chat_histories[chat_id].append({"role": "assistant", "content": ai_reply})
    code_blocks = extract_code_blocks(ai_reply)
    clean_reply = re.sub(r"```[\w]*\n[\s\S]*?```", "", ai_reply).strip() or "✅ Готово!"

    if code_blocks:
        for i, (lang, code) in enumerate(code_blocks):
            filename = get_filename(lang, i, original_filename if file_content else None)
            with tempfile.NamedTemporaryFile(mode="w", suffix=f".{filename.split('.')[-1]}", delete=False, encoding="utf-8") as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            try:
                with open(tmp_path, "rb") as f:
                    caption = clean_reply[:1024] if i == 0 else f"📄 {filename}"
                    await update.message.reply_document(document=InputFile(f, filename=filename), caption=caption, reply_markup=get_keyboard(chat_id))
            finally:
                os.unlink(tmp_path)
        if len(clean_reply) > 1024:
            for chunk in [clean_reply[i:i+4096] for i in range(0, len(clean_reply), 4096)]:
                await update.message.reply_text(chunk, reply_markup=get_keyboard(chat_id))
    else:
        for chunk in [ai_reply[i:i+4096] for i in range(0, len(ai_reply), 4096)]:
            await update.message.reply_text(chunk, reply_markup=get_keyboard(chat_id))


# ========== MAIN ==========

def main():
    logger.info(f"Запуск з {len(GROQ_KEYS)} Groq ключами")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Збираємо всі варіанти кнопок для всіх мов
    all_image_btns = "|".join(LANGUAGES[l]["btn_image"] for l in LANGUAGES)
    all_translate_btns = "|".join(LANGUAGES[l]["btn_translate"] for l in LANGUAGES)
    all_url_btns = "|".join(LANGUAGES[l]["btn_url"] for l in LANGUAGES)
    all_reminder_btns = "|".join(LANGUAGES[l]["btn_reminder"] for l in LANGUAGES)

    image_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^({all_image_btns})$"), start_image)],
        states={WAITING_IMAGE_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_image_prompt)]},
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    translate_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^({all_translate_btns})$"), start_translate)],
        states={WAITING_TRANSLATE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_translate_text)]},
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    url_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^({all_url_btns})$"), start_url)],
        states={WAITING_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url)]},
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    reminder_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^({all_reminder_btns})$"), start_reminder)],
        states={
            WAITING_REMINDER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reminder_text)],
            WAITING_REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reminder_time)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )

    app.add_handler(image_conv)
    app.add_handler(translate_conv)
    app.add_handler(url_conv)
    app.add_handler(reminder_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("image", image_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_message))

    scheduler.start()

    if APP_URL:
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=f"{APP_URL}/webhook", url_path="webhook")
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
