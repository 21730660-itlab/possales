"""Open the main screens with sample data and save screenshots (used by CI on Windows).

    set POS_EDITION=shop_ar
    python tools/windows_screenshots.py screenshots

Needs Pillow (pip install pillow). Uses a throw-away data folder.
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(out_dir: str):
    from PIL import ImageGrab

    os.makedirs(out_dir, exist_ok=True)
    os.environ["POS_DATA_DIR"] = tempfile.mkdtemp()
    from pos import demo, edition, i18n
    from pos.db import Database

    db = Database()
    i18n.set_language(db.get_setting("ui_language", "en"))
    from pos.services import auth, catalog, operations, receipts, sales
    from pos.ui import app as appmod
    from pos.ui import sales as uisales
    from pos.ui.widgets import TextPreview

    prefix = edition.current_key()
    auth.ensure_default_admin(db)
    auth.set_password(db, 1, "admin")
    demo.load_demo_data(db, 1)
    shift = operations.open_shift(db, 1, 100)
    cart = sales.Cart(customer_id=1)
    product, _serial = catalog.find_by_code(db, "600000001")
    cart.add_product(product, 2)
    sale_id = sales.checkout(db, cart, [{"method": "Cash", "amount": 50}], 1, shift)

    a = appmod.App(db)
    a.state("normal")
    a.geometry("1366x768+0+0")

    def snap(name, widget=None):
        for _ in range(5):
            a.update()
            a.update_idletasks()
        w = widget or a
        x, y = w.winfo_rootx(), w.winfo_rooty()
        img = ImageGrab.grab((x, y, x + w.winfo_width(), y + w.winfo_height()))
        img.save(os.path.join(out_dir, f"{prefix}_{name}.png"))
        print("saved", name)

    snap("login")
    a.login(auth.get_user(db, 1))
    a.show("sales")
    view = a.views["sales"]
    uisales.SerialPicker.show = lambda self: "PH-IP15-128-SN001"
    view.code_var.set("194253401")
    view.add_code()
    view.code_var.set("600000003")
    view.qty_var.set("2")
    view.add_code()
    view.cart.customer_id = 1
    view.refresh_cart()
    snap("sales")
    pay = uisales.PaymentDialog(view, a, view.totals["total"], 1)
    pay.deiconify()
    pay.geometry("+200+30")
    pay.amount.set("500")
    pay.method.set("Card")
    pay.add_payment()
    snap("payment", pay)
    pay.destroy()
    for key in ("dashboard", "products", "history", "repairs", "reports", "settings"):
        a.show(key)
        snap(key)
    preview = TextPreview(a, "receipt", receipts.sale_receipt(db, sale_id))
    preview.deiconify()
    preview.geometry("+300+20")
    snap("receipt", preview)
    preview.destroy()
    a.destroy()
    if sys.platform.startswith("win"):
        # Windows prints receipts through Notepad, so show the receipt file the way Notepad lays it out.
        import subprocess
        import time
        path = receipts.save_text(receipts.sale_receipt(db, sale_id), "screenshot_receipt")
        notepad = subprocess.Popen(["notepad.exe", path])
        time.sleep(4)
        ImageGrab.grab().save(os.path.join(out_dir, f"{prefix}_notepad_receipt.png"))
        notepad.kill()
        print("saved notepad_receipt")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
