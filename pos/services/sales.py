"""Cart calculation, checkout, held (parked) sales and returns/refunds."""
from __future__ import annotations

import calendar
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from ..db import Database, POSError, money, now, setting_bool, setting_float

PAYMENT_METHODS = ("Cash", "Card", "Bank Transfer", "Mobile Wallet", "Cheque", "Account", "Points")
REFUND_METHODS = ("Cash", "Card", "Bank Transfer", "Mobile Wallet", "Account")


@dataclass
class CartLine:
    product_id: int
    name: str
    sku: str
    qty: int
    unit_price: float
    unit_cost: float = 0.0
    discount: float = 0.0          # line discount, money amount for the whole line
    tax_exempt: bool = False
    serial_no: str = ""
    warranty_months: int = 0
    track_serial: bool = False

    @property
    def gross(self) -> float:
        return money(self.qty * self.unit_price)


@dataclass
class Cart:
    lines: list = field(default_factory=list)
    customer_id: int | None = None
    order_discount: float = 0.0     # money amount applied to the whole order
    notes: str = ""

    def add_product(self, product, qty: int = 1, serial_no: str = "") -> CartLine:
        """Add a product row (sqlite Row or dict). Non-serial items are merged."""
        if not product["track_serial"] and not serial_no:
            for line in self.lines:
                if line.product_id == product["id"] and not line.serial_no:
                    line.qty += qty
                    return line
        line = CartLine(
            product_id=product["id"], name=product["name"], sku=product["sku"],
            qty=1 if serial_no else qty, unit_price=float(product["sell_price"]),
            unit_cost=float(product["cost_price"]), tax_exempt=bool(product["tax_exempt"]),
            serial_no=serial_no, warranty_months=int(product["warranty_months"] or 0),
            track_serial=bool(product["track_serial"]))
        self.lines.append(line)
        return line

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "Cart":
        data = json.loads(text)
        lines = [CartLine(**line) for line in data.pop("lines", [])]
        return cls(lines=lines, **data)


def compute_totals(cart: Cart, tax_rate: float) -> dict:
    """Work out per-line and order totals.

    The order discount is spread over the lines in proportion to their net value
    so that tax is charged on the discounted price.
    """
    nets = []
    for line in cart.lines:
        disc = min(max(money(line.discount), 0), line.gross)
        nets.append(money(line.gross - disc))
    sum_net = money(sum(nets))
    order_disc = min(max(money(cart.order_discount), 0), sum_net)

    shares, remaining = [], order_disc
    for i, net in enumerate(nets):
        if i == len(nets) - 1:
            share = remaining
        else:
            share = money(order_disc * net / sum_net) if sum_net else 0.0
            share = min(share, remaining)
        shares.append(share)
        remaining = money(remaining - share)

    lines_out = []
    for line, net, share in zip(cart.lines, nets, shares):
        taxable = money(net - share)
        tax = 0.0 if line.tax_exempt else money(taxable * tax_rate / 100.0)
        lines_out.append({
            "gross": line.gross,
            "discount": money(line.gross - taxable),
            "net": taxable,
            "tax": tax,
            "total": money(taxable + tax),
        })
    subtotal = money(sum(l.gross for l in cart.lines))
    tax_total = money(sum(l["tax"] for l in lines_out))
    total = money(sum(l["total"] for l in lines_out))
    return {
        "subtotal": subtotal,
        "line_discounts": money(sum(l.gross for l in cart.lines) - sum_net),
        "order_discount": order_disc,
        "discount_total": money(subtotal - sum(l["net"] for l in lines_out)),
        "tax_total": tax_total,
        "total": total,
        "lines": lines_out,
        "items": sum(l.qty for l in cart.lines),
    }


def discount_percent(cart: Cart, tax_rate: float) -> float:
    totals = compute_totals(cart, tax_rate)
    if not totals["subtotal"]:
        return 0.0
    return totals["discount_total"] * 100.0 / totals["subtotal"]


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


