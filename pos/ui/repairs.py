"""Repair / service tickets for customer devices."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..services import operations, receipts, sales
from .app import View
from .sales import CustomerPicker
from .widgets import DataTable, SearchBar, TextPreview, ask_form, toolbar


def repair_fields(statuses=False):
    f = [
        {"key": "device", "label": "Device type", "type": "combo", "strict": False, "required": True,
         "values": ["Phone", "Laptop", "Tablet", "Desktop PC", "TV", "Console", "Smartwatch",
                    "Printer", "Headphones", "Other"]},
        {"key": "brand_model", "label": "Brand / model"},
        {"key": "serial_no", "label": "Serial / IMEI"},
        {"key": "issue", "label": "Problem reported", "type": "multiline", "height": 3, "required": True},
        {"key": "accessories", "label": "Accessories left", "hint": "charger, case..."},
        {"key": "passcode", "label": "Device passcode"},
        {"key": "estimate", "label": "Estimated cost", "type": "float", "default": "0"},
        {"key": "technician", "label": "Technician"},
        {"key": "due_date", "label": "Promised date", "hint": "YYYY-MM-DD"},
        {"key": "notes", "label": "Internal notes", "type": "multiline", "height": 3},
    ]
    if statuses:
        f.insert(7, {"key": "final_cost", "label": "Final cost", "type": "float"})
        f.insert(0, {"key": "status", "label": "Status", "type": "combo",
                     "values": list(operations.REPAIR_STATUSES)})
    return f


class RepairsView(View):
    title = "Repairs & Service"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search = SearchBar(bar, self.reload, "ticket, device, serial, customer", width=32)
        self.search.pack(side="left")
        ttk.Label(bar, text="  Status").pack(side="left")
        self.status = tk.StringVar(value="Open tickets")
        cb = ttk.Combobox(bar, textvariable=self.status, state="readonly", width=18,
                          values=["Open tickets", "All"] + list(operations.REPAIR_STATUSES))
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.reload())
        toolbar(self, [("+ New ticket", self.new, "Accent.TButton"), ("Edit / update", self.edit),
                       None] + [(s, lambda s=s: self.set_status(s)) for s in
                                ("In Progress", "Ready for Pickup", "Delivered")] +
                [None, ("Take payment", self.payment), ("Print ticket", self.print_ticket)]).pack(
            fill="x", pady=(0, 8))
        money = lambda v: f"{v:,.2f}"
        self.table = DataTable(self, [
            ("ticket_no", "Ticket", 95), ("received_at", "Received", 140, lambda v: v[:16]),
            ("customer_name", "Customer", 150), ("customer_phone", "Phone", 110),
            ("device", "Device", 90), ("brand_model", "Model", 140), ("issue", "Issue", 200),
            ("status", "Status", 130), ("final_cost", "Cost", -80, money), ("paid", "Paid", -80, money),
            ("balance", "Due", -80, money), ("due_date", "Promised", 100), ("technician", "Tech", 90)],
            height=20, on_double=lambda r: self.edit())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.reload()

    def reload(self):
        st = self.status.get()
        rows = operations.list_repairs(self.db, status=st if st in operations.REPAIR_STATUSES else None,
                                       search=self.search.get(), open_only=st == "Open tickets")
        self.table.set_rows(rows, tag_fn=lambda r: "ok" if r["status"] == "Ready for Pickup" else
                            ("muted" if r["status"] in ("Delivered", "Cancelled") else None))

    def selected(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, "Select a ticket first.", parent=self)
        return row

    def new(self):
        if not messagebox.askyesno("New ticket", "Attach a customer to this ticket?\n"
                                                 "(Recommended so you can contact them.)", parent=self):
            customer_id = None
        else:
            customer_id = CustomerPicker(self, self.app).show()
        res = ask_form(self, "New repair ticket", repair_fields())
        if not res:
            return
        res["customer_id"] = customer_id
        repair_id = operations.create_repair(self.db, res, self.app.user["id"])
        deposit = ask_form(self, "Deposit", [
            {"key": "amount", "label": "Deposit received now (0 = none)", "type": "float", "default": "0"},
            {"key": "method", "label": "Method", "type": "combo", "default": "Cash",
             "values": sales.tender_methods(self.db.get_settings())}], ok_text="OK")
        if deposit and deposit["amount"] > 0:
            operations.add_repair_payment(self.db, repair_id, deposit["amount"], deposit["method"],
                                          self.app.user["id"], self.app.current_shift_id())
        self.reload()
        self._print(repair_id)

    def edit(self):
        row = self.selected()
        if not row:
            return
        rep = operations.get_repair(self.db, row["id"])
        res = ask_form(self, f"Ticket {rep['ticket_no']}", repair_fields(True), rep)
        if res:
            operations.update_repair(self.db, rep["id"], res, self.app.user["id"])
            self.reload()

    def set_status(self, status):
        row = self.selected()
        if not row:
            return
        if status == "Delivered" and row["balance"] > 0.004:
            if messagebox.askyesno("Balance due", f"{row['balance']:,.2f} is still due. Take payment now?",
                                   parent=self):
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
        res = ask_form(self, f"Payment — {rep['ticket_no']}", [
            {"key": "amount", "label": "Amount", "type": "float", "default": f"{due:.2f}", "required": True},
            {"key": "method", "label": "Method", "type": "combo", "default": "Cash",
             "values": sales.tender_methods(self.db.get_settings())}], ok_text="Receive")
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
