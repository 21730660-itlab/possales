"""Reports with CSV export."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from ..i18n import _, plain, tr_value
from ..services import receipts, reports
from .app import View
from .widgets import MONO_FAMILY, RTL, START, DataTable, DateRangeBar, TextPreview, info

m = lambda v: f"{v:,.2f}" if isinstance(v, (int, float)) else (v or "")

# name -> (function, columns); the names are translated when shown.
REPORTS = {
    "Daily sales": (reports.daily_sales, [
        ("day", _("Day"), 110), ("sales", _("Sales"), -70), ("units", _("Units"), -70),
        ("total", _("Total"), -110, m), ("tax", _("Tax"), -90, m), ("profit", _("Profit"), -110, m)]),
    "Top products": (reports.top_products, [
        ("sku", _("SKU"), 90), ("name", _("Product"), 280), ("units", _("Units"), -70),
        ("revenue", _("Revenue (ex tax)"), -130, m), ("profit", _("Profit"), -110, m)]),
    "Sales by category": (reports.sales_by_category, [
        ("category", _("Category"), 200, tr_value), ("units", _("Units"), -70),
        ("revenue", _("Revenue (ex tax)"), -130, m), ("profit", _("Profit"), -110, m)]),
    "Sales by brand": (reports.sales_by_brand, [
        ("brand", _("Brand"), 200, tr_value), ("units", _("Units"), -70),
        ("revenue", _("Revenue (ex tax)"), -130, m), ("profit", _("Profit"), -110, m)]),
    "Sales by cashier": (reports.sales_by_cashier, [
        ("cashier", _("Cashier"), 160), ("sales", _("Sales"), -70), ("total", _("Total"), -110, m),
        ("discounts", _("Discounts given"), -130, m)]),
    "Sales by hour": (reports.sales_by_hour, [
        ("hour", _("Hour"), 90), ("sales", _("Sales"), -70), ("total", _("Total"), -110, m)]),
    "Payments by method": (reports.payments_by_method, [
        ("method", _("Method"), 160, tr_value), ("count", _("Count"), -70), ("amount", _("Amount"), -120, m)]),
    "Top customers": (reports.top_customers, [
        ("name", _("Customer"), 200), ("phone", _("Phone"), 120), ("sales", _("Sales"), -70),
        ("total", _("Total"), -110, m), ("points", _("Points"), -80), ("balance", _("Owes"), -100, m)]),
    "Expenses by category": (reports.expenses_report, [
        ("category", _("Category"), 200, tr_value), ("count", _("Count"), -70),
        ("amount", _("Amount"), -120, m)]),
    "Customer debts (receivables)": (lambda db, d1, d2: reports.receivables(db), [
        ("name", _("Customer"), 220), ("phone", _("Phone"), 130), ("balance", _("Owes"), -110, m),
        ("credit_limit", _("Credit limit"), -110, m)]),
}
REPORT_NAMES = {key: tr_value(key) for key in REPORTS}


class ReportsView(View):
    title = _("Reports")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header(buttons=[(_("Profit & loss statement"), self.pnl, "Accent.TButton"),
                             (_("Export CSV"), self.export)])
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.range = DateRangeBar(bar, self.run, preset="This month")
        self.range.pack(side=START)
        ttk.Label(bar, text="   " + _("Report")).pack(side=START)
        self.kind = tk.StringVar(value=REPORT_NAMES["Daily sales"])
        cb = ttk.Combobox(bar, textvariable=self.kind, values=list(REPORT_NAMES.values()), state="readonly",
                          width=28)
        cb.pack(side=START, padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.run())
        self.summary = tk.Text(self, height=4, font=(MONO_FAMILY, 11), relief="flat", bg="#ffffff")
        self.summary.tag_configure("dir", justify="right" if RTL else "left")
        self.summary.pack(fill="x", pady=(0, 8))
        self.holder = ttk.Frame(self)
        self.holder.pack(fill="both", expand=True)
        self.table = None

    def on_show(self):
        self.run()

    def report_key(self) -> str:
        return next((k for k, shown in REPORT_NAMES.items() if shown == self.kind.get()), "Daily sales")

    def run(self):
        d1, d2 = self.range.range()
        fn, cols = REPORTS[self.report_key()]
        if self.table:
            self.table.destroy()
        self.table = DataTable(self.holder, cols, height=18)
        self.table.pack(fill="both", expand=True)
        self.table.set_rows(fn(self.db, d1, d2), id_key=None)
        s = reports.sales_summary(self.db, d1, d2)
        sym = self.currency
        money_ = lambda v: f"{sym}{v:,.2f}"
        text = "\n".join([
            _("{d1} → {d2}   Sales: {n}   Units: {units}   Gross: {gross}   Discounts: {disc}   "
              "Tax: {tax}").format(d1=d1, d2=d2, n=s["transactions"], units=s["units"],
                                   gross=money_(s["gross_sales"]), disc=money_(s["discounts"]),
                                   tax=money_(s["tax_collected"])),
            _("Returns: {n} ({total})   NET SALES: {net}   Avg sale: {avg}").format(
                n=s["returns_count"], total=money_(s["returns_total"]), net=money_(s["net_sales"]),
                avg=money_(s["avg_sale"])),
            _("Revenue ex tax: {rev}   Cost of goods: {cost}   GROSS PROFIT: {profit}").format(
                rev=money_(s["revenue_ex_tax"]), cost=money_(s["cost_of_goods"]),
                profit=money_(s["gross_profit"]))])
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text, "dir")
        self.summary.configure(state="disabled")

    def export(self):
        if not self.table:
            return
        name = self.report_key().lower().replace(" ", "_").replace("(", "").replace(")", "")
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile=f"{name}.csv",
                                            filetypes=[(_("CSV files"), "*.csv")])
        if path:
            headers, rows = self.table.export_rows()
            reports.write_csv(path, [plain(h) for h in headers], rows)
            info(self, _("Export"), _("Saved {count} rows to\n{path}").format(count=len(rows), path=path))

    def pnl(self):
        t = lambda text: plain(_(text))  # no direction marks in printed documents
        d1, d2 = self.range.range()
        p = reports.profit_and_loss(self.db, d1, d2)
        settings = self.db.get_settings()
        f = lambda v: receipts.fmt(v, settings)
        r = receipts.Receipt(52)
        r.center(settings.get("shop_name", ""))
        r.center(t("PROFIT & LOSS"))
        r.center(t("{d1} to {d2}").format(d1=d1, d2=d2))
        r.rule("=")
        r.pair(t("Sales (incl. tax)"), f(p["sales_total"]))
        r.pair(t("Less returns"), "-" + f(p["returns_total"]))
        r.pair(t("Net sales (incl. tax)"), f(p["net_sales"]))
        r.pair(t("Tax collected"), f(p["tax_collected"]))
        r.rule()
        r.pair(t("Revenue (excl. tax, net of returns)"), f(p["revenue_ex_tax"]))
        r.pair(t("Cost of goods sold"), "-" + f(p["cost_of_goods"]))
        r.pair(t("GROSS PROFIT"), f(p["gross_profit"]))
        r.pair(t("Repair / service income"), f(p["repair_income"]))
        r.rule()
        r.text(t("Expenses:"))
        for row in p["expenses_by_category"]:
            r.pair(f"  {plain(tr_value(row['category']))}", "-" + f(row["amount"]))
        r.pair(t("Total expenses"), "-" + f(p["expenses"]))
        r.rule("=")
        r.pair(t("NET PROFIT"), f(p["net_profit"]))
        if p["revenue_ex_tax"]:
            r.pair(t("Gross margin"), f"{p['gross_profit'] * 100 / p['revenue_ex_tax']:.1f}%")
        text = r.render()
        TextPreview(self, _("Profit & loss"), text, width=56,
                    on_print=lambda: receipts.print_text(self.db, text, f"pnl_{d1}_{d2}")).show()
