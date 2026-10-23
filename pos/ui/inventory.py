"""Inventory overview: movements, low stock, valuation and slow movers."""
from __future__ import annotations

from tkinter import filedialog, ttk

from ..i18n import _, tr_reason
from ..services import catalog, reports
from .app import View
from .widgets import START, DataTable, StatCard, add_tabs, fmt_money, info, pad


class InventoryView(View):
    title = _("Inventory")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[(_("Export current tab"), self.export), (_("↻ Refresh"), self.on_show)])
        cards = ttk.Frame(self)
        cards.pack(fill="x", pady=(0, 12))
        self.c_units = StatCard(cards, _("Units in stock"))
        self.c_cost = StatCard(cards, _("Stock value (cost)"))
        self.c_retail = StatCard(cards, _("Stock value (retail)"))
        self.c_low = StatCard(cards, _("Low / out of stock"))
        for i, c in enumerate((self.c_units, self.c_cost, self.c_retail, self.c_low)):
            c.pack(side=START, fill="x", expand=True, padx=pad(0 if i == 0 else 10, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        money_fmt = lambda v: f"{v:,.2f}" if v is not None else ""
        self.low = DataTable(self.tabs, [
            ("sku", _("SKU"), 90), ("name", _("Product"), 260), ("supplier", _("Supplier"), 150),
            ("stock_qty", _("Stock"), -70), ("reorder_level", _("Reorder at"), -90),
            ("cost_price", _("Cost"), -90, money_fmt)])
        self.moves = DataTable(self.tabs, [
            ("created_at", _("Date"), 160), ("sku", _("SKU"), 90), ("product", _("Product"), 240),
            ("change", _("Change"), -70), ("balance", _("Balance"), -75),
            ("reason", _("Reason"), 200, tr_reason), ("ref", _("Reference"), 120), ("user", _("User"), 90)])
        self.value = DataTable(self.tabs, [
            ("sku", _("SKU"), 90), ("name", _("Product"), 260), ("category", _("Category"), 120),
            ("stock_qty", _("Stock"), -70), ("cost_price", _("Cost"), -85, money_fmt),
            ("sell_price", _("Price"), -85, money_fmt), ("cost_value", _("Cost value"), -105, money_fmt),
            ("retail_value", _("Retail value"), -110, money_fmt)])
        self.slow = DataTable(self.tabs, [
            ("sku", _("SKU"), 90), ("name", _("Product"), 260), ("stock_qty", _("Stock"), -70),
            ("cost_value", _("Money tied up"), -120, money_fmt), ("last_sold", _("Last sold"), 160)])
        add_tabs(self.tabs, [(self.low, _("Low stock / reorder")), (self.moves, _("Stock movements")),
                             (self.value, _("Stock valuation")), (self.slow, _("Slow movers (60 days)"))])

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
                                            filetypes=[(_("CSV files"), "*.csv")])
        if path:
            headers, rows = table.export_rows()
            reports.write_csv(path, headers, rows)
            info(self, _("Export"), _("Saved {count} rows to\n{path}").format(count=len(rows), path=path))
