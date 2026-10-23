"""Shop expenses (rent, electricity, salaries...)."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..db import today
from ..i18n import _, plain, tr_value
from ..services import operations
from .app import View
from .widgets import FONT_FAMILY, W, DataTable, DateRangeBar, ask_form, confirm, toolbar


class ExpensesView(View):
    title = _("Expenses")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        self.range = DateRangeBar(self, self.reload, preset="This month")
        self.range.pack(anchor=W, pady=(0, 8))
        toolbar(self, [(_("+ Add expense"), self.add, "Accent.TButton"), (_("Delete"), self.delete)]).pack(
            fill="x", pady=(0, 8))
        self.table = DataTable(self, [
            ("date", _("Date"), 110), ("category", _("Category"), 140, tr_value),
            ("description", _("Description"), 320), ("amount", _("Amount"), -110, lambda v: f"{v:,.2f}"),
            ("paid_from_drawer", _("From drawer"), 100, lambda v: _("Yes") if v else ""),
            ("user", _("By"), 90)], height=20)
        self.table.pack(fill="both", expand=True)
        self.total = ttk.Label(self, text="", font=(FONT_FAMILY, 13, "bold"))
        self.total.pack(anchor="e", pady=(8, 0))

    def on_show(self):
        self.reload()

    def reload(self):
        d1, d2 = self.range.range()
        rows = operations.list_expenses(self.db, d1, d2)
        self.table.set_rows(rows)
        self.total.configure(text=_("Total: {amount}").format(
            amount=f"{self.currency}{sum(r['amount'] for r in rows):,.2f}"))

    def add(self):
        def submit(values):
            # Keep the English category when one of the suggestions was picked.
            values["category"] = next((c for c in operations.EXPENSE_CATEGORIES
                                       if plain(tr_value(c)) == values["category"]), values["category"])
            operations.add_expense(self.db, values, self.app.user["id"], self.app.current_shift_id())

        res = ask_form(self, _("Add expense"), [
            {"key": "date", "label": _("Date"), "default": today(), "hint": "YYYY-MM-DD"},
            {"key": "category", "label": _("Category"), "type": "combo", "strict": False,
             "values": [tr_value(c) for c in operations.EXPENSE_CATEGORIES], "default": tr_value("General")},
            {"key": "description", "label": _("Description")},
            {"key": "amount", "label": _("Amount"), "type": "float", "required": True},
            {"key": "paid_from_drawer", "label": _("Paid with cash from the drawer"), "type": "check"}],
            on_submit=submit)
        if res:
            self.reload()

    def delete(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, _("Select an expense first."), parent=self)
            return
        if confirm(self, _("Delete"), _("Delete expense of {amount}?").format(amount=f"{row['amount']:,.2f}")):
            operations.delete_expense(self.db, row["id"], self.app.user["id"])
            self.reload()
