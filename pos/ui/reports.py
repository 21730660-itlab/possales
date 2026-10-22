"""Reports with CSV export."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from ..services import receipts, reports
from .app import View
from .widgets import MONO_FAMILY, DataTable, DateRangeBar, TextPreview, info

m = lambda v: f"{v:,.2f}" if isinstance(v, (int, float)) else (v or "")

# name -> (function, columns)
REPORTS = {
    "Daily sales": (reports.daily_sales, [
        ("day", "Day", 110), ("sales", "Sales", -70), ("units", "Units", -70), ("total", "Total", -110, m),
        ("tax", "Tax", -90, m), ("profit", "Profit", -110, m)]),
    "Top products": (reports.top_products, [
        ("sku", "SKU", 90), ("name", "Product", 280), ("units", "Units", -70),
        ("revenue", "Revenue (ex tax)", -130, m), ("profit", "Profit", -110, m)]),
    "Sales by category": (reports.sales_by_category, [
        ("category", "Category", 200), ("units", "Units", -70), ("revenue", "Revenue (ex tax)", -130, m),
        ("profit", "Profit", -110, m)]),
    "Sales by brand": (reports.sales_by_brand, [
        ("brand", "Brand", 200), ("units", "Units", -70), ("revenue", "Revenue (ex tax)", -130, m),
        ("profit", "Profit", -110, m)]),
    "Sales by cashier": (reports.sales_by_cashier, [
        ("cashier", "Cashier", 160), ("sales", "Sales", -70), ("total", "Total", -110, m),
        ("discounts", "Discounts given", -130, m)]),
    "Sales by hour": (reports.sales_by_hour, [
        ("hour", "Hour", 90), ("sales", "Sales", -70), ("total", "Total", -110, m)]),
    "Payments by method": (reports.payments_by_method, [
        ("method", "Method", 160), ("count", "Count", -70), ("amount", "Amount", -120, m)]),
    "Top customers": (reports.top_customers, [
        ("name", "Customer", 200), ("phone", "Phone", 120), ("sales", "Sales", -70),
        ("total", "Total", -110, m), ("points", "Points", -80), ("balance", "Owes", -100, m)]),
    "Expenses by category": (reports.expenses_report, [
        ("category", "Category", 200), ("count", "Count", -70), ("amount", "Amount", -120, m)]),
    "Customer debts (receivables)": (lambda db, d1, d2: reports.receivables(db), [
        ("name", "Customer", 220), ("phone", "Phone", 130), ("balance", "Owes", -110, m),
        ("credit_limit", "Credit limit", -110, m)]),
}


class ReportsView(View):
    title = "Reports"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[("Profit & loss statement", self.pnl, "Accent.TButton"),
                             ("Export CSV", self.export)])
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.range = DateRangeBar(bar, self.run, preset="This month")
        self.range.pack(side="left")
        ttk.Label(bar, text="   Report").pack(side="left")
        self.kind = tk.StringVar(value="Daily sales")
        cb = ttk.Combobox(bar, textvariable=self.kind, values=list(REPORTS), state="readonly", width=28)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.run())
        self.summary = tk.Text(self, height=4, font=(MONO_FAMILY, 11), relief="flat", bg="#ffffff")
        self.summary.pack(fill="x", pady=(0, 8))
        self.holder = ttk.Frame(self)
        self.holder.pack(fill="both", expand=True)
        self.table = None

    def on_show(self):
        self.run()

    def run(self):
        d1, d2 = self.range.range()
        fn, cols = REPORTS[self.kind.get()]
        if self.table:
            self.table.destroy()
        self.table = DataTable(self.holder, cols, height=18)
        self.table.pack(fill="both", expand=True)
        self.table.set_rows(fn(self.db, d1, d2), id_key=None)
        s = reports.sales_summary(self.db, d1, d2)
        sym = self.currency
        text = (f"{d1} → {d2}   Sales: {s['transactions']}   Units: {s['units']}   "
                f"Gross: {sym}{s['gross_sales']:,.2f}   Discounts: {sym}{s['discounts']:,.2f}   "
                f"Tax: {sym}{s['tax_collected']:,.2f}\n"
                f"Returns: {s['returns_count']} ({sym}{s['returns_total']:,.2f})   "
                f"NET SALES: {sym}{s['net_sales']:,.2f}   Avg sale: {sym}{s['avg_sale']:,.2f}\n"
                f"Revenue ex tax: {sym}{s['revenue_ex_tax']:,.2f}   Cost of goods: {sym}{s['cost_of_goods']:,.2f}"
                f"   GROSS PROFIT: {sym}{s['gross_profit']:,.2f}")
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.configure(state="disabled")

    def export(self):
        if not self.table:
            return
        name = self.kind.get().lower().replace(" ", "_").replace("(", "").replace(")", "")
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile=f"{name}.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if path:
            headers, rows = self.table.export_rows()
            reports.write_csv(path, headers, rows)
            info(self, "Export", f"Saved {len(rows)} rows to\n{path}")

    def pnl(self):
        d1, d2 = self.range.range()
        p = reports.profit_and_loss(self.db, d1, d2)
        settings = self.db.get_settings()
        f = lambda v: receipts.fmt(v, settings)
        r = receipts.Receipt(52)
        r.center(settings.get("shop_name", ""))
        r.center("PROFIT & LOSS")
        r.center(f"{d1} to {d2}")
        r.rule("=")
        r.pair("Sales (incl. tax)", f(p["sales_total"]))
        r.pair("Less returns", "-" + f(p["returns_total"]))
        r.pair("Net sales (incl. tax)", f(p["net_sales"]))
        r.pair("Tax collected", f(p["tax_collected"]))
        r.rule()
        r.pair("Revenue (excl. tax, net of returns)", f(p["revenue_ex_tax"]))
        r.pair("Cost of goods sold", "-" + f(p["cost_of_goods"]))
        r.pair("GROSS PROFIT", f(p["gross_profit"]))
        r.pair("Repair / service income", f(p["repair_income"]))
        r.rule()
        r.text("Expenses:")
        for row in p["expenses_by_category"]:
            r.pair(f"  {row['category']}", "-" + f(row["amount"]))
        r.pair("Total expenses", "-" + f(p["expenses"]))
        r.rule("=")
        r.pair("NET PROFIT", f(p["net_profit"]))
        if p["revenue_ex_tax"]:
            r.pair("Gross margin", f"{p['gross_profit'] * 100 / p['revenue_ex_tax']:.1f}%")
        text = r.render()
        TextPreview(self, "Profit & loss", text, width=56,
                    on_print=lambda: receipts.print_text(self.db, text, f"pnl_{d1}_{d2}")).show()