# --------------------------------------------------------------------- checkout
def checkout(db: Database, cart: Cart, payments: list[dict], user_id: int,
             shift_id: int | None = None) -> int:
    """Validate and save a sale. Returns the new sale id.

    `payments` is a list of {"method", "amount", "reference"} dicts; the cash entry
    may exceed the remaining balance (change is given back in cash).
    """
    settings = db.get_settings()
    tax_rate = setting_float(settings, "tax_rate")
    if not cart.lines:
        raise POSError("The cart is empty.")
    for line in cart.lines:
        if line.qty <= 0:
            raise POSError(f"Quantity for '{line.name}' must be at least 1.")
        if line.unit_price < 0:
            raise POSError(f"Price for '{line.name}' cannot be negative.")
    totals = compute_totals(cart, tax_rate)
    total = totals["total"]

    payments = [dict(p, amount=money(p.get("amount") or 0)) for p in payments
                if money(p.get("amount") or 0) != 0]
    for p in payments:
        if p["amount"] < 0:
            raise POSError("Payment amounts cannot be negative.")
        if p["method"] not in PAYMENT_METHODS:
            raise POSError(f"Unknown payment method: {p['method']}")
    paid = money(sum(p["amount"] for p in payments))
    non_cash = money(sum(p["amount"] for p in payments if p["method"] != "Cash"))
    if paid + 0.001 < total:
        raise POSError(f"Payment is short by {money(total - paid):.2f}.")
    if non_cash > total + 0.001:
        raise POSError("Only cash payments can exceed the total (to give change).")
    change = money(paid - total)

    customer = None
    if cart.customer_id:
        customer = db.one("SELECT * FROM customers WHERE id = ?", (cart.customer_id,))
        if not customer:
            raise POSError("The selected customer no longer exists.")
    account_amt = money(sum(p["amount"] for p in payments if p["method"] == "Account"))
    points_amt = money(sum(p["amount"] for p in payments if p["method"] == "Points"))
    point_value = setting_float(settings, "loyalty_point_value", 0.01)
    points_used = 0
    if (account_amt or points_amt) and not customer:
        raise POSError("Select a customer to pay on account or with loyalty points.")
    if account_amt and customer["credit_limit"] > 0 and \
            customer["balance"] + account_amt > customer["credit_limit"] + 0.001:
        raise POSError(f"This exceeds the customer's credit limit "
                       f"({customer['credit_limit']:.2f}).")
    if points_amt:
        if point_value <= 0:
            raise POSError("Loyalty point redemption is disabled.")
        points_used = int(round(points_amt / point_value))
        if points_used > customer["loyalty_points"]:
            raise POSError(f"Customer only has {customer['loyalty_points']} points "
                           f"(worth {customer['loyalty_points'] * point_value:.2f}).")

    allow_negative = setting_bool(settings, "allow_negative_stock")
    created = now()
    today_d = datetime.now().date()

    with db.transaction():
        # Stock and serial checks inside the transaction.
        needed: dict[int, int] = {}
        for line in cart.lines:
            needed[line.product_id] = needed.get(line.product_id, 0) + line.qty
        for pid, qty in needed.items():
            product = db.one("SELECT name, stock_qty FROM products WHERE id = ?", (pid,))
            if not product:
                raise POSError("A product in the cart no longer exists.")
            if not allow_negative and product["stock_qty"] < qty:
                raise POSError(f"Not enough stock for '{product['name']}' "
                               f"(available {product['stock_qty']}, needed {qty}).")
        seen_serials = set()
        for line in cart.lines:
            if line.track_serial and not line.serial_no:
                raise POSError(f"'{line.name}' needs a serial number.")
            if line.serial_no:
                key = line.serial_no.lower()
                if key in seen_serials:
                    raise POSError(f"Serial {line.serial_no} is in the cart twice.")
                seen_serials.add(key)
                sold = db.one("SELECT 1 FROM product_serials WHERE serial_no = ? AND status = 'sold'",
                              (line.serial_no,))
                if sold:
                    raise POSError(f"Serial {line.serial_no} has already been sold.")

        points_rate = setting_float(settings, "loyalty_points_per_unit", 0)
        points_earned = int(max(0.0, total - points_amt) * points_rate) if customer else 0

        sale_id = db.insert("sales", {
            "customer_id": cart.customer_id, "user_id": user_id, "shift_id": shift_id,
            "created_at": created, "subtotal": totals["subtotal"],
            "discount_total": totals["discount_total"], "tax_total": totals["tax_total"],
            "total": total, "tendered": paid, "change_due": change,
            "points_earned": points_earned, "status": "completed", "notes": cart.notes,
        })
        invoice_no = f"{settings.get('invoice_prefix', 'INV-')}{sale_id:06d}"
        db.execute("UPDATE sales SET invoice_no = ? WHERE id = ?", (invoice_no, sale_id))

        for line, calc in zip(cart.lines, totals["lines"]):
            warranty_until = None
            if line.warranty_months:
                warranty_until = add_months(today_d, line.warranty_months).isoformat()
            db.insert("sale_items", {
                "sale_id": sale_id, "product_id": line.product_id, "name": line.name,
                "sku": line.sku, "qty": line.qty, "unit_price": money(line.unit_price),
                "unit_cost": money(line.unit_cost), "discount": calc["discount"],
                "tax": calc["tax"], "line_total": calc["total"], "serial_no": line.serial_no,
                "warranty_until": warranty_until,
            })
            new_bal = db.scalar("SELECT stock_qty FROM products WHERE id = ?",
                                (line.product_id,)) - line.qty
            db.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (new_bal, line.product_id))
            db.insert("stock_movements", {
                "product_id": line.product_id, "change": -line.qty, "balance": new_bal,
                "reason": "Sale", "ref": invoice_no, "user_id": user_id, "created_at": created})
            if line.serial_no:
                serial = db.one("SELECT id FROM product_serials WHERE serial_no = ?", (line.serial_no,))
                if serial:
                    db.update("product_serials", serial["id"], {
                        "status": "sold", "sale_id": sale_id, "product_id": line.product_id})
                else:
                    db.insert("product_serials", {
                        "product_id": line.product_id, "serial_no": line.serial_no,
                        "status": "sold", "sale_id": sale_id, "created_at": created})

        # Cash is stored net of change so the drawer reconciles.
        cash = [p for p in payments if p["method"] == "Cash"]
        cash_net = money(sum(p["amount"] for p in cash) - change)
        for p in payments:
            if p["method"] != "Cash":
                db.insert("payments", {"sale_id": sale_id, "method": p["method"],
                                       "amount": p["amount"], "reference": p.get("reference", "")})
        if cash_net > 0:
            ref = "; ".join(p.get("reference", "") for p in cash if p.get("reference"))
            db.insert("payments", {"sale_id": sale_id, "method": "Cash", "amount": cash_net,
                                   "reference": ref})

        if customer:
            db.execute(
                "UPDATE customers SET balance = ROUND(balance + ?, 2), "
                "loyalty_points = loyalty_points + ? - ? WHERE id = ?",
                (account_amt, points_earned, points_used, customer["id"]))
        db.log(user_id, "sale", f"{invoice_no} total={total:.2f}")
    return sale_id


