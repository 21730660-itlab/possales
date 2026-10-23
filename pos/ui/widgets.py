"""Reusable Tkinter widgets: theme, data tables, form dialogs and helpers.

Layout helpers mirror automatically for right-to-left languages (Arabic): use START/END
instead of "left"/"right" for pack sides, W/E/NW for anchors and stickies, and col() for
grid columns. These are fixed when this module is imported, so the interface language
must be chosen before the screens are imported (see main.py).
"""
from __future__ import annotations

import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, timedelta
from tkinter import messagebox, ttk

from ..db import POSError, money
from ..i18n import _, is_rtl, plain
from ..services import auth

IS_WIN = sys.platform.startswith("win")
FONT_FAMILY = "Segoe UI" if IS_WIN else "DejaVu Sans"
MONO_FAMILY = "Consolas" if IS_WIN else "DejaVu Sans Mono"

RTL = is_rtl()
ARABIC_CHARS = re.compile("[\u0600-\u06ff]")
START, END = ("right", "left") if RTL else ("left", "right")
W, E = ("e", "w") if RTL else ("w", "e")
NW = "ne" if RTL else "nw"
JUSTIFY = "right" if RTL else "left"


def pad(before: int, after: int) -> tuple[int, int]:
    """Horizontal padding given in reading order (start, end)."""
    return (after, before) if RTL else (before, after)


def col(index: int, count: int) -> int:
    """Grid column `index` (in reading order) of `count` columns."""
    return count - 1 - index if RTL else index


COLORS = {
    "bg": "#f3f5f9",
    "panel": "#ffffff",
    "sidebar": "#1f2a44",
    "sidebar_hover": "#2d3b5e",
    "sidebar_active": "#3d5afe",
    "accent": "#3d5afe",
    "success": "#2e7d32",
    "danger": "#c62828",
    "warning": "#ef6c00",
    "muted": "#6b7280",
    "text": "#111827",
}


def setup_theme(root: tk.Tk, base_size: int = 11):
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    f = (FONT_FAMILY, base_size)
    # Resize Tk's named fonts instead of setting "*Font", which would override ttk style fonts.
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family=FONT_FAMILY, size=base_size)
    tkfont.nametofont("TkFixedFont").configure(family=MONO_FAMILY, size=base_size)
    root.option_add("*TCombobox*Listbox.font", f)
    if RTL:
        root.option_add("*TEntry.justify", "right")
        root.option_add("*TCombobox.justify", "right")
        root.option_add("*TSpinbox.justify", "right")
        root.option_add("*Listbox.justify", "right")
    root.configure(bg=COLORS["bg"])
    style.configure(".", font=f, background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Panel.TFrame", background=COLORS["panel"])
    style.configure("TLabel", background=COLORS["bg"])
    style.configure("Panel.TLabel", background=COLORS["panel"])
    style.configure("Title.TLabel", font=(FONT_FAMILY, base_size + 7, "bold"))
    style.configure("H2.TLabel", font=(FONT_FAMILY, base_size + 3, "bold"))
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Total.TLabel", font=(FONT_FAMILY, base_size + 15, "bold"),
                    foreground=COLORS["accent"], background=COLORS["panel"])
    style.configure("CardValue.TLabel", font=(FONT_FAMILY, base_size + 9, "bold"),
                    background=COLORS["panel"])
    style.configure("CardTitle.TLabel", foreground=COLORS["muted"], background=COLORS["panel"])
    style.configure("TButton", padding=(10, 6))
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="white",
                    font=(FONT_FAMILY, base_size, "bold"))
    style.map("Accent.TButton", background=[("active", "#304ffe"), ("disabled", "#9fa8da")])
    style.configure("Pay.TButton", background=COLORS["success"], foreground="white",
                    font=(FONT_FAMILY, base_size + 5, "bold"), padding=(10, 14))
    style.map("Pay.TButton", background=[("active", "#1b5e20")])
    style.configure("Danger.TButton", background=COLORS["danger"], foreground="white")
    style.map("Danger.TButton", background=[("active", "#8e0000")])
    style.configure("Treeview", rowheight=int(base_size * 2.6), font=f)
    style.configure("Treeview.Heading", font=(FONT_FAMILY, base_size, "bold"))
    style.configure("TLabelframe", background=COLORS["bg"])
    style.configure("TLabelframe.Label", font=(FONT_FAMILY, base_size, "bold"),
                    background=COLORS["bg"])
    style.configure("TNotebook.Tab", padding=(14, 6))
    if RTL:
        style.configure("TLabelframe", labelanchor="ne")
        style.configure("TCheckbutton", justify="right")
    return style


