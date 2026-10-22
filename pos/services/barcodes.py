"""Code 128 barcodes and product label printing.

Labels can be produced as:
  * html_roll  - one label per page, for label printers installed as a Windows printer
  * html_sheet - a grid of labels on A4 paper
  * zpl        - raw commands for Zebra (and compatible) label printers
  * tspl       - raw commands for TSC / Xprinter (and compatible) label printers
HTML labels open in the web browser for printing and support Arabic product names.
"""
from __future__ import annotations

import html
import os
import sys
import webbrowser

from ..db import Database, POSError, app_data_dir, setting_bool, setting_float

LABEL_FORMATS = {
    "html_roll": "Label printer (one label per page, via browser)",
    "html_sheet": "A4 sheet of labels (via browser)",
    "zpl": "Zebra / ZPL label printer (direct)",
    "tspl": "TSC / Xprinter / TSPL label printer (direct)",
}

# Bar/space widths for Code 128 symbol values 0..106 (106 = stop).
PATTERNS = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split()
START_B, START_C, CODE_B, STOP = 104, 105, 100, 106


def code128_values(text: str) -> list[int]:
    """Symbol values (start, data, checksum, stop). Digit runs use the compact set C."""
    if not text:
        raise POSError("Nothing to encode.")
    if any(not 32 <= ord(ch) <= 126 for ch in text):
        raise POSError(f"Barcode '{text}' may only contain English letters, digits and symbols.")
    if text.isdigit() and len(text) >= 4:
        even = len(text) - len(text) % 2
        values = [START_C] + [int(text[i:i + 2]) for i in range(0, even, 2)]
        if len(text) % 2:
            values += [CODE_B, ord(text[-1]) - 32]
    else:
        values = [START_B] + [ord(ch) - 32 for ch in text]
    checksum = (values[0] + sum(i * v for i, v in enumerate(values[1:], start=1))) % 103
    return values + [checksum, STOP]


def code128_modules(text: str) -> str:
    """The barcode as a string of '1' (bar) and '0' (space) modules, with quiet zones."""
    out = []
    for value in code128_values(text):
        for i, width in enumerate(PATTERNS[value]):
            out.append(("1" if i % 2 == 0 else "0") * int(width))
    quiet = "0" * 10
    return quiet + "".join(out) + quiet


def barcode_svg(text: str, height: float = 40, module: float = 1.0) -> str:
    modules = code128_modules(text)
    rects, x = [], 0
    while x < len(modules):
        if modules[x] == "1":
            run = 1
            while x + run < len(modules) and modules[x + run] == "1":
                run += 1
            rects.append(f'<rect x="{x * module:g}" y="0" width="{run * module:g}" height="{height:g}"/>')
            x += run
        else:
            x += 1
    width = len(modules) * module
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
            f'preserveAspectRatio="none" class="bc">{"".join(rects)}</svg>')


