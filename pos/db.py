"""SQLite database layer: connection handling, schema and small helpers."""
from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    username             TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name            TEXT NOT NULL DEFAULT '',
    password_hash        TEXT NOT NULL,
    salt                 TEXT NOT NULL,
    role                 TEXT NOT NULL DEFAULT 'cashier',
    active               INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS brands (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS suppliers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    contact    TEXT DEFAULT '',
    phone      TEXT DEFAULT '',
    email      TEXT DEFAULT '',
    address    TEXT DEFAULT '',
    notes      TEXT DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL UNIQUE COLLATE NOCASE,
    barcode         TEXT UNIQUE,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    brand_id        INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    cost_price      REAL NOT NULL DEFAULT 0,
    sell_price      REAL NOT NULL DEFAULT 0,
    stock_qty       INTEGER NOT NULL DEFAULT 0,
    reorder_level   INTEGER NOT NULL DEFAULT 0,
    warranty_months INTEGER NOT NULL DEFAULT 0,
    track_serial    INTEGER NOT NULL DEFAULT 0,
    tax_exempt      INTEGER NOT NULL DEFAULT 0,
    location        TEXT DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);

CREATE TABLE IF NOT EXISTS product_serials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    serial_no   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    status      TEXT NOT NULL DEFAULT 'in_stock',
    purchase_id INTEGER,
    sale_id     INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    phone          TEXT DEFAULT '',
    email          TEXT DEFAULT '',
    address        TEXT DEFAULT '',
    notes          TEXT DEFAULT '',
    loyalty_points INTEGER NOT NULL DEFAULT 0,
    balance        REAL NOT NULL DEFAULT 0,
    credit_limit   REAL NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);

CREATE TABLE IF NOT EXISTS shifts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    opened_at     TEXT NOT NULL,
    closed_at     TEXT,
    opening_cash  REAL NOT NULL DEFAULT 0,
    counted_cash  REAL,
    expected_cash REAL,
    closed_by     INTEGER REFERENCES users(id),
    notes         TEXT DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS sales (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no     TEXT UNIQUE,
    customer_id    INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    shift_id       INTEGER REFERENCES shifts(id),
    created_at     TEXT NOT NULL,
    subtotal       REAL NOT NULL,
    discount_total REAL NOT NULL DEFAULT 0,
    tax_total      REAL NOT NULL DEFAULT 0,
    total          REAL NOT NULL,
    tendered       REAL NOT NULL DEFAULT 0,
    change_due     REAL NOT NULL DEFAULT 0,
    points_earned  INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'completed',
    notes          TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at);

CREATE TABLE IF NOT EXISTS sale_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id        INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES products(id) ON DELETE SET NULL,
    name           TEXT NOT NULL,
    sku            TEXT DEFAULT '',
    qty            INTEGER NOT NULL,
    unit_price     REAL NOT NULL,
    unit_cost      REAL NOT NULL DEFAULT 0,
    discount       REAL NOT NULL DEFAULT 0,
    tax            REAL NOT NULL DEFAULT 0,
    line_total     REAL NOT NULL,
    serial_no      TEXT DEFAULT '',
    warranty_until TEXT,
    returned_qty   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_serial ON sale_items(serial_no);

CREATE TABLE IF NOT EXISTS payments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id   INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    method    TEXT NOT NULL,
    amount    REAL NOT NULL,
    reference TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS held_sales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT DEFAULT '',
    user_id     INTEGER REFERENCES users(id),
    customer_id INTEGER,
    data        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS returns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    return_no     TEXT UNIQUE,
    sale_id       INTEGER NOT NULL REFERENCES sales(id),
    user_id       INTEGER NOT NULL REFERENCES users(id),
    shift_id      INTEGER REFERENCES shifts(id),
    created_at    TEXT NOT NULL,
    total         REAL NOT NULL,
    reason        TEXT DEFAULT '',
    refund_method TEXT NOT NULL DEFAULT 'Cash',
    restocked     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS return_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id    INTEGER NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
    sale_item_id INTEGER NOT NULL REFERENCES sale_items(id),
    product_id   INTEGER,
    qty          INTEGER NOT NULL,
    amount       REAL NOT NULL,
    cost         REAL NOT NULL DEFAULT 0,
    tax          REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    po_no       TEXT UNIQUE,
    supplier_id INTEGER REFERENCES suppliers(id),
    user_id     INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,
    received_at TEXT,
    status      TEXT NOT NULL DEFAULT 'ordered',
    total       REAL NOT NULL DEFAULT 0,
    notes       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS purchase_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id        INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    qty          INTEGER NOT NULL,
    unit_cost    REAL NOT NULL,
    received_qty INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    change     INTEGER NOT NULL,
    balance    INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    ref        TEXT DEFAULT '',
    user_id    INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_id);

