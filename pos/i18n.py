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


def _(text: str) -> str:
    """Translate `text` into the current language (unchanged when there is no translation)."""
    return _catalog.get(text, text)


def tr_value(value) -> str:
    """Translate a stored English value (status, role, method...) for display."""
    if value is None:
        return ""
    return _catalog.get(str(value), str(value))
