import logging
import asyncio
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import ollama

# Carrega as variáveis salvas no arquivo .env
load_dotenv()

OLLAMA_MODEL = 'gemma'
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Olá! Sou o seu assistente de IA local. Como posso ajudar?")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = await asyncio.to_thread(
            ollama.chat,
            model=OLLAMA_MODEL,
            messages=[{'role': 'user', 'content': user_text}]
        )
        reply_text = response['message']['content']
        await update.message.reply_text(reply_text)
    except Exception as e:
        logging.error(f"Erro: {e}")
        await update.message.reply_text("Ocorreu um erro ao comunicar com o Ollama.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot rodando de forma segura!")
    app.run_polling()


if __name__ == '__main__':
    main()
