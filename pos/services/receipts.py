"""Plain-text receipts / tickets / reports and printing on Windows.

Receipts are fixed-width text so they print well on 58/80 mm thermal printers.
If `pywin32` is installed and a printer name is configured, text is sent RAW
(ESC/POS) to that printer, which also allows paper cut and cash-drawer kick.
Otherwise Windows' default "print" action for .txt files is used.
"""
from __future__ import annotations

import os
import subprocess
import sys

from ..db import Database, app_data_dir, money, setting_bool, setting_float
from . import operations, sales

ESC_INIT = b"\x1b@"
ESC_CUT = b"\x1dV\x41\x10"
ESC_DRAWER = b"\x1bp\x00\x19\xfa"


class Receipt:
    def __init__(self, width: int = 42):
        self.width = max(30, width)
        self.lines: list[str] = []

    def center(self, text: str = ""):
        for part in str(text).splitlines() or [""]:
            self.lines.append(part.strip()[:self.width].center(self.width).rstrip())

    def text(self, text: str = ""):
        for part in str(text).splitlines() or [""]:
            while len(part) > self.width:
                self.lines.append(part[:self.width])
                part = part[self.width:]
            self.lines.append(part)

    def pair(self, left: str, right: str = ""):
        left, right = str(left), str(right)
        space = self.width - len(right) - 1
        if len(left) > space:
            self.text(left)
            left = ""
        self.lines.append(f"{left:<{space}} {right}"[:self.width])

    def rule(self, char: str = "-"):
        self.lines.append(char * self.width)

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"


def fmt(amount, settings: dict) -> str:
    amount = money(amount)
    sign = "-" if amount < 0 else ""
    return f"{sign}{settings.get('currency_symbol', '$')}{abs(amount):,.2f}"


def secondary(amount, settings: dict) -> str | None:
    if not setting_bool(settings, "show_secondary_currency"):
        return None
    rate = setting_float(settings, "exchange_rate")
    if rate <= 0:
        return None
    return f"{settings.get('secondary_currency', '')} {amount * rate:,.0f}"


def _header(r: Receipt, settings: dict):
    r.center(settings.get("shop_name", ""))
    for key in ("shop_address", "shop_phone", "shop_email"):
        if settings.get(key):
            r.center(settings[key])
    if settings.get("tax_id"):
        r.center(f"Tax ID: {settings['tax_id']}")
    r.rule("=")


def sale_receipt(db: Database, sale_id: int, copy: bool = False) -> str:
    settings = db.get_settings()
    data = sales.get_sale(db, sale_id)
    sale = data["sale"]
    r = Receipt(int(setting_float(settings, "receipt_width", 42)))
    _header(r, settings)
    if copy:
        r.center("*** COPY ***")
    r.pair("Invoice:", sale["invoice_no"])
    r.pair("Date:", sale["created_at"])
    r.pair("Cashier:", sale["cashier"])
    if sale["customer_name"]:
        r.pair("Customer:", sale["customer_name"])
        if sale["customer_phone"]:
            r.pair("Phone:", sale["customer_phone"])
    r.rule()
    for item in data["items"]:
        r.text(item["name"])
        r.pair(f"  {item['qty']} x {money(item['unit_price']):,.2f}",
               f"{money(item['qty'] * item['unit_price']):,.2f}")
        if item["discount"]:
            r.pair("  Discount", f"-{money(item['discount']):,.2f}")
        if item["serial_no"]:
            r.text(f"  S/N: {item['serial_no']}")
        if item["warranty_until"]:
            r.text(f"  Warranty until: {item['warranty_until']}")
    r.rule()
    r.pair("Subtotal", fmt(sale["subtotal"], settings))
    if sale["discount_total"]:
        r.pair("Discount", "-" + fmt(sale["discount_total"], settings))
    tax_label = f"{settings.get('tax_name', 'Tax')} ({setting_float(settings, 'tax_rate'):g}%)"
    r.pair(tax_label, fmt(sale["tax_total"], settings))
    r.rule("=")
    r.pair("TOTAL", fmt(sale["total"], settings))
    alt = secondary(sale["total"], settings)
    if alt:
        r.pair("", alt)
    r.rule()
    for p in data["payments"]:
        label = p["method"] + (f" ({p['reference']})" if p["reference"] else "")
        amount = p["amount"] + (sale["change_due"] if p["method"] == "Cash" else 0)
        r.pair(label, fmt(amount, settings))
    if sale["change_due"]:
        r.pair("Change", fmt(sale["change_due"], settings))
        alt = secondary(sale["change_due"], settings)
        if alt:
            r.pair("", alt)
    if sale["customer_name"]:
        r.rule()
        if sale["points_earned"]:
            r.pair("Points earned", str(sale["points_earned"]))
        r.pair("Points balance", str(sale["customer_points"]))
        if sale["customer_balance"] and abs(sale["customer_balance"]) > 0.004:
            r.pair("Account balance", fmt(sale["customer_balance"], settings))
    if sale["notes"]:
        r.rule()
        r.text(f"Note: {sale['notes']}")
    if data["returns"]:
        r.rule()
        for ret in data["returns"]:
            r.pair(f"Returned {ret['return_no']}", "-" + fmt(ret["total"], settings))
    r.rule()
    r.center(settings.get("receipt_footer", ""))
    r.text("")
    return r.render()


