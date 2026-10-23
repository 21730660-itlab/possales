"""Windows check: which way of marking text direction makes mixed Arabic/number text read right?

Saves screenshots/tk_probe.png.
"""
import os
import tkinter as tk

from PIL import ImageGrab

SAMPLES = ["المجموع الفرعي: $224.22 (11%)", "الباقي 3.99 دولار - Mixed", "فقط 5 من 'USB-C cable' في المخزون."]
VARIANTS = [("plain", lambda s: s), ("RLM", lambda s: "‏" + s),
            ("RLE..PDF", lambda s: "‫" + s + "‬"), ("RLI..PDI", lambda s: "⁧" + s + "⁩")]

root = tk.Tk()
root.geometry("760x560+40+40")
root.configure(bg="white")
for name, fn in VARIANTS:
    tk.Label(root, text=name, font=("Segoe UI", 10, "bold"), bg="#ddd").pack(fill="x")
    for s in SAMPLES:
        tk.Label(root, text=fn(s), font=("Segoe UI", 13), bg="white").pack(anchor="e", padx=10)
root.update()
root.after(1500, root.quit)
root.mainloop()
root.update()
x, y = root.winfo_rootx(), root.winfo_rooty()
img = ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height()))
os.makedirs("screenshots", exist_ok=True)
img.save("screenshots/tk_probe.png")
print("TK", root.tk.call("info", "patchlevel"))