def get_sale(db: Database, sale_id: int) -> dict:
    sale = db.one("""SELECT s.*, u.full_name AS cashier, c.name AS customer_name,
                            c.phone AS customer_phone, c.loyalty_points AS customer_points,
                            c.balance AS customer_balance
                     FROM sales s JOIN users u ON u.id = s.user_id
                     LEFT JOIN customers c ON c.id = s.customer_id WHERE s.id = ?""", (sale_id,))
    if not sale:
        raise POSError("Sale not found.")
    return {
        "sale": sale,
        "items": db.query("SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id", (sale_id,)),
        "payments": db.query("SELECT * FROM payments WHERE sale_id = ? ORDER BY id", (sale_id,)),
        "returns": db.query("SELECT * FROM returns WHERE sale_id = ? ORDER BY id", (sale_id,)),
    }


def find_sale_by_invoice(db: Database, invoice_no: str):
    invoice_no = invoice_no.strip()
    row = db.one("SELECT id FROM sales WHERE invoice_no = ? COLLATE NOCASE", (invoice_no,))
    if not row and invoice_no.isdigit():
        row = db.one("SELECT id FROM sales WHERE id = ?", (int(invoice_no),))
    return row["id"] if row else None


def list_sales(db: Database, date_from: str, date_to: str, search: str = "", user_id=None,
               limit: int = 2000):
    sql = """SELECT s.*, u.username AS cashier, c.name AS customer_name
             FROM sales s JOIN users u ON u.id = s.user_id
             LEFT JOIN customers c ON c.id = s.customer_id
             WHERE date(s.created_at) BETWEEN ? AND ?"""
    params = [date_from, date_to]
    if search:
        like = f"%{search.strip()}%"
        sql += """ AND (s.invoice_no LIKE ? OR c.name LIKE ? OR c.phone LIKE ?
                   OR EXISTS (SELECT 1 FROM sale_items i WHERE i.sale_id = s.id
                              AND (i.serial_no LIKE ? OR i.name LIKE ?)))"""
        params += [like] * 5
    if user_id:
        sql += " AND s.user_id = ?"
        params.append(user_id)
    sql += " ORDER BY s.id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


