# Electronics POS

A complete point-of-sale system for an electronics shop. It runs on Windows with Python and needs
**no extra packages**: it uses only Tkinter and SQLite, which come with Python.

## Quick start (Windows)

1. Install **Python 3.10 or newer** from <https://www.python.org/downloads/>. During setup, tick
   **"Add python.exe to PATH"**.
2. Double-click **`run_pos.bat`** (or run `python main.py`).
3. Sign in with **`admin` / `admin`**. You will be asked to choose a new password.
4. Optional: go to **Settings → Load sample electronics data** to try the system with demo products.
5. Go to **Settings** and enter your shop name, address, tax rate, currency and exchange rate.

To install on a till PC that has no Python, run **`build_exe.bat`** once. It builds `dist\POS.exe`,
which you can copy to the shop computer.

## Features

### Selling (New Sale screen)
- Scan a **barcode, SKU or serial/IMEI** (USB barcode scanners work out of the box), or search by name.
- **Serial / IMEI tracking** for phones, laptops and TVs. The POS asks for the serial when you sell
  one and blocks selling the same serial twice.
- **Warranty dates** are calculated automatically and printed on the receipt.
- Line discounts, an order discount (amount or %) and price override.
- **Discount limit** for cashiers. A manager's username and password are needed to go above it.
- **Split payments**: Cash, customer **Account** (credit), loyalty **Points**, plus **your own payment
  methods** (Card, Whish Money, OMT, Bank Transfer, Installments…). Set them in **Settings → Payments**.
- **Two currencies** (e.g. USD + LBP). Totals and change are shown in both, and cash can be taken
  in the second currency.
- **Hold / recall** sales (park a customer and serve the next one).
- Receipts for 58 mm / 80 mm thermal printers, with automatic printing and a cash-drawer kick.
- **Receipts in English, Arabic, or both.** Set the language in **Settings → Receipts**, and your
  Arabic shop name, address and footer in **Settings → Arabic**.
- Keyboard shortcuts: `F2` qty · `F3` find · `F4` discount · `F5` price · `F6` order discount ·
  `F7` customer · `F8` hold · `F9` recall · `Del` remove · `F12` pay.

### Sales & returns
- Search past invoices by number, customer, phone, serial or item, and reprint receipts.
- **Returns / refunds** (partial or full): choose whether to restock, set the refund method and
  reason, and print a return receipt. Returns have a time limit, and managers can override it.

### Products & inventory
- Categories, brands, suppliers, cost and selling price, margin, shelf location and reorder level.
- Opening stock, stock adjustments with reasons, **stock count (stock-take)** and full movement history.
- Low-stock alerts, stock valuation (at cost and retail) and a slow-movers report.
- **CSV import / export** of the product list (works with Excel).
- **Barcode labels** (Code 128): select products and press **Print labels**, or print labels for
  everything received on a purchase order. Products without a barcode can get an in-store barcode
  automatically (**Generate missing barcodes**).

### Purchasing
- Purchase orders to suppliers, with **one-click reorder of low-stock items**.
- Receive orders fully or partly, scan serial numbers as you receive, and update cost by
  weighted average.

### Customers
- Contact details, purchase history and **loyalty points** (earn and redeem).
- **Customer accounts (credit / debt)** with a credit limit and payment collection.

### Repairs / service desk
- Repair tickets (device, model, IMEI, problem, accessories, passcode, estimate, technician,
  promised date).
- Status workflow: Received → Diagnosing → Waiting for Parts → In Progress → Ready for Pickup →
  Delivered.
- Deposits and payments, plus a printed ticket for the customer.

### Warranty check
- Look up any sold item by serial/IMEI, invoice number or customer phone to see whether its
  warranty is still valid.

### Cash drawer & shifts
- Open a shift with a starting float, record cash in / cash out, and print X reports.
- Close the shift with a **Z report**: expected vs counted cash, and over/short.

### Expenses & reports
- Expenses by category (rent, generator, salaries…), optionally paid from the drawer.
- Reports: daily sales, top products, sales by category / brand / cashier / hour, payments by
  method, top customers, expenses, customer debts. Every report can be exported to CSV.
- **Profit & loss statement** (revenue, cost of goods, gross profit, repair income, expenses and
  net profit).

### Users & security
- Roles: **admin**, **manager** and **cashier**, each with its own permissions.
- Passwords are hashed (PBKDF2). Every important action is recorded in the **audit log**.
- **Automatic backup** each time the program closes (the last 30 are kept), plus manual
  backup / restore.

## Receipt printer & cash drawer

- By default, receipts are printed on the **Windows default printer**.
- For a thermal ESC/POS printer with paper cut and cash drawer kick, install `pywin32`
  (`pip install pywin32`). Then enter the printer's exact Windows name under
  **Settings → Receipts**.
- Set the receipt width to **32** characters for 58 mm paper, or **42–48** for 80 mm paper.
- **Arabic receipts:** thermal printers' built-in character sets cannot join Arabic letters, so
  receipts with Arabic text are printed through Windows (Notepad), which shapes Arabic correctly.
  With pywin32 installed they go to the printer you named; without it, to the Windows default printer.

## Barcode label printer

Choose the printer type in **Settings → Labels**:

| Type | Use it for |
|---|---|
| Label printer (via browser) | any label printer installed in Windows. One label per page, sized in mm. |
| A4 sheet (via browser) | sticker sheets on a normal printer |
| Zebra / ZPL (direct) | Zebra and compatible printers (needs pywin32 + the printer name) |
| TSC / Xprinter / TSPL (direct) | TSC, Xprinter and compatible printers (needs pywin32 + the printer name) |

Browser labels support Arabic product names. The direct ZPL/TSPL modes print English text only
(other characters are left out), but the barcode is the same.

## Data

Everything is stored in the `data` folder next to the program:

| Path | Contents |
|---|---|
| `data/pos.db` | the database |
| `data/backups/` | automatic backups |
| `data/receipts/` | a text copy of every receipt / report |
| `data/labels/` | the last printed labels |
| `data/error.log` | details of unexpected errors |

Copy the whole `data` folder to move the shop to another PC.

## Development

```
python -m unittest        # run the test suite
```

| Path | Contents |
|---|---|
| `pos/db.py` | database schema, settings, transactions, backup |
| `pos/services/` | business logic (no UI): sales, catalog, purchasing, people, operations, reports, receipts, auth |
| `pos/ui/` | Tkinter screens |
| `tests/` | unit tests for the business logic |
