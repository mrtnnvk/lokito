#!/usr/bin/env python3
"""
V1 PIPELINE — Stáhne ČSÚ SLDB 2021 data pro ZSJ (základní sídelní jednotky) Prahy 10.
Výstup: pipeline/data/zsj_demographics.json

STAV: V0 tento skript NEPOTŘEBUJE — compute_probability.py funguje jen s kapacitami.
      V1 tento skript přidá prostorovou poptávku pro přesnější model.

Zdroj: https://csu.gov.cz/produkty/pocty-obyvatel-a-obydlenych-bytu-ze-scitani-2021-i-za-nejmensi-uzemni-jednotky
CSV:   https://csu.gov.cz/docs/107508/91765d52-c844-dfb1-b086-91b8f1d6e758/sldb2021_obyv_byt_cob_zsj.csv

CSV formát (long format):
  idhod, hodnota, ukaz_kod, uzemi_cis, uzemi_kod, sldb_rok, sldb_datum, ukaz_txt, uzemi_txt, uzemi_typ
  "ukaz_txt" = "Počet obyvatel" nebo "Počet bytů"
  "uzemi_cis" = "47" pro ZSJ (základní sídelní jednotka)
  "uzemi_cis" = "42" pro části obcí

Praha 10 ZSJ: filtrujeme podle uzemi_txt obsahujícího názvy čtvrtí Prahy 10:
  Vršovice, Strašnice, Záběhlice, Malešice, Hostivař, Uhříněves, Horní Měcholupy, Petrovice

Pro centroidy ZSJ (lat/lon) použijeme Nominatim geocoding.
Limit: max 1 dotaz/sekunda (Nominatim usage policy).

⚠️ Věkové skupiny NEJSOU dostupné na úrovni ZSJ ze SLDB 2021.
   Používáme celkový počet obyvatel jako proxy.
   Age_6 estimate = total_pop × (P10_age6 / P10_total) ≈ total_pop × 0.0095
"""

import csv
import io
import json
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

SLDB_CSV_URL = (
    "https://csu.gov.cz/docs/107508/"
    "91765d52-c844-dfb1-b086-91b8f1d6e758/"
    "sldb2021_obyv_byt_cob_zsj.csv"
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Praha 10 age_6 fraction (SLDB 2021, Praha 10 level): ~1.0%
# Zdroj: ČSÚ veřejná databáze - Praha 10, věk 6 let / celkem obyvatel
AGE_6_FRACTION = 0.0095

CACHE_PATH = Path(__file__).parent / "data" / "sldb2021_zsj_cache.csv"
OUTPUT_PATH = Path(__file__).parent / "data" / "zsj_demographics.json"

# Názvy částí obce v Praze 10 (filtr)
PRAHA10_ZSJ_NAMES = [
    "Vršovice", "Strašnice", "Záběhlice", "Malešice",
    "Hostivař", "Uhříněves", "Horní Měcholupy", "Petrovice",
    "Dolní Měcholupy", "Benice", "Dubeč", "Kolovraty",
    "Královice", "Nedvězí",
]

Praha10_ZSJ_PREFIXES = tuple(p.lower() for p in PRAHA10_ZSJ_NAMES)


def is_praha10_zsj(name: str) -> bool:
    name_lower = name.lower()
    return any(name_lower.startswith(prefix) for prefix in PRAHA10_ZSJ_PREFIXES)


def download_csv() -> str:
    if CACHE_PATH.exists():
        print(f"Načítám CSV z cache: {CACHE_PATH}")
        return CACHE_PATH.read_text(encoding="utf-8")
    print(f"Stahuji CSV ({SLDB_CSV_URL})...")
    result = subprocess.run(
        ["curl", "-fsSL", "--max-time", "120", "-A", "Lokito/1.0", SLDB_CSV_URL],
        capture_output=True,
        check=True,
    )
    content = result.stdout.decode("utf-8")
    CACHE_PATH.write_text(content, encoding="utf-8")
    print(f"  Uloženo do cache: {CACHE_PATH}")
    return content


def parse_zsj_population(csv_content: str) -> dict[str, dict]:
    """
    Vrátí slovník: zsj_kod → {nazev, count_total}
    Filtruje: uzemi_cis=="47" (ZSJ) + ukaz_txt=="Počet obyvatel" + Praha 10 název
    """
    result: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(csv_content))
    for row in reader:
        if row.get("uzemi_cis") != "47":
            continue
        if row.get("ukaz_txt", "").strip() != "Počet obyvatel":
            continue
        nazev = row.get("uzemi_txt", "").strip()
        if not is_praha10_zsj(nazev):
            continue
        kod = row.get("uzemi_kod", "").strip()
        try:
            count = int(row.get("hodnota", "0") or "0")
        except ValueError:
            count = 0
        result[kod] = {"zsj_kod": kod, "zsj_nazev": nazev, "count_total": count}
    return result


def geocode_zsj(name: str) -> tuple[float, float] | None:
    """Geocode ZSJ jméno pomocí Nominatim. Vrátí (lat, lon) nebo None."""
    import urllib.parse as _up
    query = f"{name}, Praha 10, Česko"
    params = _up.urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "cz"})
    url = f"{NOMINATIM_URL}?{params}"
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "--max-time", "10",
             "-A", "Lokito/1.0 civic-tech",
             url],
            capture_output=True, check=True,
        )
        data = json.loads(result.stdout)
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  ⚠️ Geocoding selhalo pro '{name}': {e}")
    return None


def main() -> None:
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    csv_content = download_csv()

    print("Parsovám ZSJ záznamy pro Prahu 10...")
    zsj_data = parse_zsj_population(csv_content)
    print(f"  Nalezeno {len(zsj_data)} ZSJ s obyvateli v Praze 10")

    print("Geocoduji centroidy ZSJ (Nominatim, max 1 req/s)...")
    zsj_list = []
    for kod, info in sorted(zsj_data.items()):
        coords = geocode_zsj(info["zsj_nazev"])
        lat, lon = coords if coords else (None, None)
        count_age6_est = round(info["count_total"] * AGE_6_FRACTION)
        zsj_list.append({
            "zsj_kod": kod,
            "zsj_nazev": info["zsj_nazev"],
            "centroid_lat": lat,
            "centroid_lon": lon,
            "count_total": info["count_total"],
            "count_age_6": count_age6_est,  # odhad: count_total × 0.0095
            "age_6_estimated": True,        # flag: věk není přímý, je odhadnut
        })
        status = f"lat={lat:.4f}, lon={lon:.4f}" if lat else "geocoding selhalo"
        print(f"  {info['zsj_nazev']} ({kod}): {info['count_total']} obyv, age6≈{count_age6_est} | {status}")
        time.sleep(1.1)  # Nominatim rate limit

    missing_coords = [z for z in zsj_list if z["centroid_lat"] is None]
    if missing_coords:
        print(f"\n⚠️ {len(missing_coords)} ZSJ bez centroidu — budou přeskočeny v build_catchment_map.py")

    output = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "source_csv": SLDB_CSV_URL,
        "source_geocoder": "Nominatim / OSM",
        "data_version": "sldb2021",
        "age_6_method": f"estimate: count_total × {AGE_6_FRACTION} (věk 6 není na ZSJ úrovni dostupný)",
        "zsj_count": len(zsj_list),
        "zsj": zsj_list,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Výstup: {OUTPUT_PATH} ({len(zsj_list)} ZSJ)")


if __name__ == "__main__":
    main()
