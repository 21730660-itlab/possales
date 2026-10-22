"""Inventory overview: movements, low stock, valuation and slow movers."""
from __future__ import annotations

from tkinter import filedialog, ttk

from ..services import catalog, reports
from .app import View
from .widgets import DataTable, StatCard, fmt_money, info


class InventoryView(View):
    title = "Inventory"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[("Export current tab", self.export), ("↻ Refresh", self.on_show)])
        cards = ttk.Frame(self)
        cards.pack(fill="x", pady=(0, 12))
        self.c_units = StatCard(cards, "Units in stock")
        self.c_cost = StatCard(cards, "Stock value (cost)")
        self.c_retail = StatCard(cards, "Stock value (retail)")
        self.c_low = StatCard(cards, "Low / out of stock")
        for i, c in enumerate((self.c_units, self.c_cost, self.c_retail, self.c_low)):
            c.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 10, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        money_fmt = lambda v: f"{v:,.2f}" if v is not None else ""
        self.low = DataTable(self.tabs, [
            ("sku", "SKU", 90), ("name", "Product", 260), ("supplier", "Supplier", 150),
            ("stock_qty", "Stock", -70), ("reorder_level", "Reorder at", -90),
            ("cost_price", "Cost", -90, money_fmt)])
        self.moves = DataTable(self.tabs, [
            ("created_at", "Date", 160), ("sku", "SKU", 90), ("product", "Product", 240),
            ("change", "Change", -70), ("balance", "Balance", -75), ("reason", "Reason", 200),
            ("ref", "Reference", 120), ("user", "User", 90)])
        self.value = DataTable(self.tabs, [
            ("sku", "SKU", 90), ("name", "Product", 260), ("category", "Category", 120),
            ("stock_qty", "Stock", -70), ("cost_price", "Cost", -85, money_fmt),
            ("sell_price", "Price", -85, money_fmt), ("cost_value", "Cost value", -105, money_fmt),
            ("retail_value", "Retail value", -110, money_fmt)])
        self.slow = DataTable(self.tabs, [
            ("sku", "SKU", 90), ("name", "Product", 260), ("stock_qty", "Stock", -70),
            ("cost_value", "Money tied up", -120, money_fmt), ("last_sold", "Last sold", 160)])
        self.tabs.add(self.low, text="Low stock / reorder")
        self.tabs.add(self.moves, text="Stock movements")
        self.tabs.add(self.value, text="Stock valuation")
        self.tabs.add(self.slow, text="Slow movers (60 days)")

    def on_show(self):
        low = catalog.low_stock(self.db)
        self.low.set_rows(low, tag_fn=lambda r: "warn" if r["stock_qty"] <= 0 else None)
        self.moves.set_rows(catalog.stock_movements(self.db, limit=2000),
                            tag_fn=lambda r: "warn" if r["change"] < 0 else "ok")
        rows, totals = reports.inventory_valuation(self.db)
        self.value.set_rows(rows, id_key=None)
        self.slow.set_rows(reports.slow_movers(self.db), id_key=None)
        sym = self.currency
        self.c_units.set(f"{totals['units']:,}")
        self.c_cost.set(fmt_money(totals["cost_value"], sym))
        self.c_retail.set(fmt_money(totals["retail_value"], sym))
        self.c_low.set(str(len(low)))

    def export(self):
        table = self.tabs.nametowidget(self.tabs.select())
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile="inventory.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if path:
            headers, rows = table.export_rows()
            reports.write_csv(path, headers, rows)
            info(self, "Export", f"Saved {len(rows)} rows to\n{path}")
