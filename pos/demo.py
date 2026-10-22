"""Sample data for trying the system."""
from __future__ import annotations

from .db import Database
from .services import catalog, people

PRODUCTS = [
    # sku, barcode, name, category, brand, cost, price, stock, reorder, warranty, serial
    ("PH-IP15-128", "194253401", "iPhone 15 128GB", "Smartphones", "Apple", 690, 799, 6, 2, 12, 1),
    ("PH-S24-256", "880609512", "Galaxy S24 256GB", "Smartphones", "Samsung", 620, 749, 5, 2, 12, 1),
    ("PH-RN13", "690622713", "Redmi Note 13 128GB", "Smartphones", "Xiaomi", 150, 199, 10, 3, 12, 1),
    ("LT-HP15", "196068115", "HP 15 Laptop i5 / 8GB / 512GB", "Laptops", "HP", 430, 549, 4, 1, 12, 1),
    ("LT-LEN-IP3", "196802333", "Lenovo IdeaPad 3 Ryzen 5", "Laptops", "Lenovo", 400, 499, 3, 1, 12, 1),
    ("TB-IPAD10", "194253387", "iPad 10th gen 64GB", "Tablets", "Apple", 320, 379, 3, 1, 12, 1),
    ("TV-SAM-55", "880609555", "Samsung 55\" 4K Smart TV", "TVs", "Samsung", 380, 479, 2, 1, 24, 1),
    ("AC-USBC-1M", "600000001", "USB-C cable 1m", "Accessories", "Anker", 2.5, 7, 60, 15, 3, 0),
    ("AC-LTN-1M", "600000002", "Lightning cable 1m", "Accessories", "Anker", 3, 9, 40, 10, 3, 0),
    ("AC-CHG-20W", "600000003", "20W USB-C fast charger", "Accessories", "Anker", 6, 15, 35, 10, 6, 0),
    ("AC-PB-10K", "600000004", "Power bank 10000mAh", "Accessories", "Anker", 12, 25, 20, 5, 6, 0),
    ("AC-CASE-IP15", "600000005", "iPhone 15 silicone case", "Accessories", "Generic", 2, 10, 25, 5, 0, 0),
    ("AC-GLASS", "600000006", "Tempered glass screen protector", "Accessories", "Generic", 0.5, 5, 100, 20, 0, 0),
    ("AU-AIRP2", "194253398", "AirPods (2nd gen)", "Audio", "Apple", 95, 129, 8, 2, 12, 1),
    ("AU-JBL-GO3", "605086301", "JBL Go 3 speaker", "Audio", "JBL", 28, 45, 12, 3, 12, 0),
    ("ST-SD-64", "619659188", "microSD 64GB", "Storage", "SanDisk", 5, 12, 30, 8, 24, 0),
    ("ST-USB-128", "619659189", "USB flash drive 128GB", "Storage", "SanDisk", 8, 16, 25, 6, 24, 0),
    ("PC-MOUSE-WL", "509920001", "Wireless mouse", "Computer accessories", "Logitech", 7, 15, 20, 5, 12, 0),
    ("PC-KB-USB", "509920002", "USB keyboard", "Computer accessories", "Logitech", 8, 18, 15, 4, 12, 0),
    ("NW-ROUTER", "693536401", "Wi-Fi 6 router", "Networking", "TP-Link", 35, 59, 6, 2, 24, 1),
]


def load_demo_data(db: Database, user_id=None) -> int:
    supplier = db.one("SELECT id FROM suppliers WHERE name = 'Demo Electronics Wholesale'")
    supplier_id = supplier["id"] if supplier else people.save_supplier(
        db, {"name": "Demo Electronics Wholesale", "contact": "Sales desk", "phone": "01 000000"}, user_id=user_id)
    if not db.one("SELECT id FROM customers WHERE phone = '70000000'"):
        people.save_customer(db, {"name": "Sample Customer", "phone": "70000000"}, user_id=user_id)
    added = 0
    for sku, barcode, name, cat, brand, cost, price, stock, reorder, warranty, serial in PRODUCTS:
        if db.one("SELECT 1 FROM products WHERE sku = ?", (sku,)):
            continue
        pid = catalog.save_product(db, {
            "sku": sku, "barcode": barcode, "name": name, "category": cat, "brand": brand,
            "supplier_id": supplier_id, "cost_price": cost, "sell_price": price, "stock_qty": stock,
            "reorder_level": reorder, "warranty_months": warranty, "track_serial": serial}, user_id)
        if serial:
            catalog.add_serials(db, pid, [f"{sku}-SN{n:03d}" for n in range(1, stock + 1)])
        added += 1
    return added
