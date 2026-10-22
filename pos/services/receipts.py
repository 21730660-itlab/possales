"""Plain-text receipts / tickets / reports and printing on Windows.

Receipts are fixed-width text so they print well on 58/80 mm thermal printers.
Customer documents (sale receipt, return receipt, repair ticket) can be printed
in English, Arabic or both (setting `receipt_language`: en / ar / both).

Printing on Windows:
  * pywin32 installed + printer name set + plain English text -> sent RAW (ESC/POS),
    which also allows paper cut and the cash-drawer kick.
  * Text with Arabic (which ESC/POS code pages cannot shape) is printed through
    Windows ("printto" the configured printer), which shapes Arabic correctly.
  * Otherwise Windows' default "print" action for .txt files is used.
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

RECEIPT_LANGUAGES = {"en": "English", "ar": "Arabic / عربي", "both": "English + Arabic"}

ARABIC = {
    "Invoice": "فاتورة", "Date": "التاريخ", "Cashier": "الكاشير", "Customer": "الزبون",
    "Phone": "الهاتف", "Discount": "الخصم", "S/N": "الرقم التسلسلي", "Warranty until": "الكفالة حتى",
    "Subtotal": "المجموع الفرعي", "TOTAL": "المجموع", "Tax": "الضريبة", "Change": "الباقي",
    "Points earned": "النقاط المكتسبة", "Points balance": "رصيد النقاط",
    "Account balance": "رصيد الحساب", "Returned": "مرتجع", "Note": "ملاحظة", "COPY": "نسخة",
    "Tax ID": "الرقم الضريبي", "Qty": "الكمية",
    # payment methods
    "Cash": "نقداً", "Card": "بطاقة", "Bank Transfer": "تحويل مصرفي",
    "Mobile Wallet": "محفظة إلكترونية", "Cheque": "شيك", "Account": "على الحساب", "Points": "نقاط",
    # returns
    "RETURN / REFUND": "مرتجع / استرداد", "Return no": "رقم المرتجع",
    "Original invoice": "الفاتورة الأصلية", "REFUND TOTAL": "المبلغ المسترد",
    "Refund method": "طريقة الاسترداد", "Reason": "السبب", "Customer signature": "توقيع الزبون",
    # repairs
    "REPAIR TICKET": "إيصال تصليح", "Ticket": "رقم الإيصال", "Received": "تاريخ الاستلام",
    "Ready by": "جاهز بتاريخ", "Status": "الحالة", "Device": "الجهاز", "Model": "الطراز",
    "S/N / IMEI": "الرقم التسلسلي", "Issue": "العطل", "Accessories": "الملحقات",
    "Estimate": "الكلفة التقديرية", "Final cost": "الكلفة النهائية", "Paid": "المدفوع",
    "Balance due": "المبلغ المتبقي",
    "REPAIR_TERMS": "الأجهزة غير المستلمة خلال 90 يوماً قد يتم التخلص منها. "
                    "نحن غير مسؤولين عن فقدان البيانات.",
}
# Kept apart from ARABIC because the status "Received" clashes with the date label.
REPAIR_STATUS_AR = {
    "Received": "مستلم", "Diagnosing": "قيد الفحص", "Waiting for Parts": "بانتظار القطع",
    "In Progress": "قيد التصليح", "Ready for Pickup": "جاهز للاستلام", "Delivered": "تم التسليم",
    "Cancelled": "ملغى",
}
REPAIR_TERMS_EN = ("Devices not collected within 90 days may be disposed of. "
                   "We are not responsible for data loss.")


class Receipt:
    def __init__(self, width: int = 42, lang: str = "en"):
        self.width = max(30, width)
        self.lang = lang if lang in RECEIPT_LANGUAGES else "en"
        self.lines: list[str] = []

    def t(self, label: str, table: dict = ARABIC) -> str:
        """Translate a label according to the receipt language."""
        arabic = table.get(label)
        if self.lang == "en" or not arabic:
            return label
        if self.lang == "ar":
            return arabic
        return f"{label} {arabic}"

    def center(self, text: str = ""):
        for part in str(text).splitlines() or [""]:
            self.lines.append(part.strip()[:self.width].center(self.width).rstrip())

    def text(self, text: str = ""):
        for part in str(text).splitlines() or [""]:
            while len(part) > self.width:
                cut = part.rfind(" ", 0, self.width)
                cut = cut if cut > self.width // 2 else self.width
                self.lines.append(part[:cut].rstrip())
                part = part[cut:].lstrip()
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


def new_receipt(settings: dict, customer_facing: bool = True) -> Receipt:
    lang = settings.get("receipt_language", "en") if customer_facing else "en"
    return Receipt(int(setting_float(settings, "receipt_width", 42)), lang)


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
    english = r.lang in ("en", "both") or not settings.get("shop_name_ar")
    arabic = r.lang in ("ar", "both")
    if english:
        r.center(settings.get("shop_name", ""))
    if arabic and settings.get("shop_name_ar"):
        r.center(settings["shop_name_ar"])
    if english or not settings.get("shop_address_ar"):
        if settings.get("shop_address"):
            r.center(settings["shop_address"])
    if arabic and settings.get("shop_address_ar"):
        r.center(settings["shop_address_ar"])
    for key in ("shop_phone", "shop_email"):
        if settings.get(key):
            r.center(settings[key])
    if settings.get("tax_id"):
        r.center(f"{r.t('Tax ID')}: {settings['tax_id']}")
    r.rule("=")


def _footer(r: Receipt, settings: dict):
    if r.lang in ("en", "both") or not settings.get("receipt_footer_ar"):
        r.center(settings.get("receipt_footer", ""))
    if r.lang in ("ar", "both") and settings.get("receipt_footer_ar"):
        r.center(settings["receipt_footer_ar"])


def sale_receipt(db: Database, sale_id: int, copy: bool = False) -> str:
    settings = db.get_settings()
    data = sales.get_sale(db, sale_id)
    sale = data["sale"]
    r = new_receipt(settings)
    t = r.t
    _header(r, settings)
    if copy:
        r.center(f"*** {t('COPY')} ***")
    r.pair(t("Invoice"), sale["invoice_no"])
    r.pair(t("Date"), sale["created_at"])
    r.pair(t("Cashier"), sale["cashier"])
    if sale["customer_name"]:
        r.pair(t("Customer"), sale["customer_name"])
        if sale["customer_phone"]:
            r.pair(t("Phone"), sale["customer_phone"])
    r.rule()
    for item in data["items"]:
        r.text(item["name"])
        r.pair(f"  {item['qty']} x {money(item['unit_price']):,.2f}",
               f"{money(item['qty'] * item['unit_price']):,.2f}")
        if item["discount"]:
            r.pair(f"  {t('Discount')}", f"-{money(item['discount']):,.2f}")
        if item["serial_no"]:
            r.text(f"  {t('S/N')}: {item['serial_no']}")
        if item["warranty_until"]:
            r.text(f"  {t('Warranty until')}: {item['warranty_until']}")
    r.rule()
    r.pair(t("Subtotal"), fmt(sale["subtotal"], settings))
    if sale["discount_total"]:
        r.pair(t("Discount"), "-" + fmt(sale["discount_total"], settings))
    tax_name = settings.get("tax_name", "Tax")
    if r.lang != "en":
        tax_name = f"{tax_name} {ARABIC['Tax']}" if r.lang == "both" else ARABIC["Tax"]
    r.pair(f"{tax_name} ({setting_float(settings, 'tax_rate'):g}%)", fmt(sale["tax_total"], settings))
    r.rule("=")
    r.pair(t("TOTAL"), fmt(sale["total"], settings))
    alt = secondary(sale["total"], settings)
    if alt:
        r.pair("", alt)
    r.rule()
    for p in data["payments"]:
        label = t(p["method"]) + (f" ({p['reference']})" if p["reference"] else "")
        amount = p["amount"] + (sale["change_due"] if p["method"] == "Cash" else 0)
        r.pair(label, fmt(amount, settings))
    if sale["change_due"]:
        r.pair(t("Change"), fmt(sale["change_due"], settings))
        alt = secondary(sale["change_due"], settings)
        if alt:
            r.pair("", alt)
    if sale["customer_name"]:
        r.rule()
        if sale["points_earned"]:
            r.pair(t("Points earned"), str(sale["points_earned"]))
        r.pair(t("Points balance"), str(sale["customer_points"]))
        if sale["customer_balance"] and abs(sale["customer_balance"]) > 0.004:
            r.pair(t("Account balance"), fmt(sale["customer_balance"], settings))
    if sale["notes"]:
        r.rule()
        r.text(f"{t('Note')}: {sale['notes']}")
    if data["returns"]:
        r.rule()
        for ret in data["returns"]:
            r.pair(f"{t('Returned')} {ret['return_no']}", "-" + fmt(ret["total"], settings))
    r.rule()
    _footer(r, settings)
    r.text("")
    return r.render()


def return_receipt(db: Database, return_id: int) -> str:
    settings = db.get_settings()
    data = sales.get_return(db, return_id)
    ret = data["return"]
    r = new_receipt(settings)
    t = r.t
    _header(r, settings)
    r.center(t("RETURN / REFUND"))
    r.pair(t("Return no"), ret["return_no"])
    r.pair(t("Original invoice"), ret["invoice_no"])
    r.pair(t("Date"), ret["created_at"])
    r.pair(t("Cashier"), ret["cashier"])
    if ret["customer_name"]:
        r.pair(t("Customer"), ret["customer_name"])
    r.rule()
    for item in data["items"]:
        r.text(item["name"])
        r.pair(f"  {t('Qty')} {item['qty']}", fmt(item["amount"], settings))
        if item["serial_no"]:
            r.text(f"  {t('S/N')}: {item['serial_no']}")
    r.rule()
    r.pair(t("REFUND TOTAL"), fmt(ret["total"], settings))
    r.pair(t("Refund method"), t(ret["refund_method"]))
    if ret["reason"]:
        r.text(f"{t('Reason')}: {ret['reason']}")
    r.text("")
    r.text(f"{t('Customer signature')}: ________________")
    r.text("")
    return r.render()


def z_report(db: Database, shift_id: int) -> str:
    settings = db.get_settings()
    s = operations.shift_summary(db, shift_id)
    shift = s["shift"]
    r = new_receipt(settings, customer_facing=False)
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
    r = new_receipt(settings)
    t = r.t
    _header(r, settings)
    r.center(t("REPAIR TICKET"))
    r.pair(t("Ticket"), rep["ticket_no"])
    r.pair(t("Received"), rep["received_at"])
    if rep["due_date"]:
        r.pair(t("Ready by"), rep["due_date"])
    r.pair(t("Status"), t(rep["status"], REPAIR_STATUS_AR))
    r.rule()
    r.pair(t("Customer"), rep["customer_name"] or "-")
    if rep["customer_phone"]:
        r.pair(t("Phone"), rep["customer_phone"])
    r.pair(t("Device"), rep["device"])
    if rep["brand_model"]:
        r.pair(t("Model"), rep["brand_model"])
    if rep["serial_no"]:
        r.pair(t("S/N / IMEI"), rep["serial_no"])
    r.text(f"{t('Issue')}: {rep['issue']}")
    if rep["accessories"]:
        r.text(f"{t('Accessories')}: {rep['accessories']}")
    r.rule()
    r.pair(t("Estimate"), fmt(rep["estimate"], settings))
    if rep["final_cost"] != rep["estimate"]:
        r.pair(t("Final cost"), fmt(rep["final_cost"], settings))
    r.pair(t("Paid"), fmt(rep["paid"], settings))
    r.pair(t("Balance due"), fmt(rep["final_cost"] - rep["paid"], settings))
    r.rule()
    if r.lang in ("en", "both"):
        r.text(REPAIR_TERMS_EN)
    if r.lang in ("ar", "both"):
        r.text(ARABIC["REPAIR_TERMS"])
    r.text("")
    r.text(f"{t('Customer signature')}: ________________")
    r.text("")
    return r.render()


# ---------------------------------------------------------------------- printing
def save_text(text: str, name: str) -> str:
    folder = os.path.join(app_data_dir(), "receipts")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}.txt")
    # A UTF-8 BOM makes Notepad (used by Windows to print .txt files) read Arabic correctly.
    with open(path, "w", encoding="utf-8-sig") as fh:
        fh.write(text)
    return path


def is_plain(text: str) -> bool:
    """True if the text can be printed by an ESC/POS printer's built-in code page."""
    try:
        text.encode("cp437")
        return True
    except UnicodeEncodeError:
        return False


