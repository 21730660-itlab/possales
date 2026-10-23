"""Customer management: contacts, loyalty points, account (credit) balances."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..i18n import _, tr_value
from ..services import people, receipts, sales
from .app import View
from .widgets import (W, DataTable, Dialog, SearchBar, TextPreview, add_tabs, ask_form, confirm,
                      fmt_money, require_permission, toolbar)


def customer_fields():
    return [
        {"key": "name", "label": _("Name"), "required": True},
        {"key": "phone", "label": _("Phone")},
        {"key": "email", "label": _("Email")},
        {"key": "address", "label": _("Address")},
        {"key": "credit_limit", "label": _("Credit limit"), "type": "float", "default": "0",
         "hint": _("0 = no limit")},
        {"key": "notes", "label": _("Notes"), "type": "multiline", "height": 3},
    ]


class CustomersView(View):
    title = _("Customers")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        self.search = SearchBar(self, self.reload, _("name, phone or email"), width=36)
        self.search.pack(anchor=W, pady=(0, 8))
        toolbar(self, [
            (_("+ New customer"), self.new, "Accent.TButton"), (_("Edit"), self.edit),
            (_("Delete"), self.delete), None, (_("Purchase history"), self.history),
            (_("Receive payment"), self.receive), (_("Adjust points"), self.points),
        ]).pack(fill="x", pady=(0, 8))
        self.table = DataTable(self, [
            ("name", _("Name"), 220), ("phone", _("Phone"), 130), ("email", _("Email"), 200),
            ("loyalty_points", _("Points"), -80),
            ("balance", _("Owes"), -100, lambda v: f"{v:,.2f}" if v else ""),
            ("credit_limit", _("Credit limit"), -100, lambda v: f"{v:,.2f}" if v else ""),
            ("address", _("Address"), 200), ("created_at", _("Since"), 110, lambda v: v[:10])],
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
            messagebox.showinfo(self.title, _("Select a customer first."), parent=self)
        return row

    def new(self):
        if ask_form(self, _("New customer"), customer_fields(),
                    on_submit=lambda v: people.save_customer(self.db, v, user_id=self.app.user["id"])):
            self.reload()

    def edit(self):
        row = self.selected()
        if row and ask_form(self, _("Edit — {name}").format(name=row["name"]), customer_fields(), row,
                            on_submit=lambda v: people.save_customer(self.db, v, row["id"],
                                                                     self.app.user["id"])):
            self.reload()

    def delete(self):
        row = self.selected()
        if row and confirm(self, _("Delete"), _("Delete customer '{name}'? Their past sales are kept.").format(
                name=row["name"])):
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
        methods = sales.tender_methods(self.db.get_settings())
        res = ask_form(self, _("Receive payment — {name}").format(name=row["name"]), [
            {"key": "amount", "label": _("Amount (owes {amount})").format(
                amount=fmt_money(row["balance"], self.currency)),
             "type": "float", "required": True, "default": f"{max(row['balance'], 0):.2f}"},
            {"key": "method", "label": _("Method"), "type": "combo", "default": "Cash",
             "choices": [(m, tr_value(m)) for m in methods]},
            {"key": "notes", "label": _("Notes")}], ok_text=_("Receive"))
        if res:
            shift_id = self.app.current_shift_id()
            if res["method"] == "Cash" and not shift_id:
                if not messagebox.askyesno(_("No shift"), _("No shift is open, so this cash will not be "
                                                            "counted in a drawer. Continue?"), parent=self):
                    return
            people.receive_account_payment(self.db, row["id"], res["amount"], res["method"], res["notes"],
                                           self.app.user["id"], shift_id)
            self.reload()

    def points(self):
        row = self.selected()
        if not row or not require_permission(self, self.app, "customers_points",
                                             _("Adjusting loyalty points needs a manager.")):
            return
        res = ask_form(self, _("Loyalty points — {name} ({points})").format(
            name=row["name"], points=row["loyalty_points"]), [
            {"key": "delta", "label": _("Add (+) or remove (−) points"), "type": "int", "required": True},
            {"key": "reason", "label": _("Reason")}], ok_text=_("Apply"))
        if res:
            people.adjust_points(self.db, row["id"], res["delta"], self.app.user["id"], res["reason"])
            self.reload()


class CustomerHistory(Dialog):
    def __init__(self, parent, app, customer_id):
        c = people.get_customer(app.db, customer_id)
        super().__init__(parent, _("Customer — {name}").format(name=c["name"]))
        self.app, self.db = app, app.db
        sym = app.db.get_setting("currency_symbol", "$")
        salesrows = people.customer_sales(self.db, customer_id)
        spent = sum(s["total"] for s in salesrows)
        ttk.Label(self.body, style="H2.TLabel",
                  text=f"{c['name']}   {c['phone'] or ''}").pack(anchor=W)
        ttk.Label(self.body, text=_("Purchases: {count}    Total spent: {spent}    Points: {points}    "
                                    "Owes: {owes}").format(count=len(salesrows), spent=fmt_money(spent, sym),
                                                           points=c["loyalty_points"],
                                                           owes=fmt_money(c["balance"], sym))
                  ).pack(anchor=W, pady=(0, 8))
        tabs = ttk.Notebook(self.body)
        tabs.pack(fill="both", expand=True)
        self.sales = DataTable(tabs, [
            ("invoice_no", _("Invoice"), 120), ("created_at", _("Date"), 160),
            ("total", _("Total"), -100, lambda v: f"{v:,.2f}"), ("status", _("Status"), 140, tr_value)],
            height=12, on_double=self.show_receipt)
        self.sales.set_rows(salesrows)
        pays = DataTable(tabs, [("created_at", _("Date"), 160),
                                ("amount", _("Amount"), -100, lambda v: f"{v:,.2f}"),
                                ("method", _("Method"), 120, tr_value), ("notes", _("Notes"), 200)], height=12)
        pays.set_rows(people.customer_payments(self.db, customer_id))
        add_tabs(tabs, [(self.sales, _("Purchases (double-click for receipt)")),
                        (pays, _("Account payments"))])
        self.buttons(ok_text="", cancel_text=_("Close"))

    def show_receipt(self, row):
        text = receipts.sale_receipt(self.db, row["id"], copy=True)
        TextPreview(self, row["invoice_no"], text,
                    on_print=lambda: receipts.print_text(self.db, text, row["invoice_no"] + "_copy")).show()
