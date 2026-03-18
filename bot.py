import logging
import os
import re
import tempfile
import requests
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8651979197:AAFOFTR5s8vzFhZ-6K4q1jgIBoGOyup5qUk")
MODEL = "arcee-ai/trinity-large-preview:free"
PORT = int(os.environ.get("PORT", 8443))
APP_URL = os.environ.get("APP_URL", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def _load_keys():
    keys = []
    raw = os.environ.get(
        "OPENROUTER_KEYS",
        "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,"
        "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,"
        "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,"
        "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"
    )
    if raw:
        keys = [k.strip() for k in raw.split(",") if k.strip()]
    i = 1
    while True:
        k = os.environ.get(f"OPENROUTER_KEY_{i}", "")
        if not k:
            break
        keys.append(k.strip())
        i += 1
    return keys

OPENROUTER_KEYS = _load_keys()
_key_index = 0

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_current_key():
    if not OPENROUTER_KEYS:
        raise RuntimeError("Немає жодного OpenRouter ключа!")
    return OPENROUTER_KEYS[_key_index]


def rotate_key():
    global _key_index
    if len(OPENROUTER_KEYS) <= 1:
        return False
    _key_index = (_key_index + 1) % len(OPENROUTER_KEYS)
    logger.warning(f"Ротація ключа! Тепер #{_key_index + 1}/{len(OPENROUTER_KEYS)}")
    return True


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

chat_histories = {}


def ask_openrouter(messages):
    last_error = None
    attempted = set()

    while True:
        key = get_current_key()
        key_id = _key_index

        if key_id in attempted:
            raise last_error or RuntimeError("Всі ключі заблоковані")

        attempted.add(key_id)

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://t.me/bot",
            "X-Title": "VyteAI Bot",
        }

        try:
            resp = requests.post(
                OPENROUTER_URL,
                json={"model": MODEL, "messages": messages, "max_tokens": 4096},
                headers=headers,
                timeout=120,
            )

            if resp.status_code in (401, 403):
                logger.warning(f"Ключ #{key_id + 1} відхилено ({resp.status_code}), ротуємо...")
                last_error = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                if not rotate_key():
                    raise last_error
                continue

            if resp.status_code == 429:
                logger.warning(f"Ключ #{key_id + 1} ліміт вичерпано (429), ротуємо...")
                last_error = requests.HTTPError("HTTP 429", response=resp)
                if not rotate_key():
                    raise last_error
                continue

            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            raise RuntimeError("OpenRouter не відповідає (timeout)")
        except requests.HTTPError:
            raise


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Я VyteAI — твій AI-асистент.\n\n"
        "💬 Напиши будь-що — я відповім.\n"
        "📁 Попроси зробити файл — надішлю його!\n"
        "✏️ Прикріпи файл + напиши що змінити — відредагую і поверну!\n\n"
        "Приклади:\n"
        "• Зроби мені сайт на HTML\n"
        "• [прикріпи файл] Додай темну тему\n"
        "• [прикріпи файл] Виправ помилки\n\n"
        f"🔑 Активних ключів: {len(OPENROUTER_KEYS)}\n"
        "Команда /reset — очистити розмову."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories.pop(chat_id, None)
    await update.message.reply_text("🔄 Розмову очищено!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message = update.message
    user_text = message.text or message.caption or ""

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

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
            await update.message.reply_text(f"❌ Помилка завантаження файлу: {e}")
            return

    if chat_id not in chat_histories:
        chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if file_content and original_filename:
        if user_text:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nЗавдання: {user_text}"
        else:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nПроаналізуй і запитай що з ним зробити."
    else:
        user_message = user_text

    if not user_message:
        await update.message.reply_text("✏️ Напиши що зробити або задай питання!")
        return

    chat_histories[chat_id].append({"role": "user", "content": user_message})

    if len(chat_histories[chat_id]) > 21:
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-20:]

    try:
        ai_reply = ask_openrouter(chat_histories[chat_id])
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        await update.message.reply_text(f"❌ Помилка: {e}")
        return

    chat_histories[chat_id].append({"role": "assistant", "content": ai_reply})
    code_blocks = extract_code_blocks(ai_reply)
    clean_reply = re.sub(r"```[\w]*\n[\s\S]*?```", "", ai_reply).strip() or "✅ Готово!"

    if code_blocks:
        for i, (lang, code) in enumerate(code_blocks):
            filename = get_filename(lang, i, original_filename if file_content else None)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=f".{filename.split('.')[-1]}", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            try:
                with open(tmp_path, "rb") as f:
                    caption = clean_reply[:1024] if i == 0 else f"📄 {filename}"
                    await update.message.reply_document(
                        document=InputFile(f, filename=filename),
                        caption=caption,
                    )
            finally:
                os.unlink(tmp_path)

        if len(clean_reply) > 1024:
            for chunk in [clean_reply[i:i+4096] for i in range(0, len(clean_reply), 4096)]:
                await update.message.reply_text(chunk)
    else:
        for chunk in [ai_reply[i:i+4096] for i in range(0, len(ai_reply), 4096)]:
            await update.message.reply_text(chunk)


def main():
    logger.info(f"Запуск з {len(OPENROUTER_KEYS)} ключами OpenRouter")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    if APP_URL:
        logger.info(f"Webhook mode: port={PORT}, url={APP_URL}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{APP_URL}/webhook",
            url_path="webhook"
        )
    else:
        logger.info("Polling mode")
        app.run_polling()


