"""Cash drawer shifts: open/close, cash in/out and X/Z reports."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..services import operations, receipts
from .app import View
from .widgets import FONT_FAMILY, DataTable, TextPreview, ask_form, ask_value, fmt_money, toolbar


class ShiftsView(View):
    title = "Cash Drawer & Shifts"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        self.state_label = ttk.Label(self, text="", font=(FONT_FAMILY, 15, "bold"))
        self.state_label.pack(anchor="w")
        self.detail = ttk.Label(self, text="", style="Muted.TLabel", font=(FONT_FAMILY, 12))
        self.detail.pack(anchor="w", pady=(2, 10))
        toolbar(self, [("Open shift", self.open, "Accent.TButton"), ("Cash in", lambda: self.move("in")),
                       ("Cash out / payout", lambda: self.move("out")), ("X report (current)", self.x_report),
                       ("Close shift (Z report)", self.close, "Danger.TButton"), None,
                       ("Reprint selected Z report", self.reprint)]).pack(fill="x", pady=(0, 10))
        ttk.Label(self, text="Shift history", style="H2.TLabel").pack(anchor="w")
        m = lambda v: f"{v:,.2f}" if v is not None else ""
        self.table = DataTable(self, [
            ("id", "#", 50), ("user", "Opened by", 100), ("opened_at", "Opened", 160),
            ("closed_at", "Closed", 160), ("opening_cash", "Float", -90, m),
            ("expected_cash", "Expected", -100, m), ("counted_cash", "Counted", -100, m),
            ("diff", "Over/short", -100), ("status", "Status", 80)], height=16,
            on_double=lambda r: self.reprint())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        sym = self.currency
        shift = operations.current_shift(self.db)
        if shift:
            s = operations.shift_summary(self.db, shift["id"])
            self.state_label.configure(text=f"🟢 Shift #{shift['id']} is open — opened by {shift['opened_by']} "
                                      f"at {shift['opened_at']}")
            self.detail.configure(text=f"Sales: {s['sales_count']} ({fmt_money(s['sales_total'], sym)})    "
                                       f"Expected cash in drawer: {fmt_money(s['expected_cash'], sym)}")
        else:
            self.state_label.configure(text="🔴 No shift is open")
            self.detail.configure(text="Open a shift with the starting cash (float) before selling.")
        rows = []
        for r in operations.list_shifts(self.db):
            r = dict(r)
            if r["counted_cash"] is not None and r["expected_cash"] is not None:
                r["diff"] = f"{r['counted_cash'] - r['expected_cash']:+,.2f}"
            rows.append(r)
        self.table.set_rows(rows, tag_fn=lambda r: "warn" if r.get("diff", "").startswith("-") else None)
        self.app.refresh_status()

    def open(self):
        amount = ask_value(self, "Open shift", "Opening cash (float) in the drawer", "float", "0")
        if amount is not None:
            operations.open_shift(self.db, self.app.user["id"], amount)
            self.on_show()

    def _shift(self):
        shift = operations.current_shift(self.db)
        if not shift:
            messagebox.showinfo(self.title, "No shift is open.", parent=self)
        return shift

    def move(self, kind):
        shift = self._shift()
        if not shift:
            return
        res = ask_form(self, "Cash in" if kind == "in" else "Cash out", [
            {"key": "amount", "label": "Amount", "type": "float", "required": True},
            {"key": "reason", "label": "Reason", "required": True}], ok_text="Record")
        if res:
            operations.cash_movement(self.db, shift["id"], kind, res["amount"], res["reason"],
                                     self.app.user["id"])
            receipts.open_cash_drawer(self.db)
            self.on_show()

    def x_report(self):
        shift = self._shift()
        if shift:
            self._preview(shift["id"])

    def close(self):
        shift = self._shift()
        if not shift:
            return
        held = self.db.scalar("SELECT COUNT(*) FROM held_sales", default=0)
        if held and not messagebox.askyesno("Held sales", f"There are {held} held sales. Close anyway?",
                                            parent=self):
            return
        res = ask_form(self, "Close shift", [
            {"key": "counted", "label": "Cash counted in drawer", "type": "float", "required": True},
            {"key": "notes", "label": "Notes"}], ok_text="Close shift")
        if res is None:
            return
        operations.close_shift(self.db, shift["id"], res["counted"], self.app.user["id"], res["notes"])
        self.on_show()
        self._preview(shift["id"])

    def reprint(self):
        row = self.table.selected()
        if row:
            self._preview(row["id"])

    def _preview(self, shift_id):
        text = receipts.z_report(self.db, shift_id)
        TextPreview(self, f"Shift #{shift_id}", text,
                    on_print=lambda: receipts.print_text(self.db, text, f"shift_{shift_id}")).show()
