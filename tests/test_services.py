import os
import tempfile
import unittest

from pos.db import Database, POSError
from pos.services import (auth, barcodes, catalog, operations, people, purchasing, receipts,
                          reports, sales)


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["POS_DATA_DIR"] = self.tmp.name
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        self.db.set_settings({"tax_rate": "10", "loyalty_points_per_unit": "1",
                              "loyalty_point_value": "0.1"})
        auth.ensure_default_admin(self.db)
        self.admin = auth.authenticate(self.db, "admin", "admin")
        self.uid = self.admin["id"]
        self.phone = catalog.get_product(self.db, catalog.save_product(self.db, {
            "sku": "PH1", "barcode": "111", "name": "Phone X", "category": "Phones",
            "brand": "Acme", "cost_price": 200, "sell_price": 300, "stock_qty": 5,
            "warranty_months": 12, "track_serial": 1}, self.uid))
        self.cable = catalog.get_product(self.db, catalog.save_product(self.db, {
            "sku": "CB1", "barcode": "222", "name": "USB-C Cable", "category": "Accessories",
            "cost_price": 2, "sell_price": 5, "stock_qty": 50, "reorder_level": 10}, self.uid))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class AuthTests(BaseCase):
    def test_login_and_wrong_password(self):
        self.assertTrue(self.admin["must_change_password"])
        with self.assertRaises(POSError):
            auth.authenticate(self.db, "admin", "nope")

    def test_permissions(self):
        uid = auth.create_user(self.db, "cash", "1234", "Cashier", "cashier")
        user = auth.get_user(self.db, uid)
        self.assertTrue(auth.has_permission(user, "sales"))
        self.assertFalse(auth.has_permission(user, "reports"))
        self.assertTrue(auth.has_permission(self.admin, "settings"))

    def test_cannot_demote_last_admin(self):
        with self.assertRaises(POSError):
            auth.update_user(self.db, self.uid, "Admin", "cashier", True)


class CatalogTests(BaseCase):
    def test_find_by_code_and_serial(self):
        product, serial = catalog.find_by_code(self.db, "111")
        self.assertEqual(product["id"], self.phone["id"])
        catalog.add_serials(self.db, self.phone["id"], ["SN-1", "SN-2"])
        product, serial = catalog.find_by_code(self.db, "SN-2")
        self.assertEqual((product["id"], serial), (self.phone["id"], "SN-2"))

    def test_duplicate_sku_rejected(self):
        with self.assertRaises(POSError):
            catalog.save_product(self.db, {"sku": "PH1", "name": "Dup"})

    def test_stock_count_and_low_stock(self):
        catalog.set_stock_count(self.db, self.cable["id"], 8, self.uid)
        self.assertEqual(catalog.get_product(self.db, self.cable["id"])["stock_qty"], 8)
        self.assertIn(self.cable["id"], [p["id"] for p in catalog.low_stock(self.db)])

    def test_csv_round_trip(self):
        path = os.path.join(self.tmp.name, "p.csv")
        self.assertEqual(catalog.export_products_csv(self.db, path), 2)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("NEW1,333,Charger,,Accessories,,3,9,4,1,0,0,0,,1\n")
        created, updated, errors = catalog.import_products_csv(self.db, path)
        self.assertEqual((created, updated, errors), (1, 2, []))
        product, _ = catalog.find_by_code(self.db, "333")
        self.assertEqual(product["stock_qty"], 4)
        self.assertEqual(catalog.get_product(self.db, self.cable["id"])["stock_qty"], 50)