# ------------------------------------------------------------------ held sales
def hold_cart(db: Database, cart: Cart, user_id: int, label: str = "") -> int:
    if not cart.lines:
        raise POSError("The cart is empty.")
    return db.insert("held_sales", {
        "label": label, "user_id": user_id, "customer_id": cart.customer_id,
        "data": cart.to_json(), "created_at": now()})


def list_held(db: Database):
    return db.query("""SELECT h.*, u.username AS user, c.name AS customer_name
                       FROM held_sales h LEFT JOIN users u ON u.id = h.user_id
                       LEFT JOIN customers c ON c.id = h.customer_id ORDER BY h.id""")


def resume_held(db: Database, held_id: int) -> Cart:
    row = db.one("SELECT * FROM held_sales WHERE id = ?", (held_id,))
    if not row:
        raise POSError("Held sale not found.")
    cart = Cart.from_json(row["data"])
    db.execute("DELETE FROM held_sales WHERE id = ?", (held_id,))
    return cart


def delete_held(db: Database, held_id: int):
    db.execute("DELETE FROM held_sales WHERE id = ?", (held_id,))


# --------------------------------------------------------------------- returns
def returnable_items(db: Database, sale_id: int):
    return db.query("SELECT *, qty - returned_qty AS returnable FROM sale_items "
                    "WHERE sale_id = ? ORDER BY id", (sale_id,))


def _portion(value: float, done: int, now_qty: int, qty: int) -> float:
    """Share of `value` for units done..done+now_qty out of qty, rounding-safe."""
    return money(money(value * (done + now_qty) / qty) - money(value * done / qty))


