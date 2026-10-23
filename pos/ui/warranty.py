"""Warranty lookup by serial / IMEI, invoice number or customer phone."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ..i18n import _
from ..services import sales
from .app import View
from .widgets import FONT_FAMILY, START, W, DataTable


class WarrantyView(View):
    title = _("Warranty Check")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Label(bar, text=_("Serial / IMEI, invoice no. or customer phone:")).pack(side=START)
        self.var = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.var, font=(FONT_FAMILY, 14), width=30)
        e.pack(side=START, padx=8)
        e.bind("<Return>", lambda ev: self.lookup())
        ttk.Button(bar, text=_("Check"), style="Accent.TButton", command=self.lookup).pack(side=START)
        self.entry = e
        self.result = ttk.Label(self, text="", style="H2.TLabel")
        self.result.pack(anchor=W, pady=(0, 8))
        self.table = DataTable(self, [
            ("name", _("Product"), 240), ("serial_no", _("Serial / IMEI"), 160),
            ("invoice_no", _("Invoice"), 120), ("sold_at", _("Sold"), 150),
            ("customer_name", _("Customer"), 150), ("customer_phone", _("Phone"), 110),
            ("warranty_until", _("Warranty until"), 120), ("state", _("Status"), 160)], height=18)
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.entry.focus_set()

    def lookup(self):
        today = date.today().isoformat()
        rows = []
        for r in sales.warranty_lookup(self.db, self.var.get()):
            r = dict(r)
            r["valid"] = False
            if r["returned_qty"] >= r["qty"]:
                r["state"] = _("Returned")
            elif not r["warranty_until"]:
                r["state"] = _("No warranty")
            elif r["warranty_until"] >= today:
                days = (date.fromisoformat(r["warranty_until"]) - date.today()).days
                r["state"] = _("✔ Valid ({days} days left)").format(days=days)
                r["valid"] = True
            else:
                r["state"] = _("✘ Expired")
            rows.append(r)
        self.table.set_rows(rows, tag_fn=lambda r: "ok" if r["valid"] else "warn")
        self.result.configure(text=_("{count} item(s) found").format(count=len(rows)) if rows
                              else _("Nothing found."))
