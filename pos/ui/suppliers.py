"""Supplier management."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..i18n import _
from ..services import people
from .app import View
from .widgets import START, DataTable, SearchBar, ask_form, toolbar


def supplier_fields():
    return [
        {"key": "name", "label": _("Company name"), "required": True},
        {"key": "contact", "label": _("Contact person")},
        {"key": "phone", "label": _("Phone")},
        {"key": "email", "label": _("Email")},
        {"key": "address", "label": _("Address")},
        {"key": "notes", "label": _("Notes"), "type": "multiline", "height": 3},
        {"key": "active", "label": _("Active"), "type": "check", "default": True},
    ]


class SuppliersView(View):
    title = _("Suppliers")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search = SearchBar(bar, self.reload, _("name, contact, phone"), width=34)
        self.search.pack(side=START)
        self.inactive = tk.BooleanVar()
        ttk.Checkbutton(bar, text=_("Show inactive"), variable=self.inactive, command=self.reload).pack(
            side=START, padx=10)
        toolbar(self, [(_("+ New supplier"), self.new, "Accent.TButton"), (_("Edit"), self.edit),
                       (_("New purchase order"), self.new_po)]).pack(fill="x", pady=(0, 8))
        self.table = DataTable(self, [
            ("name", _("Name"), 220), ("contact", _("Contact"), 160), ("phone", _("Phone"), 130),
            ("email", _("Email"), 200), ("address", _("Address"), 220), ("notes", _("Notes"), 200)],
            height=20, on_double=lambda r: self.edit())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        self.reload()

    def reload(self):
        self.table.set_rows(people.list_suppliers(self.db, self.search.get(), self.inactive.get()),
                            tag_fn=lambda r: None if r["active"] else "muted")

    def new(self):
        if ask_form(self, _("New supplier"), supplier_fields(),
                    on_submit=lambda v: people.save_supplier(self.db, v, user_id=self.app.user["id"])):
            self.reload()

    def edit(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, _("Select a supplier first."), parent=self)
            return
        if ask_form(self, _("Edit — {name}").format(name=row["name"]), supplier_fields(), row,
                    on_submit=lambda v: people.save_supplier(self.db, v, row["id"], self.app.user["id"])):
            self.reload()

    def new_po(self):
        row = self.table.selected()
        view = self.app.get_view("purchases")
        if view:
            self.app.show("purchases")
            view.new(row["id"] if row else None)