CREATE TABLE IF NOT EXISTS cash_movements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id   INTEGER NOT NULL REFERENCES shifts(id),
    user_id    INTEGER,
    type       TEXT NOT NULL,
    amount     REAL NOT NULL,
    reason     TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    amount      REAL NOT NULL,
    method      TEXT NOT NULL DEFAULT 'Cash',
    notes       TEXT DEFAULT '',
    user_id     INTEGER,
    shift_id    INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'General',
    description TEXT DEFAULT '',
    amount      REAL NOT NULL,
    paid_from_drawer INTEGER NOT NULL DEFAULT 0,
    shift_id    INTEGER,
    user_id     INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repairs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no    TEXT UNIQUE,
    customer_id  INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    device       TEXT NOT NULL,
    brand_model  TEXT DEFAULT '',
    serial_no    TEXT DEFAULT '',
    issue        TEXT NOT NULL,
    accessories  TEXT DEFAULT '',
    passcode     TEXT DEFAULT '',
    estimate     REAL NOT NULL DEFAULT 0,
    final_cost   REAL NOT NULL DEFAULT 0,
    paid         REAL NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'Received',
    technician   TEXT DEFAULT '',
    notes        TEXT DEFAULT '',
    due_date     TEXT,
    received_at  TEXT NOT NULL,
    delivered_at TEXT,
    user_id      INTEGER
);

CREATE TABLE IF NOT EXISTS repair_payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    repair_id  INTEGER NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
    amount     REAL NOT NULL,
    method     TEXT NOT NULL DEFAULT 'Cash',
    user_id    INTEGER,
    shift_id   INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    action     TEXT NOT NULL,
    details    TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "shop_name": "My Electronics Shop",
    "shop_address": "Main Street",
    "shop_phone": "",
    "shop_email": "",
    "tax_id": "",
    "tax_rate": "11",
    "tax_name": "VAT",
    "currency_symbol": "$",
    "secondary_currency": "LBP",
    "exchange_rate": "89500",
    "show_secondary_currency": "1",
    "invoice_prefix": "INV-",
    "receipt_footer": "Thank you for shopping with us!\nKeep this receipt for warranty claims.",
    "receipt_width": "42",
    "auto_print_receipt": "0",
    "printer_name": "",
    "open_cash_drawer": "0",
    "loyalty_points_per_unit": "1",
    "loyalty_point_value": "0.01",
    "cashier_max_discount_pct": "10",
    "allow_negative_stock": "0",
    "require_open_shift": "1",
    "return_days_limit": "14",
}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def money(value) -> float:
    """Round a value to 2 decimals using commercial (half-up) rounding."""
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def app_data_dir() -> str:
    """Folder that holds the database, receipts and backups."""
    base = os.environ.get("POS_DATA_DIR")
    if not base:
        if getattr(sys, "frozen", False):  # running as a PyInstaller .exe
            root = os.path.dirname(sys.executable)
        else:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        base = os.path.join(root, "data")
    os.makedirs(base, exist_ok=True)
    return base


class POSError(Exception):
    """A business rule was violated; the message is safe to show to the user."""


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(app_data_dir(), "pos.db")
        # Autocommit mode; multi-statement work goes through transaction().
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._in_tx = False
        self._init_schema()

    # ------------------------------------------------------------------ setup
    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        self.conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),))

    def close(self):
        self.conn.close()

    # ---------------------------------------------------------------- queries
    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params=()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params=(), default=None):
        row = self.conn.execute(sql, params).fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]

    def insert(self, table: str, data: dict) -> int:
        cols = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        cur = self.conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))
        return cur.lastrowid

    def update(self, table: str, row_id: int, data: dict):
        if not data:
            return
        sets = ", ".join(f"{k} = ?" for k in data)
        self.conn.execute(
            f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), row_id))

    @contextmanager
    def transaction(self):
        """Run a block atomically. Nested calls join the outer transaction."""
        if self._in_tx:
            yield
            return
        self._in_tx = True
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")
        finally:
            self._in_tx = False

    # --------------------------------------------------------------- settings
    def get_settings(self) -> dict:
        return {r["key"]: r["value"] for r in self.query("SELECT key, value FROM settings")}

    def get_setting(self, key: str, default: str = "") -> str:
        value = self.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return default if value is None else value

    def set_settings(self, values: dict):
        with self.transaction():
            for key, value in values.items():
                self.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, "" if value is None else str(value)))

    # ------------------------------------------------------------------ audit
    def log(self, user_id, action: str, details: str = ""):
        self.execute(
            "INSERT INTO audit_log(user_id, action, details, created_at) VALUES (?, ?, ?, ?)",
            (user_id, action, details, now()))

    # --------------------------------------------------------- backup/restore
    def backup_to(self, dest_path: str):
        dest = sqlite3.connect(dest_path)
        try:
            self.conn.backup(dest)
        finally:
            dest.close()

    def restore_from(self, src_path: str):
        src = sqlite3.connect(src_path)
        try:
            tables = {r[0] for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"products", "sales", "users", "settings"} <= tables:
                raise POSError("The selected file is not a POS backup.")
            src.backup(self.conn)
        finally:
            src.close()
        self._init_schema()


def setting_float(settings: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(settings.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def setting_bool(settings: dict, key: str) -> bool:
    return str(settings.get(key, "0")).strip().lower() in ("1", "true", "yes", "on")
