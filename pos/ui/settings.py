"""Shop settings, backup / restore and sample data."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import backup, demo
from ..db import POSError, app_data_dir
from ..i18n import LANGUAGES, _, tr_value
from ..services import auth, barcodes
from ..services.receipts import RECEIPT_LANGUAGES
from .app import View
from .widgets import (END, JUSTIFY, NW, START, W, add_tabs, ask_form, col, confirm, info, pad)


def _translated(options: dict) -> dict:
    return {code: tr_value(shown) for code, shown in options.items()}


SECTIONS = [
    (_("Shop"), [
        ("shop_name", _("Shop name"), "text"),
        ("shop_address", _("Address"), "text"),
        ("shop_phone", _("Phone"), "text"),
        ("shop_email", _("Email"), "text"),
        ("tax_id", _("Tax / VAT registration no."), "text"),
        ("ui_language", _("Interface language (restart the program to apply)"), dict(LANGUAGES)),
    ]),
    (_("Tax & money"), [
        ("tax_name", _("Tax name (VAT, GST...)"), "text"),
        ("tax_rate", _("Tax rate %"), "text"),
        ("currency_symbol", _("Main currency symbol"), "text"),
        ("show_secondary_currency", _("Show totals in a second currency"), "check"),
        ("secondary_currency", _("Second currency code (e.g. LBP)"), "text"),
        ("exchange_rate", _("Exchange rate (1 main = ? second)"), "text"),
    ]),
    (_("Receipts"), [
        ("receipt_language", _("Receipt language"), _translated(RECEIPT_LANGUAGES)),
        ("invoice_prefix", _("Invoice number prefix"), "text"),
        ("receipt_width", _("Receipt width (chars: 32 = 58mm, 42/48 = 80mm)"), "text"),
        ("receipt_footer", _("Receipt footer"), "multiline"),
        ("auto_print_receipt", _("Print the receipt automatically after each sale"), "check"),
        ("printer_name", _("Receipt printer name (blank = Windows default)"), "text"),
        ("open_cash_drawer", _("Open cash drawer after cash sales (ESC/POS printer)"), "check"),
    ]),
    (_("Arabic"), [
        ("shop_name_ar", _("Shop name in Arabic"), "text"),
        ("shop_address_ar", _("Address in Arabic"), "text"),
        ("receipt_footer_ar", _("Receipt footer in Arabic"), "multiline"),
    ]),
    (_("Payments"), [
        ("payment_methods", _("Payment methods (comma separated)"), "text"),
    ]),
    (_("Labels"), [
        ("label_format", _("Label printer type"), _translated(barcodes.LABEL_FORMATS)),
        ("label_printer_name", _("Label printer name (for Zebra / TSC direct printing)"), "text"),
        ("label_width_mm", _("Label width (mm)"), "text"),
        ("label_height_mm", _("Label height (mm)"), "text"),
        ("label_show_price", _("Print the price on labels"), "check"),
        ("label_show_shop", _("Print the shop name on labels"), "check"),
    ]),
    (_("Rules"), [
        ("cashier_max_discount_pct", _("Max discount % without manager approval"), "text"),
        ("allow_negative_stock", _("Allow selling when stock is 0"), "check"),
        ("require_open_shift", _("Require an open cash-drawer shift to sell"), "check"),
        ("return_days_limit", _("Return period in days (0 = unlimited)"), "text"),
    ]),
    (_("Loyalty"), [
        ("loyalty_points_per_unit", _("Points earned per 1 unit of currency spent"), "text"),
        ("loyalty_point_value", _("Value of 1 point when redeemed"), "text"),
    ]),
]
PAYMENTS_HELP = _("Cash, Account (customer credit) and Points (loyalty) are always available.\n"
                  "List any other ways customers can pay, for example:\n"
                  "Card, Bank Transfer, Whish Money, OMT, Cheque, Installments")
NUMERIC_KEYS = ("tax_rate", "exchange_rate", "receipt_width", "cashier_max_discount_pct",
                "return_days_limit", "loyalty_points_per_unit", "loyalty_point_value",
                "label_width_mm", "label_height_mm")


class SettingsView(View):
    title = _("Settings")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[(_("💾 Save settings"), self.save, "Accent.TButton")])
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        # The side panel is packed first so the (wide) row of tabs cannot squeeze it.
        side = ttk.LabelFrame(body, text=" " + _("Data & security") + " ", padding=14)
        side.pack(side=END, fill="y", padx=pad(16, 0))
        tabs = ttk.Notebook(body)
        tabs.pack(side=START, fill="both", expand=True)
        self.vars, self.texts, self.choices = {}, {}, {}
        label_col, field_col = col(0, 2), col(1, 2)
        pages = []
        for title, fields in SECTIONS:
            tab = ttk.Frame(tabs, padding=16)
            tab.columnconfigure(field_col, weight=1)
            for row, (key, label, kind) in enumerate(fields):
                if isinstance(kind, dict):  # choice: {stored value: shown text}
                    ttk.Label(tab, text=label).grid(row=row, column=label_col, sticky=W, pady=5,
                                                    padx=pad(0, 12))
                    var = tk.StringVar()
                    ttk.Combobox(tab, textvariable=var, values=list(kind.values()), state="readonly",
                                 width=48).grid(row=row, column=field_col, sticky=W, pady=5)
                    self.vars[key] = var
                    self.choices[key] = kind
                elif kind == "check":
                    var = tk.BooleanVar()
                    ttk.Checkbutton(tab, text=label, variable=var).grid(row=row, column=0, columnspan=2,
                                                                       sticky=W, pady=5)
                    self.vars[key] = var
                elif kind == "multiline":
                    ttk.Label(tab, text=label).grid(row=row, column=label_col, sticky=NW, pady=5,
                                                    padx=pad(0, 12))
                    t = tk.Text(tab, height=4, width=50, relief="solid", borderwidth=1)
                    t.grid(row=row, column=field_col, sticky="ew", pady=5)
                    self.texts[key] = t
                else:
                    ttk.Label(tab, text=label).grid(row=row, column=label_col, sticky=W, pady=5,
                                                    padx=pad(0, 12))
                    var = tk.StringVar()
                    ttk.Entry(tab, textvariable=var, width=50).grid(row=row, column=field_col, sticky="ew",
                                                                    pady=5)
                    self.vars[key] = var
            if fields[0][0] == "payment_methods":
                ttk.Label(tab, style="Muted.TLabel", wraplength=560, justify=JUSTIFY, text=PAYMENTS_HELP).grid(
                    row=len(fields), column=0, columnspan=2, sticky=W, pady=(8, 0))
            pages.append((tab, title))
        add_tabs(tabs, pages)

        for text, cmd in ((_("Change my password"), self.change_password),
                          (_("Back up now…"), self.backup_now),
                          (_("Restore from backup…"), self.restore),
                          (_("Open data folder"), self.open_folder),
                          (_("Load sample data"), self.load_demo)):
            ttk.Button(side, text=text, command=cmd).pack(fill="x", pady=4)
        ttk.Label(side, text=_("Database:\n{db}\n\nAutomatic backups are made every time the program closes "
                               "(last {keep} kept) in:\n{folder}").format(
            db=self.db.path, keep=backup.KEEP, folder=backup.backup_dir()),
            style="Muted.TLabel", wraplength=260, justify=JUSTIFY).pack(anchor=W, pady=(12, 0))

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
        for key in NUMERIC_KEYS:
            try:
                if float(values[key] or 0) < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(self.title, _("'{value}' is not a valid number.").format(
                    value=values[key]), parent=self)
                return
        language_changed = values["ui_language"] != self.db.get_setting("ui_language")
        self.db.set_settings(values)
        self.db.log(self.app.user["id"], "settings.save", "")
        info(self, self.title, _("Settings saved.") + (
            "\n\n" + _("Restart the program to use the new interface language.") if language_changed else ""))

    def change_password(self):
        user = self.app.user

        def submit(v):
            auth.authenticate(self.db, user["username"], v["old"])
            if v["new1"] != v["new2"]:
                raise POSError(_("The new passwords do not match."))
            auth.set_password(self.db, user["id"], v["new1"], actor_id=user["id"])
        if ask_form(self, _("Change password"), [
                {"key": "old", "label": _("Current password"), "type": "password", "required": True},
                {"key": "new1", "label": _("New password"), "type": "password", "required": True},
                {"key": "new2", "label": _("Repeat new password"), "type": "password", "required": True}],
                on_submit=submit, ok_text=_("Change")):
            info(self, self.title, _("Password changed."))

    def backup_now(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".db",
                                            initialfile=os.path.basename(backup.backup_name()),
                                            filetypes=[(_("POS backup"), "*.db")])
        if path:
            self.db.backup_to(path)
            self.db.log(self.app.user["id"], "backup", path)
            info(self, _("Backup"), _("Backup saved to\n{path}").format(path=path))

    def restore(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[(_("POS backup"), "*.db"), (_("All files"), "*.*")],
                                          initialdir=backup.backup_dir())
        if not path or not confirm(self, _("Restore"), _("Replace ALL current data with this backup?\n"
                                                         "A safety backup of the current data is made first.")):
            return
        backup.auto_backup(self.db, "before_restore")
        self.db.restore_from(path)
        info(self, _("Restore"), _("Data restored. Please sign in again."))
        self.app.show_login()

    def open_folder(self):
        folder = app_data_dir()
        if sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def load_demo(self):
        if confirm(self, _("Sample data"), _("Add sample categories, brands, products, a supplier and a "
                                             "customer so you can try the system?")):
            n = demo.load_demo_data(self.db, self.app.user["id"])
            info(self, _("Sample data"), _("Added {count} sample products.").format(count=n))