def process_return(db: Database, sale_id: int, items: dict[int, int], reason: str,
                   refund_method: str, restock: bool, user_id: int, shift_id=None,
                   override_days: bool = False) -> int:
    """Return items of a sale. `items` maps sale_item_id -> quantity to return."""
    items = {int(k): int(v) for k, v in items.items() if int(v) > 0}
    if not items:
        raise POSError("Select at least one item to return.")
    if refund_method not in REFUND_METHODS:
        raise POSError(f"Unknown refund method: {refund_method}")
    sale = db.one("SELECT * FROM sales WHERE id = ?", (sale_id,))
    if not sale:
        raise POSError("Sale not found.")
    if refund_method == "Account" and not sale["customer_id"]:
        raise POSError("This sale has no customer, so it cannot be refunded to an account.")
    limit_days = int(setting_float(db.get_settings(), "return_days_limit", 0))
    sale_date = datetime.strptime(sale["created_at"][:10], "%Y-%m-%d").date()
    if limit_days and not override_days and (date.today() - sale_date).days > limit_days:
        raise POSError(f"This sale is older than the {limit_days}-day return period.")

    created = now()
    with db.transaction():
        return_id = db.insert("returns", {
            "sale_id": sale_id, "user_id": user_id, "shift_id": shift_id, "created_at": created,
            "total": 0, "reason": reason, "refund_method": refund_method,
            "restocked": int(restock)})
        return_no = f"RET-{return_id:06d}"
        db.execute("UPDATE returns SET return_no = ? WHERE id = ?", (return_no, return_id))
        total = 0.0
        for item_id, qty in items.items():
            item = db.one("SELECT * FROM sale_items WHERE id = ? AND sale_id = ?", (item_id, sale_id))
            if not item:
                raise POSError("Item does not belong to this sale.")
            available = item["qty"] - item["returned_qty"]
            if qty > available:
                raise POSError(f"Only {available} of '{item['name']}' can be returned.")
            amount = _portion(item["line_total"], item["returned_qty"], qty, item["qty"])
            tax = _portion(item["tax"], item["returned_qty"], qty, item["qty"])
            total = money(total + amount)
            db.insert("return_items", {
                "return_id": return_id, "sale_item_id": item_id, "product_id": item["product_id"],
                "qty": qty, "amount": amount, "cost": money(item["unit_cost"] * qty), "tax": tax})
            db.execute("UPDATE sale_items SET returned_qty = returned_qty + ? WHERE id = ?",
                       (qty, item_id))
            if item["product_id"] and restock:
                bal = db.scalar("SELECT stock_qty FROM products WHERE id = ?",
                                (item["product_id"],))
                if bal is not None:
                    db.execute("UPDATE products SET stock_qty = ? WHERE id = ?",
                               (bal + qty, item["product_id"]))
                    db.insert("stock_movements", {
                        "product_id": item["product_id"], "change": qty, "balance": bal + qty,
                        "reason": "Customer return", "ref": return_no, "user_id": user_id,
                        "created_at": created})
            if item["serial_no"]:
                db.execute("UPDATE product_serials SET status = ? WHERE serial_no = ?",
                           ("in_stock" if restock else "defective", item["serial_no"]))
        db.execute("UPDATE returns SET total = ? WHERE id = ?", (total, return_id))

        left = db.scalar("SELECT SUM(qty - returned_qty) FROM sale_items WHERE sale_id = ?",
                         (sale_id,), 0)
        db.execute("UPDATE sales SET status = ? WHERE id = ?",
                   ("returned" if left == 0 else "partially_returned", sale_id))
        if sale["customer_id"]:
            points_back = 0
            if sale["total"]:
                # Cumulative so that several partial returns reverse exactly what was earned.
                prior = db.scalar("SELECT SUM(total) FROM returns WHERE sale_id = ? AND id != ?",
                                  (sale_id, return_id), 0)
                earned = sale["points_earned"]
                points_back = (round(earned * min(1, (prior + total) / sale["total"]))
                               - round(earned * min(1, prior / sale["total"])))
            balance_change = total if refund_method == "Account" else 0
            db.execute("UPDATE customers SET balance = ROUND(balance - ?, 2), "
                       "loyalty_points = MAX(0, loyalty_points - ?) WHERE id = ?",
                       (balance_change, points_back, sale["customer_id"]))
        db.log(user_id, "return", f"{return_no} for {sale['invoice_no']} total={total:.2f}")
    return return_id


def get_return(db: Database, return_id: int) -> dict:
    ret = db.one("""SELECT r.*, s.invoice_no, u.full_name AS cashier, c.name AS customer_name
                    FROM returns r JOIN sales s ON s.id = r.sale_id
                    JOIN users u ON u.id = r.user_id
                    LEFT JOIN customers c ON c.id = s.customer_id WHERE r.id = ?""", (return_id,))
    if not ret:
        raise POSError("Return not found.")
    items = db.query("""SELECT ri.*, si.name, si.sku, si.serial_no FROM return_items ri
                        JOIN sale_items si ON si.id = ri.sale_item_id
                        WHERE ri.return_id = ?""", (return_id,))
    return {"return": ret, "items": items}


def list_returns(db: Database, date_from: str, date_to: str):
    return db.query("""SELECT r.*, s.invoice_no, u.username AS cashier FROM returns r
                       JOIN sales s ON s.id = r.sale_id JOIN users u ON u.id = r.user_id
                       WHERE date(r.created_at) BETWEEN ? AND ? ORDER BY r.id DESC""",
                    (date_from, date_to))


# -------------------------------------------------------------------- warranty
def warranty_lookup(db: Database, term: str):
    """Find sold items by serial number, invoice number or customer phone."""
    term = term.strip()
    if not term:
        return []
    like = f"%{term}%"
    return db.query("""SELECT i.*, s.invoice_no, s.created_at AS sold_at, c.name AS customer_name,
                              c.phone AS customer_phone
                       FROM sale_items i JOIN sales s ON s.id = i.sale_id
                       LEFT JOIN customers c ON c.id = s.customer_id
                       WHERE i.serial_no LIKE ? OR s.invoice_no LIKE ? OR c.phone LIKE ?
                       ORDER BY s.id DESC LIMIT 200""", (like, like, like))
