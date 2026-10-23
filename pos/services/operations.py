"""Cash drawer shifts, expenses and repair (service) tickets."""
from __future__ import annotations

from ..db import Database, POSError, money, now, today
from ..i18n import _

REPAIR_STATUSES = ("Received", "Diagnosing", "Waiting for Parts", "In Progress",
                   "Ready for Pickup", "Delivered", "Cancelled")
OPEN_REPAIR_STATUSES = REPAIR_STATUSES[:5]
EXPENSE_CATEGORIES = ("Rent", "Electricity", "Generator", "Internet", "Salaries", "Transport",
                      "Maintenance", "Marketing", "Supplies", "Taxes", "General")


# ----------------------------------------------------------------------- shifts
def current_shift(db: Database):
    return db.one("""SELECT sh.*, u.full_name AS opened_by FROM shifts sh
                     JOIN users u ON u.id = sh.user_id
                     WHERE sh.status = 'open' ORDER BY sh.id DESC LIMIT 1""")


def open_shift(db: Database, user_id: int, opening_cash: float) -> int:
    if current_shift(db):
        raise POSError(_("A shift is already open. Close it before opening a new one."))
    opening_cash = money(opening_cash)
    if opening_cash < 0:
        raise POSError(_("Opening cash cannot be negative."))
    shift_id = db.insert("shifts", {"user_id": user_id, "opened_at": now(),
                                    "opening_cash": opening_cash, "status": "open"})
    db.log(user_id, "shift.open", f"#{shift_id} float={opening_cash:.2f}")
    return shift_id


def cash_movement(db: Database, shift_id: int, kind: str, amount: float, reason: str,
                  user_id=None) -> int:
    if kind not in ("in", "out"):
        raise ValueError(kind)
    amount = money(amount)
    if amount <= 0:
        raise POSError(_("Amount must be greater than zero."))
    move_id = db.insert("cash_movements", {"shift_id": shift_id, "user_id": user_id, "type": kind,
                                           "amount": amount, "reason": reason, "created_at": now()})
    db.log(user_id, f"cash.{kind}", f"{amount:.2f} {reason}")
    return move_id


def shift_summary(db: Database, shift_id: int) -> dict:
    shift = db.one("""SELECT sh.*, u.full_name AS opened_by, c.full_name AS closed_by_name
                      FROM shifts sh JOIN users u ON u.id = sh.user_id
                      LEFT JOIN users c ON c.id = sh.closed_by WHERE sh.id = ?""", (shift_id,))
    if not shift:
        raise POSError(_("Shift not found."))
    p = (shift_id,)
    sales = db.one("""SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS total,
                             COALESCE(SUM(tax_total),0) AS tax,
                             COALESCE(SUM(discount_total),0) AS discounts
                      FROM sales WHERE shift_id = ?""", p)
    by_method = db.query("""SELECT method, SUM(amount) AS amount FROM payments
                            WHERE sale_id IN (SELECT id FROM sales WHERE shift_id = ?)
                            GROUP BY method ORDER BY method""", p)
    refunds = db.query("""SELECT refund_method AS method, COUNT(*) AS n, SUM(total) AS amount
                          FROM returns WHERE shift_id = ? GROUP BY refund_method""", p)
    cash_in = db.scalar("SELECT SUM(amount) FROM cash_movements WHERE shift_id=? AND type='in'", p, 0)
    cash_out = db.scalar("SELECT SUM(amount) FROM cash_movements WHERE shift_id=? AND type='out'", p, 0)
    acct = db.scalar("SELECT SUM(amount) FROM customer_payments WHERE shift_id=? AND method='Cash'",
                     p, 0)
    repairs = db.scalar("SELECT SUM(amount) FROM repair_payments WHERE shift_id=? AND method='Cash'",
                        p, 0)
    expenses = db.scalar("SELECT SUM(amount) FROM expenses WHERE shift_id=? AND paid_from_drawer=1",
                         p, 0)
    cash_sales = sum(r["amount"] for r in by_method if r["method"] == "Cash")
    cash_refunds = sum(r["amount"] for r in refunds if r["method"] == "Cash")
    expected = money(shift["opening_cash"] + cash_sales - cash_refunds + cash_in - cash_out
                     + acct + repairs - expenses)
    return {
        "shift": shift, "sales_count": sales["n"], "sales_total": money(sales["total"]),
        "tax_total": money(sales["tax"]), "discounts": money(sales["discounts"]),
        "by_method": by_method, "refunds": refunds, "cash_sales": money(cash_sales),
        "cash_refunds": money(cash_refunds), "cash_in": money(cash_in), "cash_out": money(cash_out),
        "account_payments": money(acct), "repair_payments": money(repairs),
        "drawer_expenses": money(expenses), "expected_cash": expected,
        "movements": db.query("SELECT * FROM cash_movements WHERE shift_id = ? ORDER BY id", p),
    }


