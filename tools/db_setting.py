"""Print one setting from a POS database (used by CI):  python tools/db_setting.py pos.db ui_language"""
import sqlite3
import sys

row = sqlite3.connect(sys.argv[1]).execute("SELECT value FROM settings WHERE key = ?", (sys.argv[2],)).fetchone()
print(row[0] if row else "")
