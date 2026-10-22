"""Automatic rolling backups of the database."""
from __future__ import annotations

import glob
import os
from datetime import datetime

from .db import Database, app_data_dir

KEEP = 30


def backup_dir() -> str:
    path = os.path.join(app_data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def backup_name(tag: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(backup_dir(), f"pos_backup_{stamp}{'_' + tag if tag else ''}.db")


def auto_backup(db: Database, tag: str = "auto") -> str:
    path = backup_name(tag)
    db.backup_to(path)
    files = sorted(glob.glob(os.path.join(backup_dir(), "pos_backup_*.db")))
    for old in files[:-KEEP]:
        try:
            os.remove(old)
        except OSError:
            pass
    return path
