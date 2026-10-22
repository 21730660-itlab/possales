"""Point-of-sale checkout screen."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..db import POSError, money, setting_bool, setting_float
from ..services import catalog, operations, people, receipts, sales
from .app import View
from .widgets import (COLORS, FONT_FAMILY, DataTable, Dialog, FlowFrame, SearchBar, TextPreview,
                      ask_form, ask_value, fmt_money, parse_float, require_permission, toolbar)

SHORTCUTS = ("Enter: add scanned code   F2: qty   F3: find product   F4: line discount   "
             "F5: price   F6: order discount   F7: customer   F8: hold   F9: recall   "
             "Del: remove   F12: PAY")


class SalesView(View):
    title = "New Sale"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.cart = sales.Cart()
        self.totals = None
        self._build()
        self.refresh_cart()

    # ------------------------------------------------------------------ layout
    def _build(self):
        # The totals panel is packed first so it keeps its width on small screens.
        right = ttk.Frame(self, style="Panel.TFrame", padding=16, width=380)
        right.pack(side="right", fill="y", padx=(16, 0))
        right.pack_propagate(False)
        left = ttk.Frame(self)
        left.pack(side="left", fill="both", expand=True)

        scan = ttk.Frame(left)
        scan.pack(fill="x")
        ttk.Label(scan, text="Scan barcode / SKU / serial, or type a name:",
                  style="H2.TLabel").pack(anchor="w")
        row = ttk.Frame(scan)
        row.pack(fill="x", pady=(4, 10))
        self.code_var = tk.StringVar()
        self.code_entry = ttk.Entry(row, textvariable=self.code_var, font=(FONT_FAMILY, 16))
        self.code_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.code_entry.bind("<Return>", lambda e: self.add_code())
        ttk.Label(row, text=" Qty").pack(side="left")
        self.qty_var = tk.StringVar(value="1")
        ttk.Spinbox(row, from_=1, to=9999, textvariable=self.qty_var, width=5,
                    font=(FONT_FAMILY, 14)).pack(side="left", padx=6)
        ttk.Button(row, text="Add", style="Accent.TButton", command=self.add_code).pack(side="left")
        ttk.Button(row, text="🔍 Find (F3)", command=self.find_product).pack(side="left", padx=(6, 0))

        self.table = DataTable(left, [
            ("n", "#", 36), ("name", "Item", 210), ("serial_no", "Serial / IMEI", 140),
            ("qty", "Qty", -50), ("price", "Price", -85), ("discount", "Discount", -80),
            ("total", "Total", -95)], height=14, on_double=lambda r: self.change_qty())
        # Bottom widgets are packed first (bottom-up) so the cart table takes whatever height is left.
        hint = ttk.Label(left, text=SHORTCUTS, style="Muted.TLabel", wraplength=680)
        hint.pack(anchor="w", pady=(8, 0), side="bottom")
        toolbar(left, [("Qty (F2)", self.change_qty), ("+  1", lambda: self.bump_qty(1)),
                       ("−  1", lambda: self.bump_qty(-1)), ("Discount (F4)", self.line_discount),
                       ("Price (F5)", self.change_price), ("Remove (Del)", self.remove_line), None,
                       ("Clear sale", self.clear_sale, "Danger.TButton")]).pack(
            fill="x", pady=(10, 0), side="bottom")
        self.table.pack(fill="both", expand=True)

        # Right side: customer, totals and payment.
        ttk.Label(right, text="Customer", style="CardTitle.TLabel").pack(anchor="w")
        self.cust_label = ttk.Label(right, text="Walk-in customer", style="Panel.TLabel",
                                    font=(FONT_FAMILY, 13, "bold"), wraplength=340)
        self.cust_label.pack(anchor="w")
        self.cust_info = ttk.Label(right, text="", style="CardTitle.TLabel", wraplength=340)
        self.cust_info.pack(anchor="w")
        cb = ttk.Frame(right, style="Panel.TFrame")
        cb.pack(fill="x", pady=(6, 12))
        ttk.Button(cb, text="Select (F7)", command=self.select_customer).pack(side="left")
        ttk.Button(cb, text="Remove", command=self.clear_customer).pack(side="left", padx=6)
        ttk.Separator(right).pack(fill="x", pady=6)

        self.sum_labels = {}
        for key, text in (("items", "Items"), ("subtotal", "Subtotal"), ("discount_total", "Discount"),
                          ("tax_total", "Tax")):
            line = ttk.Frame(right, style="Panel.TFrame")
            line.pack(fill="x", pady=2)
            lbl = ttk.Label(line, text=text, style="Panel.TLabel", font=(FONT_FAMILY, 13))
            lbl.pack(side="left")
            val = ttk.Label(line, text="0", style="Panel.TLabel", font=(FONT_FAMILY, 13))
            val.pack(side="right")
            self.sum_labels[key] = val
            if key == "tax_total":
                self.tax_name_label = lbl
        ttk.Separator(right).pack(fill="x", pady=8)
        ttk.Label(right, text="TOTAL", style="CardTitle.TLabel").pack(anchor="w")
        self.total_label = ttk.Label(right, text="$0.00", style="Total.TLabel")
        self.total_label.pack(anchor="e")
        self.alt_label = ttk.Label(right, text="", style="CardTitle.TLabel", font=(FONT_FAMILY, 13))
        self.alt_label.pack(anchor="e")

        ttk.Button(right, text="💳  PAY  (F12)", style="Pay.TButton", command=self.pay).pack(
            fill="x", pady=(16, 8), side="bottom")
        ob = ttk.Frame(right, style="Panel.TFrame")
        ob.pack(fill="x", side="bottom")
        ttk.Button(ob, text="Order discount (F6)", command=self.order_discount).pack(fill="x", pady=2)
        hb = ttk.Frame(ob, style="Panel.TFrame")
        hb.pack(fill="x", pady=2)
        ttk.Button(hb, text="Hold (F8)", command=self.hold).pack(side="left", fill="x", expand=True)
        ttk.Button(hb, text="Recall (F9)", command=self.recall).pack(side="left", fill="x",
                                                                    expand=True, padx=(6, 0))
        ttk.Button(ob, text="Note", command=self.edit_note).pack(fill="x", pady=2)
        ttk.Button(ob, text="Open cash drawer", command=self.kick_drawer).pack(fill="x", pady=2)
        self.held_label = ttk.Label(ob, text="", style="CardTitle.TLabel")
        self.held_label.pack(anchor="w", pady=(4, 0))

    def on_show(self):
        top = self.winfo_toplevel()
        keys = {"<F2>": self.change_qty, "<F3>": self.find_product, "<F4>": self.line_discount,
                "<F5>": self.change_price, "<F6>": self.order_discount, "<F7>": self.select_customer,
                "<F8>": self.hold, "<F9>": self.recall, "<F12>": self.pay,
                "<Control-Return>": self.pay}
        for seq, fn in keys.items():
            top.bind(seq, lambda e, f=fn: self._if_visible(f))
        self.table.tree.bind("<Delete>", lambda e: self.remove_line())
        self.refresh_cart()
        self.code_entry.focus_set()

    def _if_visible(self, fn):
        if self.app.current == "sales" and self.winfo_ismapped():
            fn()
            return "break"

    # ---------------------------------------------------------------- helpers
    def tax_rate(self) -> float:
        return setting_float(self.db.get_settings(), "tax_rate")

    def refresh_cart(self):
        settings = self.db.get_settings()
        sym = settings.get("currency_symbol", "$")
        self.totals = sales.compute_totals(self.cart, setting_float(settings, "tax_rate"))
        rows = []
        for i, (line, calc) in enumerate(zip(self.cart.lines, self.totals["lines"])):
            rows.append({"id": i, "n": i + 1, "name": line.name, "serial_no": line.serial_no,
                         "qty": line.qty, "price": f"{line.unit_price:,.2f}",
                         "discount": f"{calc['discount']:,.2f}" if calc["discount"] else "",
                         "total": f"{calc['total']:,.2f}"})
        sel = self.table.tree.selection()
        self.table.set_rows(rows)
        if sel and self.table.tree.exists(sel[0]):
            self.table.tree.selection_set(sel[0])
        elif rows:
            last = str(len(rows) - 1)
            self.table.tree.selection_set(last)
            self.table.tree.see(last)
        t = self.totals
        self.sum_labels["items"].configure(text=str(t["items"]))
        self.sum_labels["subtotal"].configure(text=fmt_money(t["subtotal"], sym))
        self.sum_labels["discount_total"].configure(
            text=("-" if t["discount_total"] else "") + fmt_money(t["discount_total"], sym))
        self.sum_labels["tax_total"].configure(text=fmt_money(t["tax_total"], sym))
        self.tax_name_label.configure(
            text=f"{settings.get('tax_name', 'Tax')} ({setting_float(settings, 'tax_rate'):g}%)")
        self.total_label.configure(text=fmt_money(t["total"], sym))
        alt = receipts.secondary(t["total"], settings)
        self.alt_label.configure(text=alt or "")
        held = len(sales.list_held(self.db))
        self.held_label.configure(text=f"{held} sale(s) on hold" if held else "")
        self._refresh_customer()

    def _refresh_customer(self):
        if not self.cart.customer_id:
            self.cust_label.configure(text="Walk-in customer")
            self.cust_info.configure(text="")
            return
        try:
            c = people.get_customer(self.db, self.cart.customer_id)
        except POSError:
            self.cart.customer_id = None
            return self._refresh_customer()
        self.cust_label.configure(text=c["name"])
        bits = [c["phone"]] if c["phone"] else []
        bits.append(f"Points: {c['loyalty_points']}")
        if c["balance"]:
            bits.append(f"Owes: {fmt_money(c['balance'], self.currency)}")
        self.cust_info.configure(text="   ".join(bits))

    def selected_line(self, quiet=False):
        row = self.table.selected()
        if row is None:
            if not quiet:
                messagebox.showinfo("Sale", "Select a line in the cart first.", parent=self)
            return None, None
        return row["id"], self.cart.lines[row["id"]]

    # ------------------------------------------------------------ adding items
    def add_code(self):
        code = self.code_var.get().strip()
        if not code:
            if self.cart.lines:
                self.pay()
            return
        qty = self._qty()
        product, serial = catalog.find_by_code(self.db, code)
        if product:
            self.add_product(product, qty, serial)
        else:
            self.find_product(code)
        self.code_var.set("")
        self.qty_var.set("1")
        self.code_entry.focus_set()

    def find_product(self, search=""):
        picked = ProductPicker(self, self.app, search).show()
        if picked:
            self.add_product(picked, self._qty())
        self.code_entry.focus_set()

    def _qty(self) -> int:
        try:
            return max(1, int(self.qty_var.get() or 1))
        except ValueError:
            return 1

    def add_product(self, product, qty=1, serial=""):
        if product["track_serial"] and not serial:
            for _ in range(qty):
                serial = SerialPicker(self, self.db, product, self.cart).show()
                if not serial:
                    break
                self._add(product, 1, serial)
            self.refresh_cart()
            return
        self._add(product, qty, serial)
        self.refresh_cart()

    def _add(self, product, qty, serial):
        if serial and any(l.serial_no.lower() == serial.lower() for l in self.cart.lines):
            raise POSError(f"Serial {serial} is already in the cart.")
        in_cart = sum(l.qty for l in self.cart.lines if l.product_id == product["id"])
        allow_neg = setting_bool(self.db.get_settings(), "allow_negative_stock")
        stock = self.db.scalar("SELECT stock_qty FROM products WHERE id = ?", (product["id"],), 0)
        if not allow_neg and in_cart + qty > stock:
            raise POSError(f"Only {stock} of '{product['name']}' in stock.")
        self.cart.add_product(product, qty, serial)

    # ---------------------------------------------------------- line actions
    def change_qty(self):
        idx, line = self.selected_line()
        if line is None:
            return
        if line.serial_no:
            raise POSError("Items with a serial number are sold one per line.")
        qty = ask_value(self, "Quantity", f"Quantity for {line.name}", "int", line.qty)
        if qty is None:
            return
        self._set_qty(line, qty)

    def bump_qty(self, delta):
        idx, line = self.selected_line()
        if line is None:
            return
        if line.serial_no:
            raise POSError("Items with a serial number are sold one per line.")
        self._set_qty(line, line.qty + delta)

    def _set_qty(self, line, qty):
        if qty <= 0:
            self.cart.lines.remove(line)
        else:
            stock = self.db.scalar("SELECT stock_qty FROM products WHERE id = ?", (line.product_id,), 0)
            other = sum(l.qty for l in self.cart.lines if l.product_id == line.product_id and l is not line)
            if not setting_bool(self.db.get_settings(), "allow_negative_stock") and qty + other > stock:
                raise POSError(f"Only {stock} of '{line.name}' in stock.")
            line.qty = qty
            line.discount = min(line.discount, line.gross)
        self.refresh_cart()

    def remove_line(self):
        idx, line = self.selected_line()
        if line is not None:
            del self.cart.lines[idx]
            self.refresh_cart()

    def line_discount(self):
        idx, line = self.selected_line()
        if line is None:
            return
        res = DiscountDialog(self, f"Discount — {line.name}", line.gross, line.discount,
                             self.currency).show()
        if res is None:
            return
        old = line.discount
        line.discount = res
        if not self._discount_allowed():
            line.discount = old
        self.refresh_cart()

    def order_discount(self):
        if not self.cart.lines:
            return
        base = money(sum(l.gross - l.discount for l in self.cart.lines))
        res = DiscountDialog(self, "Order discount", base, self.cart.order_discount, self.currency).show()
        if res is None:
            return
        old = self.cart.order_discount
        self.cart.order_discount = res
        if not self._discount_allowed():
            self.cart.order_discount = old
        self.refresh_cart()

    def _discount_allowed(self) -> bool:
        limit = setting_float(self.db.get_settings(), "cashier_max_discount_pct", 100)
        pct = sales.discount_percent(self.cart, self.tax_rate())
        if pct <= limit + 1e-9:
            return True
        return require_permission(self, self.app, "discount_override",
                                  f"A discount of {pct:.1f}% is above the {limit:g}% limit.")

    def change_price(self):
        idx, line = self.selected_line()
        if line is None:
            return
        if not require_permission(self, self.app, "price_override", "Changing an item price."):
            return
        price = ask_value(self, "Price", f"Unit price for {line.name}", "float", f"{line.unit_price:.2f}")
        if price is None:
            return
        if price < 0:
            raise POSError("Price cannot be negative.")
        line.unit_price = money(price)
        line.discount = min(line.discount, line.gross)
        self.refresh_cart()

    def edit_note(self):
        res = ask_form(self, "Sale note", [{"key": "notes", "label": "Note (printed on invoice)",
                                            "type": "multiline"}], {"notes": self.cart.notes}, ok_text="OK")
        if res is not None:
            self.cart.notes = res["notes"]

    # -------------------------------------------------------------- customer
    def select_customer(self):
        cid = CustomerPicker(self, self.app).show()
        if cid:
            self.cart.customer_id = cid
            self.refresh_cart()

    def clear_customer(self):
        self.cart.customer_id = None
        self.refresh_cart()

    # ---------------------------------------------------------- hold / recall
    def hold(self):
        if not self.cart.lines:
            return
        res = ask_form(self, "Hold sale", [{"key": "label", "label": "Label (e.g. customer name)"}],
                       ok_text="Hold")
        if res is None:
            return
        sales.hold_cart(self.db, self.cart, self.app.user["id"], res["label"])
        self.cart = sales.Cart()
        self.refresh_cart()

    def recall(self):
        held = sales.list_held(self.db)
        if not held:
            messagebox.showinfo("Recall", "There are no held sales.", parent=self)
            return
        if self.cart.lines and not messagebox.askyesno(
                "Recall", "Put the current cart on hold first?", parent=self):
            return
        held_id = HeldPicker(self, self.db, held).show()
        if not held_id:
            return
        if self.cart.lines:
            sales.hold_cart(self.db, self.cart, self.app.user["id"], "Auto-held")
        self.cart = sales.resume_held(self.db, held_id)
        self.refresh_cart()

    def clear_sale(self):
        if self.cart.lines and not messagebox.askyesno("Clear", "Remove all items from this sale?",
                                                       parent=self):
            return
        self.cart = sales.Cart()
        self.refresh_cart()
        self.code_entry.focus_set()

    def kick_drawer(self):
        if not require_permission(self, self.app, "shifts", "Opening the cash drawer."):
            return
        self.db.log(self.app.user["id"], "drawer.open", "no sale")
        if not receipts.open_cash_drawer(self.db):
            messagebox.showinfo("Cash drawer", "No receipt printer with a cash drawer is configured "
                                "(Settings → Printer name, requires pywin32).", parent=self)

    # ------------------------------------------------------------------ pay
    def ensure_shift(self):
        shift_id = self.app.current_shift_id()
        if shift_id or not setting_bool(self.db.get_settings(), "require_open_shift"):
            return shift_id or None, True
        amount = ask_value(self, "Open shift", "No shift is open. Opening cash in drawer:", "float", "0")
        if amount is None:
            return None, False
        shift_id = operations.open_shift(self.db, self.app.user["id"], amount)
        self.app.refresh_status()
        return shift_id, True

    def pay(self):
        if not self.cart.lines:
            messagebox.showinfo("Pay", "The cart is empty.", parent=self)
            return
        shift_id, ok = self.ensure_shift()
        if not ok:
            return
        self.refresh_cart()
        payments = PaymentDialog(self, self.app, self.totals["total"], self.cart.customer_id).show()
        if payments is None:
            return
        sale_id = sales.checkout(self.db, self.cart, payments, self.app.user["id"], shift_id)
        self.cart = sales.Cart()
        self.refresh_cart()
        self.after_sale(sale_id, any(p["method"] == "Cash" for p in payments))

    def after_sale(self, sale_id, used_cash):
        settings = self.db.get_settings()
        sale = sales.get_sale(self.db, sale_id)["sale"]
        text = receipts.sale_receipt(self.db, sale_id)
        drawer = used_cash and setting_bool(settings, "open_cash_drawer")

        def do_print():
            receipts.print_text(self.db, text, sale["invoice_no"], open_drawer=drawer)

        if setting_bool(settings, "auto_print_receipt"):
            try:
                do_print()
            except Exception as exc:
                messagebox.showerror("Print", f"Could not print the receipt: {exc}", parent=self)
        else:
            receipts.save_text(text, sale["invoice_no"])
            if drawer:
                receipts.open_cash_drawer(self.db)
        change = sale["change_due"]
        title = f"Sale complete — {sale['invoice_no']}"
        if change:
            title += f"   CHANGE: {fmt_money(change, self.currency)}"
        TextPreview(self, title, text, on_print=do_print).show()
        self.code_entry.focus_set()


# =============================================================== dialogs
class ProductPicker(Dialog):
    def __init__(self, parent, app, search=""):
        super().__init__(parent, "Find product")
        self.db = app.db
        self.search = SearchBar(self.body, self.reload, "name, SKU, barcode or brand", width=40)
        self.search.pack(fill="x")
        self.table = DataTable(self.body, [
            ("sku", "SKU", 100), ("name", "Name", 320), ("brand", "Brand", 110),
            ("stock_qty", "Stock", -70), ("sell_price", "Price", -100, lambda v: f"{v:,.2f}"),
            ("location", "Location", 90)], height=14, on_double=self.choose)
        self.table.pack(fill="both", expand=True, pady=10)
        self.buttons(ok_text="Add to sale")
        self.search.var.set(search)
        self.reload()
        self.search.entry.bind("<Down>", lambda e: (self.table.tree.focus_set(), self.table.select_first()))
        self.search.entry.bind("<Return>", lambda e: self.ok())
        self.after(50, self.search.entry.focus_set)

    def reload(self):
        rows = catalog.list_products(self.db, self.search.get(), limit=300)
        self.table.set_rows(rows, tag_fn=lambda r: "warn" if r["stock_qty"] <= 0 else None)
        self.table.select_first()

    def choose(self, row):
        self.result = catalog.get_product(self.db, row["id"])
        self.destroy()

    def ok(self):
        row = self.table.selected()
        if row:
            self.choose(row)


class SerialPicker(Dialog):
    def __init__(self, parent, db, product, cart):
        super().__init__(parent, f"Serial / IMEI — {product['name']}")
        in_cart = {l.serial_no.lower() for l in cart.lines if l.serial_no}
        serials = [s for s in catalog.list_serials(db, product["id"], "in_stock")
                   if s["serial_no"].lower() not in in_cart]
        ttk.Label(self.body, text="Scan or type the serial number, or pick one in stock:").pack(anchor="w")
        self.var = tk.StringVar()
        e = ttk.Entry(self.body, textvariable=self.var, font=(FONT_FAMILY, 14), width=34)
        e.pack(fill="x", pady=8)
        self.listbox = tk.Listbox(self.body, height=min(10, max(3, len(serials))), font=(FONT_FAMILY, 12))
        for s in serials:
            self.listbox.insert("end", s["serial_no"])
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda ev: self._pick())
        self.listbox.bind("<Double-1>", lambda ev: self.ok())
        if not serials:
            ttk.Label(self.body, text="No serials registered in stock — type the serial from the box.",
                      style="Muted.TLabel").pack(anchor="w")
        self.buttons(ok_text="Use serial")
        e.bind("<Return>", lambda ev: self.ok())
        self.after(50, e.focus_set)

    def _pick(self):
        sel = self.listbox.curselection()
        if sel:
            self.var.set(self.listbox.get(sel[0]))

    def ok(self):
        value = self.var.get().strip()
        if not value:
            messagebox.showwarning(self.title(), "Enter a serial number.", parent=self)
            return
        self.result = value
        self.destroy()


class DiscountDialog(Dialog):
    def __init__(self, parent, title, base, current, symbol):
        super().__init__(parent, title)
        self.base = base
        ttk.Label(self.body, text=f"Amount before discount: {fmt_money(base, symbol)}").pack(anchor="w")
        self.mode = tk.StringVar(value="percent")
        f = ttk.Frame(self.body)
        f.pack(fill="x", pady=8)
        ttk.Radiobutton(f, text="Percent %", variable=self.mode, value="percent").pack(side="left")
        ttk.Radiobutton(f, text=f"Amount {symbol}", variable=self.mode, value="amount").pack(
            side="left", padx=12)
        self.var = tk.StringVar(value=f"{current * 100 / base:g}" if current and base else "")
        e = ttk.Entry(self.body, textvariable=self.var, font=(FONT_FAMILY, 14))
        e.pack(fill="x")
        quick = ttk.Frame(self.body)
        quick.pack(fill="x", pady=8)
        for pct in (5, 10, 15, 20, 0):
            ttk.Button(quick, text=f"{pct}%" if pct else "None",
                       command=lambda p=pct: (self.mode.set("percent"), self.var.set(str(p)), self.ok())
                       ).pack(side="left", padx=(0, 4))
        self.buttons(ok_text="Apply")
        e.bind("<Return>", lambda ev: self.ok())
        self.after(50, e.focus_set)

    def ok(self):
        try:
            value = parse_float(self.var.get(), "Discount")
        except POSError as exc:
            messagebox.showwarning(self.title(), str(exc), parent=self)
            return
        if value < 0:
            messagebox.showwarning(self.title(), "Discount cannot be negative.", parent=self)
            return
        amount = self.base * value / 100 if self.mode.get() == "percent" else value
        if amount > self.base + 0.001:
            messagebox.showwarning(self.title(), "Discount is larger than the amount.", parent=self)
            return
        self.result = money(amount)
        self.destroy()


class CustomerPicker(Dialog):
    def __init__(self, parent, app):
        super().__init__(parent, "Select customer")
        self.app, self.db = app, app.db
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        self.search = SearchBar(top, self.reload, "name, phone or email", width=34)
        self.search.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="+ New customer", command=self.new).pack(side="right")
        self.table = DataTable(self.body, [
            ("name", "Name", 220), ("phone", "Phone", 130), ("loyalty_points", "Points", -80),
            ("balance", "Balance", -100, lambda v: f"{v:,.2f}")], height=12, on_double=self.choose)
        self.table.pack(fill="both", expand=True, pady=10)
        self.buttons(ok_text="Select")
        self.search.entry.bind("<Return>", lambda e: self.ok())
        self.search.entry.bind("<Down>", lambda e: (self.table.tree.focus_set(), self.table.select_first()))
        self.reload()
        self.after(50, self.search.entry.focus_set)

    def reload(self):
        self.table.set_rows(people.list_customers(self.db, self.search.get(), limit=300))
        self.table.select_first()

    def new(self):
        from .customers import CUSTOMER_FIELDS
        initial = {"phone": self.search.get()} if self.search.get().replace("+", "").isdigit() else \
            {"name": self.search.get()}
        res = ask_form(self, "New customer", CUSTOMER_FIELDS, initial)
        if res:
            self.result = people.save_customer(self.db, res, user_id=self.app.user["id"])
            self.destroy()

    def choose(self, row):
        self.result = row["id"]
        self.destroy()

    def ok(self):
        row = self.table.selected()
        if row:
            self.choose(row)


class HeldPicker(Dialog):
    def __init__(self, parent, db, held):
        super().__init__(parent, "Held sales")
        self.db = db
        rows = []
        for h in held:
            cart = sales.Cart.from_json(h["data"])
            rows.append({"id": h["id"], "label": h["label"], "customer": h["customer_name"] or "",
                         "items": sum(l.qty for l in cart.lines), "user": h["user"],
                         "created_at": h["created_at"]})
        self.table = DataTable(self.body, [
            ("label", "Label", 180), ("customer", "Customer", 160), ("items", "Items", -60),
            ("user", "By", 90), ("created_at", "Held at", 160)], height=10, on_double=self.choose)
        self.table.set_rows(rows)
        self.table.select_first()
        self.table.pack(fill="both", expand=True)
        bar = self.buttons(ok_text="Resume")
        ttk.Button(bar, text="Delete", style="Danger.TButton", command=self.delete).pack(side="left")

    def delete(self):
        row = self.table.selected()
        if row and messagebox.askyesno("Delete", "Delete this held sale?", parent=self):
            sales.delete_held(self.db, row["id"])
            self.table.tree.delete(self.table.tree.selection())

    def choose(self, row):
        self.result = row["id"]
        self.destroy()

    def ok(self):
        row = self.table.selected()
        if row:
            self.choose(row)


class PaymentDialog(Dialog):
    """Collects one or more payments (split tender) for a total."""

    def __init__(self, parent, app, total, customer_id):
        super().__init__(parent, "Payment")
        self.db = app.db
        self.settings = self.db.get_settings()
        self.sym = self.settings.get("currency_symbol", "$")
        self.rate = setting_float(self.settings, "exchange_rate")
        self.alt_code = self.settings.get("secondary_currency", "")
        self.show_alt = setting_bool(self.settings, "show_secondary_currency") and self.rate > 0
        self.total = total
        self.customer = people.get_customer(self.db, customer_id) if customer_id else None
        self.payments: list[dict] = []

        top = ttk.Frame(self.body, style="Panel.TFrame", padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="Amount due", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(top, text=fmt_money(total, self.sym), style="Total.TLabel").pack(anchor="w")
        if self.show_alt:
            ttk.Label(top, text=f"{self.alt_code} {total * self.rate:,.0f}   (rate {self.rate:,.0f})",
                      style="CardTitle.TLabel", font=(FONT_FAMILY, 13)).pack(anchor="w")

        methods = [m for m in sales.payment_methods(self.settings)
                   if m not in ("Account", "Points") or self.customer]
        self.method = tk.StringVar(value="Cash")
        mf = FlowFrame(self.body, gap=12, height=28)  # wraps when the shop has many methods
        mf.pack(fill="x", pady=(12, 4))
        for m in methods:
            ttk.Radiobutton(mf, text=m, variable=self.method, value=m, command=self._method_changed)
        if self.customer:
            pv = setting_float(self.settings, "loyalty_point_value")
            ttk.Label(self.body, style="Muted.TLabel",
                      text=f"{self.customer['name']}: {self.customer['loyalty_points']} points "
                           f"(worth {fmt_money(self.customer['loyalty_points'] * pv, self.sym)}), "
                           f"account balance {fmt_money(self.customer['balance'], self.sym)}").pack(anchor="w")

        entry_row = ttk.Frame(self.body)
        entry_row.pack(fill="x", pady=6)
        ttk.Label(entry_row, text=f"Amount ({self.sym})").pack(side="left")
        self.amount = tk.StringVar()
        self.amount_entry = ttk.Entry(entry_row, textvariable=self.amount, font=(FONT_FAMILY, 16), width=12)
        self.amount_entry.pack(side="left", padx=8)
        ttk.Label(entry_row, text="Ref").pack(side="left")
        self.ref = tk.StringVar()
        ttk.Entry(entry_row, textvariable=self.ref, width=14).pack(side="left", padx=6)
        ttk.Button(entry_row, text="Add payment", style="Accent.TButton", command=self.add_payment).pack(
            side="left")
        self.amount_entry.bind("<Return>", lambda e: self.add_payment())

        if self.show_alt:
            alt_row = ttk.Frame(self.body)
            alt_row.pack(fill="x", pady=4)
            ttk.Label(alt_row, text=f"Cash in {self.alt_code}").pack(side="left")
            self.alt_amount = tk.StringVar()
            ae = ttk.Entry(alt_row, textvariable=self.alt_amount, font=(FONT_FAMILY, 14), width=14)
            ae.pack(side="left", padx=8)
            ttk.Button(alt_row, text=f"Add {self.alt_code} cash", command=self.add_alt).pack(side="left")
            ae.bind("<Return>", lambda e: self.add_alt())

        quick = ttk.Frame(self.body)
        quick.pack(fill="x", pady=6)
        ttk.Button(quick, text="Exact amount", command=self.exact).pack(side="left", padx=(0, 4))
        for note in (5, 10, 20, 50, 100):
            ttk.Button(quick, text=f"{self.sym}{note}",
                       command=lambda n=note: self._quick_cash(n)).pack(side="left", padx=(0, 4))

        self.list = DataTable(self.body, [("method", "Method", 160), ("reference", "Reference", 180),
                                          ("amount", "Amount", -110, lambda v: f"{v:,.2f}")], height=4)
        self.list.pack(fill="both", expand=True, pady=6)
        ttk.Button(self.body, text="Remove selected payment", command=self.remove).pack(anchor="w")

        self.status = ttk.Label(self.body, text="", font=(FONT_FAMILY, 16, "bold"))
        self.status.pack(anchor="e", pady=(8, 0))
        self.alt_status = ttk.Label(self.body, text="", style="Muted.TLabel", font=(FONT_FAMILY, 12))
        self.alt_status.pack(anchor="e")

        bar = ttk.Frame(self.body)
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="Cancel", command=self.cancel).pack(side="right", padx=(8, 0))
        self.complete_btn = ttk.Button(bar, text="✔ Complete sale", style="Pay.TButton", command=self.ok)
        self.complete_btn.pack(side="right")
        self.bind("<F12>", lambda e: self.ok())
        self.update_status()
        self.after(50, self.amount_entry.focus_set)

    def paid(self):
        return money(sum(p["amount"] for p in self.payments))

    def remaining(self):
        return money(self.total - self.paid())

    def _method_changed(self):
        rem = max(0, self.remaining())
        if self.method.get() == "Points" and self.customer:
            pv = setting_float(self.settings, "loyalty_point_value")
            rem = min(rem, money(self.customer["loyalty_points"] * pv))
        if self.method.get() != "Cash":
            self.amount.set(f"{rem:.2f}" if rem else "")
        self.amount_entry.focus_set()
        self.amount_entry.select_range(0, "end")

    def update_status(self):
        rem = self.remaining()
        if rem > 0:
            self.status.configure(text=f"Remaining: {fmt_money(rem, self.sym)}", foreground=COLORS["danger"])
            alt = f"{self.alt_code} {rem * self.rate:,.0f}" if self.show_alt else ""
            self.complete_btn.state(["disabled"])
        else:
            self.status.configure(text=f"Change: {fmt_money(-rem, self.sym)}", foreground=COLORS["success"])
            alt = f"Change in {self.alt_code}: {max(0.0, -rem) * self.rate:,.0f}" if self.show_alt else ""
            self.complete_btn.state(["!disabled"])
        self.alt_status.configure(text=alt)
        self.list.set_rows([dict(p, id=i) for i, p in enumerate(self.payments)])

    def add_payment(self, method=None, amount=None, ref=None):
        method = method or self.method.get()
        try:
            amount = money(parse_float(self.amount.get(), "Amount")) if amount is None else money(amount)
        except POSError as exc:
            messagebox.showwarning("Payment", str(exc), parent=self)
            return
        if amount <= 0:
            if self.remaining() <= 0:
                self.ok()
                return
            amount = self.remaining()
        if method != "Cash" and amount > self.remaining() + 0.001:
            messagebox.showwarning("Payment", f"{method} cannot be more than the remaining amount.",
                                   parent=self)
            return
        self.payments.append({"method": method, "amount": amount,
                              "reference": self.ref.get().strip() if ref is None else ref})
        self.amount.set("")
        self.ref.set("")
        self.method.set("Cash")
        self.update_status()
        self.amount_entry.focus_set()

    def add_alt(self):
        try:
            value = parse_float(self.alt_amount.get(), "Amount")
        except POSError as exc:
            messagebox.showwarning("Payment", str(exc), parent=self)
            return
        if value <= 0:
            return
        self.add_payment("Cash", money(value / self.rate), f"{self.alt_code} {value:,.0f}")
        self.alt_amount.set("")

    def exact(self):
        rem = self.remaining()
        if rem > 0:
            self.add_payment(self.method.get(), rem)

    def _quick_cash(self, note):
        self.add_payment("Cash", note)

    def remove(self):
        row = self.list.selected()
        if row is not None:
            del self.payments[row["id"]]
            self.update_status()

    def ok(self):
        if not self.payments and self.amount.get().strip():
            self.add_payment()
            if self.remaining() > 0:
                return
        if self.remaining() > 0.001:
            messagebox.showwarning("Payment", "The full amount has not been paid yet.", parent=self)
            return
        self.result = self.payments
        self.destroy()
