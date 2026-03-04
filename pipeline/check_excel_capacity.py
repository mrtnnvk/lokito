#!/usr/bin/env python3
"""
Ověří, zda Adresar-2.xlsx obsahuje sloupec s kapacitami škol.
V0 pipeline: potvrzuje, že kapacity MUSÍME stáhnout z MŠMT JSON-LD.
"""

import sys
import json
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("Nainstaluj: pip install openpyxl")
    sys.exit(1)

DEFAULT_PATH = Path.home() / "Downloads" / "Adresar-2.xlsx"

def main(xlsx_path: str | None = None) -> None:
    path = Path(xlsx_path) if xlsx_path else DEFAULT_PATH
    if not path.exists():
        print(f"Soubor nenalezen: {path}")
        sys.exit(1)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    headers = [str(cell.value or "").strip() for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    wb.close()

    CAPACITY_KEYWORDS = ["kapacita", "capacity", "počet žáků", "pocet zaku", "nejvyšší", "max žáků"]
    found = [h for h in headers if any(kw in h.lower() for kw in CAPACITY_KEYWORDS)]

    print("=" * 60)
    print(f"Soubor: {path.name}")
    print(f"Počet sloupců: {len(headers)}")
    print()
    print("Všechny sloupce:")
    for i, h in enumerate(headers, 1):
        print(f"  {i:2}. {h}")
    print()

    if found:
        print(f"✅ Nalezeny sloupce s kapacitou: {found}")
        result = "HAS_CAPACITY"
    else:
        print("❌ Žádný sloupec s kapacitou nenalezen.")
        print("   → Kapacity budeme stahovat z MŠMT JSON-LD (pipeline/download_msmt_capacity.py)")
        result = "NO_CAPACITY"

    print("=" * 60)

    # Uložit výsledek jako JSON pro potenciální strojové čtení
    out = Path(__file__).parent / "data" / "check_excel_capacity_result.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "result": result,
        "xlsx_path": str(path),
        "columns": headers,
        "capacity_columns_found": found,
    }, ensure_ascii=False, indent=2))
    print(f"Výsledek uložen: {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
