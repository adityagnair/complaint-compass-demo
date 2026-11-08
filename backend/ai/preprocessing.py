import html
import re
import unicodedata


def normalize_complaint(text: str) -> str:
    """Normalize whitespace and markup while keeping the complaint's meaning."""
    value = unicodedata.normalize("NFKC", html.unescape(text or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"(?:https?://|www\.)\S+", " URLTOKEN ", value, flags=re.IGNORECASE)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " EMAILTOKEN ", value)
    value = value.casefold()
    value = "".join(char if char.isalnum() or char.isspace() else " " for char in value)
    return " ".join(value.split())
