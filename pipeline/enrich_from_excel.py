#!/usr/bin/env python3
"""
enrich_from_excel.py — Obohatí web/data/{municipalityId}.json o metadata z MŠMT adresáře škol (Excel).

Použití:
    python3 pipeline/enrich_from_excel.py \
        --excel /cesta/k/Adresar-2.xlsx \
        --json web/data/praha10.json \
        [--district "Praha 10"]

Skript matchuje školy z JSON na řádky v Excelu podle ulice (normalizovaný lowercase bez diakritiky).
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

try:
    import openpyxl
except ImportError:
    raise SystemExit("❌ Chybí openpyxl. Nainstaluj: pip3 install openpyxl")


# ---------------------------------------------------------------------------
# Normalizace textu pro matching
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Lowercase, odstraní diakritiku, zkrátí vícenásobné mezery."""
    if not text:
        return ""
    text = str(text).lower().strip()
    # Odstranění diakritiky (NFD decomposition + strip combining chars)
    nfd = unicodedata.normalize("NFD", text)
    text = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Zkrácení mezer
    text = re.sub(r"\s+", " ", text)
    return text


def extract_street_from_name(school_name: str) -> str:
    """
    Extrahuje ulici ze jména školy.
    Příklady:
      "Základní škola, Praha 10, Kodaňská 658/16" → "Kodaňská"
      "Základní škola, Praha 10, Nad Vodovodem 460/81" → "Nad Vodovodem"
      "Základní škola, Praha 10, V Rybníčkách 1980/31" → "V Rybníčkách"
      "Základní škola Eden, Praha 10, Vladivostocká 1035/6" → "Vladivostocká"
    """
    # Vezmi část za "Praha 10, " nebo "Praha 10 - "
    m = re.search(r"Praha\s+10[,\s-]+(.+)$", school_name)
    if not m:
        return ""
    addr_part = m.group(1).strip()
    # Odstraň ", příspěvková organizace" a podobné sufixy
    addr_part = re.sub(r",?\s*příspěvková organizace.*$", "", addr_part, flags=re.IGNORECASE)
    addr_part = addr_part.strip()
    # Ulice = vše před číslem (první číslice nebo lomítko)
    street_m = re.match(r"^(.*?)\s+\d", addr_part)
    if street_m:
        return street_m.group(1).strip()
    return addr_part  # fallback: celý string


def extract_address_from_plny_nazev(plny_nazev: str) -> str:
    """
    Extrahuje adresní část z plného názvu školy v Excelu.
    "Základní škola Eden, Praha 10, Vladivostocká 1035/6, příspěvková organizace"
    → "Vladivostocká 1035/6, Praha 10"
    """
    m = re.search(r"Praha\s+10[,\s-]+(.+?)(?:,\s*příspěvková|\s*$)", plny_nazev, re.IGNORECASE)
    if m:
        addr = m.group(1).strip().rstrip(",").strip()
        return f"{addr}, Praha 10"
    return ""


def parse_phone(raw: str) -> str | None:
    """Vrátí první telefonní číslo z řetězce (ostatní ignoruje)."""
    if not raw:
        return None
    # Rozdělení na čárce nebo " ,"
    parts = re.split(r"\s*,\s*", str(raw).strip())
    first = parts[0].strip() if parts else ""
    return first if first else None


FOUNDER_TYPE_MAP = {
    "2": "public",   # MČ (městská část)
    "7": "public",   # Kraj / stát
    "3": "church",   # Církev
    "5": "private",  # Soukromý
}


# ---------------------------------------------------------------------------
# Načtení Excelu
# ---------------------------------------------------------------------------

def load_excel_schools(excel_path: Path, district: str) -> list[dict]:
    """Načte všechny řádky z Excelu pro daný okres/obvod."""
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h else "" for h in next(rows)]

    schools = []
    for row in rows:
        row_dict = dict(zip(headers, row))
        if str(row_dict.get("Okres/Obvod", "")).strip() == district:
            schools.append(row_dict)

    wb.close()
    return schools