def close_shift(db: Database, shift_id: int, counted_cash: float, user_id: int, notes: str = "") -> dict:
    summary = shift_summary(db, shift_id)
    if summary["shift"]["status"] != "open":
        raise POSError(_("This shift is already closed."))
    counted = money(counted_cash)
    db.update("shifts", shift_id, {
        "closed_at": now(), "counted_cash": counted, "expected_cash": summary["expected_cash"],
        "closed_by": user_id, "notes": notes, "status": "closed"})
    db.log(user_id, "shift.close",
           f"#{shift_id} expected={summary['expected_cash']:.2f} counted={counted:.2f}")
    return shift_summary(db, shift_id)


def list_shifts(db: Database, limit: int = 200):
    return db.query("""SELECT sh.*, u.username AS user FROM shifts sh JOIN users u ON u.id = sh.user_id
                       ORDER BY sh.id DESC LIMIT ?""", (limit,))


# --------------------------------------------------------------------- expenses
def add_expense(db: Database, data: dict, user_id=None, shift_id=None) -> int:
    try:
        amount = money(data.get("amount") or 0)
    except (TypeError, ValueError, ArithmeticError):
        raise POSError(_("Amount must be a number."))
    if amount <= 0:
        raise POSError(_("Amount must be greater than zero."))
    from_drawer = bool(data.get("paid_from_drawer"))
    if from_drawer and not shift_id:
        raise POSError(_("Open a shift to pay an expense from the cash drawer."))
    exp_id = db.insert("expenses", {
        "date": (data.get("date") or today()).strip(),
        "category": (data.get("category") or "General").strip(),
        "description": (data.get("description") or "").strip(),
        "amount": amount, "paid_from_drawer": int(from_drawer),
        "shift_id": shift_id if from_drawer else None,
        "user_id": user_id, "created_at": now()})
    db.log(user_id, "expense.add", f"{amount:.2f} {data.get('category')}")
    return exp_id


def list_expenses(db: Database, date_from: str, date_to: str):
    return db.query("""SELECT e.*, u.username AS user FROM expenses e
                       LEFT JOIN users u ON u.id = e.user_id
                       WHERE e.date BETWEEN ? AND ? ORDER BY e.date DESC, e.id DESC""",
                    (date_from, date_to))


