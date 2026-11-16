from __future__ import annotations

import telebot
import asyncio
import logging
from multiprocessing import context
import os
import re
import time
from pathlib import Path
from agent import compararIdeiasJogos

import ollama
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent import SteamAgent
from steam_analytics import SteamAnalytics
from steam_analytics import SteamAnalytics, UserFacingError

HISTORY_TURNS = 3  
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
            "Oi! Eu sou um assistente para quem desenvolve jogos. "
            "Analiso dados da Steam e também ajudo com dúvidas de programação.\n\n"
            "Pode perguntar do seu jeito. Alguns exemplos:\n\n"
            "📊 Panorama da Steam\n"
            "• Qual gênero tem mais jogos?\n"
            "• Qual gênero está em alta?\n"
            "• Qual plataforma aparece mais?\n"
            "• Qual é o preço médio dos jogos?\n"
            "• Quais jogos têm mais avaliações positivas?\n"
            "• Qual ano teve mais lançamentos?\n\n"
            "🎯 Mercado e lançamento\n"
            "• Quais as épocas com maior número de vendas?\n"
            "• Qual a porcentagem de jogos por faixa etária?\n"
            "• Qual o mercado de jogos de terror?\n\n"
            "💰 Receita e lucro\n"
            "• Quanto posso faturar se meu jogo de RPG vender bem?\n"
            "• Qual o lucro de um Adventure com orçamento de 100000?\n"
            "• Qual a receita de um jogo de Puzzle?\n\n"
            "💻 Programação\n"
            "• Como faço um loop em Python?\n\n"
            "Use /status para checar se a base e o modelo estão funcionando."
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

async def keep_typing(bot, chat_id: int, stop: asyncio.Event) -> None:
    """Mantém o 'digitando...' ativo enquanto a resposta é gerada (o Telegram apaga o aviso em ~5s)."""
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            logger.warning("Não consegui enviar o aviso de 'digitando'")
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat_obj = update.effective_chat
    if not message or not chat_obj or not message.text:
        return

    question = message.text.strip()
    if not question:
        return

    # A short budget reply can continue the previous profit question for this user.
    pending = context.user_data.pop("profit_pending", None)
    if pending and time.monotonic() - pending["at"] < 900:
        short_budget = re.fullmatch(
            r"\s*(?:(?:meu |o )?(?:orçamento|orcamento|custo|gasto)(?: (?:é|e|seria|foi|de))?\s*)?"
            r"(?:R\$|US\$|\$)?\s*\d[\d.,]*(?:\s*(?:mil|milhão|milhões|milhao|milhoes|k))?\s*",
            question, re.IGNORECASE,
        )
        if short_budget:
            cost_question = (question if re.search(r"orçamento|orcamento|custo|gasto", question, re.IGNORECASE)
                             else f"orçamento de {question}")
            question = f"Qual o lucro de um jogo de {pending['term']}? {cost_question}"

    history = context.user_data.setdefault("history", [])

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(context.bot, chat_obj.id, stop_typing))

    try:
        answer, plan = await asyncio.to_thread(AGENT.answer, question, history)
        history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])
        del history[:-HISTORY_TURNS * 2]
        if plan and plan.get("operation") == "profit_estimate" and plan.get("budget") is None:
            context.user_data["profit_pending"] = {"term": plan["term"], "at": time.monotonic()}
        if plan:
            logger.info("Plano da pergunta %r: %s", question, plan)
    except UserFacingError as exc:
        await send_long(update, str(exc))
        return
    except FileNotFoundError as exc:
        logger.exception("Arquivo não encontrado")
        await send_long(update, str(exc))
        return
    except (ConnectionError, ollama.ResponseError):
        logger.exception("Falha ao falar com o Ollama")
        await send_long(
            update,
            "Não consegui falar com o modelo de IA agora. Confere se o Ollama está aberto "
            "e o modelo instalado, e tenta de novo.",
        )
        return
    except Exception:
        logger.exception("Erro ao processar a pergunta")
        await send_long(
            update,
            "Opa, tive um problema para responder agora. Tenta de novo ou reformula a pergunta?",
        )
        return
    finally:
        stop_typing.set()
        await typing_task

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




bot = telebot.TeleBot("8991254570:AAFaA8IERySVyjIsrzhj9k9gMWVjfdDRUkM")

@bot.message_handler(commands=["comparar"])

def iniciarComparacao(message):
    texto = message.text.replace("/comparar", "").strip()

    if " vs " in texto.lower():
        partes = texto.lower().split( " vs ")
        resultado = compararIdeiasJogos(partes[0].strip(), partes[1].strip())
        bot.reply_to(message, resultado, parse_mode="Markdown")
    else:
        msg = bot.reply_to(
            message, "Qual o genero ou tag da **Ideia A**? (Ex: RPG, Platformer)"
        )
        bot.register_next_handler(msg, receber_ideia_a)

def receber_ideia_a(message):
  ideia_a = message.text.strip()
  msg = bot.reply_to(
      message, f"Anotado ({ideia_a}). Agora digite o gênero da **Ideia B**:"
  )
  bot.register_next_step_handler(msg, receber_ideia_b, ideia_a)


def receber_ideia_b(message, ideia_a):
  ideia_b = message.text.strip()
  bot.send_message(message.chat.id, "⏳ Analisando base de dados da Steam...")
  resultado = compararIdeiasJogos(ideia_a, ideia_b)
  bot.send_message(message.chat.id, resultado, parse_mode="Markdown")


bot.infinity_polling()

if __name__ == "__main__":
    main()
