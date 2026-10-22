"""Sales history: find invoices, reprint receipts and process returns."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from ..db import POSError, setting_float
from ..services import receipts, sales
from .app import View
from .widgets import (FONT_FAMILY, DataTable, DateRangeBar, Dialog, SearchBar, TextPreview,
                      parse_int, require_permission, toolbar)


class HistoryView(View):
    title = "Sales & Returns"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.range = DateRangeBar(bar, self.reload, preset="Last 7 days")
        self.range.pack(side="left")
        self.search = SearchBar(bar, self.reload, "invoice, customer, serial, item", width=24)
        self.search.pack(side="left", padx=(16, 0))
        toolbar(self, [("View / reprint receipt", self.view, "Accent.TButton"),
                       ("Return / refund items", self.do_return)]).pack(fill="x", pady=(0, 8))
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        m = lambda v: f"{v:,.2f}"
        self.sales = DataTable(self.tabs, [
            ("invoice_no", "Invoice", 120), ("created_at", "Date", 160), ("customer_name", "Customer", 170),
            ("cashier", "Cashier", 90), ("subtotal", "Subtotal", -95, m), ("discount_total", "Discount", -90, m),
            ("tax_total", "Tax", -80, m), ("total", "Total", -100, m), ("status", "Status", 140)],
            height=18, on_double=lambda r: self.view())
        self.returns = DataTable(self.tabs, [
            ("return_no", "Return", 120), ("created_at", "Date", 160), ("invoice_no", "Invoice", 120),
            ("total", "Refund", -100, m), ("refund_method", "Method", 120), ("reason", "Reason", 240),
            ("cashier", "By", 90)], height=18, on_double=self.view_return)
        self.tabs.add(self.sales, text="Sales")
        self.tabs.add(self.returns, text="Returns")
        self.summary = ttk.Label(self, text="", font=(FONT_FAMILY, 12, "bold"))
        self.summary.pack(anchor="e", pady=(8, 0))

    def on_show(self):
        self.reload()

    def reload(self):
        d1, d2 = self.range.range()
        user_filter = self.app.user["id"] if self.app.user["role"] == "cashier" else None
        rows = sales.list_sales(self.db, d1, d2, self.search.get(), user_filter)
        self.sales.set_rows(rows, tag_fn=lambda r: "warn" if r["status"] != "completed" else None)
        rets = sales.list_returns(self.db, d1, d2)
        self.returns.set_rows(rets)
        sym = self.currency
        self.summary.configure(text=f"{len(rows)} sales   total {sym}{sum(r['total'] for r in rows):,.2f}"
                                    f"      {len(rets)} returns   {sym}{sum(r['total'] for r in rets):,.2f}")

    def view(self):
        row = self.sales.selected()
        if not row:
            messagebox.showinfo(self.title, "Select a sale first.", parent=self)
            return
        text = receipts.sale_receipt(self.db, row["id"], copy=True)
        TextPreview(self, row["invoice_no"], text,
                    on_print=lambda: receipts.print_text(self.db, text, row["invoice_no"] + "_copy")).show()

    def view_return(self, row):
        text = receipts.return_receipt(self.db, row["id"])
        TextPreview(self, row["return_no"], text,
                    on_print=lambda: receipts.print_text(self.db, text, row["return_no"])).show()

    def do_return(self):
        row = self.sales.selected()
        if not row:
            messagebox.showinfo(self.title, "Select the sale to return items from.", parent=self)
            return
        if row["status"] == "returned":
            raise POSError("Everything on this sale has already been returned.")
        if not require_permission(self, self.app, "returns", "Processing a return / refund."):
            return
        limit = int(setting_float(self.db.get_settings(), "return_days_limit", 0))
        age = (date.today() - date.fromisoformat(row["created_at"][:10])).days
        override = False
        if limit and age > limit:
            override = require_permission(self, self.app, "return_override",
                                          f"This sale is {age} days old (limit {limit} days).")
            if not override:
                return
        return_id = ReturnDialog(self, self.app, row["id"], override).show()
        if return_id:
            self.reload()
            text = receipts.return_receipt(self.db, return_id)
            name = sales.get_return(self.db, return_id)["return"]["return_no"]
            TextPreview(self, "Return complete", text,
                        on_print=lambda: receipts.print_text(self.db, text, name)).show()


class ReturnDialog(Dialog):
    def __init__(self, parent, app, sale_id, override_days):
        data = sales.get_sale(app.db, sale_id)
        super().__init__(parent, f"Return items — {data['sale']['invoice_no']}")
        self.app, self.db, self.sale_id, self.override = app, app.db, sale_id, override_days
        self.has_customer = bool(data["sale"]["customer_id"])
        grid = ttk.Frame(self.body)
        grid.pack(fill="both", expand=True)
        for col, text in enumerate(("Item", "Serial", "Sold", "Returned", "Paid / unit", "Return qty")):
            ttk.Label(grid, text=text, font=(FONT_FAMILY, 11, "bold")).grid(row=0, column=col, padx=6, sticky="w")
        self.qtys = {}
        for r, item in enumerate(sales.returnable_items(self.db, sale_id), start=1):
            ttk.Label(grid, text=item["name"]).grid(row=r, column=0, padx=6, sticky="w")
            ttk.Label(grid, text=item["serial_no"] or "").grid(row=r, column=1, padx=6, sticky="w")
            ttk.Label(grid, text=str(item["qty"])).grid(row=r, column=2, padx=6)
            ttk.Label(grid, text=str(item["returned_qty"])).grid(row=r, column=3, padx=6)
            ttk.Label(grid, text=f"{item['line_total'] / item['qty']:,.2f}").grid(row=r, column=4, padx=6)
            if item["returnable"] > 0:
                var = tk.StringVar(value="0")
                ttk.Spinbox(grid, from_=0, to=item["returnable"], textvariable=var, width=6).grid(
                    row=r, column=5, padx=6, pady=3)
                self.qtys[item["id"]] = (var, item["returnable"])
        opts = ttk.Frame(self.body)
        opts.pack(fill="x", pady=(12, 0))
        ttk.Button(opts, text="Return everything", command=self.all).pack(side="left")
        ttk.Label(opts, text="   Refund by").pack(side="left")
        self.method = tk.StringVar(value="Cash")
        methods = [m for m in sales.REFUND_METHODS if m != "Account" or self.has_customer]
        ttk.Combobox(opts, textvariable=self.method, values=methods, state="readonly", width=14).pack(
            side="left", padx=6)
        self.restock = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Put back in stock (uncheck if faulty)", variable=self.restock).pack(
            side="left", padx=10)
        rf = ttk.Frame(self.body)
        rf.pack(fill="x", pady=8)
        ttk.Label(rf, text="Reason").pack(side="left")
        self.reason = tk.StringVar()
        ttk.Combobox(rf, textvariable=self.reason, width=40,
                     values=["Changed mind", "Faulty / defective", "Wrong item", "Damaged in box",
                             "Warranty replacement", "Price adjustment"]).pack(side="left", padx=6)
        self.buttons(ok_text="Process refund")

    def all(self):
        for var, max_qty in self.qtys.values():
            var.set(str(max_qty))

    def ok(self):
        try:
            items = {item_id: parse_int(var.get(), "Quantity") for item_id, (var, _) in self.qtys.items()}
            return_id = sales.process_return(
                self.db, self.sale_id, items, self.reason.get().strip(), self.method.get(),
                self.restock.get(), self.app.user["id"], self.app.current_shift_id(), self.override)
        except POSError as exc:
            messagebox.showwarning(self.title(), str(exc), parent=self)
            return
        self.result = return_id
        self.destroy()
