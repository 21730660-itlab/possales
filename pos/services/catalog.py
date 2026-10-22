"""Products, categories, brands, serial numbers and stock movements."""
from __future__ import annotations

import csv

from ..db import Database, POSError, money, now
from .barcodes import ean13_check_digit

LOOKUP_TABLES = ("categories", "brands")

PRODUCT_CSV_FIELDS = [
    "sku", "barcode", "name", "description", "category", "brand", "cost_price",
    "sell_price", "stock_qty", "reorder_level", "warranty_months", "track_serial",
    "tax_exempt", "location", "active",
]


# ------------------------------------------------------------ categories/brands
def list_lookup(db: Database, table: str):
    _check_lookup(table)
    return db.query(f"SELECT * FROM {table} ORDER BY name")


def get_or_create_lookup(db: Database, table: str, name: str) -> int | None:
    _check_lookup(table)
    name = (name or "").strip()
    if not name:
        return None
    row = db.one(f"SELECT id FROM {table} WHERE name = ?", (name,))
    if row:
        return row["id"]
    return db.insert(table, {"name": name})


def rename_lookup(db: Database, table: str, row_id: int, name: str):
    _check_lookup(table)
    name = name.strip()
    if not name:
        raise POSError("Name is required.")
    clash = db.one(f"SELECT id FROM {table} WHERE name = ? AND id != ?", (name, row_id))
    if clash:
        raise POSError(f"'{name}' already exists.")
    db.update(table, row_id, {"name": name})


def delete_lookup(db: Database, table: str, row_id: int):
    _check_lookup(table)
    db.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))


def _check_lookup(table: str):
    if table not in LOOKUP_TABLES:
        raise ValueError(table)


# --------------------------------------------------------------------- products
PRODUCT_SELECT = """
SELECT p.*, c.name AS category, b.name AS brand, s.name AS supplier
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN suppliers s ON s.id = p.supplier_id
"""


def list_products(db: Database, search: str = "", category_id: int | None = None,
                  include_inactive: bool = False, low_stock_only: bool = False, limit: int = 1000):
    where, params = [], []
    if not include_inactive:
        where.append("p.active = 1")
    if search:
        like = f"%{search.strip()}%"
        where.append("(p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ? OR b.name LIKE ? "
                     "OR p.description LIKE ?)")
        params += [like] * 5
    if category_id:
        where.append("p.category_id = ?")
        params.append(category_id)
    if low_stock_only:
        where.append("p.stock_qty <= p.reorder_level")
    sql = PRODUCT_SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY p.name LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


def get_product(db: Database, product_id: int):
    row = db.one(PRODUCT_SELECT + " WHERE p.id = ?", (product_id,))
    if not row:
        raise POSError("Product not found.")
    return row


def find_by_code(db: Database, code: str):
    """Look up an active product by barcode, SKU or an in-stock serial number.

    Returns (product_row, serial_no) or (None, "").
    """
    code = (code or "").strip()
    if not code:
        return None, ""
    row = db.one(PRODUCT_SELECT + " WHERE p.active = 1 AND (p.barcode = ? OR p.sku = ?)",
                 (code, code))
    if row:
        return row, ""
    serial = db.one("SELECT * FROM product_serials WHERE serial_no = ? AND status = 'in_stock'",
                    (code,))
    if serial:
        product = db.one(PRODUCT_SELECT + " WHERE p.id = ? AND p.active = 1",
                         (serial["product_id"],))
        if product:
            return product, serial["serial_no"]
    return None, ""


