"""Customer management: contacts, loyalty points, account (credit) balances."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..services import people, receipts, sales
from .app import View
from .widgets import (DataTable, Dialog, SearchBar, TextPreview, ask_form, confirm, fmt_money,
                      require_permission, toolbar)

CUSTOMER_FIELDS = [
    {"key": "name", "label": "Name", "required": True},
    {"key": "phone", "label": "Phone"},
    {"key": "email", "label": "Email"},
    {"key": "address", "label": "Address"},
    {"key": "credit_limit", "label": "Credit limit", "type": "float", "default": "0",
     "hint": "0 = no limit"},
    {"key": "notes", "label": "Notes", "type": "multiline", "height": 3},
]


class CustomersView(View):
    title = "Customers"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        self.search = SearchBar(self, self.reload, "name, phone or email", width=36)
        self.search.pack(anchor="w", pady=(0, 8))
        toolbar(self, [
            ("+ New customer", self.new, "Accent.TButton"), ("Edit", self.edit), ("Delete", self.delete),
            None, ("Purchase history", self.history), ("Receive payment", self.receive),
            ("Adjust points", self.points),
        ]).pack(fill="x", pady=(0, 8))
        self.table = DataTable(self, [
            ("name", "Name", 220), ("phone", "Phone", 130), ("email", "Email", 200),
            ("loyalty_points", "Points", -80),
            ("balance", "Owes", -100, lambda v: f"{v:,.2f}" if v else ""),
            ("credit_limit", "Credit limit", -100, lambda v: f"{v:,.2f}" if v else ""),
            ("address", "Address", 200), ("created_at", "Since", 110, lambda v: v[:10])],
            height=20, on_double=lambda r: self.history())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.reload()

    def reload(self):
        self.table.set_rows(people.list_customers(self.db, self.search.get(), limit=5000),
                            tag_fn=lambda r: "warn" if r["balance"] > 0.004 else None)

    def selected(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, "Select a customer first.", parent=self)
        return row

    def new(self):
        if ask_form(self, "New customer", CUSTOMER_FIELDS,
                    on_submit=lambda v: people.save_customer(self.db, v, user_id=self.app.user["id"])):
            self.reload()

    def edit(self):
        row = self.selected()
        if row and ask_form(self, f"Edit — {row['name']}", CUSTOMER_FIELDS, row,
                            on_submit=lambda v: people.save_customer(self.db, v, row["id"],
                                                                     self.app.user["id"])):
            self.reload()

    def delete(self):
        row = self.selected()
        if row and confirm(self, "Delete", f"Delete customer '{row['name']}'? Their past sales are kept."):
            people.delete_customer(self.db, row["id"], self.app.user["id"])
            self.reload()

    def history(self):
        row = self.selected()
        if row:
            CustomerHistory(self, self.app, row["id"]).show()
            self.reload()

    def receive(self):
        row = self.selected()
        if not row:
            return
        res = ask_form(self, f"Receive payment — {row['name']}", [
            {"key": "amount", "label": f"Amount (owes {fmt_money(row['balance'], self.currency)})",
             "type": "float", "required": True, "default": f"{max(row['balance'], 0):.2f}"},
            {"key": "method", "label": "Method", "type": "combo",
             "values": ["Cash", "Card", "Bank Transfer", "Mobile Wallet", "Cheque"], "default": "Cash"},
            {"key": "notes", "label": "Notes"}], ok_text="Receive")
        if res:
            shift_id = self.app.current_shift_id()
            if res["method"] == "Cash" and not shift_id:
                if not messagebox.askyesno("No shift", "No shift is open, so this cash will not be counted "
                                                       "in a drawer. Continue?", parent=self):
                    return
            people.receive_account_payment(self.db, row["id"], res["amount"], res["method"], res["notes"],
                                           self.app.user["id"], shift_id)
            self.reload()

    def points(self):
        row = self.selected()
        if not row or not require_permission(self, self.app, "customers_points",
                                             "Adjusting loyalty points needs a manager."):
            return
        res = ask_form(self, f"Loyalty points — {row['name']} ({row['loyalty_points']})", [
            {"key": "delta", "label": "Add (+) or remove (−) points", "type": "int", "required": True},
            {"key": "reason", "label": "Reason"}], ok_text="Apply")
        if res:
            people.adjust_points(self.db, row["id"], res["delta"], self.app.user["id"], res["reason"])
            self.reload()


class CustomerHistory(Dialog):
    def __init__(self, parent, app, customer_id):
        c = people.get_customer(app.db, customer_id)
        super().__init__(parent, f"Customer — {c['name']}")
        self.app, self.db = app, app.db
        sym = app.db.get_setting("currency_symbol", "$")
        salesrows = people.customer_sales(self.db, customer_id)
        spent = sum(s["total"] for s in salesrows)
        ttk.Label(self.body, style="H2.TLabel",
                  text=f"{c['name']}   {c['phone'] or ''}").pack(anchor="w")
        ttk.Label(self.body, text=f"Purchases: {len(salesrows)}    Total spent: {fmt_money(spent, sym)}    "
                                  f"Points: {c['loyalty_points']}    Owes: {fmt_money(c['balance'], sym)}"
                  ).pack(anchor="w", pady=(0, 8))
        tabs = ttk.Notebook(self.body)
        tabs.pack(fill="both", expand=True)
        self.sales = DataTable(tabs, [
            ("invoice_no", "Invoice", 120), ("created_at", "Date", 160),
            ("total", "Total", -100, lambda v: f"{v:,.2f}"), ("status", "Status", 140)],
            height=12, on_double=self.show_receipt)
        self.sales.set_rows(salesrows)
        pays = DataTable(tabs, [("created_at", "Date", 160), ("amount", "Amount", -100, lambda v: f"{v:,.2f}"),
                                ("method", "Method", 120), ("notes", "Notes", 200)], height=12)
        pays.set_rows(people.customer_payments(self.db, customer_id))
        tabs.add(self.sales, text="Purchases (double-click for receipt)")
        tabs.add(pays, text="Account payments")
        self.buttons(ok_text="", cancel_text="Close")

    def show_receipt(self, row):
        text = receipts.sale_receipt(self.db, row["id"], copy=True)
        TextPreview(self, row["invoice_no"], text,
                    on_print=lambda: receipts.print_text(self.db, text, row["invoice_no"] + "_copy")).show()
