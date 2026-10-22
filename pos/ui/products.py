"""Product catalogue management."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..db import POSError
from ..services import catalog, people
from .app import View
from .widgets import (DataTable, Dialog, SearchBar, ask_form, ask_value, confirm, info,
                      toolbar)


class ProductsView(View):
    title = "Products"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search = SearchBar(bar, self.reload, "name, SKU, barcode, brand", width=32)
        self.search.pack(side="left")
        ttk.Label(bar, text="  Category").pack(side="left")
        self.cat_var = tk.StringVar(value="All")
        self.cat_box = ttk.Combobox(bar, textvariable=self.cat_var, state="readonly", width=18)
        self.cat_box.pack(side="left", padx=6)
        self.cat_box.bind("<<ComboboxSelected>>", lambda e: self.reload())
        self.inactive = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Show inactive", variable=self.inactive, command=self.reload).pack(
            side="left", padx=6)
        self.low_only = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Low stock only", variable=self.low_only, command=self.reload).pack(
            side="left")
        self.count = ttk.Label(bar, text="", style="Muted.TLabel")
        self.count.pack(side="right")

        toolbar(self, [
            ("+ New product", self.new, "Accent.TButton"), ("Edit", self.edit),
            ("Duplicate", self.duplicate), ("Activate / deactivate", self.toggle_active), None,
            ("Adjust stock", self.adjust), ("Stock count", self.count_stock),
            ("Serial numbers", self.serials), ("History", self.history), None,
            ("Categories", lambda: self.lookups("categories")),
            ("Brands", lambda: self.lookups("brands")), None,
            ("Import CSV", self.import_csv), ("Export CSV", self.export_csv),
        ]).pack(fill="x", pady=(0, 8))

        self.table = DataTable(self, [
            ("sku", "SKU", 90), ("barcode", "Barcode", 120), ("name", "Name", 260),
            ("category", "Category", 120), ("brand", "Brand", 100),
            ("cost_price", "Cost", -85, lambda v: f"{v:,.2f}"),
            ("sell_price", "Price", -85, lambda v: f"{v:,.2f}"),
            ("margin", "Margin", -70), ("stock_qty", "Stock", -65),
            ("reorder_level", "Reorder", -70), ("warranty_months", "Warranty (m)", -95),
            ("track_serial", "Serial?", 65, lambda v: "Yes" if v else ""),
            ("location", "Location", 90)], height=20, on_double=lambda r: self.edit())
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        cats = catalog.list_lookup(self.db, "categories")
        self.categories = {c["name"]: c["id"] for c in cats}
        self.cat_box.configure(values=["All"] + list(self.categories))
        self.reload()

    def reload(self):
        cat_id = self.categories.get(self.cat_var.get()) if hasattr(self, "categories") else None
        rows = []
        for r in catalog.list_products(self.db, self.search.get(), cat_id, self.inactive.get(),
                                       self.low_only.get(), limit=5000):
            r = dict(r)
            r["margin"] = (f"{(r['sell_price'] - r['cost_price']) * 100 / r['sell_price']:.0f}%"
                           if r["sell_price"] else "")
            rows.append(r)

        def tag(r):
            if not r["active"]:
                return "muted"
            return "warn" if r["stock_qty"] <= r["reorder_level"] else None

        self.table.set_rows(rows, tag_fn=tag)
        self.count.configure(text=f"{len(rows)} products")

    def selected(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, "Select a product first.", parent=self)
        return row

    # ------------------------------------------------------------- editing
    def fields(self, new: bool):
        cats = [c["name"] for c in catalog.list_lookup(self.db, "categories")]
        brands = [b["name"] for b in catalog.list_lookup(self.db, "brands")]
        suppliers = [""] + [s["name"] for s in people.list_suppliers(self.db)]
        f = [
            {"key": "name", "label": "Name", "required": True},
            {"key": "sku", "label": "SKU / code", "hint": "blank = automatic"},
            {"key": "barcode", "label": "Barcode", "hint": "scan it here"},
            {"key": "category", "label": "Category", "type": "combo", "values": cats, "strict": False},
            {"key": "brand", "label": "Brand", "type": "combo", "values": brands, "strict": False},
            {"key": "supplier", "label": "Supplier", "type": "combo", "values": suppliers},
            {"key": "cost_price", "label": "Cost price", "type": "float", "default": "0"},
            {"key": "sell_price", "label": "Selling price", "type": "float", "required": True},
        ]
        if new:
            f.append({"key": "stock_qty", "label": "Opening stock", "type": "int", "default": "0"})
        f += [
            {"key": "reorder_level", "label": "Reorder level", "type": "int", "default": "2",
             "hint": "alert at or below"},
            {"key": "warranty_months", "label": "Warranty (months)", "type": "int", "default": "0"},
            {"key": "location", "label": "Shelf / location"},
            {"key": "description", "label": "Description", "type": "multiline", "height": 3},
            {"key": "track_serial", "label": "Track serial / IMEI numbers", "type": "check"},
            {"key": "tax_exempt", "label": "Tax exempt", "type": "check"},
        ]
        return f

    def _supplier_id(self, values):
        name = values.pop("supplier", "")
        if not name:
            return None
        for s in people.list_suppliers(self.db, include_inactive=True):
            if s["name"] == name:
                return s["id"]
        return None

    def new(self, initial=None):
        def submit(values):
            values["supplier_id"] = self._supplier_id(values)
            catalog.save_product(self.db, values, self.app.user["id"])
        if ask_form(self, "New product", self.fields(True), initial, on_submit=submit):
            self.on_show()

    def edit(self):
        row = self.selected()
        if not row:
            return
        initial = dict(row)
        initial["supplier"] = row["supplier"] or ""

        def submit(values):
            values["supplier_id"] = self._supplier_id(values)
            values["active"] = row["active"]
            catalog.save_product(self.db, values, self.app.user["id"], row["id"])
        if ask_form(self, f"Edit product — {row['name']}", self.fields(False), initial, on_submit=submit):
            self.on_show()

    def duplicate(self):
        row = self.selected()
        if row:
            initial = dict(row, sku="", barcode="", supplier=row["supplier"] or "", stock_qty=0)
            self.new(initial)

    def toggle_active(self):
        row = self.selected()
        if row:
            catalog.set_active(self.db, row["id"], not row["active"], self.app.user["id"])
            self.reload()

    # --------------------------------------------------------------- stock
    def adjust(self):
        row = self.selected()
        if not row:
            return
        reasons = ["Damaged", "Lost / stolen", "Found", "Internal use", "Supplier return",
                   "Correction", "Other"]
        res = ask_form(self, f"Adjust stock — {row['name']}", [
            {"key": "change", "label": "Change (+ add / − remove)", "type": "int", "required": True},
            {"key": "reason", "label": "Reason", "type": "combo", "values": reasons, "default": "Correction"},
            {"key": "note", "label": "Note"},
        ], ok_text="Apply")
        if res and res["change"]:
            reason = res["reason"] + (f": {res['note']}" if res["note"] else "")
            catalog.adjust_stock(self.db, row["id"], res["change"], reason, self.app.user["id"])
            self.reload()

    def count_stock(self):
        row = self.selected()
        if not row:
            return
        counted = ask_value(self, "Stock count", f"Counted quantity of {row['name']} "
                                                 f"(system says {row['stock_qty']})", "int", row["stock_qty"])
        if counted is not None:
            catalog.set_stock_count(self.db, row["id"], counted, self.app.user["id"])
            self.reload()

    def serials(self):
        row = self.selected()
        if row:
            SerialsDialog(self, self.app, row).show()

    def history(self):
        row = self.selected()
        if not row:
            return
        d = Dialog(self, f"Stock history — {row['name']}")
        t = DataTable(d.body, [("created_at", "Date", 160), ("change", "Change", -70),
                               ("balance", "Balance", -75), ("reason", "Reason", 220),
                               ("ref", "Reference", 120), ("user", "User", 90)], height=16)
        t.set_rows(catalog.stock_movements(self.db, row["id"]))
        t.pack(fill="both", expand=True)
        d.buttons(ok_text="", cancel_text="Close")
        d.show()

    def lookups(self, table):
        LookupDialog(self, self.db, table).show()
        self.on_show()

    # ----------------------------------------------------------------- CSV
    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, title="Import products",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        created, updated, errors = catalog.import_products_csv(self.db, path, self.app.user["id"])
        msg = f"Created {created}, updated {updated} products."
        if errors:
            msg += f"\n\n{len(errors)} rows were skipped:\n" + "\n".join(errors[:15])
        info(self, "Import", msg)
        self.on_show()

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, title="Export products", defaultextension=".csv",
                                            initialfile="products.csv", filetypes=[("CSV files", "*.csv")])
        if path:
            n = catalog.export_products_csv(self.db, path)
            info(self, "Export", f"Exported {n} products to\n{path}")


class SerialsDialog(Dialog):
    def __init__(self, parent, app, product):
        super().__init__(parent, f"Serial numbers — {product['name']}")
        self.app, self.db, self.product = app, app.db, product
        ttk.Label(self.body, text="Registered serial / IMEI numbers. Stock quantity is managed separately "
                                  "(purchases add both).", style="Muted.TLabel", wraplength=520).pack(anchor="w")
        self.table = DataTable(self.body, [("serial_no", "Serial / IMEI", 220), ("status", "Status", 100),
                                           ("created_at", "Added", 160)], height=12)
        self.table.pack(fill="both", expand=True, pady=8)
        toolbar(self.body, [("Add serials", self.add), ("Delete", self.delete)]).pack(fill="x")
        self.buttons(ok_text="", cancel_text="Close")
        self.reload()

    def reload(self):
        self.table.set_rows(catalog.list_serials(self.db, self.product["id"]),
                            tag_fn=lambda r: "ok" if r["status"] == "in_stock" else "muted")

    def add(self):
        res = ask_form(self, "Add serials", [{"key": "serials", "label": "One per line (scan them)",
                                              "type": "multiline", "height": 10}], ok_text="Add")
        if res:
            n = catalog.add_serials(self.db, self.product["id"], res["serials"].splitlines())
            info(self, "Serials", f"Added {n} serial numbers.")
            self.reload()

    def delete(self):
        row = self.table.selected()
        if not row:
            return
        if row["status"] == "sold":
            raise POSError("Sold serial numbers are kept for warranty records.")
        if confirm(self, "Delete", f"Delete serial {row['serial_no']}?"):
            catalog.delete_serial(self.db, row["id"])
            self.reload()


class LookupDialog(Dialog):
    def __init__(self, parent, db, table):
        super().__init__(parent, table.title())
        self.db, self.table_name = db, table
        self.table = DataTable(self.body, [("name", "Name", 260)], height=12,
                               on_double=lambda r: self.rename())
        self.table.pack(fill="both", expand=True)
        toolbar(self.body, [("Add", self.add), ("Rename", self.rename), ("Delete", self.delete)]).pack(
            fill="x", pady=(8, 0))
        self.buttons(ok_text="", cancel_text="Close")
        self.reload()

    def reload(self):
        self.table.set_rows(catalog.list_lookup(self.db, self.table_name))

    def add(self):
        name = ask_value(self, "Add", "Name", "text")
        if name:
            catalog.get_or_create_lookup(self.db, self.table_name, name)
            self.reload()

    def rename(self):
        row = self.table.selected()
        if row:
            name = ask_value(self, "Rename", "New name", "text", row["name"])
            if name:
                catalog.rename_lookup(self.db, self.table_name, row["id"], name)
                self.reload()

    def delete(self):
        row = self.table.selected()
        if row and confirm(self, "Delete", f"Delete '{row['name']}'? Products keep working without it."):
            catalog.delete_lookup(self.db, self.table_name, row["id"])
            self.reload()
