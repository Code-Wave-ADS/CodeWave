from __future__ import annotations

import logging
import os
from typing import Any


logger = logging.getLogger("steam-analytics-bot")

_whisper: Any = None


def whisper_model_name() -> str:
    """Nome do modelo de transcrição (lido do .env na hora de usar)."""
    return os.getenv("WHISPER_MODEL", "small").strip() or "small"


def get_whisper() -> Any:
    """Carrega o modelo de transcrição só na primeira vez que um áudio chega."""
    global _whisper
    if _whisper is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "A biblioteca de áudio não está instalada. Rode: pip install -r requirements.txt"
            ) from exc

        name = whisper_model_name()
        logger.info("Carregando modelo de transcrição: %s", name)
        _whisper = WhisperModel(name, device="cpu", compute_type="int8")
    return _whisper


def transcribe_audio(path: str) -> str:
    """Converte um arquivo de áudio em texto (português)."""
    segments, _info = get_whisper().transcribe(path, language="pt", vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()
