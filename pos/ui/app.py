"""Main window: login, sidebar navigation and status bar."""
from __future__ import annotations

import os
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import messagebox, ttk

from .. import APP_NAME, __version__, backup
from ..db import Database, POSError, app_data_dir
from ..services import auth, operations
from .widgets import COLORS, FONT_FAMILY, ask_form, setup_theme


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
        ttk.Label(bar, text=text or self.title, style="Title.TLabel").pack(side="left")
        for label, cmd, *style in reversed(buttons):
            ttk.Button(bar, text=label, command=cmd,
                       style=style[0] if style else "TButton").pack(side="right", padx=(6, 0))
        return bar

    @property
    def currency(self) -> str:
        return self.db.get_setting("currency_symbol", "$")


def _nav_items():
    # Imported lazily so a broken screen does not stop the app from starting.
    from . import (customers, dashboard, expenses, history, inventory, products, purchases,
                   repairs, reports, sales, settings, shifts, suppliers, users, warranty)
    return [
        ("dashboard", "🏠  Dashboard", dashboard.DashboardView),
        ("sales", "🛒  New Sale", sales.SalesView),
        ("history", "🧾  Sales & Returns", history.HistoryView),
        ("products", "📦  Products", products.ProductsView),
        ("inventory", "📊  Inventory", inventory.InventoryView),
        ("purchases", "🚚  Purchases", purchases.PurchasesView),
        ("customers", "👥  Customers", customers.CustomersView),
        ("suppliers", "🏭  Suppliers", suppliers.SuppliersView),
        ("repairs", "🔧  Repairs", repairs.RepairsView),
        ("warranty", "🛡  Warranty", warranty.WarrantyView),
        ("shifts", "💵  Cash Drawer", shifts.ShiftsView),
        ("expenses", "💸  Expenses", expenses.ExpensesView),
        ("reports", "📈  Reports", reports.ReportsView),
        ("users", "🔑  Users", users.UsersView),
        ("settings", "⚙  Settings", settings.SettingsView),
    ]