def ean13_check_digit(first12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


# ------------------------------------------------------------------ labels
def label_items(db: Database, product_copies: dict[int, int]) -> list[dict]:
    items = []
    for pid, copies in product_copies.items():
        if copies <= 0:
            continue
        p = db.one("SELECT * FROM products WHERE id = ?", (pid,))
        if not p:
            continue
        code = p["barcode"] or p["sku"]
        code128_values(code)  # validate before printing anything
        items.append({"name": p["name"], "code": code, "price": p["sell_price"], "copies": int(copies)})
    if not items:
        raise POSError("Choose at least one label to print.")
    return items


def _label_settings(settings: dict) -> dict:
    return {
        "width": setting_float(settings, "label_width_mm", 50) or 50,
        "height": setting_float(settings, "label_height_mm", 25) or 25,
        "show_price": setting_bool(settings, "label_show_price"),
        "show_shop": setting_bool(settings, "label_show_shop"),
        "symbol": settings.get("currency_symbol", "$"),
        "shop": settings.get("shop_name", ""),
    }


def labels_html(items: list[dict], settings: dict, sheet: bool) -> str:
    s = _label_settings(settings)
    w, h = s["width"], s["height"]
    cells = []
    for item in items:
        price = f'<div class="price">{html.escape(s["symbol"])}{item["price"]:,.2f}</div>' if s["show_price"] else ""
        shop = f'<div class="shop">{html.escape(s["shop"])}</div>' if s["show_shop"] else ""
        cell = (f'<div class="label">{shop}<div class="name" dir="auto">{html.escape(item["name"])}</div>'
                f'{barcode_svg(item["code"])}<div class="code">{html.escape(item["code"])}</div>{price}</div>')
        cells += [cell] * item["copies"]
    if sheet:
        page = "@page { size: A4; margin: 8mm; }"
        layout = (f".grid {{ display: flex; flex-wrap: wrap; gap: 2mm; }} "
                  f".label {{ border: 0.2mm dashed #bbb; }}")
    else:
        page = f"@page {{ size: {w:g}mm {h:g}mm; margin: 0; }}"
        layout = ".label { page-break-after: always; break-after: page; }"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Labels</title><style>
{page}
body {{ margin: 0; font-family: Arial, Tahoma, sans-serif; }}
{layout}
.label {{ width: {w:g}mm; height: {h:g}mm; box-sizing: border-box; padding: 1mm 2mm; overflow: hidden;
          display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.shop {{ font-size: 2.2mm; color: #444; }}
.name {{ font-size: 2.8mm; font-weight: bold; text-align: center; white-space: nowrap; overflow: hidden;
         max-width: 100%; }}
.bc {{ width: 100%; height: {h * 0.38:.1f}mm; }}
.code {{ font-size: 2.4mm; letter-spacing: 0.3mm; }}
.price {{ font-size: 3.8mm; font-weight: bold; }}
@media screen {{ body {{ background: #eee; padding: 10px; }} .label {{ background: #fff; margin: 4px; }}
                 .hint {{ font: 14px Arial; margin-bottom: 8px; }} }}
@media print {{ .hint {{ display: none; }} }}
</style></head><body><div class="hint">Press <b>Ctrl+P</b> to print. Set margins to "None" and scale to 100%.</div>
<div class="grid">{"".join(cells)}</div></body></html>"""


def _dots(mm: float, dpi: int = 203) -> int:
    return int(round(mm * dpi / 25.4))


def _latin(text: str) -> str:
    """Direct label printers need plain ASCII; other characters are dropped."""
    return "".join(ch for ch in text if 32 <= ord(ch) <= 126).strip() or "?"


def labels_zpl(items: list[dict], settings: dict) -> str:
    s = _label_settings(settings)
    w = _dots(s["width"])
    out = []
    for item in items:
        name = _latin(item["name"])[:32].replace("^", " ").replace("~", " ")
        parts = [f"^XA^PW{w}^LL{_dots(s['height'])}^CI0",
                 f"^FO10,8^A0N,22,22^FB{w - 20},1,0,C^FD{name}^FS",
                 f"^FO20,36^BY2^BCN,{_dots(s['height'] * 0.38)},Y,N,N^FD{item['code']}^FS"]
        if s["show_price"]:
            parts.append(f"^FO10,{_dots(s['height']) - 34}^A0N,28,28^FB{w - 20},1,0,C^FD"
                         f"{_latin(s['symbol'])}{item['price']:,.2f}^FS")
        parts.append(f"^PQ{item['copies']}^XZ")
        out.append("".join(parts))
    return "\n".join(out) + "\n"


def labels_tspl(items: list[dict], settings: dict) -> str:
    s = _label_settings(settings)
    out = []
    for item in items:
        name = _latin(item["name"])[:30].replace('"', "'")
        out += [f"SIZE {s['width']:g} mm,{s['height']:g} mm", "GAP 2 mm,0", "DIRECTION 1", "CLS",
                f'TEXT 10,8,"2",0,1,1,"{name}"',
                f'BARCODE 10,36,"128",{_dots(s["height"] * 0.38)},1,0,2,2,"{item["code"]}"']
        if s["show_price"]:
            out.append(f'TEXT 10,{_dots(s["height"]) - 34},"3",0,1,1,'
                       f'"{_latin(s["symbol"])}{item["price"]:,.2f}"')
        out.append(f"PRINT 1,{item['copies']}")
    return "\r\n".join(out) + "\r\n"


def print_labels(db: Database, product_copies: dict[int, int]) -> str:
    """Produce labels in the configured format. Returns a message for the user."""
    from . import receipts  # local import: receipts imports this module's siblings

    settings = db.get_settings()
    items = label_items(db, product_copies)
    fmt = settings.get("label_format", "html_roll")
    folder = os.path.join(app_data_dir(), "labels")
    os.makedirs(folder, exist_ok=True)
    count = sum(i["copies"] for i in items)
    if fmt in ("zpl", "tspl"):
        data = labels_zpl(items, settings) if fmt == "zpl" else labels_tspl(items, settings)
        path = os.path.join(folder, f"labels.{fmt}")
        with open(path, "w", encoding="ascii", newline="") as fh:
            fh.write(data)
        printer = settings.get("label_printer_name", "").strip()
        if printer and sys.platform.startswith("win") and receipts.send_raw(printer, data.encode("ascii")):
            return f"Sent {count} label(s) to {printer}."
        return (f"Saved {count} label(s) as {fmt.upper()} commands to\n{path}\n\n"
                "To print directly, install pywin32 and set the label printer name in Settings.")
    path = os.path.join(folder, "labels.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(labels_html(items, settings, sheet=fmt == "html_sheet"))
    webbrowser.open("file://" + os.path.abspath(path).replace("\\", "/"))
    return f"{count} label(s) opened in your web browser. Press Ctrl+P there to print."