def print_text(db: Database, text: str, name: str, open_drawer: bool = False) -> str:
    """Save the text and send it to the printer. Returns the saved file path."""
    path = save_text(text, name)
    printer = db.get_setting("printer_name").strip()
    if sys.platform.startswith("win"):
        if printer and is_plain(text):
            data = ESC_INIT + text.encode("cp437") + b"\n\n\n" + ESC_CUT
            if open_drawer:
                data += ESC_DRAWER
            if send_raw(printer, data):
                return path
        if not (printer and _shell_print_to(path, printer)):
            os.startfile(path, "print")  # type: ignore[attr-defined]  # default printer
        if open_drawer:
            open_cash_drawer(db)
    elif printer:
        subprocess.run(["lp", "-d", printer, path], check=False)
    else:
        subprocess.run(["lp", path], check=False)
    return path


def open_cash_drawer(db: Database) -> bool:
    printer = db.get_setting("printer_name").strip()
    if sys.platform.startswith("win") and printer:
        return send_raw(printer, ESC_INIT + ESC_DRAWER)
    return False


def _shell_print_to(path: str, printer: str) -> bool:
    try:
        import win32api  # type: ignore  # optional: pip install pywin32
    except ImportError:
        return False
    win32api.ShellExecute(0, "printto", path, f'"{printer}"', ".", 0)
    return True


def send_raw(printer: str, data: bytes) -> bool:
    """Send bytes straight to a Windows printer (needs pywin32). False if unavailable."""
    try:
        import win32print  # type: ignore  # optional: pip install pywin32
    except ImportError:
        return False
    handle = win32print.OpenPrinter(printer)
    try:
        win32print.StartDocPrinter(handle, 1, ("POS document", None, "RAW"))
        win32print.StartPagePrinter(handle)
        win32print.WritePrinter(handle, data)
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
    return True