def delete_expense(db: Database, expense_id: int, user_id=None):
    row = db.one("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    if not row:
        return
    if row["paid_from_drawer"]:
        shift = db.one("SELECT status FROM shifts WHERE id = ?", (row["shift_id"],))
        if shift and shift["status"] == "closed":
            raise POSError(_("This expense was paid from a closed shift and cannot be deleted."))
    db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.log(user_id, "expense.delete", f"#{expense_id} {row['amount']:.2f}")


# ---------------------------------------------------------------------- repairs
def create_repair(db: Database, data: dict, user_id=None) -> int:
    device = (data.get("device") or "").strip()
    issue = (data.get("issue") or "").strip()
    if not device or not issue:
        raise POSError(_("Device and issue description are required."))
    try:
        estimate = money(data.get("estimate") or 0)
    except (TypeError, ValueError, ArithmeticError):
        raise POSError(_("Estimate must be a number."))
    with db.transaction():
        repair_id = db.insert("repairs", {
            "customer_id": data.get("customer_id") or None, "device": device,
            "brand_model": (data.get("brand_model") or "").strip(),
            "serial_no": (data.get("serial_no") or "").strip(), "issue": issue,
            "accessories": (data.get("accessories") or "").strip(),
            "passcode": (data.get("passcode") or "").strip(),
            "estimate": estimate, "final_cost": estimate, "status": "Received",
            "technician": (data.get("technician") or "").strip(),
            "notes": (data.get("notes") or "").strip(),
            "due_date": (data.get("due_date") or "").strip() or None,
            "received_at": now(), "user_id": user_id})
        ticket = f"RPR-{repair_id:05d}"
        db.execute("UPDATE repairs SET ticket_no = ? WHERE id = ?", (ticket, repair_id))
        db.log(user_id, "repair.create", f"{ticket} {device}")
    return repair_id


def update_repair(db: Database, repair_id: int, data: dict, user_id=None):
    repair = get_repair(db, repair_id)
    fields = {}
    for key in ("device", "brand_model", "serial_no", "issue", "accessories", "passcode",
                "technician", "notes", "due_date"):
        if key in data:
            fields[key] = (data[key] or "").strip()
    if "customer_id" in data:
        fields["customer_id"] = data["customer_id"] or None
    for key in ("estimate", "final_cost"):
        if key in data:
            try:
                fields[key] = money(data[key] or 0)
            except (TypeError, ValueError, ArithmeticError):
                raise POSError(_('{value} must be a number.').format(
                    value=key.replace('_', ' ').title()))
    if "status" in data:
        status = data["status"]
        if status not in REPAIR_STATUSES:
            raise POSError(_('Unknown status: {status}').format(status=status))
        fields["status"] = status
        if status == "Delivered" and repair["status"] != "Delivered":
            fields["delivered_at"] = now()
    db.update("repairs", repair_id, fields)
    db.log(user_id, "repair.update", f"{repair['ticket_no']} {fields.get('status', '')}")


def add_repair_payment(db: Database, repair_id: int, amount: float, method: str = "Cash",
                       user_id=None, shift_id=None) -> int:
    amount = money(amount)
    if amount <= 0:
        raise POSError(_("Amount must be greater than zero."))
    repair = get_repair(db, repair_id)
    with db.transaction():
        pay_id = db.insert("repair_payments", {
            "repair_id": repair_id, "amount": amount, "method": method, "user_id": user_id,
            "shift_id": shift_id, "created_at": now()})
        db.execute("UPDATE repairs SET paid = ROUND(paid + ?, 2) WHERE id = ?", (amount, repair_id))
        db.log(user_id, "repair.payment", f"{repair['ticket_no']} {amount:.2f} {method}")
    return pay_id


def get_repair(db: Database, repair_id: int):
    row = db.one("""SELECT r.*, c.name AS customer_name, c.phone AS customer_phone
                    FROM repairs r LEFT JOIN customers c ON c.id = r.customer_id
                    WHERE r.id = ?""", (repair_id,))
    if not row:
        raise POSError(_("Repair ticket not found."))
    return row


def list_repairs(db: Database, status: str | None = None, search: str = "", open_only: bool = False):
    sql = """SELECT r.*, c.name AS customer_name, c.phone AS customer_phone,
                    ROUND(r.final_cost - r.paid, 2) AS balance
             FROM repairs r LEFT JOIN customers c ON c.id = r.customer_id"""
    where, params = [], []
    if status:
        where.append("r.status = ?")
        params.append(status)
    elif open_only:
        where.append("r.status IN (%s)" % ",".join("?" * len(OPEN_REPAIR_STATUSES)))
        params += list(OPEN_REPAIR_STATUSES)
    if search:
        like = f"%{search.strip()}%"
        where.append("(r.ticket_no LIKE ? OR r.device LIKE ? OR r.brand_model LIKE ? "
                     "OR r.serial_no LIKE ? OR c.name LIKE ? OR c.phone LIKE ?)")
        params += [like] * 6
    if where:
        sql += " WHERE " + " AND ".join(where)
    return db.query(sql + " ORDER BY r.id DESC", params)
