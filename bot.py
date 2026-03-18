import logging
import os
import re
import tempfile
import requests
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8651979197:AAFOFTR5s8vzFhZ-6K4q1jgIBoGOyup5qUk")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "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")
MODEL = "arcee-ai/trinity-large-preview:free"
PORT = int(os.environ.get("PORT", 8443))
APP_URL = os.environ.get("APP_URL", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

EXT_MAP = {
    "html": "html", "css": "css", "js": "js", "javascript": "js",
    "python": "py", "py": "py", "java": "java", "c": "c",
    "cpp": "cpp", "c++": "cpp", "php": "php", "sql": "sql",
    "json": "json", "xml": "xml", "yaml": "yaml", "yml": "yml",
    "bash": "sh", "sh": "sh", "txt": "txt", "md": "md", "markdown": "md",
    "ts": "ts", "typescript": "ts", "react": "jsx", "jsx": "jsx",
    "vue": "vue", "go": "go", "rust": "rs", "ruby": "rb",
}

def ask_openrouter(messages):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/bot",
        "X-Title": "TG AI Bot",
    }
    resp = requests.post(OPENROUTER_URL, json={"model": MODEL, "messages": messages, "max_tokens": 4096}, headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def extract_code_blocks(text):
    return [(lang.strip().lower() or "txt", code.strip()) for lang, code in re.findall(r"```(\w*)\n([\s\S]*?)```", text)]

def get_filename(lang, index):
    ext = EXT_MAP.get(lang, lang if len(lang) <= 5 else "txt")
    base = {"html": "index", "css": "style", "js": "script", "py": "main", "sh": "run"}.get(ext, "file")
    return f"{base}{'_'+str(index) if index > 0 else ''}.{ext}"

chat_histories = {}
SYSTEM_PROMPT = (
    "You are a helpful AI assistant inside a Telegram bot. "
    "When the user asks to create a file (website, script, program, etc.), "
    "always provide complete code inside a fenced code block with the correct language tag. "
    "After the code block, briefly explain what you created. "
    "Support both Ukrainian and English languages."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Я AI-асистент на базі Nous Hermes 3 405B.\n\n"
        "💬 Напиши будь-що — я відповім.\n"
        "📁 Попроси зробити файл — надішлю його!\n\n"
        "Приклади:\n"
        "• Зроби мені сайт на HTML\n"
        "• Напиши Python скрипт\n"
        "• Створи калькулятор на JS\n\n"
        "Команда /reset — очистити розмову."
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_histories.pop(update.effective_chat.id, None)
    await update.message.reply_text("🔄 Розмову очищено!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    if chat_id not in chat_histories:
        chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    chat_histories[chat_id].append({"role": "user", "content": user_text})
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
    clean_reply = re.sub(r"```[\w]*\n[\s\S]*?```", "", ai_reply).strip() or "✅ Ось твій файл!"

    if code_blocks:
        for i, (lang, code) in enumerate(code_blocks):
            filename = get_filename(lang, i)
            with tempfile.NamedTemporaryFile(mode="w", suffix=f".{filename.split('.')[-1]}", delete=False, encoding="utf-8") as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            try:
                with open(tmp_path, "rb") as f:
                    await update.message.reply_document(
                        document=InputFile(f, filename=filename),
                        caption=(clean_reply[:1024] if i == 0 else f"📄 {filename}"),
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

    if APP_URL:
        logger.info(f"Webhook mode: port={PORT}, url={APP_URL}")
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=f"{APP_URL}/webhook", url_path="webhook")
    else:
        logger.info("Polling mode")
        app.run_polling()

if __name__ == "__main__":
    main()
