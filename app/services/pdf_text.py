import logging
import os

log = logging.getLogger(__name__)


def extract_pdf_text(path: str, max_chars: int = 15000) -> str | None:
    """Извлекает текст из PDF. Возвращает строку или None."""
    if not os.path.isfile(path):
        return None
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            parts.append(txt)
        full = "\n".join(parts).strip()
        if not full:
            return None
        if len(full) > max_chars:
            full = full[:max_chars]
        return full
    except Exception as e:
        log.warning("PDF extract failed: %s", e)
        return None