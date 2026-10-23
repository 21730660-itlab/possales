"""Main window: login, sidebar navigation and status bar."""
from __future__ import annotations

import os
import sys
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import messagebox, ttk

from .. import APP_NAME, __version__, backup
from ..db import Database, POSError, app_data_dir
from ..i18n import _, language, tr_value
from ..services import auth, operations
from .widgets import COLORS, END, FONT_FAMILY, JUSTIFY, START, W, ask_form, pad, setup_theme

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def app_title() -> str:
    return _(APP_NAME)


def shop_name(db) -> str:
    """The shop name to show: the Arabic one when the interface is Arabic and it is set."""
    return (language() == "ar" and db.get_setting("shop_name_ar")) or db.get_setting("shop_name")


def long_date(dt: datetime) -> str:
    return f"{_(DAYS[dt.weekday()])} {dt.day} {_(MONTHS[dt.month - 1])} {dt.year}   {dt:%H:%M}"


class View(ttk.Frame):
    """Base class for every screen shown in the content area."""
    title = ""

    def __init__(self, parent, app: "App"):
        super().__init__(parent, padding=16)
        self.app = app
        self.db = app.db

    def on_show(self):
        """Called every time the screen becomes visible."""

    def header(self, text=None, buttons=()):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 12))
        ttk.Label(bar, text=text or self.title, style="Title.TLabel").pack(side=START)
        for label, cmd, *style in reversed(buttons):
            ttk.Button(bar, text=label, command=cmd,
                       style=style[0] if style else "TButton").pack(side=END, padx=pad(6, 0))
        return bar

    @property
    def currency(self) -> str:
        return self.db.get_setting("currency_symbol", "$")


def _nav_items():
    # Imported lazily so a broken screen does not stop the app from starting.
    from . import (customers, dashboard, expenses, history, inventory, products, purchases,
                   repairs, reports, sales, settings, shifts, suppliers, users, warranty)
    return [
        ("dashboard", "🏠  " + _("Dashboard"), dashboard.DashboardView),
        ("sales", "🛒  " + _("New Sale"), sales.SalesView),
        ("history", "🧾  " + _("Sales & Returns"), history.HistoryView),
        ("products", "📦  " + _("Products"), products.ProductsView),
        ("inventory", "📊  " + _("Inventory"), inventory.InventoryView),
        ("purchases", "🚚  " + _("Purchases"), purchases.PurchasesView),
        ("customers", "👥  " + _("Customers"), customers.CustomersView),
        ("suppliers", "🏭  " + _("Suppliers"), suppliers.SuppliersView),
        ("repairs", "🔧  " + _("Repairs"), repairs.RepairsView),
        ("warranty", "🛡  " + _("Warranty"), warranty.WarrantyView),
        ("shifts", "💵  " + _("Cash Drawer"), shifts.ShiftsView),
        ("expenses", "💸  " + _("Expenses"), expenses.ExpensesView),
        ("reports", "📈  " + _("Reports"), reports.ReportsView),
        ("users", "🔑  " + _("Users"), users.UsersView),
        ("settings", "⚙  " + _("Settings"), settings.SettingsView),
    ]


