"""Purchase orders and receiving stock from suppliers."""
from __future__ import annotations

from ..db import Database, POSError, money, now
from ..i18n import _
from . import catalog


def create_po(db: Database, supplier_id: int | None, items: list[dict], notes: str = "",
              user_id=None) -> int:
    """`items` is a list of {"product_id", "qty", "unit_cost"}."""
    items = [i for i in items if int(i.get("qty") or 0) > 0]
    if not items:
        raise POSError(_("Add at least one product to the purchase order."))
    with db.transaction():
        po_id = db.insert("purchase_orders", {
            "supplier_id": supplier_id, "user_id": user_id, "created_at": now(),
            "status": "ordered", "notes": notes})
        po_no = f"PO-{po_id:06d}"
        total = 0.0
        for item in items:
            qty, cost = int(item["qty"]), money(item.get("unit_cost") or 0)
            if cost < 0:
                raise POSError(_("Unit cost cannot be negative."))
            db.insert("purchase_items", {"po_id": po_id, "product_id": int(item["product_id"]),
                                         "qty": qty, "unit_cost": cost})
            total = money(total + qty * cost)
        db.execute("UPDATE purchase_orders SET po_no = ?, total = ? WHERE id = ?",
                   (po_no, total, po_id))
        db.log(user_id, "po.create", f"{po_no} total={total:.2f}")
    return po_id


def list_pos(db: Database, status: str | None = None):
    sql = """SELECT po.*, s.name AS supplier, u.username AS user FROM purchase_orders po
             LEFT JOIN suppliers s ON s.id = po.supplier_id
             LEFT JOIN users u ON u.id = po.user_id"""
    params = []
    if status:
        sql += " WHERE po.status = ?"
        params.append(status)
    return db.query(sql + " ORDER BY po.id DESC", params)


def get_po(db: Database, po_id: int) -> dict:
    po = db.one("""SELECT po.*, s.name AS supplier FROM purchase_orders po
                   LEFT JOIN suppliers s ON s.id = po.supplier_id WHERE po.id = ?""", (po_id,))
    if not po:
        raise POSError(_("Purchase order not found."))
    items = db.query("""SELECT pi.*, p.name, p.sku, p.track_serial FROM purchase_items pi
                        JOIN products p ON p.id = pi.product_id WHERE pi.po_id = ?
                        ORDER BY pi.id""", (po_id,))
    return {"po": po, "items": items}


def receive_po(db: Database, po_id: int, received: dict[int, int], user_id=None,
               serials: dict[int, list[str]] | None = None, update_cost: bool = True):
    """Receive stock. `received` maps purchase_item_id -> qty received now.

    Product cost is updated with a weighted average of old stock and new stock.
    """
    serials = serials or {}
    data = get_po(db, po_id)
    po = data["po"]
    if po["status"] in ("received", "cancelled"):
        raise POSError(_('This purchase order is already {status}.').format(status=po['status']))
    with db.transaction():
        any_received = False
        for item in data["items"]:
            qty = int(received.get(item["id"], 0) or 0)
            if qty <= 0:
                continue
            outstanding = item["qty"] - item["received_qty"]
            if qty > outstanding:
                raise POSError(_("Only {outstanding} of '{name}' are outstanding.").format(
                    outstanding=outstanding, name=item['name']))
            item_serials = [s for s in serials.get(item["id"], []) if s.strip()]
            if item_serials and len(item_serials) != qty:
                raise POSError(_("Enter {qty} serial numbers for '{name}' (got {len}).").format(
                    qty=qty, name=item['name'], len=len(item_serials)))
            product = db.one("SELECT stock_qty, cost_price FROM products WHERE id = ?",
                             (item["product_id"],))
            if update_cost:
                old_qty = max(product["stock_qty"], 0)
                new_cost = item["unit_cost"] if old_qty == 0 else money(
                    (old_qty * product["cost_price"] + qty * item["unit_cost"]) / (old_qty + qty))
                db.execute("UPDATE products SET cost_price = ?, updated_at = ? WHERE id = ?",
                           (new_cost, now(), item["product_id"]))
            catalog.adjust_stock(db, item["product_id"], qty, "Purchase received", user_id,
                                 po["po_no"])
            if item_serials:
                catalog.add_serials(db, item["product_id"], item_serials, purchase_id=po_id)
            db.execute("UPDATE purchase_items SET received_qty = received_qty + ? WHERE id = ?",
                       (qty, item["id"]))
            any_received = True
        if not any_received:
            raise POSError(_("Enter a received quantity for at least one item."))
        outstanding = db.scalar("SELECT SUM(qty - received_qty) FROM purchase_items WHERE po_id = ?",
                                (po_id,), 0)
        status = "received" if outstanding == 0 else "partial"
        db.execute("UPDATE purchase_orders SET status = ?, received_at = ? WHERE id = ?",
                   (status, now(), po_id))
        db.log(user_id, "po.receive", f"{po['po_no']} status={status}")


def cancel_po(db: Database, po_id: int, user_id=None):
    po = get_po(db, po_id)["po"]
    if po["status"] != "ordered":
        raise POSError(_("Only purchase orders with nothing received can be cancelled."))
    db.execute("UPDATE purchase_orders SET status = 'cancelled' WHERE id = ?", (po_id,))
    db.log(user_id, "po.cancel", po["po_no"])
