"""Customers (with loyalty points and account balance) and suppliers."""
from __future__ import annotations

from ..db import Database, POSError, money, now


# -------------------------------------------------------------------- customers
def list_customers(db: Database, search: str = "", limit: int = 1000):
    sql = "SELECT * FROM customers"
    params = []
    if search:
        like = f"%{search.strip()}%"
        sql += " WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?"
        params += [like, like, like]
    sql += " ORDER BY name LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


def get_customer(db: Database, customer_id: int):
    row = db.one("SELECT * FROM customers WHERE id = ?", (customer_id,))
    if not row:
        raise POSError("Customer not found.")
    return row


def save_customer(db: Database, data: dict, customer_id: int | None = None, user_id=None) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise POSError("Customer name is required.")
    phone = (data.get("phone") or "").strip()
    if phone:
        dup = db.one("SELECT id, name FROM customers WHERE phone = ? AND id != ?",
                     (phone, customer_id or 0))
        if dup:
            raise POSError(f"Phone {phone} already belongs to customer '{dup['name']}'.")
    try:
        credit_limit = money(data.get("credit_limit") or 0)
    except (TypeError, ValueError, ArithmeticError):
        raise POSError("Credit limit must be a number.")
    fields = {
        "name": name, "phone": phone,
        "email": (data.get("email") or "").strip(),
        "address": (data.get("address") or "").strip(),
        "notes": (data.get("notes") or "").strip(),
        "credit_limit": credit_limit,
    }
    if customer_id:
        db.update("customers", customer_id, fields)
        db.log(user_id, "customer.update", name)
        return customer_id
    fields["created_at"] = now()
    new_id = db.insert("customers", fields)
    db.log(user_id, "customer.create", name)
    return new_id


def delete_customer(db: Database, customer_id: int, user_id=None):
    customer = get_customer(db, customer_id)
    if abs(customer["balance"]) > 0.004:
        raise POSError("This customer has an outstanding balance and cannot be deleted.")
    db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    db.log(user_id, "customer.delete", customer["name"])


def customer_sales(db: Database, customer_id: int):
    return db.query(
        "SELECT * FROM sales WHERE customer_id = ? ORDER BY id DESC", (customer_id,))


def customer_payments(db: Database, customer_id: int):
    return db.query(
        "SELECT * FROM customer_payments WHERE customer_id = ? ORDER BY id DESC", (customer_id,))


def receive_account_payment(db: Database, customer_id: int, amount: float, method: str = "Cash",
                            notes: str = "", user_id=None, shift_id=None) -> int:
    """Customer pays down their account (credit) balance."""
    amount = money(amount)
    if amount <= 0:
        raise POSError("Amount must be greater than zero.")
    customer = get_customer(db, customer_id)
    with db.transaction():
        pay_id = db.insert("customer_payments", {
            "customer_id": customer_id, "amount": amount, "method": method, "notes": notes,
            "user_id": user_id, "shift_id": shift_id, "created_at": now()})
        db.execute("UPDATE customers SET balance = ROUND(balance - ?, 2) WHERE id = ?",
                   (amount, customer_id))
        db.log(user_id, "customer.payment", f"{customer['name']} {amount:.2f} {method}")
    return pay_id


def adjust_points(db: Database, customer_id: int, delta: int, user_id=None, reason: str = ""):
    with db.transaction():
        customer = get_customer(db, customer_id)
        new_points = max(0, customer["loyalty_points"] + int(delta))
        db.update("customers", customer_id, {"loyalty_points": new_points})
        db.log(user_id, "customer.points", f"{customer['name']} {delta:+d} {reason}")


# -------------------------------------------------------------------- suppliers
def list_suppliers(db: Database, search: str = "", include_inactive: bool = False):
    where, params = [], []
    if not include_inactive:
        where.append("active = 1")
    if search:
        like = f"%{search.strip()}%"
        where.append("(name LIKE ? OR contact LIKE ? OR phone LIKE ? OR email LIKE ?)")
        params += [like] * 4
    sql = "SELECT * FROM suppliers" + (" WHERE " + " AND ".join(where) if where else "")
    return db.query(sql + " ORDER BY name", params)


def get_supplier(db: Database, supplier_id: int):
    row = db.one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    if not row:
        raise POSError("Supplier not found.")
    return row


def save_supplier(db: Database, data: dict, supplier_id: int | None = None, user_id=None) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise POSError("Supplier name is required.")
    fields = {k: (data.get(k) or "").strip()
              for k in ("contact", "phone", "email", "address", "notes")}
    fields["name"] = name
    if "active" in data:
        fields["active"] = int(bool(data["active"]))
    if supplier_id:
        db.update("suppliers", supplier_id, fields)
        db.log(user_id, "supplier.update", name)
        return supplier_id
    fields["created_at"] = now()
    new_id = db.insert("suppliers", fields)
    db.log(user_id, "supplier.create", name)
    return new_id
