"""List every English text that needs a translation.

Used by the tests to check that the Arabic catalogue is complete:
  * every _("literal") in the code, and
  * stored English values that are shown with tr_value() (statuses, methods, roles...).
"""
from __future__ import annotations

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def literal_keys() -> dict[str, str]:
    """{text: "file:line"} for every _("...") call with a literal argument."""
    found = {}
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "pos")):
        for name in files:
            if not name.endswith(".py") or name.startswith("locale_"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                        and node.args and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    found.setdefault(node.args[0].value, f"{os.path.relpath(path, ROOT)}:{node.lineno}")
    return found


def value_keys() -> list[str]:
    """Stored values that the interface translates for display."""
    from pos.services import auth, barcodes, operations, receipts, sales
    from pos.ui import app, history, products, purchases, repairs, reports

    values = list(auth.ROLES) + list(sales.BUILTIN_METHODS)
    values += ["Card", "Bank Transfer", "Mobile Wallet", "Cheque"]          # default payment methods
    values += ["completed", "partially_returned", "returned"]                # sale status
    values += ["in_stock", "sold", "defective"]                              # serial status
    values += ["open", "closed"]                                             # shift status
    values += list(purchases.PO_STATUSES) + list(operations.REPAIR_STATUSES)
    values += list(operations.EXPENSE_CATEGORIES) + list(products.ADJUST_REASONS)
    values += list(repairs.DEVICE_TYPES) + list(history.RETURN_REASONS)
    values += ["Sale", "Purchase received", "Opening stock", "Stock count", "Customer return"]
    values += list(reports.REPORTS) + list(barcodes.LABEL_FORMATS.values())
    values += list(receipts.RECEIPT_LANGUAGES.values()) + ["VAT", "Electronics POS", "Shop POS"]
    values += list(app.DAYS) + list(app.MONTHS)
    return list(dict.fromkeys(values))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ROOT)
    from pos import i18n
    i18n.set_language("en")
    keys = list(literal_keys()) + [v for v in value_keys() if v not in literal_keys()]
    for k in keys:
        print(repr(k))
    print(len(keys), "texts", file=sys.stderr)
