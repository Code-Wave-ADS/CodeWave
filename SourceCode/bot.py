from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path

import ollama
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from agent import SteamAgent, compararIdeiasJogos
from audio.handler import make_voice_handler
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

# Estados da conversa do /comparar
IDEIA_A, IDEIA_B = range(2)


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
            "Pode perguntar do seu jeito (por texto ou mensagem de voz 🎤). "
            "Alguns exemplos:\n\n"
            "📊 Panorama da Steam\n"
            "• Qual gênero tem mais jogos?\n"
            "• Qual gênero está em alta?\n"
            "• Qual plataforma aparece mais?\n"
            "• Qual é o preço médio dos jogos?\n"
            "• Quais jogos têm mais avaliações positivas?\n"
            "• Qual ideia de jogo é melhor?\n"
            "• Qual ano teve mais lançamentos?\n\n"
            "🎯 Mercado e lançamento\n"
            "• Quais as épocas com maior número de vendas?\n"
            "• Qual a porcentagem de jogos por faixa etária?\n"
            "• Qual o mercado de jogos de terror?\n\n"
            "💰 Receita e lucro\n"
            "• Quanto posso faturar se meu jogo de RPG vender bem?\n"
            "• Qual o lucro de um Adventure com orçamento de 100000?\n"
            "• Qual a receita de um jogo de Puzzle?\n\n"
            "⚖️ Comparar ideias\n"
            "• /comparar RPG vs Platformer\n\n"
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
    """Mensagem de texto: pega o texto e entrega para o responder()."""
    message = update.effective_message
    if not message or not message.text:
        return

    question = message.text.strip()
    if not question:
        return

    await responder(update, context, question)


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    """Responde a uma pergunta em texto. Usado tanto pelo texto digitado quanto pelo áudio transcrito."""
    chat_obj = update.effective_chat
    if not chat_obj:
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


# ---------------------------------------------------------------------------
# /comparar (convertido de telebot para python-telegram-bot)
# ---------------------------------------------------------------------------

async def _comparar(update: Update, ideia_a: str, ideia_b: str) -> None:
    message = update.effective_message
    if not message:
        return
    await message.reply_text("⏳ Analisando base de dados da Steam...")
    try:
        resultado = await asyncio.to_thread(compararIdeiasJogos, ideia_a, ideia_b)
    except Exception:
        logger.exception("Erro ao comparar %r e %r", ideia_a, ideia_b)
        await message.reply_text(
            "Não consegui fazer essa comparação agora. Tenta de novo com outros gêneros?"
        )
        return

    try:
        await message.reply_text(resultado, parse_mode="Markdown")
    except Exception:
        # Se o Telegram recusar a formatação, manda como texto simples.
        await send_long(update, resultado)


async def comparar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.effective_message
    if not message:
        return ConversationHandler.END

    texto = " ".join(context.args or []).strip()
    if re.search(r"\s+vs\s+", texto, re.IGNORECASE):
        ideia_a, ideia_b = re.split(r"\s+vs\s+", texto, maxsplit=1, flags=re.IGNORECASE)
        await _comparar(update, ideia_a.strip(), ideia_b.strip())
        return ConversationHandler.END

    await message.reply_text("Qual o gênero ou tag da Ideia A? (Ex: RPG, Platformer)")
    return IDEIA_A


async def receber_ideia_a(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.effective_message
    context.user_data["ideia_a"] = (message.text or "").strip()
    await message.reply_text(
        f"Anotado ({context.user_data['ideia_a']}). Agora digite o gênero da Ideia B:"
    )
    return IDEIA_B


async def receber_ideia_b(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.effective_message
    ideia_a = context.user_data.pop("ideia_a", "")
    await _comparar(update, ideia_a, (message.text or "").strip())
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("ideia_a", None)
    if update.effective_message:
        await update.effective_message.reply_text("Comparação cancelada.")
    return ConversationHandler.END


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

    # O /comparar precisa vir ANTES do handler de texto, senão o chat() rouba as respostas.
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("comparar", comparar)],
            states={
                IDEIA_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_ideia_a)],
                IDEIA_B: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_ideia_b)],
            },
            fallbacks=[CommandHandler("cancelar", cancelar)],
        )
    )

    # Mensagens de voz/áudio: transcreve e responde como se fosse texto.
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, make_voice_handler(responder)))
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