# ------------------------------------------------------------------ formatting
def fmt_money(value, symbol: str = "$") -> str:
    value = money(value or 0)
    return f"{'-' if value < 0 else ''}{symbol}{abs(value):,.2f}"


def parse_float(text, field: str = "") -> float:
    try:
        return float(str(text).replace(",", "").strip() or 0)
    except ValueError:
        raise POSError(_("{field} must be a number.").format(field=field or _("Value")))


def parse_int(text, field: str = "") -> int:
    try:
        return int(float(str(text).replace(",", "").strip() or 0))
    except ValueError:
        raise POSError(_("{field} must be a whole number.").format(field=field or _("Value")))


def add_tabs(notebook: ttk.Notebook, tabs):
    """Add (widget, title) tabs in reading order (right to left for Arabic)."""
    tabs = list(tabs)
    for widget, title in (reversed(tabs) if RTL else tabs):
        notebook.add(widget, text=title)
    if tabs:
        notebook.select(tabs[0][0])


# ------------------------------------------------------------------ data table
class DataTable(ttk.Frame):
    """A Treeview with scrollbars, column sorting and row lookup.

    columns: list of (key, heading, width) or (key, heading, width, formatter).
    A negative width marks a numeric column (aligned to the end).
    """

    def __init__(self, parent, columns, height: int = 15, on_select=None, on_double=None,
                 selectmode="browse"):
        super().__init__(parent)
        self.columns = [c if len(c) == 4 else (*c, None) for c in columns]
        keys = [c[0] for c in self.columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings", height=height,
                                 selectmode=selectmode)
        if RTL:  # first column on the right
            self.tree.configure(displaycolumns=list(reversed(keys)))
        for key, heading, width, _fmt in self.columns:
            self.tree.heading(key, text=heading, anchor=W,
                              command=lambda k=key: self.sort_by(k))
            numeric = width < 0
            self.tree.column(key, width=abs(width), anchor=E if numeric else W,
                             stretch=True, minwidth=40)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=col(0, 2), sticky="nsew")
        ys.grid(row=0, column=col(1, 2), sticky="ns")
        xs.grid(row=1, column=col(0, 2), sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(col(0, 2), weight=1)
        self.tree.tag_configure("warn", foreground=COLORS["danger"])
        self.tree.tag_configure("ok", foreground=COLORS["success"])
        self.tree.tag_configure("muted", foreground=COLORS["muted"])
        self.rows: dict[str, dict] = {}
        self._sort_desc = False
        if on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda e: on_select(self.selected()))
        if on_double:
            self.tree.bind("<Double-1>", lambda e: self.selected() and on_double(self.selected()))
            self.tree.bind("<Return>", lambda e: self.selected() and on_double(self.selected()))

    def set_rows(self, rows, id_key: str = "id", tag_fn=None):
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for n, row in enumerate(rows):
            row = dict(row)
            iid = str(row.get(id_key, n)) if id_key else str(n)
            if iid in self.rows:
                iid = f"{iid}_{n}"
            values = []
            for key, _heading, _width, formatter in self.columns:
                value = row.get(key, "")
                if formatter:
                    value = formatter(value)
                values.append("" if value is None else value)
            tags = (tag_fn(row),) if tag_fn and tag_fn(row) else ()
            self.tree.insert("", "end", iid=iid, values=values, tags=tags)
            self.rows[iid] = row

    def selected(self) -> dict | None:
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None

    def selected_all(self) -> list[dict]:
        return [self.rows[i] for i in self.tree.selection() if i in self.rows]

    def select_first(self):
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.tree.see(children[0])

    def all_rows(self) -> list[dict]:
        return [self.rows[i] for i in self.tree.get_children()]

    def sort_by(self, key):
        items = list(self.tree.get_children())

        def sort_key(iid):
            value = self.rows[iid].get(key)
            if value is None:
                return (1, "")
            if isinstance(value, (int, float)):
                return (0, value)
            return (0, str(value).lower())

        items.sort(key=sort_key, reverse=self._sort_desc)
        for index, iid in enumerate(items):
            self.tree.move(iid, "", index)
        self._sort_desc = not self._sort_desc

    def export_rows(self):
        """Headings + displayed values, used for CSV export."""
        headers = [c[1] for c in self.columns]
        values = [list(self.tree.item(i, "values")) for i in self.tree.get_children()]
        return headers, values