class App(tk.Tk):
    def __init__(self, db: Database | None = None):
        super().__init__()
        self.db = db or Database()
        auth.ensure_default_admin(self.db)
        self.user = None
        self.views: dict[str, View] = {}
        self.current = None
        self.title(f"{APP_NAME} — {self.db.get_setting('shop_name')}")
        self.geometry("1366x800")
        self.minsize(1100, 680)
        try:
            self.state("zoomed")  # maximised on Windows
        except tk.TclError:
            pass
        setup_theme(self)
        self.report_callback_exception = self.on_error
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.show_login()

    # ------------------------------------------------------------ error handling
    def on_error(self, exc_type, exc, tb):
        if isinstance(exc, POSError):
            messagebox.showwarning(APP_NAME, str(exc), parent=self.focus_get() or self)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(os.path.join(app_data_dir(), "error.log"), "a", encoding="utf-8") as fh:
                fh.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}")
        except OSError:
            pass
        messagebox.showerror(APP_NAME, f"Unexpected error: {exc}\n\nDetails were saved to error.log.")

    def on_close(self):
        if self.current == "sales" and self.views.get("sales") and self.views["sales"].cart.lines:
            if not messagebox.askyesno(APP_NAME, "There is an unfinished sale. Exit anyway?"):
                return
        try:
            backup.auto_backup(self.db)
        except Exception as exc:  # never block closing because of a backup problem
            messagebox.showwarning(APP_NAME, f"Automatic backup failed: {exc}")
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
        ttk.Label(card, text=self.db.get_setting("shop_name"), style="Panel.TLabel",
                  font=(FONT_FAMILY, 20, "bold")).pack()
        ttk.Label(card, text=f"{APP_NAME} v{__version__}", style="CardTitle.TLabel").pack(pady=(0, 20))
        user_var, pw_var = tk.StringVar(), tk.StringVar()
        ttk.Label(card, text="Username", style="Panel.TLabel").pack(anchor="w")
        e_user = ttk.Entry(card, textvariable=user_var, width=30, font=(FONT_FAMILY, 13))
        e_user.pack(fill="x", pady=(2, 10))
        ttk.Label(card, text="Password", style="Panel.TLabel").pack(anchor="w")
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

        ttk.Button(card, text="Sign in", style="Accent.TButton", command=do_login).pack(fill="x")
        msg.pack(pady=(10, 0))
        if self.db.scalar("SELECT must_change_password FROM users WHERE username='admin'"):
            ttk.Label(card, text="First time? Sign in with admin / admin",
                      style="CardTitle.TLabel").pack(pady=(8, 0))
        e_user.bind("<Return>", lambda e: e_pw.focus_set())
        e_pw.bind("<Return>", do_login)
        e_user.focus_set()

    def login(self, user):
        if user["must_change_password"]:
            res = ask_form(self, "Choose a new password", [
                {"key": "pw1", "label": "New password", "type": "password", "required": True},
                {"key": "pw2", "label": "Repeat password", "type": "password", "required": True},
            ], on_submit=self._check_new_password, ok_text="Change password")
            if not res:
                return
            auth.set_password(self.db, user["id"], res["pw1"], actor_id=user["id"])
            user = auth.get_user(self.db, user["id"])
        self.user = user
        self.build_main()

    @staticmethod
    def _check_new_password(values):
        if values["pw1"] != values["pw2"]:
            raise POSError("The passwords do not match.")
        if len(values["pw1"]) < 4:
            raise POSError("Password must be at least 4 characters.")

    def logout(self):
        if self.current == "sales" and self.views.get("sales") and self.views["sales"].cart.lines:
            if not messagebox.askyesno("Sign out", "The current cart will be lost. Sign out anyway?"):
                return
        self.db.log(self.user["id"], "logout", self.user["username"])
        self.show_login()

    # ------------------------------------------------------------- main layout
    def build_main(self):
        self.clear()
        side = tk.Frame(self.container, bg=COLORS["sidebar"], width=230)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="⚡ " + self.db.get_setting("shop_name"), bg=COLORS["sidebar"], fg="white",
                 font=(FONT_FAMILY, 13, "bold"), wraplength=200, justify="left").pack(
            anchor="w", padx=16, pady=(18, 4))
        tk.Label(side, text=f"{self.user['full_name']} · {self.user['role']}", bg=COLORS["sidebar"],
                 fg="#aab4d4", font=(FONT_FAMILY, 10)).pack(anchor="w", padx=16, pady=(0, 14))

        self.nav_buttons = {}
        self.view_classes = {}
        for key, label, cls in _nav_items():
            if not auth.has_permission(self.user, key):
                continue
            self.view_classes[key] = cls
            btn = tk.Label(side, text=label, bg=COLORS["sidebar"], fg="white", anchor="w",
                           font=(FONT_FAMILY, 12), padx=18, pady=7, cursor="hand2")
            btn.pack(fill="x")
            btn.bind("<Button-1>", lambda e, k=key: self.show(k))
            btn.bind("<Enter>", lambda e, b=btn, k=key: k != self.current and b.configure(
                bg=COLORS["sidebar_hover"]))
            btn.bind("<Leave>", lambda e, b=btn, k=key: k != self.current and b.configure(
                bg=COLORS["sidebar"]))
            self.nav_buttons[key] = btn
        tk.Frame(side, bg=COLORS["sidebar"]).pack(fill="both", expand=True)
        out = tk.Label(side, text="⏻  Sign out", bg=COLORS["sidebar"], fg="#ffab91", anchor="w",
                       font=(FONT_FAMILY, 12), padx=18, pady=10, cursor="hand2")
        out.pack(fill="x", pady=(0, 10))
        out.bind("<Button-1>", lambda e: self.logout())

        right = ttk.Frame(self.container)
        right.pack(side="left", fill="both", expand=True)
        # The status bar is packed before the content so tall screens can't push it out of view.
        status = tk.Frame(right, bg="#e3e7f0")
        status.pack(fill="x", side="bottom")
        self.content = ttk.Frame(right)
        self.content.pack(fill="both", expand=True)
        self.status_left = tk.Label(status, bg="#e3e7f0", anchor="w", font=(FONT_FAMILY, 10))
        self.status_left.pack(side="left", padx=10, pady=3)
        self.status_right = tk.Label(status, bg="#e3e7f0", anchor="e", font=(FONT_FAMILY, 10))
        self.status_right.pack(side="right", padx=10)
        self._tick()
        self.show("sales" if self.user["role"] == "cashier" else "dashboard")

    def _tick(self):
        if not self.user or not self.status_right.winfo_exists():
            return
        self.refresh_status()
        self.status_right.configure(text=datetime.now().strftime("%A %d %b %Y   %H:%M"))
        self.after(30_000, self._tick)

    def refresh_status(self):
        shift = operations.current_shift(self.db)
        shift_text = (f"Shift #{shift['id']} open since {shift['opened_at'][11:16]} ({shift['opened_by']})"
                      if shift else "No shift open")
        self.status_left.configure(text=f"👤 {self.user['username']} ({self.user['role']})    "
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
