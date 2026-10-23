"""Windows check: does Tk draw Arabic shaped and right-to-left? Prints a screenshot as base64."""
import base64
import io
import tkinter as tk
from tkinter import ttk

from PIL import ImageGrab

root = tk.Tk()
root.geometry("700x330+40+40")
root.configure(bg="white")
f = ("Segoe UI", 14)
tk.Label(root, text="مرحباً بكم في نظام المتجر", font=("Segoe UI", 20, "bold"), bg="white").pack(anchor="e", padx=10)
tk.Label(root, text="المجموع الفرعي: $224.22 (11%)", font=f, bg="white").pack(anchor="e", padx=10)
tk.Label(root, text="Mixed: الباقي 3.99 دولار", font=f, bg="white").pack(anchor="e", padx=10)
ttk.Button(root, text="إتمام البيع").pack(anchor="e", padx=10, pady=4)
e = ttk.Entry(root, font=f, justify="right")
e.insert(0, "سماعة بلوتوث")
e.pack(anchor="e", padx=10, fill="x")
t = ttk.Treeview(root, columns=("a", "b"), show="headings", height=2)
t.heading("a", text="المنتج")
t.heading("b", text="السعر")
t.insert("", "end", values=("شاحن سريع", "15.00"))
t.pack(fill="x", padx=10, pady=6)
root.update()
root.after(1500, root.quit)
root.mainloop()
root.update()
x, y = root.winfo_rootx(), root.winfo_rooty()
img = ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height()))
buf = io.BytesIO()
img.save(buf, "PNG", optimize=True)
data = base64.b64encode(buf.getvalue()).decode()
print("TK", root.tk.call("info", "patchlevel"))
for i in range(0, len(data), 2000):
    print("IMG:" + data[i:i + 2000])
print("IMG-END")
