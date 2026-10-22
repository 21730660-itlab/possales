"""Shop expenses (rent, electricity, salaries...)."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..db import today
from ..services import operations
from .app import View
from .widgets import FONT_FAMILY, DataTable, DateRangeBar, ask_form, confirm, toolbar


class ExpensesView(View):
    title = "Expenses"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        self.range = DateRangeBar(self, self.reload, preset="This month")
        self.range.pack(anchor="w", pady=(0, 8))
        toolbar(self, [("+ Add expense", self.add, "Accent.TButton"), ("Delete", self.delete)]).pack(
            fill="x", pady=(0, 8))
        self.table = DataTable(self, [
            ("date", "Date", 110), ("category", "Category", 140), ("description", "Description", 320),
            ("amount", "Amount", -110, lambda v: f"{v:,.2f}"),
            ("paid_from_drawer", "From drawer", 100, lambda v: "Yes" if v else ""), ("user", "By", 90)],
            height=20)
        self.table.pack(fill="both", expand=True)
        self.total = ttk.Label(self, text="", font=(FONT_FAMILY, 13, "bold"))
        self.total.pack(anchor="e", pady=(8, 0))

    def on_show(self):
        self.reload()

    def reload(self):
        d1, d2 = self.range.range()
        rows = operations.list_expenses(self.db, d1, d2)
        self.table.set_rows(rows)
        self.total.configure(text=f"Total: {self.currency}{sum(r['amount'] for r in rows):,.2f}")

    def add(self):
        res = ask_form(self, "Add expense", [
            {"key": "date", "label": "Date", "default": today(), "hint": "YYYY-MM-DD"},
            {"key": "category", "label": "Category", "type": "combo", "strict": False,
             "values": list(operations.EXPENSE_CATEGORIES), "default": "General"},
            {"key": "description", "label": "Description"},
            {"key": "amount", "label": "Amount", "type": "float", "required": True},
            {"key": "paid_from_drawer", "label": "Paid with cash from the drawer", "type": "check"}],
            on_submit=lambda v: operations.add_expense(self.db, v, self.app.user["id"],
                                                       self.app.current_shift_id()))
        if res:
            self.reload()

    def delete(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, "Select an expense first.", parent=self)
            return
        if confirm(self, "Delete", f"Delete expense of {row['amount']:,.2f}?"):
            operations.delete_expense(self.db, row["id"], self.app.user["id"])
            self.reload()
