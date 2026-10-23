"""Home screen with today's key figures."""
from __future__ import annotations

from tkinter import ttk

from ..db import today
from ..i18n import _, tr_value
from ..services import catalog, reports, sales
from .app import View
from .widgets import COLORS, START, W, DataTable, StatCard, fmt_money, pad


class DashboardView(View):
    title = _("Dashboard")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[(_("🛒 New sale"), lambda: app.show("sales"), "Accent.TButton"),
                             (_("↻ Refresh"), self.on_show)])
        cards = ttk.Frame(self)
        cards.pack(fill="x")
        self.cards = {}
        specs = [("net_sales", _("Today's net sales"), COLORS["accent"]),
                 ("transactions", _("Transactions"), None),
                 ("gross_profit", _("Gross profit"), COLORS["success"]),
                 ("avg_sale", _("Average sale"), None),
                 ("low_stock", _("Low stock items"), COLORS["danger"]),
                 ("open_repairs", _("Open repairs"), COLORS["warning"]),
                 ("receivables", _("Customer debts"), None)]
        show_profit = app.user["role"] != "cashier"
        for i, (key, title, color) in enumerate(specs):
            if key == "gross_profit" and not show_profit:
                continue
            card = StatCard(cards, title, color=color)
            card.pack(side=START, fill="x", expand=True, padx=pad(0 if i == 0 else 10, 0))
            self.cards[key] = card

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(16, 0))
        recent_box = ttk.LabelFrame(body, text=" " + _("Recent sales today") + " ", padding=8)
        recent_box.pack(side=START, fill="both", expand=True)
        self.recent = DataTable(recent_box, [
            ("invoice_no", _("Invoice"), 120), ("created_at", _("Time"), 80, lambda v: v[11:16]),
            ("customer_name", _("Customer"), 160), ("cashier", _("Cashier"), 90),
            ("total", _("Total"), -100, lambda v: f"{v:,.2f}"),
            ("status", _("Status"), 120, tr_value)], height=12)
        self.recent.pack(fill="both", expand=True)
        low_box = ttk.LabelFrame(body, text=" " + _("Low stock — reorder soon") + " ", padding=8)
        low_box.pack(side=START, fill="both", expand=True, padx=pad(16, 0))
        self.low = DataTable(low_box, [("sku", _("SKU"), 90), ("name", _("Product"), 220),
                                       ("stock_qty", _("Stock"), -60),
                                       ("reorder_level", _("Reorder at"), -90)], height=12)
        self.low.pack(fill="both", expand=True)
        self.ready = ttk.Label(self, text="", foreground=COLORS["success"], style="H2.TLabel")
        self.ready.pack(anchor=W, pady=(10, 0))

    def on_show(self):
        d = today()
        stats = reports.dashboard(self.db, d)
        sym = self.currency
        for key, card in self.cards.items():
            value = stats[key]
            card.set(fmt_money(value, sym) if isinstance(value, float) else str(value))
        self.recent.set_rows(sales.list_sales(self.db, d, d, limit=50))
        self.low.set_rows(catalog.low_stock(self.db)[:100],
                          tag_fn=lambda r: "warn" if r["stock_qty"] <= 0 else None)
        self.ready.configure(text=_("🔔 {count} repair(s) ready for pickup — call the customers.").format(
            count=stats["ready_repairs"]) if stats["ready_repairs"] else "")
