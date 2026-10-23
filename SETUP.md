# Setup guide

## 1. Install the program

There are two programs. Download the one you need — or both, they don't share data:

| Setup file | Program | Language |
|---|---|---|
| `POS_Setup_<version>.exe` | Electronics POS | English |
| `ShopPOS_Arabic_Setup_<version>.exe` | Shop POS — نظام المتجر | Arabic |

### Option A — Installer (recommended, no Python needed)

1. Download the setup file from the
   **[latest release](https://github.com/21730660-itlab/possales/releases/latest)**.
2. Double-click it. If Windows shows **"Windows protected your PC"**, click **More info → Run anyway**.
   This warning appears because the installer is not code-signed; it is expected.
3. Click **Next** through the steps and keep **"Create a desktop shortcut"** ticked.
4. Start the program from the desktop shortcut (**Electronics POS** or **نظام المتجر - Shop POS**).

| | Electronics POS | Shop POS (Arabic) |
|---|---|---|
| Program folder | `C:\Program Files\Electronics POS` | `C:\Program Files\Shop POS` |
| Shop data | `C:\ProgramData\ElectronicsPOS` | `C:\ProgramData\ShopPOS` |

Uninstalling does **not** delete the shop data.

**Updating:** run the newer `POS_Setup_….exe` over the old one. Your data stays in place.

**Publishing a new version (for whoever maintains the code):** raise `__version__` in
`pos/__init__.py`, push, then on GitHub open **Actions → Build Windows installer → Run workflow**
and enter the new tag (e.g. `v1.4.0`). Both installers are built, tested and published as a release.

### Option B — Run with Python

1. Install Python 3.10+ from <https://www.python.org/downloads/> and tick **"Add python.exe to PATH"**.
2. Download the project (GitHub → **Code → Download ZIP**) and unzip it.
3. Double-click **`run_pos.bat`** (Electronics POS) or **`run_shop_arabic.bat`** (Arabic Shop POS).
   Data is kept in the `data` / `data_shop_ar` folder next to it.

## 2. First start (10 minutes)

1. Sign in with **admin / admin**, then choose a new password.
2. **Settings → Shop:** enter your shop name, address, phone and tax number.
3. **Settings → Tax & money:** set the VAT rate, currency symbol and **today's LBP exchange rate**.
   Update the rate whenever it changes.
4. **Settings → Receipts:** choose the receipt language (English / Arabic / both) and the paper width
   (32 for 58 mm, 42 or 48 for 80 mm). Write your thank-you message.
5. **Settings → Arabic:** enter the shop name, address and footer in Arabic (if you use Arabic receipts).
6. **Settings → Payments:** list the ways you accept money, e.g.
   `Card, Whish Money, OMT, Bank Transfer, Cheque`.
7. **Settings → Rules:** set the maximum discount a cashier may give and the return period.
8. Press **💾 Save settings**.
9. **Users:** create one account per employee (role **cashier** or **manager**). Do not share the
   admin password.

## 3. Add your products

- One by one: **Products → + New product** (scan the barcode into the Barcode box).
- Many at once: **Products → Export CSV**. This gives you an Excel-ready template. Fill it in, then
  use **Import CSV**.
- Phones / laptops / TVs: tick **Track serial / IMEI numbers** and set the warranty months.
- Products with no barcode: select them → **Generate missing barcodes** → **🏷 Print labels**.

To try the program first, **Settings → Load sample data** adds demo products.

## 4. Connect the hardware

| Device | What to do |
|---|---|
| **Barcode scanner** (USB) | Plug it in — nothing to set up. It types into the scan box and presses Enter. |
| **Receipt printer** (58/80 mm) | Install its Windows driver and print a Windows test page. For paper cut + cash drawer, see below. |
| **Cash drawer** | Plug it into the receipt printer's RJ11 "DK" port. Tick **Settings → Receipts → Open cash drawer after cash sales**. |
| **Label printer** | Install its Windows driver, then pick its type in **Settings → Labels** and set the label size in mm. |

**Receipt printer with paper cut and cash drawer (ESC/POS):**
the installer already includes the needed printing support (pywin32 — with Option B run
`pip install pywin32` once). Type the printer's exact name from
*Windows Settings → Bluetooth & devices → Printers & scanners* into **Settings → Receipts →
Receipt printer name**.

**Label printer types (Settings → Labels):**
- **Label printer (via browser):** works with every label printer. Labels open in the browser.
  Press **Ctrl+P**, choose the label printer, set margins to **None** and scale to **100%**.
- **A4 sheet:** for sticker sheets on a normal office printer.
- **Zebra (ZPL)** or **TSC / Xprinter (TSPL):** these print directly with no browser step.
  Also type the label printer's Windows name. English text only.

## 5. Every day

1. **Morning:** **Cash Drawer → Open shift**, then enter the starting cash.
2. Sell from **New Sale**. Press **F12** to pay.
3. **Evening:** **Cash Drawer → Close shift**, then count the cash and enter it.
   The Z report shows over/short.

## 6. Backups — please read

- A backup is made **automatically every time the program is closed**. The last 30 are kept in
  `…\ElectronicsPOS\backups`.
- **Once a week, copy the `backups` folder to a USB stick or Google Drive.** A broken or stolen PC
  takes local backups with it.
- To move to a new PC: install the program, then **Settings → Restore from backup…** and pick
  the latest backup file.

## Problems?

| Problem | Fix |
|---|---|
| "Windows protected your PC" | **More info → Run anyway** (unsigned installer). |
| Receipt does not print | Print a Windows test page first. If you entered a printer name, check that it matches exactly. |
| Arabic shows as `???` on the receipt | Make sure Settings → Receipts language is Arabic/both; Arabic is printed through Windows automatically. |
| Forgot a cashier's password | Sign in as admin → **Users → Reset password**. |
| Program shows an error | Details are saved in `error.log` in the data folder — send that file for help. |
