import logging

log = logging.getLogger(__name__)


def transcribe(path, model_name="tiny"):
    """
    Временная заглушка: Whisper отключён.
    Возвращает None, чтобы вызывающий код показал сообщение.
    """
    log.info("Voice transcription disabled (Whisper not installed)")
    return None