# ----------------------------------------------------------------- dialogs
class Dialog(tk.Toplevel):
    """Modal dialog base class with OK/Cancel handling."""

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.configure(bg=COLORS["bg"])
        self.result = None
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())
        self.body = ttk.Frame(self, padding=16)
        self.body.pack(fill="both", expand=True)

    def show(self):
        self.update_idletasks()
        parent = self.master.winfo_toplevel()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 3)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()
        self.wait_window(self)
        return self.result

    def buttons(self, ok_text=None, cancel_text=None, row_parent=None):
        """OK / Cancel buttons at the bottom. Pass "" to leave one out."""
        ok_text = _("OK") if ok_text is None else ok_text
        cancel_text = _("Cancel") if cancel_text is None else cancel_text
        bar = ttk.Frame(row_parent or self.body)
        bar.pack(fill="x", pady=(14, 0), side="bottom")
        if cancel_text:
            ttk.Button(bar, text=cancel_text, command=self.cancel).pack(side=END, padx=pad(8, 0))
        if ok_text:
            ttk.Button(bar, text=ok_text, style="Accent.TButton", command=self.ok).pack(side=END)
        return bar

    def ok(self):
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class FormDialog(Dialog):
    """Generic form. Each field is a dict with:

    key, label, type (text|password|int|float|combo|check|multiline|readonly),
    values (for combo), choices (combo of (stored value, shown text) pairs),
    default, required, width, hint.
    `on_submit(values)` may raise POSError to keep the dialog open.
    """

    def __init__(self, parent, title, fields, initial=None, on_submit=None, ok_text=None):
        super().__init__(parent, title)
        self.fields = fields
        self.on_submit = on_submit
        self.vars, self.widgets = {}, {}
        initial = dict(initial or {})
        grid = ttk.Frame(self.body)
        grid.pack(fill="both", expand=True)
        label_col, field_col, hint_col = col(0, 3), col(1, 3), col(2, 3)
        grid.columnconfigure(field_col, weight=1)
        first = None
        for row, f in enumerate(fields):
            kind = f.get("type", "text")
            value = initial.get(f["key"], f.get("default", ""))
            if value is None:
                value = ""
            label = f["label"] + (" *" if f.get("required") else "")
            if kind != "check":
                ttk.Label(grid, text=label).grid(row=row, column=label_col, sticky=NW,
                                                 padx=pad(0, 10), pady=4)
            if kind == "check":
                var = tk.BooleanVar(value=bool(int(value or 0)) if str(value).isdigit() else bool(value))
                w = ttk.Checkbutton(grid, text=f["label"], variable=var)
                w.grid(row=row, column=field_col, sticky=W, pady=4)
            elif kind == "multiline":
                var = None
                w = tk.Text(grid, height=f.get("height", 4), width=f.get("width", 40), wrap="word",
                            font=(FONT_FAMILY, 11), relief="solid", borderwidth=1)
                w.insert("1.0", str(value))
                w.grid(row=row, column=field_col, sticky="nsew", pady=4)
            elif kind == "combo":
                values = list(f.get("values", []))
                if "choices" in f:
                    labels = dict(f["choices"])
                    values = list(labels.values())
                    value = labels.get(value, value)
                var = tk.StringVar(value=str(value))
                w = ttk.Combobox(grid, textvariable=var, values=values, width=f.get("width", 38),
                                 state="readonly" if f.get("strict", True) else "normal")
                w.grid(row=row, column=field_col, sticky="ew", pady=4)
            else:
                var = tk.StringVar(value=str(value))
                w = ttk.Entry(grid, textvariable=var, width=f.get("width", 40),
                              show="•" if kind == "password" else "")
                if kind == "readonly":
                    w.state(["readonly"])
                w.grid(row=row, column=field_col, sticky="ew", pady=4)
            if f.get("hint"):
                ttk.Label(grid, text=f["hint"], style="Muted.TLabel").grid(
                    row=row, column=hint_col, sticky=W, padx=pad(8, 0))
            self.vars[f["key"]] = var
            self.widgets[f["key"]] = w
            if first is None and kind not in ("readonly", "check"):
                first = w
        self.buttons(ok_text=_("Save") if ok_text is None else ok_text)
        self.bind("<Return>", self._on_return)
        if first is not None:
            self.after(50, first.focus_set)

    def _on_return(self, event):
        if isinstance(event.widget, tk.Text):
            return
        self.ok()

    def values(self) -> dict:
        out = {}
        for f in self.fields:
            key, kind = f["key"], f.get("type", "text")
            if kind == "multiline":
                out[key] = self.widgets[key].get("1.0", "end").strip()
            elif kind == "check":
                out[key] = bool(self.vars[key].get())
            else:
                raw = plain(self.vars[key].get()).strip()
                if f.get("required") and not raw:
                    raise POSError(_("{field} is required.").format(field=f["label"]))
                if kind == "int":
                    out[key] = parse_int(raw, f["label"])
                elif kind == "float":
                    out[key] = parse_float(raw, f["label"])
                elif "choices" in f:
                    out[key] = next((v for v, shown in f["choices"] if plain(shown) == raw), raw)
                else:
                    out[key] = raw
        return out

    def ok(self):
        try:
            values = self.values()
            if self.on_submit:
                self.on_submit(values)
        except POSError as exc:
            messagebox.showwarning(self.title(), str(exc), parent=self)
            return
        self.result = values
        self.destroy()