def save_product(db: Database, data: dict, user_id=None, product_id: int | None = None) -> int:
    """Create or update a product. `data` may hold category/brand names or ids."""
    fields = _clean_product(db, data)
    with db.transaction():
        dup = db.one("SELECT id FROM products WHERE sku = ? AND id != ?",
                     (fields["sku"], product_id or 0))
        if dup:
            raise POSError(f"SKU '{fields['sku']}' is already used by another product.")
        if fields["barcode"]:
            dup = db.one("SELECT id FROM products WHERE barcode = ? AND id != ?",
                         (fields["barcode"], product_id or 0))
            if dup:
                raise POSError(f"Barcode '{fields['barcode']}' is already used by another product.")
        if product_id:
            fields["updated_at"] = now()
            db.update("products", product_id, fields)
            db.log(user_id, "product.update", f"{fields['sku']} {fields['name']}")
            return product_id
        initial = int(data.get("stock_qty") or 0)
        fields.update(created_at=now(), stock_qty=0)
        new_id = db.insert("products", fields)
        if initial:
            adjust_stock(db, new_id, initial, "Opening stock", user_id)
        db.log(user_id, "product.create", f"{fields['sku']} {fields['name']}")
        return new_id


def _clean_product(db: Database, data: dict) -> dict:
    name = (data.get("name") or "").strip()
    sku = (data.get("sku") or "").strip()
    if not name:
        raise POSError("Product name is required.")
    if not sku:
        sku = next_sku(db)
    try:
        cost = money(data.get("cost_price") or 0)
        price = money(data.get("sell_price") or 0)
        reorder = int(data.get("reorder_level") or 0)
        warranty = int(data.get("warranty_months") or 0)
    except (TypeError, ValueError):
        raise POSError("Prices, reorder level and warranty must be numbers.")
    if cost < 0 or price < 0:
        raise POSError("Prices cannot be negative.")

    def lookup(table, id_key, name_key):
        if data.get(id_key):
            return int(data[id_key])
        return get_or_create_lookup(db, table, data.get(name_key) or "")

    return {
        "sku": sku,
        "barcode": (data.get("barcode") or "").strip() or None,
        "name": name,
        "description": (data.get("description") or "").strip(),
        "category_id": lookup("categories", "category_id", "category"),
        "brand_id": lookup("brands", "brand_id", "brand"),
        "supplier_id": int(data["supplier_id"]) if data.get("supplier_id") else None,
        "cost_price": cost,
        "sell_price": price,
        "reorder_level": reorder,
        "warranty_months": warranty,
        "track_serial": int(_truthy(data.get("track_serial"))),
        "tax_exempt": int(_truthy(data.get("tax_exempt"))),
        "location": (data.get("location") or "").strip(),
        "active": int(_truthy(1 if data.get("active") in (None, "") else data["active"])),
    }


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def next_sku(db: Database) -> str:
    n = db.scalar("SELECT COALESCE(MAX(id), 0) + 1 FROM products", default=1)
    while True:
        sku = f"P{n:05d}"
        if not db.one("SELECT 1 FROM products WHERE sku = ?", (sku,)):
            return sku
        n += 1


def next_internal_barcode(db: Database) -> str:
    """Next free in-store EAN-13 style code (prefix 20 is reserved for in-store use)."""
    rows = db.query("SELECT barcode FROM products WHERE barcode LIKE '20%' AND length(barcode) = 13")
    n = max((int(r["barcode"][2:12]) for r in rows if r["barcode"].isdigit()), default=0) + 1
    while True:
        first12 = f"20{n:010d}"
        code = first12 + ean13_check_digit(first12)
        if not db.one("SELECT 1 FROM products WHERE barcode = ?", (code,)):
            return code
        n += 1


def assign_missing_barcodes(db: Database, product_ids=None, user_id=None) -> int:
    """Give every (or each listed) product without a barcode a new in-store barcode."""
    sql = "SELECT id FROM products WHERE (barcode IS NULL OR barcode = '')"
    params: list = []
    if product_ids is not None:
        ids = [int(i) for i in product_ids] or [0]
        sql += " AND id IN (%s)" % ",".join("?" * len(ids))
        params = ids
    count = 0
    with db.transaction():
        for row in db.query(sql, params):
            db.update("products", row["id"], {"barcode": next_internal_barcode(db), "updated_at": now()})
            count += 1
        if count:
            db.log(user_id, "product.barcodes", f"generated {count}")
    return count


def set_active(db: Database, product_id: int, active: bool, user_id=None):
    db.update("products", product_id, {"active": int(active), "updated_at": now()})
    db.log(user_id, "product.active", f"id={product_id} active={int(active)}")


