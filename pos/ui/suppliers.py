"""Supplier management."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..services import people
from .app import View
from .widgets import DataTable, SearchBar, ask_form, toolbar

SUPPLIER_FIELDS = [
    {"key": "name", "label": "Company name", "required": True},
    {"key": "contact", "label": "Contact person"},
    {"key": "phone", "label": "Phone"},
    {"key": "email", "label": "Email"},
    {"key": "address", "label": "Address"},
    {"key": "notes", "label": "Notes", "type": "multiline", "height": 3},
    {"key": "active", "label": "Active", "type": "check", "default": True},
]


class SuppliersView(View):
    title = "Suppliers"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search = SearchBar(bar, self.reload, "name, contact, phone", width=34)
        self.search.pack(side="left")
        self.inactive = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Show inactive", variable=self.inactive, command=self.reload).pack(
            side="left", padx=10)
        toolbar(self, [("+ New supplier", self.new, "Accent.TButton"), ("Edit", self.edit),
                       ("New purchase order", self.new_po)]).pack(fill="x", pady=(0, 8))
        self.table = DataTable(self, [
            ("name", "Name", 220), ("contact", "Contact", 160), ("phone", "Phone", 130),
            ("email", "Email", 200), ("address", "Address", 220), ("notes", "Notes", 200)],
            height=20, on_double=lambda r: self.edit())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.reload()

    def reload(self):
        self.table.set_rows(people.list_suppliers(self.db, self.search.get(), self.inactive.get()),
                            tag_fn=lambda r: None if r["active"] else "muted")

    def new(self):
        if ask_form(self, "New supplier", SUPPLIER_FIELDS,
                    on_submit=lambda v: people.save_supplier(self.db, v, user_id=self.app.user["id"])):
            self.reload()

    def edit(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, "Select a supplier first.", parent=self)
            return
        if ask_form(self, f"Edit — {row['name']}", SUPPLIER_FIELDS, row,
                    on_submit=lambda v: people.save_supplier(self.db, v, row["id"], self.app.user["id"])):
            self.reload()

    def new_po(self):
        row = self.table.selected()
        view = self.app.get_view("purchases")
        if view:
            self.app.show("purchases")
            view.new(row["id"] if row else None)
