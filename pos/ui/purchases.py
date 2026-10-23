"""Purchase orders: order from suppliers and receive stock."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..db import POSError, money
from ..i18n import _, plain, tr_value
from ..services import catalog, people, purchasing, receipts
from .app import View
from .products import LabelDialog
from .sales import ProductPicker
from .widgets import (FONT_FAMILY, START, W, DataTable, Dialog, TextPreview, ask_form, col, confirm,
                      fmt_money, pad, parse_int, toolbar)

PO_STATUSES = ("ordered", "partial", "received", "cancelled")


class PurchasesView(View):
    title = _("Purchase Orders")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        toolbar(bar, [(_("+ New purchase order"), self.new, "Accent.TButton"),
                      (_("Receive stock"), self.receive), (_("View / print"), self.view),
                      (_("🏷 Print labels"), self.labels), (_("Cancel order"), self.cancel_po),
                      None, (_("Reorder low stock"), self.reorder)]).pack(side=START, fill="x", expand=True)
        ttk.Label(bar, text=_("Status")).pack(side=START, padx=pad(16, 4))
        self.status_choices = [(None, _("All"))] + [(s, tr_value(s)) for s in PO_STATUSES]
        self.status = tk.StringVar(value=_("All"))
        cb = ttk.Combobox(bar, textvariable=self.status, state="readonly", width=12,
                          values=[shown for _v, shown in self.status_choices])
        cb.pack(side=START)
        cb.bind("<<ComboboxSelected>>", lambda e: self.reload())
        self.table = DataTable(self, [
            ("po_no", _("PO #"), 110), ("created_at", _("Date"), 160), ("supplier", _("Supplier"), 200),
            ("status", _("Status"), 100, tr_value), ("total", _("Total"), -110, lambda v: f"{v:,.2f}"),
            ("received_at", _("Received"), 160), ("user", _("By"), 90), ("notes", _("Notes"), 220)],
            height=20, on_double=lambda r: self.view())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.reload()

    def reload(self):
        status = next((v for v, shown in self.status_choices if shown == self.status.get()), None)
        self.table.set_rows(purchasing.list_pos(self.db, status),
                            tag_fn=lambda r: {"ordered": "warn", "partial": "warn",
                                              "cancelled": "muted"}.get(r["status"]))

    def selected(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, _("Select a purchase order first."), parent=self)
        return row

    def new(self, supplier_id=None, items=None):
        if PODialog(self, self.app, supplier_id, items).show():
            self.reload()

    def reorder(self):
        """Pre-fill a PO with every low-stock product (up to twice the reorder level)."""
        low = catalog.low_stock(self.db)
        if not low:
            messagebox.showinfo(_("Reorder"), _("No products are below their reorder level."), parent=self)
            return
        items = [{"product_id": p["id"], "name": p["name"], "sku": p["sku"],
                  "qty": max(1, p["reorder_level"] * 2 - p["stock_qty"]), "unit_cost": p["cost_price"]}
                 for p in low]
        self.new(low[0]["supplier_id"], items)

    def receive(self):
        row = self.selected()
        if row and ReceiveDialog(self, self.app, row["id"]).show():
            self.reload()

    def view(self):
        row = self.selected()
        if not row:
            return
        text = po_text(self.db, row["id"])
        TextPreview(self, row["po_no"], text, width=60,
                    on_print=lambda: receipts.print_text(self.db, text, row["po_no"])).show()

    def labels(self):
        """Barcode labels for everything received on the selected order."""
        row = self.selected()
        if not row:
            return
        copies = {}
        for item in purchasing.get_po(self.db, row["id"])["items"]:
            copies[item["product_id"]] = copies.get(item["product_id"], 0) + item["received_qty"]
        if not any(copies.values()):
            messagebox.showinfo(self.title, _("Nothing has been received on this order yet."), parent=self)
            return
        LabelDialog(self, self.app, list(copies.items())).show()

    def cancel_po(self):
        row = self.selected()
        if row and confirm(self, _("Cancel"), _("Cancel purchase order {number}?").format(number=row["po_no"])):
            purchasing.cancel_po(self.db, row["id"], self.app.user["id"])
            self.reload()


def po_text(db, po_id) -> str:
    """Printable purchase order, in the interface language."""
    t = lambda text: plain(_(text))  # no direction marks in printed documents
    settings = db.get_settings()
    data = purchasing.get_po(db, po_id)
    po = data["po"]
    r = receipts.Receipt(60)
    r.center(settings.get("shop_name", ""))
    r.center(settings.get("shop_address", ""))
    r.center(t("PURCHASE ORDER"))
    r.rule("=")
    r.pair(t("PO number:"), po["po_no"])
    r.pair(t("Date:"), po["created_at"])
    r.pair(t("Supplier:"), po["supplier"] or "-")
    r.pair(t("Status:"), plain(tr_value(po["status"])))
    r.rule()
    for item in data["items"]:
        r.text(f"{item['sku']}  {item['name']}")
        r.pair(f"   {item['qty']} x {item['unit_cost']:,.2f}   " +
               t("(received {qty})").format(qty=item["received_qty"]),
               f"{item['qty'] * item['unit_cost']:,.2f}")
    r.rule()
    r.pair(t("TOTAL"), receipts.fmt(po["total"], settings))
    if po["notes"]:
        r.text(t("Notes:") + " " + po["notes"])
    return r.render()


class PODialog(Dialog):
    def __init__(self, parent, app, supplier_id=None, items=None):
        super().__init__(parent, _("New purchase order"))
        self.app, self.db = app, app.db
        self.sym = self.db.get_setting("currency_symbol", "$")
        self.items = list(items or [])
        self.suppliers = {s["name"]: s["id"] for s in people.list_suppliers(self.db)}
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        ttk.Label(top, text=_("Supplier")).pack(side=START)
        self.supplier = tk.StringVar(value=next((n for n, i in self.suppliers.items() if i == supplier_id), ""))
        ttk.Combobox(top, textvariable=self.supplier, values=list(self.suppliers), state="readonly",
                     width=30).pack(side=START, padx=8)
        ttk.Label(top, text=_("Notes")).pack(side=START, padx=pad(12, 0))
        self.notes = tk.StringVar()
        ttk.Entry(top, textvariable=self.notes, width=30).pack(side=START, padx=8)
        toolbar(self.body, [(_("+ Add product"), self.add), (_("Edit line"), self.edit_line),
                            (_("Remove line"), self.remove)]).pack(fill="x", pady=8)
        self.table = DataTable(self.body, [
            ("sku", _("SKU"), 90), ("name", _("Product"), 280), ("qty", _("Qty"), -70),
            ("unit_cost", _("Unit cost"), -100, lambda v: f"{v:,.2f}"),
            ("line", _("Line total"), -110, lambda v: f"{v:,.2f}")], height=12,
            on_double=lambda r: self.edit_line())
        self.table.pack(fill="both", expand=True)
        self.total = ttk.Label(self.body, text="", font=(FONT_FAMILY, 14, "bold"))
        self.total.pack(anchor="e", pady=6)
        self.buttons(ok_text=_("Create order"))
        self.refresh()

    def refresh(self):
        rows = [dict(i, id=n, line=money(i["qty"] * i["unit_cost"])) for n, i in enumerate(self.items)]
        self.table.set_rows(rows)
        self.total.configure(text=_("Total: {amount}").format(
            amount=fmt_money(sum(r["line"] for r in rows), self.sym)))

    def add(self):
        p = ProductPicker(self, self.app).show()
        if not p:
            return
        res = ask_form(self, p["name"], [
            {"key": "qty", "label": _("Quantity"), "type": "int", "default": "1", "required": True},
            {"key": "unit_cost", "label": _("Unit cost"), "type": "float", "default": f"{p['cost_price']:.2f}"}],
            ok_text=_("Add"))
        if res:
            self.items.append({"product_id": p["id"], "sku": p["sku"], "name": p["name"], **res})
            self.refresh()

    def edit_line(self):
        row = self.table.selected()
        if row is None:
            return
        item = self.items[row["id"]]
        res = ask_form(self, item["name"], [
            {"key": "qty", "label": _("Quantity"), "type": "int", "required": True},
            {"key": "unit_cost", "label": _("Unit cost"), "type": "float"}], item, ok_text=_("OK"))
        if res:
            item.update(res)
            self.refresh()

    def remove(self):
        row = self.table.selected()
        if row is not None:
            del self.items[row["id"]]
            self.refresh()

    def ok(self):
        try:
            purchasing.create_po(self.db, self.suppliers.get(self.supplier.get()), self.items,
                                 self.notes.get(), self.app.user["id"])
        except POSError as exc:
            messagebox.showwarning(self.title(), str(exc), parent=self)
            return
        self.result = True
        self.destroy()


class ReceiveDialog(Dialog):
    def __init__(self, parent, app, po_id):
        data = purchasing.get_po(app.db, po_id)
        super().__init__(parent, _("Receive stock — {number}").format(number=data["po"]["po_no"]))
        self.app, self.db, self.po_id = app, app.db, po_id
        ttk.Label(self.body, text=_("Enter the quantity received now. For serial-tracked products, scan the "
                                    "serial numbers (one per line) — optional."), wraplength=640).pack(anchor=W)
        grid = ttk.Frame(self.body)
        grid.pack(fill="both", expand=True, pady=10)
        heads = (_("Product"), _("Ordered"), _("Received"), _("Receive now"), _("Serials"))
        for i, text in enumerate(heads):
            ttk.Label(grid, text=text, font=(FONT_FAMILY, 11, "bold")).grid(
                row=0, column=col(i, 5), sticky=W, padx=6)
        self.rows = []
        for r, item in enumerate(data["items"], start=1):
            outstanding = item["qty"] - item["received_qty"]
            ttk.Label(grid, text=f"{item['sku']}  {item['name']}").grid(row=r, column=col(0, 5), sticky=W, padx=6)
            ttk.Label(grid, text=str(item["qty"])).grid(row=r, column=col(1, 5), padx=6)
            ttk.Label(grid, text=str(item["received_qty"])).grid(row=r, column=col(2, 5), padx=6)
            qty = tk.StringVar(value=str(outstanding))
            ttk.Entry(grid, textvariable=qty, width=8).grid(row=r, column=col(3, 5), padx=6, pady=3)
            serial_box = None
            if item["track_serial"] and outstanding > 0:
                serial_box = tk.Text(grid, width=28, height=min(4, outstanding), font=(FONT_FAMILY, 10))
                serial_box.grid(row=r, column=col(4, 5), padx=6, pady=3)
            self.rows.append((item, qty, serial_box))
        self.update_cost = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.body, text=_("Update product cost (weighted average)"),
                        variable=self.update_cost).pack(anchor=W)
        self.buttons(ok_text=_("Receive"))

    def ok(self):
        try:
            received, serials = {}, {}
            for item, qty, box in self.rows:
                received[item["id"]] = parse_int(qty.get(), _("Quantity"))
                if box is not None:
                    serials[item["id"]] = [s for s in box.get("1.0", "end").splitlines() if s.strip()]
            purchasing.receive_po(self.db, self.po_id, received, self.app.user["id"], serials,
                                  self.update_cost.get())
        except POSError as exc:
            messagebox.showwarning(self.title(), str(exc), parent=self)
            return
        self.result = True
        self.destroy()
