"""Repair / service tickets for customer devices."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..i18n import _, tr_value
from ..services import operations, receipts, sales
from .app import View
from .sales import CustomerPicker
from .widgets import START, DataTable, SearchBar, TextPreview, ask_form, toolbar

DEVICE_TYPES = ("Phone", "Laptop", "Tablet", "Desktop PC", "TV", "Console", "Smartwatch",
                "Printer", "Headphones", "Other")


def repair_fields(statuses=False):
    f = [
        {"key": "device", "label": _("Device type"), "type": "combo", "strict": False, "required": True,
         "values": [tr_value(d) for d in DEVICE_TYPES]},
        {"key": "brand_model", "label": _("Brand / model")},
        {"key": "serial_no", "label": _("Serial / IMEI")},
        {"key": "issue", "label": _("Problem reported"), "type": "multiline", "height": 3, "required": True},
        {"key": "accessories", "label": _("Accessories left"), "hint": _("charger, case...")},
        {"key": "passcode", "label": _("Device passcode")},
        {"key": "estimate", "label": _("Estimated cost"), "type": "float", "default": "0"},
        {"key": "technician", "label": _("Technician")},
        {"key": "due_date", "label": _("Promised date"), "hint": "YYYY-MM-DD"},
        {"key": "notes", "label": _("Internal notes"), "type": "multiline", "height": 3},
    ]
    if statuses:
        f.insert(7, {"key": "final_cost", "label": _("Final cost"), "type": "float"})
        f.insert(0, {"key": "status", "label": _("Status"), "type": "combo",
                     "choices": [(s, tr_value(s)) for s in operations.REPAIR_STATUSES]})
    return f


class RepairsView(View):
    title = _("Repairs & Service")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search = SearchBar(bar, self.reload, _("ticket, device, serial, customer"), width=32)
        self.search.pack(side=START)
        ttk.Label(bar, text="  " + _("Status")).pack(side=START)
        self.status_choices = ([("open", _("Open tickets")), (None, _("All"))] +
                               [(s, tr_value(s)) for s in operations.REPAIR_STATUSES])
        self.status = tk.StringVar(value=_("Open tickets"))
        cb = ttk.Combobox(bar, textvariable=self.status, state="readonly", width=18,
                          values=[shown for _v, shown in self.status_choices])
        cb.pack(side=START, padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.reload())
        toolbar(self, [(_("+ New ticket"), self.new, "Accent.TButton"), (_("Edit / update"), self.edit),
                       None] + [(tr_value(s), lambda s=s: self.set_status(s)) for s in
                                ("In Progress", "Ready for Pickup", "Delivered")] +
                [None, (_("Take payment"), self.payment), (_("Print ticket"), self.print_ticket)]).pack(
            fill="x", pady=(0, 8))
        money = lambda v: f"{v:,.2f}"
        self.table = DataTable(self, [
            ("ticket_no", _("Ticket"), 95), ("received_at", _("Received"), 140, lambda v: v[:16]),
            ("customer_name", _("Customer"), 150), ("customer_phone", _("Phone"), 110),
            ("device", _("Device"), 90, tr_value), ("brand_model", _("Model"), 140), ("issue", _("Issue"), 200),
            ("status", _("Status"), 130, tr_value), ("final_cost", _("Cost"), -80, money),
            ("paid", _("Paid"), -80, money), ("balance", _("Due"), -80, money),
            ("due_date", _("Promised"), 100), ("technician", _("Tech"), 90)],
            height=20, on_double=lambda r: self.edit())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.reload()

    def reload(self):
        st = next((v for v, shown in self.status_choices if shown == self.status.get()), "open")
        rows = operations.list_repairs(self.db, status=st if st in operations.REPAIR_STATUSES else None,
                                       search=self.search.get(), open_only=st == "open")
        self.table.set_rows(rows, tag_fn=lambda r: "ok" if r["status"] == "Ready for Pickup" else
                            ("muted" if r["status"] in ("Delivered", "Cancelled") else None))

    def selected(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, _("Select a ticket first."), parent=self)
        return row

    def _method_choices(self):
        return [(m, tr_value(m)) for m in sales.tender_methods(self.db.get_settings())]

    def new(self):
        if not messagebox.askyesno(_("New ticket"), _("Attach a customer to this ticket?\n"
                                                      "(Recommended so you can contact them.)"), parent=self):
            customer_id = None
        else:
            customer_id = CustomerPicker(self, self.app).show()
        res = ask_form(self, _("New repair ticket"), repair_fields())
        if not res:
            return
        res["customer_id"] = customer_id
        repair_id = operations.create_repair(self.db, res, self.app.user["id"])
        deposit = ask_form(self, _("Deposit"), [
            {"key": "amount", "label": _("Deposit received now (0 = none)"), "type": "float", "default": "0"},
            {"key": "method", "label": _("Method"), "type": "combo", "default": "Cash",
             "choices": self._method_choices()}], ok_text=_("OK"))
        if deposit and deposit["amount"] > 0:
            operations.add_repair_payment(self.db, repair_id, deposit["amount"], deposit["method"],
                                          self.app.user["id"], self.app.current_shift_id())
        self.reload()
        self._print(repair_id)

    def edit(self):
        row = self.selected()
        if not row:
            return
        rep = dict(operations.get_repair(self.db, row["id"]))
        rep["device"] = tr_value(rep["device"])
        res = ask_form(self, _("Ticket {number}").format(number=rep["ticket_no"]), repair_fields(True), rep)
        if res:
            operations.update_repair(self.db, rep["id"], res, self.app.user["id"])
            self.reload()

    def set_status(self, status):
        row = self.selected()
        if not row:
            return
        if status == "Delivered" and row["balance"] > 0.004:
            if messagebox.askyesno(_("Balance due"), _("{amount} is still due. Take payment now?").format(
                    amount=f"{row['balance']:,.2f}"), parent=self):
                self.payment()
                row = operations.get_repair(self.db, row["id"])
        operations.update_repair(self.db, row["id"], {"status": status}, self.app.user["id"])
        self.reload()

    def payment(self):
        row = self.selected()
        if not row:
            return
        rep = operations.get_repair(self.db, row["id"])
        due = max(0, rep["final_cost"] - rep["paid"])
        res = ask_form(self, _("Payment — {number}").format(number=rep["ticket_no"]), [
            {"key": "amount", "label": _("Amount"), "type": "float", "default": f"{due:.2f}", "required": True},
            {"key": "method", "label": _("Method"), "type": "combo", "default": "Cash",
             "choices": self._method_choices()}], ok_text=_("Receive"))
        if res:
            operations.add_repair_payment(self.db, rep["id"], res["amount"], res["method"],
                                          self.app.user["id"], self.app.current_shift_id())
            self.reload()

    def print_ticket(self):
        row = self.selected()
        if row:
            self._print(row["id"])

    def _print(self, repair_id):
        rep = operations.get_repair(self.db, repair_id)
        text = receipts.repair_ticket(self.db, repair_id)
        TextPreview(self, rep["ticket_no"], text,
                    on_print=lambda: receipts.print_text(self.db, text, rep["ticket_no"])).show()
