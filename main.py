"""Start the Electronics POS.  Run:  python main.py"""
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
    from pos.ui.app import App
    App().mainloop()


if __name__ == "__main__":
    main()