def return_receipt(db: Database, return_id: int) -> str:
    settings = db.get_settings()
    data = sales.get_return(db, return_id)
    ret = data["return"]
    r = Receipt(int(setting_float(settings, "receipt_width", 42)))
    _header(r, settings)
    r.center("RETURN / REFUND")
    r.pair("Return no:", ret["return_no"])
    r.pair("Original invoice:", ret["invoice_no"])
    r.pair("Date:", ret["created_at"])
    r.pair("Cashier:", ret["cashier"])
    if ret["customer_name"]:
        r.pair("Customer:", ret["customer_name"])
    r.rule()
    for item in data["items"]:
        r.text(item["name"])
        r.pair(f"  Qty {item['qty']}", fmt(item["amount"], settings))
        if item["serial_no"]:
            r.text(f"  S/N: {item['serial_no']}")
    r.rule()
    r.pair("REFUND TOTAL", fmt(ret["total"], settings))
    r.pair("Refund method", ret["refund_method"])
    if ret["reason"]:
        r.text(f"Reason: {ret['reason']}")
    r.text("")
    r.text("Customer signature: ____________________")
    r.text("")
    return r.render()


def z_report(db: Database, shift_id: int) -> str:
    settings = db.get_settings()
    s = operations.shift_summary(db, shift_id)
    shift = s["shift"]
    r = Receipt(int(setting_float(settings, "receipt_width", 42)))
    _header(r, settings)
    r.center("SHIFT REPORT (Z)" if shift["status"] == "closed" else "SHIFT REPORT (X)")
    r.pair("Shift #", str(shift["id"]))
    r.pair("Opened by", shift["opened_by"])
    r.pair("Opened", shift["opened_at"])
    if shift["closed_at"]:
        r.pair("Closed", shift["closed_at"])
        r.pair("Closed by", shift["closed_by_name"] or "")
    r.rule()
    r.pair("Sales", str(s["sales_count"]))
    r.pair("Sales total", fmt(s["sales_total"], settings))
    r.pair("Discounts", fmt(s["discounts"], settings))
    r.pair("Tax", fmt(s["tax_total"], settings))
    r.rule()
    r.text("Payments:")
    for row in s["by_method"]:
        r.pair(f"  {row['method']}", fmt(row["amount"], settings))
    if s["refunds"]:
        r.text("Refunds:")
        for row in s["refunds"]:
            r.pair(f"  {row['method']} ({row['n']})", "-" + fmt(row["amount"], settings))
    r.rule()
    r.text("Cash drawer:")
    r.pair("  Opening float", fmt(shift["opening_cash"], settings))
    r.pair("  + Cash sales", fmt(s["cash_sales"], settings))
    r.pair("  - Cash refunds", fmt(s["cash_refunds"], settings))
    r.pair("  + Cash in", fmt(s["cash_in"], settings))
    r.pair("  - Cash out", fmt(s["cash_out"], settings))
    r.pair("  + Account payments", fmt(s["account_payments"], settings))
    r.pair("  + Repair payments", fmt(s["repair_payments"], settings))
    r.pair("  - Expenses", fmt(s["drawer_expenses"], settings))
    r.rule()
    r.pair("EXPECTED CASH", fmt(s["expected_cash"], settings))
    if shift["counted_cash"] is not None:
        r.pair("COUNTED CASH", fmt(shift["counted_cash"], settings))
        diff = money(shift["counted_cash"] - s["expected_cash"])
        r.pair("OVER / SHORT", ("+" if diff > 0 else "") + fmt(diff, settings))
    if shift["notes"]:
        r.text(f"Notes: {shift['notes']}")
    r.text("")
    return r.render()


