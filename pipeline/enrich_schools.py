#!/usr/bin/env python3
"""
Lokito — Obohacení dat škol z MŠMT rejstříku

Pro každou školu z OZV vyhlášky najde odpovídající záznam v MŠMT rejstříku
školských zařízení a doplní: REDIZO, adresu, web, telefon, email, typ zřizovatele.
GPS souřadnice jsou geocódovány z officiální adresy přes Nominatim.

Použití:
    python enrich_schools.py [--json web/data/praha10.json] [--xml-cache msmt.xml]

Zdroj dat:
    https://rejstriky.msmt.cz/opendata/vrejstrik-po.xml.gz
"""

import argparse
import gzip
import json
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

MSMT_URL = "https://rejstriky.msmt.cz/opendata/vrejstrik-po.xml.gz"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1  # seconds between requests (rate limit)

# Mapping kódů zřizovatele → founder_type
# https://rejstriky.msmt.cz/opendata/ — číselník DruhZrizovatele
FOUNDER_MAP = {
    "1": "public",   # Obec
    "2": "public",   # Svazek obcí
    "3": "public",   # Kraj
    "4": "public",   # Ministerstvo
    "5": "public",   # Ostatní ústřední orgány státní správy
    "6": "public",   # Česká školní inspekce
    "7": "public",   # Jiné
    "8": "private",  # Fyzická osoba (soukromá)
    "9": "private",  # Právnická osoba (soukromá)
    "10": "church",  # Registrovaná církev
    "11": "public",  # Státní podnik / veřejná instituce
}


# ── Normalizace textu pro fuzzy matching ──────────────────────────────────────

