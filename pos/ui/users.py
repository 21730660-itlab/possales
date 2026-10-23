"""User accounts and the audit log (admin only)."""
from __future__ import annotations

from tkinter import messagebox, ttk

from ..i18n import _, tr_value
from ..services import auth
from .app import View
from .widgets import JUSTIFY, W, DataTable, add_tabs, ask_form, toolbar

ROLE_HELP = _("admin: everything   ·   manager: everything except users & settings, can approve "
              "discounts/returns   ·   cashier: selling, customers, repairs, cash drawer")


def role_choices():
    return [(r, tr_value(r)) for r in auth.ROLES]


class UsersView(View):
    title = _("Users & Audit Log")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        ttk.Label(self, text=ROLE_HELP, style="Muted.TLabel", justify=JUSTIFY, wraplength=1000).pack(
            anchor=W, pady=(0, 8))
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        users_tab = ttk.Frame(tabs, padding=8)
        toolbar(users_tab, [(_("+ New user"), self.new, "Accent.TButton"), (_("Edit"), self.edit),
                            (_("Reset password"), self.reset)]).pack(fill="x", pady=(0, 8))
        self.table = DataTable(users_tab, [
            ("username", _("Username"), 140), ("full_name", _("Full name"), 200),
            ("role", _("Role"), 100, tr_value),
            ("active", _("Active"), 70, lambda v: _("Yes") if v else _("No")),
            ("created_at", _("Created"), 160)], height=14, on_double=lambda r: self.edit())
        self.table.pack(fill="both", expand=True)
        self.audit = DataTable(tabs, [("created_at", _("When"), 160), ("username", _("User"), 100),
                                      ("action", _("Action"), 150), ("details", _("Details"), 500)], height=18)
        add_tabs(tabs, [(users_tab, _("Users")), (self.audit, _("Audit log (last 1000)"))])

    def on_show(self):
        self.table.set_rows(auth.list_users(self.db), tag_fn=lambda r: None if r["active"] else "muted")
        self.audit.set_rows(self.db.query(
            "SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
            "ORDER BY a.id DESC LIMIT 1000"))

    def new(self):
        def submit(v):
            auth.create_user(self.db, v["username"], v["password"], v["full_name"], v["role"],
                             v["must_change"], self.app.user["id"])
        if ask_form(self, _("New user"), [
                {"key": "username", "label": _("Username"), "required": True},
                {"key": "full_name", "label": _("Full name")},
                {"key": "password", "label": _("Password"), "type": "password", "required": True},
                {"key": "role", "label": _("Role"), "type": "combo", "choices": role_choices(),
                 "default": "cashier"},
                {"key": "must_change", "label": _("Must change password at first login"), "type": "check",
                 "default": True}], on_submit=submit):
            self.on_show()

    def edit(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, _("Select a user first."), parent=self)
            return
        if ask_form(self, _("Edit — {name}").format(name=row["username"]), [
                {"key": "full_name", "label": _("Full name")},
                {"key": "role", "label": _("Role"), "type": "combo", "choices": role_choices()},
                {"key": "active", "label": _("Active (can sign in)"), "type": "check"}], row,
                on_submit=lambda v: auth.update_user(self.db, row["id"], v["full_name"], v["role"],
                                                     v["active"], self.app.user["id"])):
            self.on_show()

    def reset(self):
        row = self.table.selected()
        if not row:
            return
        res = ask_form(self, _("Reset password — {name}").format(name=row["username"]), [
            {"key": "password", "label": _("New password"), "type": "password", "required": True},
            {"key": "must_change", "label": _("Must change at next login"), "type": "check", "default": True}])
        if res:
            auth.set_password(self.db, row["id"], res["password"], res["must_change"], self.app.user["id"])
            messagebox.showinfo(self.title, _("Password changed."), parent=self)