def build_street_index(excel_schools: list[dict]) -> dict[str, dict]:
    """Vytvoří index: normalized(ulice) → záznam. Pokud kolize, vezme první."""
    index: dict[str, dict] = {}
    for school in excel_schools:
        ulice = str(school.get("Ulice") or "").strip()
        key = normalize(ulice)
        if key and key not in index:
            index[key] = school
    return index


# ---------------------------------------------------------------------------
# Hlavní logika
# ---------------------------------------------------------------------------

def enrich(json_path: Path, excel_path: Path, district: str) -> None:
    print(f"\n=== Načítám JSON: {json_path} ===")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    schools = data.get("schools", [])
    print(f"  Škol v JSON: {len(schools)}")

    print(f"\n=== Načítám Excel: {excel_path} ===")
    excel_schools = load_excel_schools(excel_path, district)
    print(f"  Řádků pro {district}: {len(excel_schools)}")

    street_index = build_street_index(excel_schools)
    print(f"  Ulic v indexu: {len(street_index)}")

    # --- Matching ---
    print("\n=== Matchování ===")
    matched = 0
    unmatched = []

    for school in schools:
        name = school.get("name", "")
        street = extract_street_from_name(name)
        key = normalize(street)

        row = street_index.get(key)

        if not row:
            # Zkus fallback: první slovo ulice
            first_word_key = key.split()[0] if key.split() else ""
            for idx_key, idx_row in street_index.items():
                if idx_key.startswith(first_word_key) and len(first_word_key) > 4:
                    row = idx_row
                    print(f"  ⚠  Fuzzy match: '{street}' → '{idx_row.get('Ulice')}'")
                    break

        if row:
            red_izo = str(row.get("RED_IZO") or "").strip()
            plny_nazev = str(row.get("Plný název") or "").strip()
            zrizovatel_kod = str(row.get("Zřizovatel") or "").strip()
            www = str(row.get("WWW") or "").strip() or None
            email = str(row.get("Email 1") or "").strip() or None
            phone_raw = str(row.get("Telefon") or "").strip()

            # Adresa: přednostně z JSON school.name (je vždy správná),
            # fallback na plný název z Excelu
            address = extract_address_from_plny_nazev(name)
            if not address or "příspěvková" in address:
                address = extract_address_from_plny_nazev(plny_nazev)
            if not address or "příspěvková" in address:
                address = f"{row.get('Ulice', '')}, Praha 10"

            school["redizo"] = red_izo if red_izo else None
            school["address"] = address
            school["website"] = www
            school["phone"] = parse_phone(phone_raw)
            school["email"] = email
            school["founder_type"] = FOUNDER_TYPE_MAP.get(zrizovatel_kod, "public")

            print(f"  ✓  {name[:60]}")
            print(f"       redizo={red_izo}  address={address}")
            matched += 1
        else:
            unmatched.append(name)
            print(f"  ✗  {name[:60]}")

    # --- Výsledek ---
    print(f"\n=== Výsledek: {matched}/{len(schools)} matched ===")
    if unmatched:
        print("Nespárované školy:")
        for u in unmatched:
            print(f"  - {u}")
        print()

    # --- Uložit JSON ---
    data["schools"] = schools
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅  Uloženo do {json_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Obohatí JSON škol z MŠMT adresáře (Excel)")
    parser.add_argument(
        "--excel",
        default=str(Path.home() / "Downloads" / "Adresar-2.xlsx"),
        help="Cesta k Adresar-2.xlsx",
    )
    parser.add_argument(
        "--json",
        default=str(Path(__file__).parent.parent / "web" / "data" / "praha10.json"),
        help="Cesta k {municipalityId}.json",
    )
    parser.add_argument(
        "--district",
        default="Praha 10",
        help="Hodnota sloupce Okres/Obvod v Excelu",
    )
    args = parser.parse_args()

    enrich(
        json_path=Path(args.json),
        excel_path=Path(args.excel),
        district=args.district,
    )


if __name__ == "__main__":
    main()