# ------------------------------------------------------------------------ stock
def adjust_stock(db: Database, product_id: int, change: int, reason: str, user_id=None,
                 ref: str = "") -> int:
    """Change stock by `change` units and record a movement. Returns new balance."""
    change = int(change)
    with db.transaction():
        product = db.one("SELECT stock_qty FROM products WHERE id = ?", (product_id,))
        if not product:
            raise POSError("Product not found.")
        balance = product["stock_qty"] + change
        db.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (balance, product_id))
        db.insert("stock_movements", {
            "product_id": product_id, "change": change, "balance": balance,
            "reason": reason, "ref": ref, "user_id": user_id, "created_at": now(),
        })
    return balance


def set_stock_count(db: Database, product_id: int, counted: int, user_id=None, note: str = "") -> int:
    """Stock-take: set the quantity to what was physically counted."""
    current = db.scalar("SELECT stock_qty FROM products WHERE id = ?", (product_id,))
    if current is None:
        raise POSError("Product not found.")
    diff = int(counted) - current
    if diff == 0:
        return current
    return adjust_stock(db, product_id, diff, "Stock count" + (f": {note}" if note else ""), user_id)


def stock_movements(db: Database, product_id: int | None = None, limit: int = 500):
    sql = """SELECT m.*, p.name AS product, p.sku, u.username AS user
             FROM stock_movements m JOIN products p ON p.id = m.product_id
             LEFT JOIN users u ON u.id = m.user_id"""
    params = []
    if product_id:
        sql += " WHERE m.product_id = ?"
        params.append(product_id)
    sql += " ORDER BY m.id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


def low_stock(db: Database):
    return db.query(PRODUCT_SELECT + " WHERE p.active = 1 AND p.stock_qty <= p.reorder_level "
                    "ORDER BY p.stock_qty - p.reorder_level, p.name")


# ---------------------------------------------------------------------- serials
def add_serials(db: Database, product_id: int, serials, purchase_id=None) -> int:
    added = 0
    with db.transaction():
        for serial in serials:
            serial = serial.strip()
            if not serial:
                continue
            existing = db.one("SELECT * FROM product_serials WHERE serial_no = ?", (serial,))
            if existing:
                if existing["status"] == "in_stock":
                    raise POSError(f"Serial '{serial}' is already in stock.")
                db.update("product_serials", existing["id"], {
                    "product_id": product_id, "status": "in_stock", "sale_id": None})
            else:
                db.insert("product_serials", {
                    "product_id": product_id, "serial_no": serial, "status": "in_stock",
                    "purchase_id": purchase_id, "created_at": now()})
            added += 1
    return added


def list_serials(db: Database, product_id: int, status: str | None = None):
    sql = "SELECT * FROM product_serials WHERE product_id = ?"
    params = [product_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    return db.query(sql + " ORDER BY serial_no", params)


def delete_serial(db: Database, serial_id: int):
    db.execute("DELETE FROM product_serials WHERE id = ? AND status != 'sold'", (serial_id,))


# ------------------------------------------------------------------- CSV import
def export_products_csv(db: Database, path: str) -> int:
    rows = list_products(db, include_inactive=True, limit=1_000_000)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=PRODUCT_CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: (r[k] if r[k] is not None else "") for k in PRODUCT_CSV_FIELDS})
    return len(rows)


def import_products_csv(db: Database, path: str, user_id=None) -> tuple[int, int, list[str]]:
    """Import products. Existing SKUs are updated (stock is not overwritten)."""
    created = updated = 0
    errors = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            try:
                existing = db.one("SELECT id FROM products WHERE sku = ?", (row.get("sku", ""),)) \
                    if row.get("sku") else None
                if existing:
                    save_product(db, row, user_id, existing["id"])
                    updated += 1
                else:
                    save_product(db, row, user_id)
                    created += 1
            except (POSError, ValueError) as exc:
                errors.append(f"Line {line_no}: {exc}")
    return created, updated, errors