def repair_ticket(db: Database, repair_id: int) -> str:
    settings = db.get_settings()
    rep = operations.get_repair(db, repair_id)
    r = Receipt(int(setting_float(settings, "receipt_width", 42)))
    _header(r, settings)
    r.center("REPAIR TICKET")
    r.pair("Ticket:", rep["ticket_no"])
    r.pair("Received:", rep["received_at"])
    if rep["due_date"]:
        r.pair("Ready by:", rep["due_date"])
    r.pair("Status:", rep["status"])
    r.rule()
    r.pair("Customer:", rep["customer_name"] or "-")
    if rep["customer_phone"]:
        r.pair("Phone:", rep["customer_phone"])
    r.pair("Device:", rep["device"])
    if rep["brand_model"]:
        r.pair("Model:", rep["brand_model"])
    if rep["serial_no"]:
        r.pair("S/N / IMEI:", rep["serial_no"])
    r.text(f"Issue: {rep['issue']}")
    if rep["accessories"]:
        r.text(f"Accessories: {rep['accessories']}")
    r.rule()
    r.pair("Estimate", fmt(rep["estimate"], settings))
    if rep["final_cost"] != rep["estimate"]:
        r.pair("Final cost", fmt(rep["final_cost"], settings))
    r.pair("Paid", fmt(rep["paid"], settings))
    r.pair("Balance due", fmt(rep["final_cost"] - rep["paid"], settings))
    r.rule()
    r.text("Devices not collected within 90 days may be disposed of. "
           "We are not responsible for data loss.")
    r.text("")
    r.text("Customer signature: ____________________")
    r.text("")
    return r.render()


# ---------------------------------------------------------------------- printing
def save_text(text: str, name: str) -> str:
    folder = os.path.join(app_data_dir(), "receipts")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def print_text(db: Database, text: str, name: str, open_drawer: bool = False) -> str:
    """Save the text and send it to the printer. Returns the saved file path."""
    path = save_text(text, name)
    settings = db.get_settings()
    printer = settings.get("printer_name", "").strip()
    if sys.platform.startswith("win"):
        if printer and _print_raw_windows(printer, text, open_drawer):
            return path
        os.startfile(path, "print")  # type: ignore[attr-defined]  # default printer
    elif printer:
        subprocess.run(["lp", "-d", printer, path], check=False)
    else:
        subprocess.run(["lp", path], check=False)
    return path


def open_cash_drawer(db: Database) -> bool:
    printer = db.get_setting("printer_name").strip()
    if sys.platform.startswith("win") and printer:
        return _send_raw_windows(printer, ESC_INIT + ESC_DRAWER)
    return False


def _print_raw_windows(printer: str, text: str, open_drawer: bool) -> bool:
    data = ESC_INIT + text.encode("cp437", errors="replace") + b"\n\n\n" + ESC_CUT
    if open_drawer:
        data += ESC_DRAWER
    return _send_raw_windows(printer, data)


def _send_raw_windows(printer: str, data: bytes) -> bool:
    try:
        import win32print  # type: ignore  # optional: pip install pywin32
    except ImportError:
        return False
    handle = win32print.OpenPrinter(printer)
    try:
        win32print.StartDocPrinter(handle, 1, ("POS Receipt", None, "RAW"))
        win32print.StartPagePrinter(handle)
        win32print.WritePrinter(handle, data)
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
    return True
