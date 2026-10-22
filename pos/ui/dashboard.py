"""Home screen with today's key figures."""
from __future__ import annotations

from tkinter import ttk

from ..db import today
from ..services import catalog, reports, sales
from .app import View
from .widgets import COLORS, DataTable, StatCard, fmt_money


class DashboardView(View):
    title = "Dashboard"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[("🛒 New sale", lambda: app.show("sales"), "Accent.TButton"),
                             ("↻ Refresh", self.on_show)])
        cards = ttk.Frame(self)
        cards.pack(fill="x")
        self.cards = {}
        specs = [("net_sales", "Today's net sales", COLORS["accent"]),
                 ("transactions", "Transactions", None),
                 ("gross_profit", "Gross profit", COLORS["success"]),
                 ("avg_sale", "Average sale", None),
                 ("low_stock", "Low stock items", COLORS["danger"]),
                 ("open_repairs", "Open repairs", COLORS["warning"]),
                 ("receivables", "Customer debts", None)]
        show_profit = app.user["role"] != "cashier"
        for i, (key, title, color) in enumerate(specs):
            if key == "gross_profit" and not show_profit:
                continue
            card = StatCard(cards, title, color=color)
            card.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 10, 0))
            self.cards[key] = card

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(16, 0))
        left = ttk.LabelFrame(body, text=" Recent sales today ", padding=8)
        left.pack(side="left", fill="both", expand=True)
        self.recent = DataTable(left, [
            ("invoice_no", "Invoice", 120), ("created_at", "Time", 80, lambda v: v[11:16]),
            ("customer_name", "Customer", 160), ("cashier", "Cashier", 90),
            ("total", "Total", -100, lambda v: f"{v:,.2f}"), ("status", "Status", 120)], height=12)
        self.recent.pack(fill="both", expand=True)
        right = ttk.LabelFrame(body, text=" Low stock — reorder soon ", padding=8)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self.low = DataTable(right, [("sku", "SKU", 90), ("name", "Product", 220),
                                     ("stock_qty", "Stock", -60), ("reorder_level", "Reorder at", -90)],
                             height=12)
        self.low.pack(fill="both", expand=True)
        self.ready = ttk.Label(self, text="", foreground=COLORS["success"], style="H2.TLabel")
        self.ready.pack(anchor="w", pady=(10, 0))

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
        self.ready.configure(text=f"🔔 {stats['ready_repairs']} repair(s) ready for pickup — call the customers."
                             if stats["ready_repairs"] else "")
