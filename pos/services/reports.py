"""Sales, profit, inventory and expense reports."""
from __future__ import annotations

import csv

from ..db import Database, money

# Profit per sold item, net of tax and of any units that were returned later.
ITEM_NET = "(i.line_total - i.tax) * (i.qty - i.returned_qty) * 1.0 / i.qty"
ITEM_COST = "i.unit_cost * (i.qty - i.returned_qty)"


def sales_summary(db: Database, d1: str, d2: str) -> dict:
    s = db.one("""SELECT COUNT(*) AS n, COALESCE(SUM(subtotal),0) AS gross,
                         COALESCE(SUM(discount_total),0) AS discounts,
                         COALESCE(SUM(tax_total),0) AS tax, COALESCE(SUM(total),0) AS total
                  FROM sales WHERE date(created_at) BETWEEN ? AND ?""", (d1, d2))
    r = db.one("""SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS total,
                         COALESCE(SUM(ri_tax),0) AS tax FROM (
                    SELECT r.total, (SELECT SUM(tax) FROM return_items WHERE return_id = r.id) AS ri_tax
                    FROM returns r WHERE date(r.created_at) BETWEEN ? AND ?)""", (d1, d2))
    items = db.one(f"""SELECT COALESCE(SUM(i.qty),0) AS units,
                              COALESCE(SUM({ITEM_NET}),0) AS net, COALESCE(SUM({ITEM_COST}),0) AS cost
                       FROM sale_items i JOIN sales s ON s.id = i.sale_id
                       WHERE date(s.created_at) BETWEEN ? AND ?""", (d1, d2))
    net_sales = money(s["total"] - r["total"])
    return {
        "transactions": s["n"],
        "units": items["units"],
        "gross_sales": money(s["gross"]),
        "discounts": money(s["discounts"]),
        "tax_collected": money(s["tax"] - r["tax"]),
        "sales_total": money(s["total"]),
        "returns_count": r["n"],
        "returns_total": money(r["total"]),
        "net_sales": net_sales,
        "avg_sale": money(s["total"] / s["n"]) if s["n"] else 0.0,
        "revenue_ex_tax": money(items["net"]),
        "cost_of_goods": money(items["cost"]),
        "gross_profit": money(items["net"] - items["cost"]),
    }


def profit_and_loss(db: Database, d1: str, d2: str) -> dict:
    summary = sales_summary(db, d1, d2)
    repairs = db.scalar("SELECT SUM(amount) FROM repair_payments WHERE date(created_at) BETWEEN ? AND ?",
                        (d1, d2), 0)
    expenses = db.scalar("SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?", (d1, d2), 0)
    by_cat = db.query("""SELECT category, SUM(amount) AS amount FROM expenses
                         WHERE date BETWEEN ? AND ? GROUP BY category ORDER BY amount DESC""", (d1, d2))
    net = money(summary["gross_profit"] + repairs - expenses)
    return {**summary, "repair_income": money(repairs), "expenses": money(expenses),
            "expenses_by_category": by_cat, "net_profit": net}


def daily_sales(db: Database, d1: str, d2: str):
    return db.query(f"""SELECT date(s.created_at) AS day, COUNT(DISTINCT s.id) AS sales,
                               SUM(i.qty) AS units,
                               ROUND(SUM(i.line_total), 2) AS total,
                               ROUND(SUM(i.tax), 2) AS tax,
                               ROUND(SUM({ITEM_NET} - {ITEM_COST}), 2) AS profit
                        FROM sales s JOIN sale_items i ON i.sale_id = s.id
                        WHERE date(s.created_at) BETWEEN ? AND ?
                        GROUP BY day ORDER BY day""", (d1, d2))


def top_products(db: Database, d1: str, d2: str, limit: int = 50):
    return db.query(f"""SELECT i.sku, i.name, SUM(i.qty - i.returned_qty) AS units,
                               ROUND(SUM({ITEM_NET}), 2) AS revenue,
                               ROUND(SUM({ITEM_NET} - {ITEM_COST}), 2) AS profit
                        FROM sale_items i JOIN sales s ON s.id = i.sale_id
                        WHERE date(s.created_at) BETWEEN ? AND ?
                        GROUP BY i.product_id, i.name ORDER BY revenue DESC LIMIT ?""", (d1, d2, limit))


def sales_by_category(db: Database, d1: str, d2: str):
    return db.query(f"""SELECT COALESCE(c.name, '(none)') AS category,
                               SUM(i.qty - i.returned_qty) AS units,
                               ROUND(SUM({ITEM_NET}), 2) AS revenue,
                               ROUND(SUM({ITEM_NET} - {ITEM_COST}), 2) AS profit
                        FROM sale_items i JOIN sales s ON s.id = i.sale_id
                        LEFT JOIN products p ON p.id = i.product_id
                        LEFT JOIN categories c ON c.id = p.category_id
                        WHERE date(s.created_at) BETWEEN ? AND ?
                        GROUP BY category ORDER BY revenue DESC""", (d1, d2))


