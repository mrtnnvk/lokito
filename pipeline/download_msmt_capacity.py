#!/usr/bin/env python3
"""
Stáhne MŠMT NKOD JSON-LD rejstřík škol a extrahuje kapacity
pro 14 spádových ZŠ Prahy 10 podle REDIZO.

Zdroj: https://data.gov.cz/dataset?iri=...8e4bab9c3d258b0850c9f43080ba78e5
       (Rejstřík škol a školských zařízení - celá ČR 2025)

Formát JSON-LD:
  { "list": [
      {
        "redIzo": "600041158",
        "skolyAZarizeni": [
          {
            "druh": "B00",              ← B** = základní škola
            "kapacity": [
              { "mernaJednotka": "04",  ← 04 = žáci
                "nejvyssiPovolenyPocet": 600 }
            ]
          }
        ]
      }
  ]}
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

# Nejnovější dostupná verze (September 30, 2025)
MSMT_URL = (
    "https://lkod-ftp.msmt.gov.cz/00022985/"
    "e9c07729-877e-4af0-be4a-9d36e45806ae/"
    "rssz-cela-cr-2025-09-30.jsonld"
)

# Fallback verze (March 31, 2025) — použij pokud hlavní URL nefunguje
MSMT_URL_FALLBACK = (
    "https://lkod-ftp.msmt.gov.cz/00022985/"
    "e9c07729-877e-4af0-be4a-9d36e45806ae/"
    "rssz-cela-cr-2025-03-31.jsonld"
)

CACHE_PATH = Path(__file__).parent / "data" / "msmt_rejstrik_2025.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "capacity_raw.json"
SCHOOLS_JSON = Path(__file__).parent.parent / "web" / "data" / "praha10.json"

# Kód druhu pro základní školy (B00 = ZŠ, B22 = ZŠ při zdravotnickém zařízení apod.)
ZS_DRUH_PREFIX = "B"

# Měrné jednotky kapacity v MŠMT rejstříku pro ZŠ:
#   "01" = žáci ZŠ (nejvyssiPovolenyPocet = kapacita školy)
#   "04" = místa MŠ (pro mateřské školy)
# Akceptujeme "01" i "04" a bereme první nalezenou hodnotu pro druh B*.
ZS_KAPACITA_JEDNOTKY = {"01", "04"}


def load_redizo_set() -> dict[str, str]:
    """Načte REDIZO → school_id z web/data/praha10.json."""
    data = json.loads(SCHOOLS_JSON.read_text(encoding="utf-8"))
    result = {}
    for s in data.get("schools", []):
        r = s.get("redizo")
        if r:
            result[r] = s["id"]
    return result


def download_json(url: str) -> dict:
    """Stáhne JSON pomocí curl (workaround pro SSL certifikáty na macOS Python 3.13)."""
    print(f"Stahuji: {url}")
    result = subprocess.run(
        ["curl", "-fsSL", "--max-time", "120", "-A", "Lokito/1.0 (civic-tech)", url],
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout.decode("utf-8"))


def extract_zs_kapacita(skola_record: dict) -> int | None:
    """
    Projde skolyAZarizeni a najde kapacitu pro ZŠ (druh B*).
    Měrná jednotka: "01" = žáci ZŠ, "04" = místa MŠ.
    Vrátí nejvyssiPovolenyPocet pro první B* zařízení s nenulovou kapacitou.
    """
    for zarizeni in skola_record.get("skolyAZarizeni", []):
        druh = zarizeni.get("druh", "")
        if not druh.startswith(ZS_DRUH_PREFIX):
            continue
        # Vezmi první kapacitu s libovolnou měrnou jednotkou (pro ZŠ je to "01")
        for kap in zarizeni.get("kapacity", []):
            val = kap.get("nejvyssiPovolenyPocet")
            if val is not None and int(val) > 0:
                return int(val)
    return None


def main() -> None:
    OUTPUT_PATH.parent.mkdir(exist_ok=True)

    redizo_map = load_redizo_set()
    if not redizo_map:
        print("Chyba: Žádné REDIZO nenačteno z praha10.json")
        sys.exit(1)
    print(f"Hledám kapacity pro {len(redizo_map)} škol: {list(redizo_map.keys())}")

    # Načíst z cache nebo stáhnout
    if CACHE_PATH.exists():
        print(f"Načítám z cache: {CACHE_PATH}")
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    else:
        try:
            data = download_json(MSMT_URL)
        except Exception as e:
            print(f"Hlavní URL selhala ({e}), zkouším fallback...")
            data = download_json(MSMT_URL_FALLBACK)
        CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"Uloženo do cache: {CACHE_PATH}")

    records = data.get("list", [])
    print(f"Zpracovávám {len(records)} záznamů z rejstříku...")

    results: dict[str, dict] = {}
    not_found = list(redizo_map.keys())

    for record in records:
        redizo = record.get("redIzo", "")
        if redizo not in redizo_map:
            continue

        kapacita = extract_zs_kapacita(record)
        school_id = redizo_map[redizo]
        uplny_nazev = record.get("uplnyNazev", "")

        results[redizo] = {
            "school_id": school_id,
            "uplny_nazev": uplny_nazev,
            "kapacita": kapacita,
            "pocet_zaku": None,  # Není v rejstříku — viz MŠMT výkonová data (V1)
        }
        not_found.remove(redizo)
        status = f"kapacita={kapacita}" if kapacita else "kapacita=N/A"
        print(f"  ✓ {redizo} ({school_id}): {status}")

    if not_found:
        print(f"\n⚠️  REDIZO nenalezena v rejstříku: {not_found}")
        for redizo in not_found:
            results[redizo] = {
                "school_id": redizo_map[redizo],
                "uplny_nazev": None,
                "kapacita": None,
                "pocet_zaku": None,
            }

    output = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "source_url": MSMT_URL,
        "data_version": "msmt-2025-09",
        "note": "pocet_zaku není dostupný z rejstříku; přidán v V1 z MŠMT výkonových dat",
        "schools": results,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Výstup: {OUTPUT_PATH}")
    print(f"   Nalezeno: {len(results) - len(not_found)}/{len(redizo_map)} škol s kapacitou")


if __name__ == "__main__":
    main()
