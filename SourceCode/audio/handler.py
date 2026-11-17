from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from audio.transcriber import transcribe_audio


logger = logging.getLogger("steam-analytics-bot")

# Função do bot que recebe uma pergunta em texto e responde: (update, context, pergunta)
ReplyFn = Callable[[Update, ContextTypes.DEFAULT_TYPE, str], Awaitable[None]]


def make_voice_handler(reply_to_question: ReplyFn):
    """Cria o handler de áudio. Ele transcreve e entrega o texto para o bot responder."""

    async def voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat_obj = update.effective_chat
        if not message or not chat_obj:
            return

        audio = message.voice or message.audio
        if not audio:
            return

        await context.bot.send_chat_action(chat_id=chat_obj.id, action=ChatAction.TYPING)

        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "audio.ogg"
            try:
                telegram_file = await context.bot.get_file(audio.file_id)
                await telegram_file.download_to_drive(audio_path)
                question = await asyncio.to_thread(transcribe_audio, str(audio_path))
            except Exception as exc:
                logger.exception("Erro ao transcrever o áudio")
                await message.reply_text(
                    "Não consegui entender esse áudio. Tente enviar de novo ou escreva a pergunta.\n\n"
                    f"Detalhe técnico: {type(exc).__name__}: {exc}"
                )
                return

        if not question:
            await message.reply_text("Não consegui ouvir nada nesse áudio. Tente gravar novamente.")
            return

        await message.reply_text(f"🎤 Entendi: {question}")
        await reply_to_question(update, context, question)

    return voice
