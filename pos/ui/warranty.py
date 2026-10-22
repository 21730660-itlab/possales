"""Warranty lookup by serial / IMEI, invoice number or customer phone."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from ..services import sales
from .app import View
from .widgets import FONT_FAMILY, DataTable


class WarrantyView(View):
    title = "Warranty Check"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Label(bar, text="Serial / IMEI, invoice no. or customer phone:").pack(side="left")
        self.var = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.var, font=(FONT_FAMILY, 14), width=30)
        e.pack(side="left", padx=8)
        e.bind("<Return>", lambda ev: self.lookup())
        ttk.Button(bar, text="Check", style="Accent.TButton", command=self.lookup).pack(side="left")
        self.entry = e
        self.result = ttk.Label(self, text="", style="H2.TLabel")
        self.result.pack(anchor="w", pady=(0, 8))
        self.table = DataTable(self, [
            ("name", "Product", 240), ("serial_no", "Serial / IMEI", 160), ("invoice_no", "Invoice", 120),
            ("sold_at", "Sold", 150), ("customer_name", "Customer", 150), ("customer_phone", "Phone", 110),
            ("warranty_until", "Warranty until", 120), ("state", "Status", 160)], height=18)
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.entry.focus_set()

    def lookup(self):
        today = date.today().isoformat()
        rows = []
        for r in sales.warranty_lookup(self.db, self.var.get()):
            r = dict(r)
            if r["returned_qty"] >= r["qty"]:
                r["state"] = "Returned"
            elif not r["warranty_until"]:
                r["state"] = "No warranty"
            elif r["warranty_until"] >= today:
                days = (date.fromisoformat(r["warranty_until"]) - date.today()).days
                r["state"] = f"✔ Valid ({days} days left)"
            else:
                r["state"] = "✘ Expired"
            rows.append(r)
        self.table.set_rows(rows, tag_fn=lambda r: "ok" if r["state"].startswith("✔") else "warn")
        self.result.configure(text=f"{len(rows)} item(s) found" if rows else "Nothing found.")
