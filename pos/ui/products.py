"""Product catalogue management."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..db import POSError
from ..i18n import _, tr_reason, tr_value
from ..services import barcodes, catalog, people
from .app import View
from .widgets import (END, START, W, DataTable, Dialog, SearchBar, ask_form, ask_value, confirm,
                      info, toolbar)

ADJUST_REASONS = ("Damaged", "Lost / stolen", "Found", "Internal use", "Supplier return",
                  "Correction", "Other")
LOOKUP_TITLES = {"categories": _("Categories"), "brands": _("Brands")}
CSV_TYPES = [(_("CSV files"), "*.csv"), (_("All files"), "*.*")]


class ProductsView(View):
    title = _("Products")

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.header()
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search = SearchBar(bar, self.reload, _("name, SKU, barcode, brand"), width=32)
        self.search.pack(side=START)
        ttk.Label(bar, text="  " + _("Category")).pack(side=START)
        self.cat_var = tk.StringVar(value=_("All"))
        self.cat_box = ttk.Combobox(bar, textvariable=self.cat_var, state="readonly", width=18)
        self.cat_box.pack(side=START, padx=6)
        self.cat_box.bind("<<ComboboxSelected>>", lambda e: self.reload())
        self.inactive = tk.BooleanVar()
        ttk.Checkbutton(bar, text=_("Show inactive"), variable=self.inactive, command=self.reload).pack(
            side=START, padx=6)
        self.low_only = tk.BooleanVar()
        ttk.Checkbutton(bar, text=_("Low stock only"), variable=self.low_only, command=self.reload).pack(
            side=START)
        self.count = ttk.Label(bar, text="", style="Muted.TLabel")
        self.count.pack(side=END)

        toolbar(self, [
            (_("+ New product"), self.new, "Accent.TButton"), (_("Edit"), self.edit),
            (_("Duplicate"), self.duplicate), (_("Activate / deactivate"), self.toggle_active), None,
            (_("Adjust stock"), self.adjust), (_("Stock count"), self.count_stock),
            (_("Serial numbers"), self.serials), (_("History"), self.history), None,
            (_("Categories"), lambda: self.lookups("categories")),
            (_("Brands"), lambda: self.lookups("brands")), None,
            (_("🏷 Print labels"), self.print_labels), (_("Generate missing barcodes"), self.gen_barcodes),
            None, (_("Import CSV"), self.import_csv), (_("Export CSV"), self.export_csv),
        ]).pack(fill="x", pady=(0, 8))

        self.table = DataTable(self, [
            ("sku", _("SKU"), 90), ("barcode", _("Barcode"), 120), ("name", _("Name"), 260),
            ("category", _("Category"), 120), ("brand", _("Brand"), 100),
            ("cost_price", _("Cost"), -85, lambda v: f"{v:,.2f}"),
            ("sell_price", _("Price"), -85, lambda v: f"{v:,.2f}"),
            ("margin", _("Margin"), -70), ("stock_qty", _("Stock"), -65),
            ("reorder_level", _("Reorder"), -70), ("warranty_months", _("Warranty (m)"), -95),
            ("track_serial", _("Serial?"), 65, lambda v: _("Yes") if v else ""),
            ("location", _("Location"), 90)], height=20, on_double=lambda r: self.edit(),
            selectmode="extended")
        self.table.pack(fill="both", expand=True)

    def on_show(self):
        cats = catalog.list_lookup(self.db, "categories")
        self.categories = {c["name"]: c["id"] for c in cats}
        self.cat_box.configure(values=[_("All")] + list(self.categories))
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
        self.count.configure(text=_("{count} products").format(count=len(rows)))

    def selected(self):
        row = self.table.selected()
        if not row:
            messagebox.showinfo(self.title, _("Select a product first."), parent=self)
        return row

    # ------------------------------------------------------------- editing
    def fields(self, new: bool):
        cats = [c["name"] for c in catalog.list_lookup(self.db, "categories")]
        brands = [b["name"] for b in catalog.list_lookup(self.db, "brands")]
        suppliers = [""] + [s["name"] for s in people.list_suppliers(self.db)]
        f = [
            {"key": "name", "label": _("Name"), "required": True},
            {"key": "sku", "label": _("SKU / code"), "hint": _("blank = automatic")},
            {"key": "barcode", "label": _("Barcode"), "hint": _("scan it here")},
            {"key": "category", "label": _("Category"), "type": "combo", "values": cats, "strict": False},
            {"key": "brand", "label": _("Brand"), "type": "combo", "values": brands, "strict": False},
            {"key": "supplier", "label": _("Supplier"), "type": "combo", "values": suppliers},
            {"key": "cost_price", "label": _("Cost price"), "type": "float", "default": "0"},
            {"key": "sell_price", "label": _("Selling price"), "type": "float", "required": True},
        ]
        if new:
            f.append({"key": "stock_qty", "label": _("Opening stock"), "type": "int", "default": "0"})
        f += [
            {"key": "reorder_level", "label": _("Reorder level"), "type": "int", "default": "2",
             "hint": _("alert at or below")},
            {"key": "warranty_months", "label": _("Warranty (months)"), "type": "int", "default": "0"},
            {"key": "location", "label": _("Shelf / location")},
            {"key": "description", "label": _("Description"), "type": "multiline", "height": 3},
            {"key": "track_serial", "label": _("Track serial / IMEI numbers"), "type": "check"},
            {"key": "tax_exempt", "label": _("Tax exempt"), "type": "check"},
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
        if ask_form(self, _("New product"), self.fields(True), initial, on_submit=submit):
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
        if ask_form(self, _("Edit product — {name}").format(name=row["name"]), self.fields(False), initial,
                    on_submit=submit):
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
        res = ask_form(self, _("Adjust stock — {name}").format(name=row["name"]), [
            {"key": "change", "label": _("Change (+ add / − remove)"), "type": "int", "required": True},
            {"key": "reason", "label": _("Reason"), "type": "combo", "default": "Correction",
             "choices": [(r, tr_value(r)) for r in ADJUST_REASONS]},
            {"key": "note", "label": _("Note")},
        ], ok_text=_("Apply"))
        if res and res["change"]:
            reason = res["reason"] + (f": {res['note']}" if res["note"] else "")
            catalog.adjust_stock(self.db, row["id"], res["change"], reason, self.app.user["id"])
            self.reload()

    def count_stock(self):
        row = self.selected()
        if not row:
            return
        counted = ask_value(self, _("Stock count"), _("Counted quantity of {name} (system says {qty})").format(
            name=row["name"], qty=row["stock_qty"]), "int", row["stock_qty"])
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
        d = Dialog(self, _("Stock history — {name}").format(name=row["name"]))
        t = DataTable(d.body, [("created_at", _("Date"), 160), ("change", _("Change"), -70),
                               ("balance", _("Balance"), -75), ("reason", _("Reason"), 220, tr_reason),
                               ("ref", _("Reference"), 120), ("user", _("User"), 90)], height=16)
        t.set_rows(catalog.stock_movements(self.db, row["id"]))
        t.pack(fill="both", expand=True)
        d.buttons(ok_text="", cancel_text=_("Close"))
        d.show()

    def lookups(self, table):
        LookupDialog(self, self.db, table).show()
        self.on_show()

    # -------------------------------------------------------------- labels
    def print_labels(self):
        rows = self.table.selected_all()
        if not rows:
            messagebox.showinfo(self.title, _("Select one or more products (Ctrl+click or Shift+click)."),
                                parent=self)
            return
        LabelDialog(self, self.app, [(r["id"], 1) for r in rows]).show()

    def gen_barcodes(self):
        rows = self.table.selected_all()
        question = (_("Create a new in-store barcode for the selected products that have none?") if rows
                    else _("Create a new in-store barcode for ALL products that have none?"))
        if not confirm(self, _("Barcodes"), question):
            return
        n = catalog.assign_missing_barcodes(self.db, [r["id"] for r in rows] if rows else None,
                                            self.app.user["id"])
        info(self, _("Barcodes"), _("Created {count} barcode(s). Use Print labels to stick them on the "
                                    "products.").format(count=n))
        self.reload()

    # ----------------------------------------------------------------- CSV
    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, title=_("Import products"), filetypes=CSV_TYPES)
        if not path:
            return
        created, updated, errors = catalog.import_products_csv(self.db, path, self.app.user["id"])
        msg = _("Created {created}, updated {updated} products.").format(created=created, updated=updated)
        if errors:
            msg += "\n\n" + _("{count} rows were skipped:").format(count=len(errors)) + "\n" + \
                "\n".join(errors[:15])
        info(self, _("Import"), msg)
        self.on_show()

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, title=_("Export products"), defaultextension=".csv",
                                            initialfile="products.csv", filetypes=CSV_TYPES[:1])
        if path:
            n = catalog.export_products_csv(self.db, path)
            info(self, _("Export"), _("Exported {count} products to\n{path}").format(count=n, path=path))


class SerialsDialog(Dialog):
    def __init__(self, parent, app, product):
        super().__init__(parent, _("Serial numbers — {name}").format(name=product["name"]))
        self.app, self.db, self.product = app, app.db, product
        ttk.Label(self.body, text=_("Registered serial / IMEI numbers. Stock quantity is managed separately "
                                    "(purchases add both)."), style="Muted.TLabel", wraplength=520).pack(anchor=W)
        self.table = DataTable(self.body, [("serial_no", _("Serial / IMEI"), 220),
                                           ("status", _("Status"), 100, tr_value),
                                           ("created_at", _("Added"), 160)], height=12)
        self.table.pack(fill="both", expand=True, pady=8)
        toolbar(self.body, [(_("Add serials"), self.add), (_("Delete"), self.delete)]).pack(fill="x")
        self.buttons(ok_text="", cancel_text=_("Close"))
        self.reload()

    def reload(self):
        self.table.set_rows(catalog.list_serials(self.db, self.product["id"]),
                            tag_fn=lambda r: "ok" if r["status"] == "in_stock" else "muted")

    def add(self):
        res = ask_form(self, _("Add serials"), [{"key": "serials", "label": _("One per line (scan them)"),
                                                 "type": "multiline", "height": 10}], ok_text=_("Add"))
        if res:
            n = catalog.add_serials(self.db, self.product["id"], res["serials"].splitlines())
            info(self, _("Serials"), _("Added {count} serial numbers.").format(count=n))
            self.reload()

    def delete(self):
        row = self.table.selected()
        if not row:
            return
        if row["status"] == "sold":
            raise POSError(_("Sold serial numbers are kept for warranty records."))
        if confirm(self, _("Delete"), _("Delete serial {serial}?").format(serial=row["serial_no"])):
            catalog.delete_serial(self.db, row["id"])
            self.reload()


class LookupDialog(Dialog):
    def __init__(self, parent, db, table):
        super().__init__(parent, LOOKUP_TITLES[table])
        self.db, self.table_name = db, table
        self.table = DataTable(self.body, [("name", _("Name"), 260)], height=12,
                               on_double=lambda r: self.rename())
        self.table.pack(fill="both", expand=True)
        toolbar(self.body, [(_("Add"), self.add), (_("Rename"), self.rename), (_("Delete"), self.delete)]).pack(
            fill="x", pady=(8, 0))
        self.buttons(ok_text="", cancel_text=_("Close"))
        self.reload()

    def reload(self):
        self.table.set_rows(catalog.list_lookup(self.db, self.table_name))

    def add(self):
        name = ask_value(self, _("Add"), _("Name"), "text")
        if name:
            catalog.get_or_create_lookup(self.db, self.table_name, name)
            self.reload()

    def rename(self):
        row = self.table.selected()
        if row:
            name = ask_value(self, _("Rename"), _("New name"), "text", row["name"])
            if name:
                catalog.rename_lookup(self.db, self.table_name, row["id"], name)
                self.reload()

    def delete(self):
        row = self.table.selected()
        if row and confirm(self, _("Delete"), _("Delete '{name}'? Products keep working without it.").format(
                name=row["name"])):
            catalog.delete_lookup(self.db, self.table_name, row["id"])
            self.reload()


class LabelDialog(Dialog):
    """Choose how many barcode labels to print for each product."""

    def __init__(self, parent, app, product_copies):
        super().__init__(parent, _("Print barcode labels"))
        self.app, self.db = app, app.db
        settings = self.db.get_settings()
        fmt = settings.get("label_format", "html_roll")
        ttk.Label(self.body, text=_("Printer type: {type}   ({width} × {height} mm, change in Settings → "
                                    "Labels)").format(type=tr_value(barcodes.LABEL_FORMATS.get(fmt, fmt)),
                                                      width=settings.get("label_width_mm"),
                                                      height=settings.get("label_height_mm")),
                  style="Muted.TLabel").pack(anchor=W)
        self.items = []
        for pid, copies in product_copies:
            p = catalog.get_product(self.db, pid)
            self.items.append({"id": p["id"], "name": p["name"], "code": p["barcode"] or p["sku"],
                               "price": p["sell_price"], "stock": p["stock_qty"], "copies": copies})
        self.table = DataTable(self.body, [
            ("name", _("Product"), 280), ("code", _("Barcode"), 150),
            ("price", _("Price"), -90, lambda v: f"{v:,.2f}"),
            ("stock", _("Stock"), -60), ("copies", _("Labels"), -70)], height=12,
            on_double=lambda r: self.set_copies())
        self.table.pack(fill="both", expand=True, pady=8)
        toolbar(self.body, [(_("Change number of labels"), self.set_copies),
                            (_("Labels = stock quantity"), self.copies_from_stock),
                            (_("Remove"), self.remove)]).pack(fill="x")
        self.buttons(ok_text=_("🖨 Print labels"))
        self.refresh()

    def refresh(self):
        self.table.set_rows(self.items)

    def set_copies(self):
        row = self.table.selected()
        if row:
            n = ask_value(self, _("Labels"), _("Number of labels for {name}").format(name=row["name"]),
                          "int", row["copies"])
            if n is not None:
                next(i for i in self.items if i["id"] == row["id"])["copies"] = max(0, n)
                self.refresh()

    def copies_from_stock(self):
        for item in self.items:
            item["copies"] = max(0, item["stock"])
        self.refresh()

    def remove(self):
        row = self.table.selected()
        if row:
            self.items = [i for i in self.items if i["id"] != row["id"]]
            self.refresh()

    def ok(self):
        try:
            msg = barcodes.print_labels(self.db, {i["id"]: i["copies"] for i in self.items})
        except POSError as exc:
            messagebox.showwarning(self.title(), str(exc), parent=self)
            return
        info(self, _("Labels"), msg)
        self.result = True
        self.destroy()