class CartTests(unittest.TestCase):
    def test_totals_with_order_discount(self):
        cart = sales.Cart()
        cart.lines = [sales.CartLine(1, "A", "A", 2, 50.0),
                      sales.CartLine(2, "B", "B", 1, 100.0, discount=10, tax_exempt=True)]
        cart.order_discount = 19
        t = sales.compute_totals(cart, 10)
        self.assertEqual(t["subtotal"], 200)
        self.assertEqual(t["discount_total"], 29)
        # Line A: net 100 - 10 share = 90, tax 9; line B: 90 - 9 share = 81, exempt.
        self.assertEqual([l["total"] for l in t["lines"]], [99.0, 81.0])
        self.assertEqual(t["total"], 180.0)

    def test_hold_round_trip(self):
        cart = sales.Cart(customer_id=3, order_discount=1.5)
        cart.lines.append(sales.CartLine(1, "A", "A", 2, 9.99, serial_no="X"))
        again = sales.Cart.from_json(cart.to_json())
        self.assertEqual(again, cart)

    def test_add_months(self):
        from datetime import date
        self.assertEqual(sales.add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(sales.add_months(date(2024, 11, 15), 14), date(2026, 1, 15))


class CheckoutTests(BaseCase):
    def make_cart(self, customer_id=None):
        cart = sales.Cart(customer_id=customer_id)
        cart.add_product(self.phone, serial_no="IMEI-1")
        cart.add_product(self.cable, 2)
        cart.add_product(self.cable, 1)
        return cart

    def test_checkout_updates_everything(self):
        cust = people.save_customer(self.db, {"name": "Ali", "phone": "70123456"})
        shift = operations.open_shift(self.db, self.uid, 100)
        cart = self.make_cart(cust)
        self.assertEqual(len(cart.lines), 2)  # cables merged
        total = sales.compute_totals(cart, 10)["total"]  # (300 + 15) * 1.1
        self.assertEqual(total, 346.5)
        sale_id = sales.checkout(self.db, cart, [
            {"method": "Card", "amount": 300}, {"method": "Cash", "amount": 50}], self.uid, shift)
        data = sales.get_sale(self.db, sale_id)
        self.assertEqual(data["sale"]["change_due"], 3.5)
        self.assertEqual({p["method"]: p["amount"] for p in data["payments"]},
                         {"Card": 300, "Cash": 46.5})
        self.assertEqual(catalog.get_product(self.db, self.cable["id"])["stock_qty"], 47)
        self.assertEqual(catalog.get_product(self.db, self.phone["id"])["stock_qty"], 4)
        self.assertEqual(people.get_customer(self.db, cust)["loyalty_points"], 346)
        self.assertTrue(data["items"][0]["warranty_until"])
        self.assertEqual(operations.shift_summary(self.db, shift)["expected_cash"], 146.5)
        text = receipts.sale_receipt(self.db, sale_id)
        self.assertIn("IMEI-1", text)
        self.assertIn("$346.50", text)
        # The same serial cannot be sold twice.
        again = sales.Cart()
        again.add_product(self.phone, serial_no="IMEI-1")
        with self.assertRaises(POSError):
            sales.checkout(self.db, again, [{"method": "Cash", "amount": 999}], self.uid)

    def test_validation(self):
        cart = self.make_cart()
        with self.assertRaises(POSError):  # short payment
            sales.checkout(self.db, cart, [{"method": "Cash", "amount": 10}], self.uid)
        with self.assertRaises(POSError):  # card overpay
            sales.checkout(self.db, cart, [{"method": "Card", "amount": 1000}], self.uid)
        with self.assertRaises(POSError):  # account needs customer
            sales.checkout(self.db, cart, [{"method": "Account", "amount": 346.5}], self.uid)
        big = sales.Cart()
        big.add_product(self.cable, 51)
        with self.assertRaises(POSError):  # not enough stock
            sales.checkout(self.db, big, [{"method": "Cash", "amount": 1000}], self.uid)
        serial_missing = sales.Cart()
        serial_missing.add_product(self.phone)
        with self.assertRaises(POSError):
            sales.checkout(self.db, serial_missing, [{"method": "Cash", "amount": 1000}], self.uid)

    def test_account_and_points(self):
        cust = people.save_customer(self.db, {"name": "Rami", "credit_limit": 100})
        cart = sales.Cart(customer_id=cust)
        cart.add_product(self.cable, 10)  # 55.00
        sales.checkout(self.db, cart, [{"method": "Account", "amount": 55}], self.uid)
        c = people.get_customer(self.db, cust)
        self.assertEqual((c["balance"], c["loyalty_points"]), (55, 55))
        cart = sales.Cart(customer_id=cust)
        cart.add_product(self.cable, 10)
        with self.assertRaises(POSError):  # credit limit
            sales.checkout(self.db, cart, [{"method": "Account", "amount": 55}], self.uid)
        sales.checkout(self.db, cart, [{"method": "Points", "amount": 5.5},
                                       {"method": "Cash", "amount": 49.5}], self.uid)
        c = people.get_customer(self.db, cust)
        self.assertEqual(c["loyalty_points"], 55 - 55 + 49)
        people.receive_account_payment(self.db, cust, 20, user_id=self.uid)
        self.assertEqual(people.get_customer(self.db, cust)["balance"], 35)

    def test_return_partial_then_full(self):
        cust = people.save_customer(self.db, {"name": "Ali"})
        cart = sales.Cart(customer_id=cust)
        cart.add_product(self.cable, 3)
        sale_id = sales.checkout(self.db, cart, [{"method": "Cash", "amount": 20}], self.uid)
        item = sales.returnable_items(self.db, sale_id)[0]
        r1 = sales.process_return(self.db, sale_id, {item["id"]: 1}, "faulty", "Cash", True, self.uid)
        r2 = sales.process_return(self.db, sale_id, {item["id"]: 2}, "", "Cash", False, self.uid)
        totals = [sales.get_return(self.db, r)["return"]["total"] for r in (r1, r2)]
        self.assertAlmostEqual(sum(totals), 16.5)  # refunds add up to the line total
        self.assertEqual(sales.get_sale(self.db, sale_id)["sale"]["status"], "returned")
        self.assertEqual(catalog.get_product(self.db, self.cable["id"])["stock_qty"], 48)
        self.assertEqual(people.get_customer(self.db, cust)["loyalty_points"], 0)
        with self.assertRaises(POSError):
            sales.process_return(self.db, sale_id, {item["id"]: 1}, "", "Cash", True, self.uid)
        self.assertIn("RET-", receipts.return_receipt(self.db, r1))

    def test_held_sales(self):
        held = sales.hold_cart(self.db, self.make_cart(), self.uid, "Table 1")
        self.assertEqual(len(sales.list_held(self.db)), 1)
        cart = sales.resume_held(self.db, held)
        self.assertEqual(cart.lines[0].serial_no, "IMEI-1")
        self.assertEqual(len(sales.list_held(self.db)), 0)

    def test_warranty_lookup(self):
        sales.checkout(self.db, self.make_cart(), [{"method": "Cash", "amount": 400}], self.uid)
        rows = sales.warranty_lookup(self.db, "IMEI-1")
        self.assertEqual(len(rows), 1)


class PurchasingTests(BaseCase):
    def test_receive_updates_cost_and_stock(self):
        sup = people.save_supplier(self.db, {"name": "Tech Wholesale"})
        po = purchasing.create_po(self.db, sup, [
            {"product_id": self.phone["id"], "qty": 5, "unit_cost": 230}], user_id=self.uid)
        item = purchasing.get_po(self.db, po)["items"][0]
        with self.assertRaises(POSError):  # serial count mismatch
            purchasing.receive_po(self.db, po, {item["id"]: 2}, serials={item["id"]: ["A"]})
        purchasing.receive_po(self.db, po, {item["id"]: 2}, self.uid, {item["id"]: ["A", "B"]})
        self.assertEqual(purchasing.get_po(self.db, po)["po"]["status"], "partial")
        p = catalog.get_product(self.db, self.phone["id"])
        self.assertEqual(p["stock_qty"], 7)
        self.assertEqual(p["cost_price"], round((5 * 200 + 2 * 230) / 7, 2))
        purchasing.receive_po(self.db, po, {item["id"]: 3}, self.uid)
        self.assertEqual(purchasing.get_po(self.db, po)["po"]["status"], "received")
        self.assertEqual(len(catalog.list_serials(self.db, self.phone["id"], "in_stock")), 2)


class OperationsTests(BaseCase):
    def test_shift_cash_reconciliation(self):
        shift = operations.open_shift(self.db, self.uid, 50)
        with self.assertRaises(POSError):
            operations.open_shift(self.db, self.uid, 50)
        operations.cash_movement(self.db, shift, "in", 20, "change float", self.uid)
        operations.cash_movement(self.db, shift, "out", 5, "coffee", self.uid)
        operations.add_expense(self.db, {"amount": 10, "category": "Transport",
                                         "paid_from_drawer": True}, self.uid, shift)
        rep = operations.create_repair(self.db, {"device": "Laptop", "issue": "No power",
                                                 "estimate": 40}, self.uid)
        operations.add_repair_payment(self.db, rep, 15, "Cash", self.uid, shift)
        summary = operations.close_shift(self.db, shift, 69, self.uid)
        self.assertEqual(summary["expected_cash"], 70)
        self.assertIn("OVER / SHORT", receipts.z_report(self.db, shift))
        self.assertIsNone(operations.current_shift(self.db))

    def test_repair_flow(self):
        rep = operations.create_repair(self.db, {"device": "Phone", "issue": "Screen"}, self.uid)
        operations.update_repair(self.db, rep, {"status": "Delivered", "final_cost": 60}, self.uid)
        r = operations.get_repair(self.db, rep)
        self.assertTrue(r["delivered_at"])
        self.assertIn("RPR-", receipts.repair_ticket(self.db, rep))
        with self.assertRaises(POSError):
            operations.update_repair(self.db, rep, {"status": "Bogus"})


class ReportTests(BaseCase):
    def test_reports(self):
        cart = sales.Cart()
        cart.add_product(self.cable, 4)  # revenue ex tax 20, cost 8
        sale_id = sales.checkout(self.db, cart, [{"method": "Cash", "amount": 22}], self.uid)
        item = sales.returnable_items(self.db, sale_id)[0]
        sales.process_return(self.db, sale_id, {item["id"]: 1}, "", "Cash", True, self.uid)
        operations.add_expense(self.db, {"amount": 3}, self.uid)
        day = sales.get_sale(self.db, sale_id)["sale"]["created_at"][:10]
        pl = reports.profit_and_loss(self.db, day, day)
        self.assertEqual(pl["revenue_ex_tax"], 15)
        self.assertEqual(pl["gross_profit"], 9)
        self.assertEqual(pl["net_profit"], 6)
        self.assertEqual(pl["net_sales"], 16.5)
        self.assertEqual(reports.top_products(self.db, day, day)[0]["units"], 3)
        rows, totals = reports.inventory_valuation(self.db)
        self.assertEqual(totals["units"], 5 + 47)
        path = os.path.join(self.tmp.name, "r.csv")
        self.assertEqual(reports.write_csv(path, ["day", "total"], reports.daily_sales(self.db, day, day)), 1)
        self.assertTrue(reports.dashboard(self.db, day)["transactions"])


class PaymentMethodTests(BaseCase):
    def test_custom_methods(self):
        self.db.set_settings({"payment_methods": "Whish Money, OMT, Cash, Whish Money"})
        settings = self.db.get_settings()
        self.assertEqual(sales.payment_methods(settings),
                         ["Cash", "Whish Money", "OMT", "Account", "Points"])
        cart = sales.Cart()
        cart.add_product(self.cable, 2)
        with self.assertRaises(POSError):  # Card was removed from the list
            sales.checkout(self.db, cart, [{"method": "Card", "amount": 11}], self.uid)
        sale_id = sales.checkout(self.db, cart, [{"method": "Whish Money", "amount": 11}], self.uid)
        self.assertEqual(sales.get_sale(self.db, sale_id)["payments"][0]["method"], "Whish Money")
        item = sales.returnable_items(self.db, sale_id)[0]
        sales.process_return(self.db, sale_id, {item["id"]: 1}, "", "OMT", True, self.uid)


class ArabicReceiptTests(BaseCase):
    def sale(self):
        cart = sales.Cart()
        cart.add_product(self.phone, serial_no="IMEI-9")
        return sales.checkout(self.db, cart, [{"method": "Cash", "amount": 400}], self.uid)

    def test_languages(self):
        self.db.set_settings({"shop_name_ar": "متجر الإلكترونيات"})
        sale_id = self.sale()
        english = receipts.sale_receipt(self.db, sale_id)
        self.assertNotIn("المجموع", english)
        self.db.set_settings({"receipt_language": "ar"})
        arabic = receipts.sale_receipt(self.db, sale_id)
        self.assertIn("المجموع", arabic)
        self.assertIn("متجر الإلكترونيات", arabic)
        self.assertIn("نقداً", arabic)
        self.assertNotIn("Subtotal", arabic)
        # Right-to-left layout: the amount starts the line and the Arabic label ends it.
        total_line = next(l for l in arabic.splitlines() if l.endswith("المجموع"))
        self.assertTrue(total_line.startswith("$"))
        self.assertEqual(len(total_line), 42)
        self.assertFalse(receipts.is_plain(arabic))
        self.db.set_settings({"receipt_language": "both"})
        both = receipts.sale_receipt(self.db, sale_id)
        self.assertIn("المجموع الفرعي Subtotal", both)
        self.assertTrue(all(len(line) <= 42 for line in both.splitlines()))
        rep = operations.create_repair(self.db, {"device": "Phone", "issue": "Screen"}, self.uid)
        self.assertIn("مستلم", receipts.repair_ticket(self.db, rep))
        path = receipts.save_text(arabic, "ar_test")
        with open(path, encoding="utf-8-sig") as fh:
            self.assertEqual(fh.read(), arabic)


class BarcodeTests(BaseCase):
    def test_code128_checksum(self):
        # "PJJ123C" in set B: (104 + 48*1 + 42*2 + 42*3 + 17*4 + 18*5 + 19*6 + 35*7) % 103 = 55.
        values = barcodes.code128_values("PJJ123C")
        self.assertEqual(values[0], barcodes.START_B)
        self.assertEqual(values[-2], 55)
        self.assertEqual(barcodes.code128_values("123456")[:4], [barcodes.START_C, 12, 34, 56])
        odd = barcodes.code128_values("12345")
        self.assertEqual(odd[:5], [barcodes.START_C, 12, 34, barcodes.CODE_B, ord("5") - 32])
        with self.assertRaises(POSError):
            barcodes.code128_values("هاتف")

    def test_generate_and_labels(self):
        catalog.save_product(self.db, {"sku": "NB1", "name": "سماعة بلوتوث", "sell_price": 20})
        self.assertEqual(catalog.assign_missing_barcodes(self.db), 1)
        product, _ = catalog.find_by_code(self.db, "NB1")
        code = product["barcode"]
        self.assertEqual(len(code), 13)
        self.assertEqual(code[-1], barcodes.ean13_check_digit(code[:12]))
        self.assertEqual(catalog.next_internal_barcode(self.db)[:12], "200000000002")
        items = barcodes.label_items(self.db, {product["id"]: 2, self.cable["id"]: 1})
        page = barcodes.labels_html(items, self.db.get_settings(), sheet=True)
        self.assertEqual(page.count('class="label"'), 3)
        self.assertIn("سماعة بلوتوث", page)
        zpl = barcodes.labels_zpl(items, self.db.get_settings())
        self.assertIn(f"^FD{code}^FS", zpl)
        self.assertIn("^PQ2^XZ", zpl)
        tspl = barcodes.labels_tspl(items, self.db.get_settings())
        self.assertIn('"128"', tspl)
        self.assertIn("PRINT 1,2", tspl)
        self.db.set_settings({"label_format": "zpl"})
        msg = barcodes.print_labels(self.db, {self.cable["id"]: 1})
        self.assertIn("ZPL", msg)


class DataFolderTests(unittest.TestCase):
    def test_installed_vs_portable(self):
        import sys
        from unittest import mock
        from pos import db as dbmod
        with tempfile.TemporaryDirectory() as tmp:
            exe_dir = os.path.join(tmp, "Electronics POS")
            os.makedirs(exe_dir)
            env = {k: v for k, v in os.environ.items() if k != "POS_DATA_DIR"}
            env["PROGRAMDATA"] = os.path.join(tmp, "ProgramData")
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "executable", os.path.join(exe_dir, "POS.exe")):
                # Portable copy: data next to the program.
                self.assertEqual(dbmod.app_data_dir(), os.path.join(exe_dir, "data"))
                # Installed copy: data in ProgramData (Program Files is read-only).
                open(os.path.join(exe_dir, dbmod.INSTALLED_MARKER), "w").close()
                self.assertEqual(dbmod.app_data_dir(), os.path.join(tmp, "ProgramData", "ElectronicsPOS"))


class BackupTests(BaseCase):
    def test_backup_restore(self):
        path = os.path.join(self.tmp.name, "backup.db")
        self.db.backup_to(path)
        catalog.save_product(self.db, {"name": "After backup"})
        self.db.restore_from(path)
        self.assertEqual(len(catalog.list_products(self.db)), 2)


if __name__ == "__main__":
    unittest.main()
