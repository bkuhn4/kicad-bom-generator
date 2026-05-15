# KiCad BOM Enhancer & Procurement Tool

A desktop application for enriching KiCad Bill of Materials CSVs with distributor data, managing part numbers, and exporting formatted Excel spreadsheets.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

- **Import KiCad BOMs** — Reads the CSV exported from KiCad's BOM generator. Flexible column detection handles varying export formats.
- **Distributor lookup** — Fetches MPN, stock, and part numbers from DigiKey and Mouser via their APIs. Supports fetching all rows or selected rows only.
- **Part Dictionary** — SQLite database that remembers MPN, manufacturer, distributor PNs, and description keyed by value + footprint. Auto-fills on load and saves after every fetch.
- **LCSC PN tracking** — Manually enter LCSC part numbers; they are saved independently and never overwritten by API lookups.
- **Footprint aliases** — Map verbose KiCad footprint names (e.g. `C_0402_1005Metric_Pad0.74x0.62mm_HandSolder`) to short aliases (`C0402`). Aliases are stored in `footprint_map.json` inside the repo so the whole team shares them via git.
- **Reference compression** — Compresses reference designator lists into ranges (`R1, R2, R3, R4` → `R1-R4`). Toggle per-session from the References column header right-click menu or Settings.
- **Status indicators** — Each row shows a color-coded dot: green (in stock), yellow (low stock / missing distributor PN), red (out of stock / missing MPN).
- **Issues panel** — Collapsible panel below the table listing every non-green row with its reason.
- **Excel export** — Styled `.xlsx` with colored header, alternating row stripes, auto-fit columns, frozen header row, optional project name/revision title row, and optional created date/time footer.
- **CSV round-trip** — Save and re-load the enhanced BOM as CSV; packaging selections, notes, LCSC PNs, and all distributor data are preserved.
- **Column control** — Show/hide and include/exclude individual columns from the export. Drag columns to reorder; order is saved between sessions.
- **Search bar** — Toolbar search filters the table to the first matching row across all text fields.

---

## Requirements

```
Python 3.9+
PyQt6 >= 6.4.0
pandas >= 2.0.0
openpyxl >= 3.1.0
requests >= 2.28.0
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Running

```bash
python main.py
```

---

## API Setup

### DigiKey

1. Go to [developer.digikey.com](https://developer.digikey.com) and create an account if you don't have one.
2. In the developer portal, create a new **Production App**.
3. Set the **OAuth Callback URL** to exactly: `https://localhost:8139/digikey_callback`
4. Under API selection, ensure you select the appropriate Product Information/Search APIs.
5. Note your **Client ID** and **Client Secret**.
6. Open **Settings → API Credentials & Preferences** in the app and enter them.
7. Click **Test Connection** — the app will open a browser for OAuth authorization. After logging in, copy the full redirect URL from the address bar and paste it into the dialog. The token is saved locally and refreshes automatically.

### Mouser

1. Go to the [Mouser API Hub](https://www.mouser.com/api-hub/) (sign in to your Mouser account).
2. Register for the **Search API** to generate your API key.
3. Enter it in **Settings → API Credentials & Preferences → Mouser API**.
4. Click **Test Connection** to verify.

API credentials are stored in `~/.kicad_bom_enhancer/config.json` and are never committed to the repo.

---

## Footprint Aliases

Footprint aliases let you normalize KiCad's verbose footprint names to short, readable strings that are also used as keys in the Part Dictionary.

- Open **Settings → Edit Footprint Aliases** to add, edit, or delete mappings.
- Use **Add from Current BOM** to pre-populate the table with all footprints from the loaded BOM.
- Aliases are saved to `footprint_map.json` at the repo root — commit this file so teammates get the same aliases automatically on `git pull`.
- Right-click the **Footprint** column header to toggle aliases on/off for the current session without changing the saved config.

---

## Team Workflow

| File | Location | Committed to repo? |
|------|----------|--------------------|
| `footprint_map.json` | repo root | **Yes** — shared aliases |
| `config.json` | `~/.kicad_bom_enhancer/` | No — API keys & personal prefs |
| `part_dictionary.db` | `~/.kicad_bom_enhancer/` | No — local cache |
| DigiKey token | `~/.kicad_bom_enhancer/digikey_tokens/` | No |

To share footprint aliases: edit them in the dialog → Save → `git add footprint_map.json && git commit`.

---

## Excel Export

Configure in **Settings → Export**:

| Option | Description |
|--------|-------------|
| Project Name | Printed as a centered bold title above the header row |
| Revision | Printed as `Rev X` in the top-right of the title row |
| Include title/revision | Toggle the title row on/off |
| Include date/time footer | Adds `Created: H:MM AM/PM M/D/YYYY` below the data |
| Header Color | Background color for the column header row (6 presets + color picker) |
| Column Visibility / Export | Control which columns appear in the table and which are exported |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Import CSV |
| `Ctrl+S` | Save CSV |
| `Ctrl+Shift+S` | Save CSV As |
| `Ctrl+E` | Export to Excel |
| `Ctrl+Q` | Quit |

---

## Project Structure

```
kicad-bom-generator/
├── main.py                  Entry point
├── requirements.txt
├── footprint_map.json       Shared footprint aliases (commit this)
├── api/
│   ├── digikey.py           DigiKey v4 API client + OAuth
│   └── mouser.py            Mouser API client
├── core/
│   ├── bom_parser.py        CSV parsing, ref expansion/compression
│   ├── config_manager.py    Load/save ~/.kicad_bom_enhancer/config.json
│   ├── database.py          SQLite part dictionary
│   ├── exporter.py          Excel + CSV export
│   ├── footprint_map.py     Load/save footprint_map.json
│   └── status.py            Row status calculation (green/yellow/red)
└── gui/
    ├── main_window.py       Main application window
    ├── bom_table.py         QAbstractTableModel + packaging delegate
    ├── footprint_dialog.py  Footprint alias editor
    ├── search_dialog.py     Part search & assign dialog
    ├── settings_dialog.py   Settings dialog (API keys, export, preferences)
    └── workers.py           Background QThread workers (fetch, search, test)
```