def ask_form(parent, title, fields, initial=None, on_submit=None, ok_text=None):
    return FormDialog(parent, title, fields, initial, on_submit, ok_text).show()


def ask_value(parent, title, label, kind="float", default="", hint=""):
    res = ask_form(parent, title, [{"key": "v", "label": label, "type": kind, "default": default,
                                    "required": True, "hint": hint}], ok_text=_("OK"))
    return None if res is None else res["v"]


class TextPreview(Dialog):
    """Shows a receipt/report with a Print option."""

    def __init__(self, parent, title, text, on_print=None, width=48):
        super().__init__(parent, title)
        if ARABIC_CHARS.search(text):
            box = self._line_canvas(text, width)
        else:
            box = tk.Text(self.body, width=width, height=min(36, text.count("\n") + 2),
                          font=(MONO_FAMILY, 11), relief="solid", borderwidth=1)
            box.insert("1.0", text)
            box.configure(state="disabled")
        ys = ttk.Scrollbar(self.body, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=ys.set)
        bar = ttk.Frame(self.body)
        bar.pack(fill="x", side="bottom", pady=(12, 0))
        ys.pack(side=END, fill="y")
        box.pack(fill="both", expand=True)
        ttk.Button(bar, text=_("Close"), command=self.cancel).pack(side=END, padx=pad(8, 0))
        if on_print:
            def do_print():
                try:
                    on_print()
                except Exception as exc:  # printing problems should not crash the POS
                    messagebox.showerror(_("Print"), _("Could not print: {error}").format(error=exc),
                                         parent=self)
            ttk.Button(bar, text=_("🖨 Print"), style="Accent.TButton", command=do_print).pack(side=END)
        self.bind("<Return>", lambda e: self.cancel())

    def _line_canvas(self, text, width):
        """Draw each line as one piece. The Text widget lays Arabic out word by word, which
        reverses the word order on Windows; whole lines are shaped like the printed receipt."""
        font = tkfont.Font(family=MONO_FAMILY, size=11)
        line_h = font.metrics("linespace") + 2
        lines = text.split("\n")
        canvas = tk.Canvas(self.body, width=font.measure("0") * width + 12,
                           height=min(36, len(lines) + 1) * line_h, bg="white",
                           highlightthickness=1, highlightbackground="#999")
        for i, line in enumerate(lines):
            canvas.create_text(6, 4 + i * line_h, text=line, anchor="nw", font=font)
        canvas.configure(scrollregion=(0, 0, 0, len(lines) * line_h + 8))
        return canvas


