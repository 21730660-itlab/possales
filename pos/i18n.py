"""Interface translation.

Every user-facing English string is written as _("...") (with .format() for values).
`set_language()` must be called before the UI modules are imported, because some of
them build translated constants at import time.
"""
from __future__ import annotations

LANGUAGES = {"en": "English", "ar": "العربية"}
RTL_LANGUAGES = {"ar"}

_current = "en"
_catalog: dict[str, str] = {}


def set_language(lang: str):
    global _current, _catalog
    _current = lang if lang in LANGUAGES else "en"
    if _current == "ar":
        from .locale_ar import ARABIC_UI
        _catalog = ARABIC_UI
    else:
        _catalog = {}


def language() -> str:
    return _current


def is_rtl() -> bool:
    return _current in RTL_LANGUAGES


# Windows draws mixed Arabic / number / English text in the wrong order unless the text is
# marked as a right-to-left run (tools/tk_arabic_probe.py shows the difference on Windows).
RLE, PDF = "\u202b", "\u202c"


def _(text: str) -> str:
    """Translate `text` into the current language (unchanged when there is no translation)."""
    translated = _catalog.get(text)
    if translated is None:
        return text
    return RLE + translated + PDF if _current in RTL_LANGUAGES else translated


def tr_value(value) -> str:
    """Translate a stored English value (status, role, method...) for display."""
    if value is None:
        return ""
    return _(str(value))


def plain(text: str) -> str:
    """Remove direction marks, e.g. before saving text the user picked from a translated list."""
    return text.replace(RLE, "").replace(PDF, "") if text else text


def tr_reason(value) -> str:
    """Translate a stored "Reason: free note" text, leaving the note as typed."""
    text = "" if value is None else str(value)
    head, sep, note = text.partition(": ")
    return tr_value(head) + (sep + note if sep else "")
