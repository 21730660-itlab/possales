"""Shop settings, backup / restore and sample data."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..db import POSError, app_data_dir
from ..services import auth, barcodes
from ..services.receipts import RECEIPT_LANGUAGES
from .. import backup, demo
from .app import View
from .widgets import ask_form, confirm, info

SECTIONS = [
    ("Shop", [
        ("shop_name", "Shop name", "text"),
        ("shop_address", "Address", "text"),
        ("shop_phone", "Phone", "text"),
        ("shop_email", "Email", "text"),
        ("tax_id", "Tax / VAT registration no.", "text"),
    ]),
    ("Tax & money", [
        ("tax_name", "Tax name (VAT, GST...)", "text"),
        ("tax_rate", "Tax rate %", "text"),
        ("currency_symbol", "Main currency symbol", "text"),
        ("show_secondary_currency", "Show totals in a second currency", "check"),
        ("secondary_currency", "Second currency code (e.g. LBP)", "text"),
        ("exchange_rate", "Exchange rate (1 main = ? second)", "text"),
    ]),
    ("Receipts", [
        ("receipt_language", "Receipt language", RECEIPT_LANGUAGES),
        ("invoice_prefix", "Invoice number prefix", "text"),
        ("receipt_width", "Receipt width (chars: 32 = 58mm, 42/48 = 80mm)", "text"),
        ("receipt_footer", "Receipt footer", "multiline"),
        ("auto_print_receipt", "Print the receipt automatically after each sale", "check"),
        ("printer_name", "Receipt printer name (blank = Windows default)", "text"),
        ("open_cash_drawer", "Open cash drawer after cash sales (ESC/POS printer)", "check"),
    ]),
    ("Arabic", [
        ("shop_name_ar", "Shop name in Arabic", "text"),
        ("shop_address_ar", "Address in Arabic", "text"),
        ("receipt_footer_ar", "Receipt footer in Arabic", "multiline"),
    ]),
    ("Payments", [
        ("payment_methods", "Payment methods (comma separated)", "text"),
    ]),
    ("Labels", [
        ("label_format", "Label printer type", barcodes.LABEL_FORMATS),
        ("label_printer_name", "Label printer name (for Zebra / TSC direct printing)", "text"),
        ("label_width_mm", "Label width (mm)", "text"),
        ("label_height_mm", "Label height (mm)", "text"),
        ("label_show_price", "Print the price on labels", "check"),
        ("label_show_shop", "Print the shop name on labels", "check"),
    ]),
    ("Rules", [
        ("cashier_max_discount_pct", "Max discount % without manager approval", "text"),
        ("allow_negative_stock", "Allow selling when stock is 0", "check"),
        ("require_open_shift", "Require an open cash-drawer shift to sell", "check"),
        ("return_days_limit", "Return period in days (0 = unlimited)", "text"),
    ]),
    ("Loyalty", [
        ("loyalty_points_per_unit", "Points earned per 1 unit of currency spent", "text"),
        ("loyalty_point_value", "Value of 1 point when redeemed", "text"),
    ]),
]


class SettingsView(View):
    title = "Settings"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[("💾 Save settings", self.save, "Accent.TButton")])
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        # The side panel is packed first so the (wide) row of tabs cannot squeeze it.
        side = ttk.LabelFrame(body, text=" Data & security ", padding=14)
        side.pack(side="right", fill="y", padx=(16, 0))
        tabs = ttk.Notebook(body)
        tabs.pack(side="left", fill="both", expand=True)
        self.vars, self.texts, self.choices = {}, {}, {}
        for title, fields in SECTIONS:
            tab = ttk.Frame(tabs, padding=16)
            tab.columnconfigure(1, weight=1)
            for row, (key, label, kind) in enumerate(fields):
                if isinstance(kind, dict):  # choice: {stored value: shown text}
                    ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 12))
                    var = tk.StringVar()
                    ttk.Combobox(tab, textvariable=var, values=list(kind.values()), state="readonly",
                                 width=48).grid(row=row, column=1, sticky="w", pady=5)
                    self.vars[key] = var
                    self.choices[key] = kind
                elif kind == "check":
                    var = tk.BooleanVar()
                    ttk.Checkbutton(tab, text=label, variable=var).grid(row=row, column=0, columnspan=2,
                                                                       sticky="w", pady=5)
                    self.vars[key] = var
                elif kind == "multiline":
                    ttk.Label(tab, text=label).grid(row=row, column=0, sticky="nw", pady=5, padx=(0, 12))
                    t = tk.Text(tab, height=4, width=50, relief="solid", borderwidth=1)
                    t.grid(row=row, column=1, sticky="ew", pady=5)
                    self.texts[key] = t
                else:
                    ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 12))
                    var = tk.StringVar()
                    ttk.Entry(tab, textvariable=var, width=50).grid(row=row, column=1, sticky="ew", pady=5)
                    self.vars[key] = var
            if title == "Payments":
                ttk.Label(tab, style="Muted.TLabel", wraplength=560, justify="left", text=(
                    "Cash, Account (customer credit) and Points (loyalty) are always available.\n"
                    "List any other ways customers can pay, for example:\n"
                    "Card, Bank Transfer, Whish Money, OMT, Cheque, Installments")).grid(
                    row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))
            tabs.add(tab, text=title)

        for text, cmd in (("Change my password", self.change_password),
                          ("Back up now…", self.backup_now),
                          ("Restore from backup…", self.restore),
                          ("Open data folder", self.open_folder),
                          ("Load sample electronics data", self.load_demo)):
            ttk.Button(side, text=text, command=cmd).pack(fill="x", pady=4)
        ttk.Label(side, text=f"Database:\n{self.db.path}\n\nAutomatic backups are made every time the "
                             f"program closes (last {backup.KEEP} kept) in:\n"
                             f"{backup.backup_dir()}", style="Muted.TLabel", wraplength=260).pack(
            anchor="w", pady=(12, 0))

    def on_show(self):
        settings = self.db.get_settings()
        for key, var in self.vars.items():
            value = settings.get(key, "")
            if key in self.choices:
                value = self.choices[key].get(value, next(iter(self.choices[key].values())))
            var.set(value == "1" if isinstance(var, tk.BooleanVar) else value)
        for key, text in self.texts.items():
            text.delete("1.0", "end")
            text.insert("1.0", settings.get(key, ""))

    def save(self):
        values = {}
        for key, var in self.vars.items():
            values[key] = ("1" if var.get() else "0") if isinstance(var, tk.BooleanVar) else var.get().strip()
        for key, text in self.texts.items():
            values[key] = text.get("1.0", "end").strip()
        for key, options in self.choices.items():
            values[key] = next(code for code, shown in options.items() if shown == values[key])
        for key in ("tax_rate", "exchange_rate", "receipt_width", "cashier_max_discount_pct",
                    "return_days_limit", "loyalty_points_per_unit", "loyalty_point_value",
                    "label_width_mm", "label_height_mm"):
            try:
                if float(values[key] or 0) < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(self.title, f"'{values[key]}' is not a valid number.", parent=self)
                return
        self.db.set_settings(values)
        self.db.log(self.app.user["id"], "settings.save", "")
        info(self, self.title, "Settings saved.")

    def change_password(self):
        user = self.app.user

        def submit(v):
            auth.authenticate(self.db, user["username"], v["old"])
            if v["new1"] != v["new2"]:
                raise POSError("The new passwords do not match.")
            auth.set_password(self.db, user["id"], v["new1"], actor_id=user["id"])
        if ask_form(self, "Change password", [
                {"key": "old", "label": "Current password", "type": "password", "required": True},
                {"key": "new1", "label": "New password", "type": "password", "required": True},
                {"key": "new2", "label": "Repeat new password", "type": "password", "required": True}],
                on_submit=submit, ok_text="Change"):
            info(self, self.title, "Password changed.")

    def backup_now(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".db",
                                            initialfile=os.path.basename(backup.backup_name()),
                                            filetypes=[("POS backup", "*.db")])
        if path:
            self.db.backup_to(path)
            self.db.log(self.app.user["id"], "backup", path)
            info(self, "Backup", f"Backup saved to\n{path}")

    def restore(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("POS backup", "*.db"), ("All", "*.*")],
                                          initialdir=backup.backup_dir())
        if not path or not confirm(self, "Restore", "Replace ALL current data with this backup?\n"
                                                    "A safety backup of the current data is made first."):
            return
        backup.auto_backup(self.db, "before_restore")
        self.db.restore_from(path)
        info(self, "Restore", "Data restored. Please sign in again.")
        self.app.show_login()

    def open_folder(self):
        folder = app_data_dir()
        if sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def load_demo(self):
        if confirm(self, "Sample data", "Add sample categories, brands, products, a supplier and a "
                                        "customer so you can try the system?"):
            n = demo.load_demo_data(self.db, self.app.user["id"])
            info(self, "Sample data", f"Added {n} sample products.")
