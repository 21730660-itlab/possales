"""Start the POS.  Run:  python main.py   (set POS_EDITION=shop_ar for the Arabic Shop edition)"""
import sys

if sys.version_info < (3, 8):
    sys.exit("Python 3.8 or newer is required.")


def main():
    if sys.platform.startswith("win"):
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    from pos import i18n
    from pos.db import Database

    db = Database()
    # The language must be set before the screens are imported (they translate at import).
    i18n.set_language(db.get_setting("ui_language", "en"))
    from pos.ui.app import App
    App(db).mainloop()


if __name__ == "__main__":
    main()
