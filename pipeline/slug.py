import re
import unicodedata


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[\s/]+", "-", text)
    # Keep word chars (includes CJK via Python's Unicode-aware \w) and hyphens
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        raise ValueError("slug cannot be empty")
    return text
