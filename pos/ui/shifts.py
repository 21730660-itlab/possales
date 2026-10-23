"""Cash drawer shifts: open/close, cash in/out and X/Z reports."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..i18n import _, tr_value
from ..services import operations, receipts
from .app import View
from .widgets import FONT_FAMILY, W, DataTable, TextPreview, ask_form, ask_value, fmt_money, toolbar


class ShiftsView(View):
    title = _("Cash Drawer & Shifts")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        self.state_label = ttk.Label(self, text="", font=(FONT_FAMILY, 15, "bold"))
        self.state_label.pack(anchor=W)
        self.detail = ttk.Label(self, text="", style="Muted.TLabel", font=(FONT_FAMILY, 12))
        self.detail.pack(anchor=W, pady=(2, 10))
        toolbar(self, [(_("Open shift"), self.open, "Accent.TButton"), (_("Cash in"), lambda: self.move("in")),
                       (_("Cash out / payout"), lambda: self.move("out")),
                       (_("X report (current)"), self.x_report),
                       (_("Close shift (Z report)"), self.close, "Danger.TButton"), None,
                       (_("Reprint selected Z report"), self.reprint)]).pack(fill="x", pady=(0, 10))
        ttk.Label(self, text=_("Shift history"), style="H2.TLabel").pack(anchor=W)
        m = lambda v: f"{v:,.2f}" if v is not None else ""
        self.table = DataTable(self, [
            ("id", "#", 50), ("user", _("Opened by"), 100), ("opened_at", _("Opened"), 160),
            ("closed_at", _("Closed"), 160), ("opening_cash", _("Float"), -90, m),
            ("expected_cash", _("Expected"), -100, m), ("counted_cash", _("Counted"), -100, m),
            ("diff", _("Over/short"), -100), ("status", _("Status"), 80, tr_value)], height=16,
            on_double=lambda r: self.reprint())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        sym = self.currency
        shift = operations.current_shift(self.db)
        if shift:
            s = operations.shift_summary(self.db, shift["id"])
            self.state_label.configure(text=_("🟢 Shift #{id} is open — opened by {name} at {time}").format(
                id=shift["id"], name=shift["opened_by"], time=shift["opened_at"]))
            self.detail.configure(text=_("Sales: {count} ({total})    Expected cash in drawer: {cash}").format(
                count=s["sales_count"], total=fmt_money(s["sales_total"], sym),
                cash=fmt_money(s["expected_cash"], sym)))
        else:
            self.state_label.configure(text=_("🔴 No shift is open"))
            self.detail.configure(text=_("Open a shift with the starting cash (float) before selling."))
        rows = []
        for r in operations.list_shifts(self.db):
            r = dict(r)
            if r["counted_cash"] is not None and r["expected_cash"] is not None:
                r["diff"] = f"{r['counted_cash'] - r['expected_cash']:+,.2f}"
            rows.append(r)
        self.table.set_rows(rows, tag_fn=lambda r: "warn" if r.get("diff", "").startswith("-") else None)
        self.app.refresh_status()

    def open(self):
        amount = ask_value(self, _("Open shift"), _("Opening cash (float) in the drawer"), "float", "0")
        if amount is not None:
            operations.open_shift(self.db, self.app.user["id"], amount)
            self.on_show()

    def _shift(self):
        shift = operations.current_shift(self.db)
        if not shift:
            messagebox.showinfo(self.title, _("No shift is open."), parent=self)
        return shift

    def move(self, kind):
        shift = self._shift()
        if not shift:
            return
        res = ask_form(self, _("Cash in") if kind == "in" else _("Cash out"), [
            {"key": "amount", "label": _("Amount"), "type": "float", "required": True},
            {"key": "reason", "label": _("Reason"), "required": True}], ok_text=_("Record"))
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
        if held and not messagebox.askyesno(_("Held sales"), _("There are {count} held sales. Close anyway?").format(
                count=held), parent=self):
            return
        res = ask_form(self, _("Close shift"), [
            {"key": "counted", "label": _("Cash counted in drawer"), "type": "float", "required": True},
            {"key": "notes", "label": _("Notes")}], ok_text=_("Close shift"))
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
        TextPreview(self, _("Shift #{id}").format(id=shift_id), text,
                    on_print=lambda: receipts.print_text(self.db, text, f"shift_{shift_id}")).show()
