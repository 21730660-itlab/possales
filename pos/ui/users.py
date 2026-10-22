"""User accounts and the audit log (admin only)."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..services import auth
from .app import View
from .widgets import DataTable, ask_form, toolbar

ROLE_HELP = ("admin: everything   ·   manager: everything except users & settings, can approve "
             "discounts/returns   ·   cashier: selling, customers, repairs, cash drawer")


class UsersView(View):
    title = "Users & Audit Log"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        ttk.Label(self, text=ROLE_HELP, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        users_tab = ttk.Frame(tabs, padding=8)
        toolbar(users_tab, [("+ New user", self.new, "Accent.TButton"), ("Edit", self.edit),
                            ("Reset password", self.reset)]).pack(fill="x", pady=(0, 8))
        self.table = DataTable(users_tab, [
            ("username", "Username", 140), ("full_name", "Full name", 200), ("role", "Role", 100),
            ("active", "Active", 70, lambda v: "Yes" if v else "No"), ("created_at", "Created", 160)],
            height=14, on_double=lambda r: self.edit())
        self.table.pack(fill="both", expand=True)
        tabs.add(users_tab, text="Users")
        self.audit = DataTable(tabs, [("created_at", "When", 160), ("username", "User", 100),
                                      ("action", "Action", 150), ("details", "Details", 500)], height=18)
        tabs.add(self.audit, text="Audit log (last 1000)")

    def on_show(self):
        self.table.set_rows(auth.list_users(self.db), tag_fn=lambda r: None if r["active"] else "muted")
        self.audit.set_rows(self.db.query(
            "SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
            "ORDER BY a.id DESC LIMIT 1000"))

    def new(self):
        def submit(v):
            auth.create_user(self.db, v["username"], v["password"], v["full_name"], v["role"],
                             v["must_change"], self.app.user["id"])
        if ask_form(self, "New user", [
                {"key": "username", "label": "Username", "required": True},
                {"key": "full_name", "label": "Full name"},
                {"key": "password", "label": "Password", "type": "password", "required": True},
                {"key": "role", "label": "Role", "type": "combo", "values": list(auth.ROLES),
                 "default": "cashier"},
                {"key": "must_change", "label": "Must change password at first login", "type": "check",
                 "default": True}], on_submit=submit):
            self.on_show()

    def edit(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, "Select a user first.", parent=self)
            return
        if ask_form(self, f"Edit — {row['username']}", [
                {"key": "full_name", "label": "Full name"},
                {"key": "role", "label": "Role", "type": "combo", "values": list(auth.ROLES)},
                {"key": "active", "label": "Active (can sign in)", "type": "check"}], row,
                on_submit=lambda v: auth.update_user(self.db, row["id"], v["full_name"], v["role"],
                                                     v["active"], self.app.user["id"])):
            self.on_show()

    def reset(self):
        row = self.table.selected()
        if not row:
            return
        res = ask_form(self, f"Reset password — {row['username']}", [
            {"key": "password", "label": "New password", "type": "password", "required": True},
            {"key": "must_change", "label": "Must change at next login", "type": "check", "default": True}])
        if res:
            auth.set_password(self.db, row["id"], res["password"], res["must_change"], self.app.user["id"])
            messagebox.showinfo(self.title, "Password changed.", parent=self)