def sales_by_brand(db: Database, d1: str, d2: str):
    return db.query(f"""SELECT COALESCE(b.name, '(none)') AS brand,
                               SUM(i.qty - i.returned_qty) AS units,
                               ROUND(SUM({ITEM_NET}), 2) AS revenue,
                               ROUND(SUM({ITEM_NET} - {ITEM_COST}), 2) AS profit
                        FROM sale_items i JOIN sales s ON s.id = i.sale_id
                        LEFT JOIN products p ON p.id = i.product_id
                        LEFT JOIN brands b ON b.id = p.brand_id
                        WHERE date(s.created_at) BETWEEN ? AND ?
                        GROUP BY brand ORDER BY revenue DESC""", (d1, d2))


def sales_by_cashier(db: Database, d1: str, d2: str):
    return db.query("""SELECT u.username AS cashier, COUNT(*) AS sales, ROUND(SUM(s.total), 2) AS total,
                              ROUND(SUM(s.discount_total), 2) AS discounts
                       FROM sales s JOIN users u ON u.id = s.user_id
                       WHERE date(s.created_at) BETWEEN ? AND ?
                       GROUP BY u.id ORDER BY total DESC""", (d1, d2))


def sales_by_hour(db: Database, d1: str, d2: str):
    return db.query("""SELECT strftime('%H', created_at) || ':00' AS hour, COUNT(*) AS sales,
                              ROUND(SUM(total), 2) AS total
                       FROM sales WHERE date(created_at) BETWEEN ? AND ?
                       GROUP BY hour ORDER BY hour""", (d1, d2))


def payments_by_method(db: Database, d1: str, d2: str):
    return db.query("""SELECT p.method, COUNT(*) AS count, ROUND(SUM(p.amount), 2) AS amount
                       FROM payments p JOIN sales s ON s.id = p.sale_id
                       WHERE date(s.created_at) BETWEEN ? AND ?
                       GROUP BY p.method ORDER BY amount DESC""", (d1, d2))


def top_customers(db: Database, d1: str, d2: str, limit: int = 50):
    return db.query("""SELECT c.name, c.phone, COUNT(s.id) AS sales, ROUND(SUM(s.total), 2) AS total,
                              c.loyalty_points AS points, c.balance
                       FROM sales s JOIN customers c ON c.id = s.customer_id
                       WHERE date(s.created_at) BETWEEN ? AND ?
                       GROUP BY c.id ORDER BY total DESC LIMIT ?""", (d1, d2, limit))


def inventory_valuation(db: Database):
    rows = db.query("""SELECT p.sku, p.name, COALESCE(c.name, '') AS category, p.stock_qty,
                              p.cost_price, p.sell_price,
                              ROUND(p.stock_qty * p.cost_price, 2) AS cost_value,
                              ROUND(p.stock_qty * p.sell_price, 2) AS retail_value
                       FROM products p LEFT JOIN categories c ON c.id = p.category_id
                       WHERE p.active = 1 AND p.stock_qty > 0 ORDER BY cost_value DESC""")
    totals = {
        "units": sum(r["stock_qty"] for r in rows),
        "cost_value": money(sum(r["cost_value"] for r in rows)),
        "retail_value": money(sum(r["retail_value"] for r in rows)),
    }
    return rows, totals


def slow_movers(db: Database, days: int = 60):
    """In-stock products that have not sold in `days` days."""
    return db.query("""SELECT p.sku, p.name, p.stock_qty,
                              ROUND(p.stock_qty * p.cost_price, 2) AS cost_value,
                              (SELECT MAX(s.created_at) FROM sale_items i JOIN sales s ON s.id = i.sale_id
                               WHERE i.product_id = p.id) AS last_sold
                       FROM products p
                       WHERE p.active = 1 AND p.stock_qty > 0 AND NOT EXISTS (
                           SELECT 1 FROM sale_items i JOIN sales s ON s.id = i.sale_id
                           WHERE i.product_id = p.id AND s.created_at >= datetime('now', 'localtime', ?))
                       ORDER BY cost_value DESC""", (f"-{int(days)} days",))


def expenses_report(db: Database, d1: str, d2: str):
    return db.query("""SELECT category, COUNT(*) AS count, ROUND(SUM(amount), 2) AS amount
                       FROM expenses WHERE date BETWEEN ? AND ?
                       GROUP BY category ORDER BY amount DESC""", (d1, d2))


def receivables(db: Database):
    return db.query("""SELECT name, phone, balance, credit_limit FROM customers
                       WHERE balance > 0.004 ORDER BY balance DESC""")


def dashboard(db: Database, day: str) -> dict:
    summary = sales_summary(db, day, day)
    return {
        **summary,
        "low_stock": db.scalar("SELECT COUNT(*) FROM products WHERE active=1 AND stock_qty <= reorder_level",
                               default=0),
        "open_repairs": db.scalar("""SELECT COUNT(*) FROM repairs WHERE status NOT IN
                                     ('Delivered','Cancelled')""", default=0),
        "ready_repairs": db.scalar("SELECT COUNT(*) FROM repairs WHERE status = 'Ready for Pickup'",
                                   default=0),
        "receivables": money(db.scalar("SELECT SUM(balance) FROM customers WHERE balance > 0", default=0)),
        "products": db.scalar("SELECT COUNT(*) FROM products WHERE active = 1", default=0),
        "customers": db.scalar("SELECT COUNT(*) FROM customers", default=0),
    }


def write_csv(path: str, headers: list[str], rows) -> int:
    count = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for row in rows:
            # Rows are either plain sequences or mappings keyed by the headers.
            writer.writerow(list(row) if isinstance(row, (list, tuple)) else [row[h] for h in headers])
            count += 1
    return count