def normalize(s: str) -> str:
    """Odstraní diakritiku, lowercase, sjednotí whitespace."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_street_number(school_name: str) -> tuple[str, str]:
    """
    Ze jména školy jako 'Základní škola Eden, Praha 10, Vladivostocká 1035/6'
    extrahuje ulici a číslo popisné/orientační.
    Vrací (street, number) nebo ("", "").
    """
    # Poslední segment za posledním ',' obsahuje adresu
    parts = school_name.split(",")
    if len(parts) < 3:
        return "", ""
    addr = parts[-1].strip()
    # Ulice + číslo: "Vladivostocká 1035/6" nebo "V Olšinách 200/69"
    m = re.match(r"^(.+?)\s+(\d+(?:/\d+)?)$", addr)
    if not m:
        return "", ""
    return m.group(1).strip(), m.group(2).strip()


# ── Stažení a parsování MŠMT XML ─────────────────────────────────────────────

def download_msmt_xml(cache_path: Path | None) -> ET.Element:
    """Stáhne a parsuje MŠMT rejstřík XML. Cachuje do souboru."""
    if cache_path and cache_path.exists():
        print(f"  Načítám XML z cache: {cache_path}")
        tree = ET.parse(cache_path)
        return tree.getroot()

    print(f"  Stahuji MŠMT rejstřík z {MSMT_URL} ...")
    req = urllib.request.Request(
        MSMT_URL,
        headers={"User-Agent": "Lokito/1.0 (civic-tech school finder)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        compressed = resp.read()

    xml_bytes = gzip.decompress(compressed)

    if cache_path:
        cache_path.write_bytes(xml_bytes)
        print(f"  XML uložen do cache: {cache_path}")

    return ET.fromstring(xml_bytes)


def build_lookup(root: ET.Element) -> list[dict]:
    """
    Z XML vytvoří seznam aktivních ZŠ záznamů.
    Namespace se zjistí dynamicky z root tagu.
    """
    # Zjisti namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    def t(tag):
        return f"{ns}{tag}"

    records = []

    for po in root.iter(t("PravnickaOsoba")):
        # Přeskočit zrušené záznamy
        if po.findtext(t("DatumVymaz")):
            continue

        # Typ: hledáme ZŠ (základní školy)
        druh = po.findtext(t("DruhPravnickeOsoby")) or ""
        if "základní škola" not in druh.lower() and "zakladni skola" not in normalize(druh):
            continue

        redizo = po.findtext(t("RedIzo")) or ""
        ico = po.findtext(t("Ico")) or ""
        name = po.findtext(t("NazevPravnickeOsoby")) or ""
        zrizovatel_kod = po.findtext(t("DruhZrizovatele")) or ""
        website = po.findtext(t("Www")) or ""
        email = po.findtext(t("Email")) or ""
        phone = po.findtext(t("Telefon")) or ""

        # Adresa
        adresa = po.find(t("Adresa"))
        ulice = ""
        cislo = ""
        psc = ""
        obec = ""
        if adresa is not None:
            ulice = adresa.findtext(t("Ulice")) or ""
            cislo_or = adresa.findtext(t("CisloOrientacni")) or ""
            cislo_pop = adresa.findtext(t("CisloPopisne")) or ""
            cislo = f"{cislo_pop}/{cislo_or}" if cislo_or else cislo_pop
            psc = adresa.findtext(t("Psc")) or ""
            obec = adresa.findtext(t("Obec")) or ""

        records.append({
            "redizo": redizo,
            "ico": ico,
            "name": name,
            "name_norm": normalize(name),
            "founder_code": zrizovatel_kod,
            "founder_type": FOUNDER_MAP.get(zrizovatel_kod, "public"),
            "street": ulice,
            "street_number": cislo,
            "psc": psc,
            "city": obec,
            "website": website.rstrip("/") if website else None,
            "email": email or None,
            "phone": phone or None,
            "address_full": f"{ulice} {cislo}, {psc} {obec}".strip(", "),
        })

    return records


def match_school(school: dict, records: list[dict]) -> dict | None:
    """
    Pokusí se namatchovat školu z OZV na záznam v rejstříku.
    Strategie (od nejpřesnější):
    1. Shoda ulice + číslo orientační (z adresy ve jménu školy)
    2. Fuzzy shoda názvu školy
    """
    street, number = extract_street_number(school["name"])
    # Normalizujeme číslo: vzít jen orientační část (za lomítkem) nebo celé
    orient_number = number.split("/")[-1] if "/" in number else number

    # 1. Přesná shoda ulice + č.o. ve stejném okrese
    if street:
        street_norm = normalize(street)
        for rec in records:
            rec_street_norm = normalize(rec["street"])
            rec_number = rec["street_number"].split("/")[-1] if "/" in rec["street_number"] else rec["street_number"]
            if rec_street_norm == street_norm and rec_number == orient_number:
                return rec

    # 2. Fuzzy shoda názvu (bez adresy)
    # Ze jména školy vezmeme první dvě části (před třetí čárkou)
    school_name_parts = school["name"].split(",")
    school_name_short = normalize(",".join(school_name_parts[:2]))
    best_score = 0
    best_rec = None
    for rec in records:
        # Startswith nebo obsahuje klíčová slova
        if school_name_short and rec["name_norm"].startswith(school_name_short[:20]):
            score = len(school_name_short)
            if score > best_score:
                best_score = score
                best_rec = rec

    return best_rec if best_score > 10 else None


# ── Geocódování ───────────────────────────────────────────────────────────────

def geocode(address: str) -> tuple[float, float] | None:
    """Geocóduje adresu přes Nominatim. Vrací (lat, lon) nebo None."""
    params = urllib.parse.urlencode({
        "format": "json",
        "limit": "1",
        "q": address,
        "countrycodes": "cz",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Lokito/1.0 (civic-tech school finder)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"    WARN geocode failed for '{address}': {e}")
    return None


# ── Hlavní logika ─────────────────────────────────────────────────────────────

def enrich(json_path: Path, xml_cache: Path | None, skip_geocode: bool) -> None:
    import urllib.parse  # noqa: needed for geocode()

    print(f"\n=== Načítám OZV data: {json_path} ===")
    data = json.loads(json_path.read_text("utf-8"))
    schools = data["schools"]
    rules = data["rules"]

    print(f"  Škol v OZV: {len(schools)}")
    print(f"  Pravidel:   {len(rules)}")

    # Všechny school_id z rules
    rule_school_ids = {r["school_id"] for r in rules}
    school_ids_in_data = {s["id"] for s in schools}
    orphan_ids = rule_school_ids - school_ids_in_data
    if orphan_ids:
        print(f"\n  ERROR: school_id v rules bez záznamu v schools[]: {orphan_ids}")
        sys.exit(1)

    print(f"\n=== Načítám MŠMT rejstřík ===")
    root = download_msmt_xml(xml_cache)
    records = build_lookup(root)
    print(f"  Aktivních ZŠ v rejstříku: {len(records)}")

    print(f"\n=== Matching ===")
    matched = 0
    unmatched = []

    for school in schools:
        rec = match_school(school, records)
        if rec:
            school["redizo"] = rec["redizo"]
            school["address"] = rec["address_full"]
            school["founder_type"] = rec["founder_type"]
            school["website"] = rec["website"]
            school["phone"] = rec["phone"]
            school["email"] = rec["email"]
            matched += 1
            print(f"  ✓ {school['id']}")
            print(f"    → {rec['name']} | REDIZO {rec['redizo']} | {rec['founder_type']}")

            # Geocódování z officiální adresy
            if not skip_geocode and rec["address_full"]:
                print(f"    → Geocóduji: {rec['address_full']}")
                coords = geocode(rec["address_full"])
                if coords:
                    school["lat"], school["lon"] = coords
                    print(f"    → GPS: {coords[0]:.7f}, {coords[1]:.7f}")
                else:
                    print(f"    WARN: geocódování selhalo, ponechávám stávající GPS")
                time.sleep(NOMINATIM_DELAY)

            # Zkontroluj DatumVymaz (nemělo by nastat, ale pro jistotu)
        else:
            school.setdefault("redizo", None)
            school.setdefault("founder_type", None)
            school.setdefault("website", None)
            school.setdefault("phone", None)
            school.setdefault("email", None)
            unmatched.append(school["id"])
            print(f"  ✗ {school['id']} — NENALEZENO v rejstříku")

    print(f"\n=== Výsledek ===")
    print(f"  Matched:   {matched}/{len(schools)}")
    if unmatched:
        print(f"  Unmatched: {unmatched}")
        print(f"  → Doplňte ručně do pipeline/data/schools_registry.json")

    # Ulož výsledek
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n  Uloženo: {json_path}")

    if unmatched:
        sys.exit(2)  # Partial match — varování


if __name__ == "__main__":
    import urllib.parse

    parser = argparse.ArgumentParser(description="Obohatí školy z MŠMT rejstříku.")
    parser.add_argument(
        "--json",
        default=str(Path(__file__).parent.parent / "web" / "data" / "praha10.json"),
        help="Cesta k OZV JSON souboru",
    )
    parser.add_argument(
        "--xml-cache",
        default=str(Path(__file__).parent / "data" / "msmt_rejstrik.xml"),
        help="Cache soubor pro MŠMT XML (vynechá stahování při opakování)",
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Nepřegeocodovávat GPS (zachovat stávající)",
    )
    args = parser.parse_args()

    enrich(
        json_path=Path(args.json),
        xml_cache=Path(args.xml_cache) if args.xml_cache else None,
        skip_geocode=args.skip_geocode,
    )
