from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import ollama
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent import SteamAgent
from steam_analytics import SteamAnalytics


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b").strip()
STEAM_CSV = Path(os.getenv("STEAM_CSV", "data/steam.csv"))
if not STEAM_CSV.is_absolute():
    STEAM_CSV = BASE_DIR / STEAM_CSV

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("steam-analytics-bot")

ANALYTICS = SteamAnalytics(STEAM_CSV)
AGENT = SteamAgent(ANALYTICS, OLLAMA_MODEL)


def split_message(text: str, limit: int = 3900) -> list[str]:
    text = (text or "").strip()
    if len(text) <= limit:
        return [text or "Não consegui gerar uma resposta."]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_long(update: Update, text: str) -> None:
    if not update.effective_message:
        return
    for chunk in split_message(text):
        await update.effective_message.reply_text(chunk)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_long(
        update,
        (
            "Olá! Eu analiso a base Steam usando Pandas + Ollama.\n\n"
            "Você pode perguntar naturalmente, por exemplo:\n"
            "• Qual gênero tem mais jogos?\n"
            "• Qual gênero está em alta?\n"
            "• Qual plataforma aparece mais?\n"
            "• Qual gênero tem mais avaliações positivas?\n"
            "• Qual é o preço médio dos jogos?\n"
            "• Quais jogos têm mais avaliações positivas?\n"
            "• Qual ano teve mais lançamentos?\n\n"
            "Também posso responder dúvidas gerais de programação.\n"
            "Use /status para verificar a base e o Ollama."
        ),
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    base_status = (
        f"Base Steam: OK | {ANALYTICS.row_count} jogos | "
        f"período {ANALYTICS.min_year}-{ANALYTICS.max_year}"
    )
    try:
        await asyncio.to_thread(ollama.list)
        ollama_status = f"Ollama: OK | modelo: {OLLAMA_MODEL}"
    except Exception as exc:
        logger.warning("Falha ao verificar Ollama: %s", exc)
        ollama_status = "Ollama: indisponível. Confira se o serviço está aberto e o modelo instalado."

    await send_long(update, f"{base_status}\n{ollama_status}")


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat_obj = update.effective_chat
    if not message or not chat_obj or not message.text:
        return

    question = message.text.strip()
    if not question:
        return

    await context.bot.send_chat_action(chat_id=chat_obj.id, action=ChatAction.TYPING)

    try:
        answer, plan = await asyncio.to_thread(AGENT.answer, question)
        if plan:
            logger.info("Plano da pergunta %r: %s", question, plan)
    except FileNotFoundError as exc:
        await send_long(update, str(exc))
        return
    except Exception as exc:
        logger.exception("Erro ao processar a pergunta")
        await send_long(
            update,
            "Não consegui processar essa pergunta. Verifique se o Ollama está rodando, "
            f"se o modelo '{OLLAMA_MODEL}' está instalado e se o steam.csv está correto. "
            f"Erro: {type(exc).__name__}: {exc}",
        )
        return

    await send_long(update, answer)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Erro não tratado no bot", exc_info=context.error)


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN não foi configurado. Copie .env.example para .env e coloque o token."
        )

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_error_handler(on_error)

    logger.info(
        "Bot iniciado | base=%s registros | modelo=%s",
        ANALYTICS.row_count,
        OLLAMA_MODEL,
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