class App(tk.Tk):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.db = db or Database()
        auth.ensure_default_admin(self.db)
        self.user = None
        self.views: dict[str, View] = {}
        self.current = None
        self.title(f"{app_title()} — {shop_name(self.db)}")
        self.geometry("1366x800")
        self.minsize(1100, 680)
        try:
            self.state("zoomed")  # maximised on Windows
        except tk.TclError:
            pass
        setup_theme(self)
        self._set_icon()
        self.report_callback_exception = self.on_error
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.show_login()

    def _set_icon(self):
        # Inside a PyInstaller build, bundled files live in sys._MEIPASS.
        root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))))
        icon = os.path.join(root, "assets", "pos.ico")
        if sys.platform.startswith("win") and os.path.exists(icon):
            try:
                self.iconbitmap(default=icon)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ error handling
    def on_error(self, exc_type, exc, tb):
        if isinstance(exc, POSError):
            messagebox.showwarning(app_title(), str(exc), parent=self.focus_get() or self)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(os.path.join(app_data_dir(), "error.log"), "a", encoding="utf-8") as fh:
                fh.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}")
        except OSError:
            pass
        messagebox.showerror(app_title(), _("Unexpected error: {error}\n\nDetails were saved to "
                                            "error.log.").format(error=exc))

    def on_close(self):
        if self.current == "sales" and self.views.get("sales") and self.views["sales"].cart.lines:
            if not messagebox.askyesno(app_title(), _("There is an unfinished sale. Exit anyway?")):
                return
        try:
            backup.auto_backup(self.db)
        except Exception as exc:  # never block closing because of a backup problem
            messagebox.showwarning(app_title(), _("Automatic backup failed: {error}").format(error=exc))
        self.db.close()
        self.destroy()

    # ------------------------------------------------------------------ login
    def clear(self):
        for w in self.container.winfo_children():
            w.destroy()
        self.views.clear()
        self.current = None

    def show_login(self):
        self.clear()
        self.user = None
        outer = tk.Frame(self.container, bg=COLORS["sidebar"])
        outer.pack(fill="both", expand=True)
        card = ttk.Frame(outer, style="Panel.TFrame", padding=36)
        card.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(card, text="⚡", style="Panel.TLabel", font=(FONT_FAMILY, 40)).pack()
        ttk.Label(card, text=shop_name(self.db), style="Panel.TLabel",
                  font=(FONT_FAMILY, 20, "bold")).pack()
        ttk.Label(card, text=f"{app_title()}  v{__version__}", style="CardTitle.TLabel").pack(pady=(0, 20))
        user_var, pw_var = tk.StringVar(), tk.StringVar()
        ttk.Label(card, text=_("Username"), style="Panel.TLabel").pack(anchor=W)
        e_user = ttk.Entry(card, textvariable=user_var, width=30, font=(FONT_FAMILY, 13))
        e_user.pack(fill="x", pady=(2, 10))
        ttk.Label(card, text=_("Password"), style="Panel.TLabel").pack(anchor=W)
        e_pw = ttk.Entry(card, textvariable=pw_var, show="•", width=30, font=(FONT_FAMILY, 13))
        e_pw.pack(fill="x", pady=(2, 16))
        msg = ttk.Label(card, text="", style="Panel.TLabel", foreground=COLORS["danger"])

        def do_login(event=None):
            try:
                user = auth.authenticate(self.db, user_var.get(), pw_var.get())
            except POSError as exc:
                msg.configure(text=str(exc))
                pw_var.set("")
                e_pw.focus_set()
                return
            self.login(user)

        ttk.Button(card, text=_("Sign in"), style="Accent.TButton", command=do_login).pack(fill="x")
        msg.pack(pady=(10, 0))
        if self.db.scalar("SELECT must_change_password FROM users WHERE username='admin'"):
            ttk.Label(card, text=_("First time? Sign in with admin / admin"),
                      style="CardTitle.TLabel").pack(pady=(8, 0))
        e_user.bind("<Return>", lambda e: e_pw.focus_set())
        e_pw.bind("<Return>", do_login)
        e_user.focus_set()

    def login(self, user):
        if user["must_change_password"]:
            res = ask_form(self, _("Choose a new password"), [
                {"key": "pw1", "label": _("New password"), "type": "password", "required": True},
                {"key": "pw2", "label": _("Repeat password"), "type": "password", "required": True},
            ], on_submit=self._check_new_password, ok_text=_("Change password"))
            if not res:
                return
            auth.set_password(self.db, user["id"], res["pw1"], actor_id=user["id"])
            user = auth.get_user(self.db, user["id"])
        self.user = user
        self.build_main()

    @staticmethod
    def _check_new_password(values):
        if values["pw1"] != values["pw2"]:
            raise POSError(_("The passwords do not match."))
        if len(values["pw1"]) < 4:
            raise POSError(_("Password must be at least 4 characters."))

    def logout(self):
        if self.current == "sales" and self.views.get("sales") and self.views["sales"].cart.lines:
            if not messagebox.askyesno(_("Sign out"), _("The current cart will be lost. Sign out anyway?")):
                return
        self.db.log(self.user["id"], "logout", self.user["username"])
        self.show_login()

    # ------------------------------------------------------------- main layout
    def build_main(self):
        self.clear()
        side = tk.Frame(self.container, bg=COLORS["sidebar"], width=230)
        side.pack(side=START, fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="⚡ " + shop_name(self.db), bg=COLORS["sidebar"], fg="white",
                 font=(FONT_FAMILY, 13, "bold"), wraplength=200, justify=JUSTIFY).pack(
            anchor=W, padx=16, pady=(18, 4))
        tk.Label(side, text=f"{self.user['full_name']} · {tr_value(self.user['role'])}",
                 bg=COLORS["sidebar"], fg="#aab4d4", font=(FONT_FAMILY, 10)).pack(
            anchor=W, padx=16, pady=(0, 14))

        self.nav_buttons = {}
        self.view_classes = {}
        for key, label, cls in _nav_items():
            if not auth.has_permission(self.user, key):
                continue
            self.view_classes[key] = cls
            btn = tk.Label(side, text=label, bg=COLORS["sidebar"], fg="white", anchor=W,
                           font=(FONT_FAMILY, 12), padx=18, pady=7, cursor="hand2")
            btn.pack(fill="x")
            btn.bind("<Button-1>", lambda e, k=key: self.show(k))
            btn.bind("<Enter>", lambda e, b=btn, k=key: k != self.current and b.configure(
                bg=COLORS["sidebar_hover"]))
            btn.bind("<Leave>", lambda e, b=btn, k=key: k != self.current and b.configure(
                bg=COLORS["sidebar"]))
            self.nav_buttons[key] = btn
        tk.Frame(side, bg=COLORS["sidebar"]).pack(fill="both", expand=True)
        out = tk.Label(side, text="⏻  " + _("Sign out"), bg=COLORS["sidebar"], fg="#ffab91", anchor=W,
                       font=(FONT_FAMILY, 12), padx=18, pady=10, cursor="hand2")
        out.pack(fill="x", pady=(0, 10))
        out.bind("<Button-1>", lambda e: self.logout())

        right = ttk.Frame(self.container)
        right.pack(side=START, fill="both", expand=True)
        # The status bar is packed before the content so tall screens can't push it out of view.
        status = tk.Frame(right, bg="#e3e7f0")
        status.pack(fill="x", side="bottom")
        self.content = ttk.Frame(right)
        self.content.pack(fill="both", expand=True)
        self.status_left = tk.Label(status, bg="#e3e7f0", anchor=W, font=(FONT_FAMILY, 10))
        self.status_left.pack(side=START, padx=10, pady=3)
        self.status_right = tk.Label(status, bg="#e3e7f0", font=(FONT_FAMILY, 10))
        self.status_right.pack(side=END, padx=10)
        self._tick()
        self.show("sales" if self.user["role"] == "cashier" else "dashboard")

    def _tick(self):
        if not self.user or not self.status_right.winfo_exists():
            return
        self.refresh_status()
        self.status_right.configure(text=long_date(datetime.now()))
        self.after(30_000, self._tick)

    def refresh_status(self):
        shift = operations.current_shift(self.db)
        if shift:
            shift_text = _("Shift #{id} open since {time} ({name})").format(
                id=shift["id"], time=shift["opened_at"][11:16], name=shift["opened_by"])
        else:
            shift_text = _("No shift open")
        self.status_left.configure(text=f"👤 {self.user['username']} ({tr_value(self.user['role'])})    "
                                        f"💵 {shift_text}    🗄 {self.db.path}")

    def show(self, key: str):
        if key not in self.view_classes:
            return
        if self.current and self.current in self.views:
            self.views[self.current].pack_forget()
            self.nav_buttons[self.current].configure(bg=COLORS["sidebar"])
        if key not in self.views:
            self.views[key] = self.view_classes[key](self.content, self)
        view = self.views[key]
        view.pack(fill="both", expand=True)
        self.nav_buttons[key].configure(bg=COLORS["sidebar_active"])
        self.current = key
        view.on_show()
        self.refresh_status()

    def get_view(self, key: str):
        if key not in self.views and key in self.view_classes:
            self.views[key] = self.view_classes[key](self.content, self)
        return self.views.get(key)

    def current_shift_id(self):
        shift = operations.current_shift(self.db)
        return shift["id"] if shift else None