class ManagerOverride(Dialog):
    def __init__(self, parent, db, perm, reason):
        super().__init__(parent, _("Manager approval required"))
        self.db, self.perm = db, perm
        ttk.Label(self.body, text=reason, wraplength=360, justify=JUSTIFY).pack(anchor=W, pady=(0, 10))
        form = ttk.Frame(self.body)
        form.pack(fill="x")
        self.user = tk.StringVar()
        self.pw = tk.StringVar()
        ttk.Label(form, text=_("Manager username")).grid(row=0, column=col(0, 2), sticky=W, pady=4)
        e = ttk.Entry(form, textvariable=self.user)
        e.grid(row=0, column=col(1, 2), sticky="ew", padx=8)
        ttk.Label(form, text=_("Password")).grid(row=1, column=col(0, 2), sticky=W, pady=4)
        ttk.Entry(form, textvariable=self.pw, show="•").grid(row=1, column=col(1, 2), sticky="ew", padx=8)
        self.buttons(ok_text=_("Approve"))
        self.bind("<Return>", lambda ev: self.ok())
        self.after(50, e.focus_set)

    def ok(self):
        try:
            user = auth.authenticate(self.db, self.user.get(), self.pw.get())
        except POSError as exc:
            messagebox.showwarning(self.title(), str(exc), parent=self)
            return
        if not auth.has_permission(user, self.perm):
            messagebox.showwarning(self.title(), _("That user is not allowed to approve this."),
                                   parent=self)
            return
        self.result = user
        self.destroy()


def require_permission(parent, app, perm: str, reason: str) -> bool:
    """True if the current user has `perm`, or a manager approves the action."""
    if auth.has_permission(app.user, perm):
        return True
    approver = ManagerOverride(parent, app.db, perm, reason).show()
    if approver:
        app.db.log(approver["id"], "override", f"{perm} for {app.user['username']}: {reason}")
        return True
    return False


def confirm(parent, title, message) -> bool:
    return messagebox.askyesno(title, message, parent=parent)


def info(parent, title, message):
    messagebox.showinfo(title, message, parent=parent)


# --------------------------------------------------------------- date range
def date_presets() -> dict[str, tuple[date, date]]:
    t = date.today()
    week_start = t - timedelta(days=t.weekday())
    month_start = t.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    return {
        "Today": (t, t),
        "Yesterday": (t - timedelta(days=1), t - timedelta(days=1)),
        "This week": (week_start, t),
        "Last 7 days": (t - timedelta(days=6), t),
        "This month": (month_start, t),
        "Last month": (last_month_end.replace(day=1), last_month_end),
        "Last 30 days": (t - timedelta(days=29), t),
        "This year": (t.replace(month=1, day=1), t),
    }


PRESET_LABELS = {
    "Today": _("Today"), "Yesterday": _("Yesterday"), "This week": _("This week"),
    "Last 7 days": _("Last 7 days"), "This month": _("This month"), "Last month": _("Last month"),
    "Last 30 days": _("Last 30 days"), "This year": _("This year"), "Custom": _("Custom"),
}


