import logging
import os

log = logging.getLogger(__name__)

_model = None
_model_name = None


def _get_model(model_name: str = "tiny"):
    global _model, _model_name
    if _model is not None and _model_name == model_name:
        return _model
    try:
        import whisper
        log.info("Loading whisper model: %s", model_name)
        _model = whisper.load_model(model_name)
        _model_name = model_name
        return _model
    except Exception as e:
        log.warning("Whisper not available: %s", e)
        return None


def transcribe(path: str, model_name: str = "tiny") -> str | None:
    """
    Распознаёт русскую речь из аудиофайла.
    Возвращает текст или None, если Whisper недоступен/ошибка.
    """
    if not os.path.exists(path):
        return None
    m = _get_model(model_name)
    if m is None:
        return None
    try:
        result = m.transcribe(path, language="ru", fp16=False)
        text = (result.get("text") or "").strip()
        return text or None
    except Exception as e:
        log.warning("Whisper transcribe failed: %s", e)
        return None