if __name__ == "__main__":
    main()
            )

            if resp.status_code in (401, 403):
                logger.warning(f"Ключ #{key_id + 1} відхилено (HTTP {resp.status_code}), ротуємо...")
                last_error = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                if not rotate_key():
                    raise last_error
                continue

            if resp.status_code == 429:
                logger.warning(f"Ключ #{key_id + 1} — ліміт вичерпано (429), ротуємо...")
                last_error = requests.HTTPError("HTTP 429 Rate limit", response=resp)
                if not rotate_key():
                    raise last_error
                continue

            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            raise RuntimeError("OpenRouter не відповідає (timeout 120s)")
        except requests.HTTPError:
            raise


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key_count = len(OPENROUTER_KEYS)
    await update.message.reply_text(
        "👋 Привіт! Я VyteAI — твій AI-асистент.\n\n"
        "💬 Напиши будь-що — я відповім.\n"
        "📁 Попроси зробити файл — надішлю його!\n"
        "✏️ Прикріпи файл + напиши що змінити — відредагую і поверну!\n\n"
        "Приклади:\n"
        "• Зроби мені сайт на HTML\n"
        "• [прикріпи файл] Додай темну тему\n"
        "• [прикріпи файл] Виправ помилки\n\n"
        f"🔑 Активних ключів: {key_count}\n"
        "Команда /reset — очистити розмову."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_histories.pop(chat_id, None)
    await update.message.reply_text("🔄 Розмову очищено!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message = update.message
    user_text = message.text or message.caption or ""

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

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
            await update.message.reply_text(f"❌ Помилка завантаження файлу: {e}")
            return

    if chat_id not in chat_histories:
        chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if file_content and original_filename:
        if user_text:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nЗавдання: {user_text}"
        else:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nПроаналізуй і запитай що з ним зробити."
    else:
        user_message = user_text

    if not user_message:
        await update.message.reply_text("✏️ Напиши що зробити або задай питання!")
        return

    chat_histories[chat_id].append({"role": "user", "content": user_message})

    if len(chat_histories[chat_id]) > 21:
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-20:]

    try:
        ai_reply = ask_openrouter(chat_histories[chat_id])
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        await update.message.reply_text(f"❌ Помилка: {e}")
        return

    chat_histories[chat_id].append({"role": "assistant", "content": ai_reply})
    code_blocks = extract_code_blocks(ai_reply)
    clean_reply = re.sub(r"```[\w]*\n[\s\S]*?```", "", ai_reply).strip() or "✅ Готово!"

    if code_blocks:
        for i, (lang, code) in enumerate(code_blocks):
            filename = get_filename(lang, i, original_filename if file_content else None)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=f".{filename.split('.')[-1]}", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            try:
                with open(tmp_path, "rb") as f:
                    caption = clean_reply[:1024] if i == 0 else f"📄 {filename}"
                    await update.message.reply_document(
                        document=InputFile(f, filename=filename),
                        caption=caption,
                    )
            finally:
                os.unlink(tmp_path)

        if len(clean_reply) > 1024:
            for chunk in [clean_reply[i:i+4096] for i in range(0, len(clean_reply), 4096)]:
                await update.message.reply_text(chunk)
    else:
        for chunk in [ai_reply[i:i+4096] for i in range(0, len(ai_reply), 4096)]:
            await update.message.reply_text(chunk)


def main():
    logger.info(f"Запуск з {len(OPENROUTER_KEYS)} ключами OpenRouter")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    if APP_URL:
        logger.info(f"Webhook mode: port={PORT}, url={APP_URL}")
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=f"{APP_URL}/webhook", url_path="webhook")
    else:
        logger.info("Polling mode")
        app.run_polling()


if __name__ == "__main__":
    main()
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
            await update.message.reply_text(f"❌ Помилка завантаження файлу: {e}")
            return

    if chat_id not in chat_histories:
        chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if file_content and original_filename:
        if user_text:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nЗавдання: {user_text}"
        else:
            user_message = f"Ось файл '{original_filename}':\n\n```\n{file_content}\n```\n\nПроаналізуй і запитай що з ним зробити."
    else:
        user_message = user_text

    if not user_message:
        await update.message.reply_text("✏️ Напиши що зробити або задай питання!")
        return

    chat_histories[chat_id].append({"role": "user", "content": user_message})

    if len(chat_histories[chat_id]) > 21:
        chat_histories[chat_id] = [chat_histories[chat_id][0]] + chat_histories[chat_id][-20:]

    try:
        ai_reply = ask_openrouter(chat_histories[chat_id])
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        await update.message.reply_text(f"❌ Помилка: {e}")
        return

    chat_histories[chat_id].append({"role": "assistant", "content": ai_reply})
    code_blocks = extract_code_blocks(ai_reply)
    clean_reply = re.sub(r"```[\w]*\n[\s\S]*?```", "", ai_reply).strip() or "✅ Готово!"

    if code_blocks:
        for i, (lang, code) in enumerate(code_blocks):
            filename = get_filename(lang, i, original_filename if file_content else None)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=f".{filename.split('.')[-1]}", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            try:
                with open(tmp_path, "rb") as f:
                    caption = clean_reply[:1024] if i == 0 else f"📄 {filename}"
                    await update.message.reply_document(
                        document=InputFile(f, filename=filename),
                        caption=caption,
                    )
            finally:
                os.unlink(tmp_path)

        if len(clean_reply) > 1024:
            for chunk in [clean_reply[i:i+4096] for i in range(0, len(clean_reply), 4096)]:
                await update.message.reply_text(chunk)
    else:
        for chunk in [ai_reply[i:i+4096] for i in range(0, len(ai_reply), 4096)]:
            await update.message.reply_text(chunk)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    if APP_URL:
        logger.info(f"Webhook mode: port={PORT}, url={APP_URL}")
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=f"{APP_URL}/webhook", url_path="webhook")
    else:
        logger.info("Polling mode")
        app.run_polling()


if __name__ == "__main__":
    main()