class DateRangeBar(ttk.Frame):
    def __init__(self, parent, on_change, preset="Today"):
        super().__init__(parent)
        self.on_change = on_change
        self.d1 = tk.StringVar()
        self.d2 = tk.StringVar()
        self.preset = tk.StringVar(value=PRESET_LABELS[preset])
        ttk.Label(self, text=_("Period")).pack(side=START)
        cb = ttk.Combobox(self, textvariable=self.preset, values=list(PRESET_LABELS.values()),
                          state="readonly", width=13)
        cb.pack(side=START, padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.apply_preset())
        ttk.Label(self, text=_("From")).pack(side=START, padx=pad(8, 2))
        ttk.Entry(self, textvariable=self.d1, width=11).pack(side=START)
        ttk.Label(self, text=_("To")).pack(side=START, padx=pad(8, 2))
        ttk.Entry(self, textvariable=self.d2, width=11).pack(side=START)
        ttk.Button(self, text=_("Go"), command=self.changed).pack(side=START, padx=6)
        self.apply_preset(notify=False)

    def apply_preset(self, notify=True):
        key = next((k for k, shown in PRESET_LABELS.items() if shown == self.preset.get()), "")
        rng = date_presets().get(key)
        if rng:
            self.d1.set(rng[0].isoformat())
            self.d2.set(rng[1].isoformat())
        if notify:
            self.changed()

    def changed(self):
        self.on_change()

    def range(self) -> tuple[str, str]:
        d1, d2 = self.d1.get().strip(), self.d2.get().strip()
        for d in (d1, d2):
            try:
                date.fromisoformat(d)
            except ValueError:
                raise POSError(_("'{date}' is not a valid date. Use YYYY-MM-DD.").format(date=d))
        return (d1, d2) if d1 <= d2 else (d2, d1)


class SearchBar(ttk.Frame):
    """Entry that calls `on_search` as the user types (debounced)."""

    def __init__(self, parent, on_search, placeholder="", width=30):
        super().__init__(parent)
        self.var = tk.StringVar()
        ttk.Label(self, text="🔍").pack(side=START)
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side=START, padx=4, fill="x", expand=True)
        self._job = None
        self.var.trace_add("write", lambda *a: self._schedule(on_search))
        self.entry.bind("<Escape>", lambda e: self.var.set(""))
        ttk.Label(self, text=placeholder, style="Muted.TLabel").pack(side=START, padx=4)

    def _schedule(self, fn):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(250, fn)

    def get(self) -> str:
        return self.var.get().strip()


class FlowFrame(ttk.Frame):
    """Lays its children out in reading order, wrapping onto new rows when out of width."""

    def __init__(self, parent, gap=6, **kw):
        super().__init__(parent, **kw)
        self.gap = gap
        self.extra_gap = set()  # children that get a wider gap before them (group separators)
        self.bind("<Configure>", lambda e: self.reflow())

    def reflow(self):
        width = max(self.winfo_width(), 1)
        x = y = row_h = 0
        for child in self.winfo_children():
            w, h = child.winfo_reqwidth(), child.winfo_reqheight()
            if child in self.extra_gap and x:
                x += self.gap * 3
            if x and x + w > width:
                x, y = 0, y + row_h + self.gap
                row_h = 0
            child.place(x=width - x - w if RTL else x, y=y)
            x += w + self.gap
            row_h = max(row_h, h)
        height = y + row_h
        if int(self.cget("height") or 0) != height:
            self.configure(height=height)


def toolbar(parent, buttons):
    """buttons: list of (text, command[, style]) or None to start a new group."""
    bar = FlowFrame(parent)
    new_group = False
    for b in buttons:
        if b is None:
            new_group = True
            continue
        text, cmd, *style = b
        btn = ttk.Button(bar, text=text, command=cmd, style=style[0] if style else "TButton")
        if new_group:
            bar.extra_gap.add(btn)
            new_group = False
    bar.configure(height=bar.winfo_children()[0].winfo_reqheight() if bar.winfo_children() else 1)
    return bar


class StatCard(ttk.Frame):
    def __init__(self, parent, title, value="-", color=None):
        super().__init__(parent, style="Panel.TFrame", padding=14)
        ttk.Label(self, text=title, style="CardTitle.TLabel").pack(anchor=W)
        self.value = ttk.Label(self, text=value, style="CardValue.TLabel")
        if color:
            self.value.configure(foreground=color)
        self.value.pack(anchor=W, pady=(4, 0))

    def set(self, value):
        self.value.configure(text=value)
