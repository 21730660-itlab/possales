"""Product editions built from the same code.

  electronics - "Electronics POS", English interface (the original program)
  shop_ar     - "Shop POS" (نظام المتجر), Arabic right-to-left interface and receipts

The edition is chosen by the POS_EDITION environment variable or, in an installed
build, by an `edition.txt` file bundled into the program. Each edition has its own
data folder so both can be installed on the same computer.
"""
from __future__ import annotations

import os
import sys

EDITIONS = {
    "electronics": {
        "app_name": "Electronics POS",
        "data_folder": "ElectronicsPOS",
        "language": "en",
        "settings": {},
    },
    "shop_ar": {
        "app_name": "Shop POS",
        "data_folder": "ShopPOS",
        "language": "ar",
        "settings": {
            "shop_name": "Shop",
            "shop_name_ar": "المتجر",
            "shop_address": "",
            "secondary_currency": "ل.ل",
            "receipt_language": "ar",
            "receipt_footer": "Thank you for shopping with us!",
            "receipt_footer_ar": "شكراً لتسوقكم معنا!",
        },
    },
}
DEFAULT_EDITION = "electronics"


def _bundled_edition() -> str | None:
    root = getattr(sys, "_MEIPASS", None)
    if not root:
        return None
    try:
        with open(os.path.join(root, "edition.txt"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def current_key() -> str:
    key = os.environ.get("POS_EDITION") or _bundled_edition() or DEFAULT_EDITION
    return key if key in EDITIONS else DEFAULT_EDITION


def current() -> dict:
    return EDITIONS[current_key()]
