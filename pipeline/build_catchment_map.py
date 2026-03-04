#!/usr/bin/env python3
"""
V1 PIPELINE — Přiřadí ZSJ k nejbližší škole (Voronoi proxy) a spočítá
demografický tlak per škola.

STAV: V0 tento skript NEPOTŘEBUJE — compute_probability.py ho přeskočí.
      V1: spusťte download_sldb_zsj.py nejdřív, pak tento skript.

Výstup: pipeline/data/catchment_demand.json

Algoritmus:
  Pro každou školu (GPS ze web/data/praha10.json):
    demand = Σ zsj.count_age_6  pro ZSJ jejichž centroid je do RADIUS_KM
  (ZSJ může být "přiřazeno" více školám naráz = překrývající se kruhy)

Poznámka: "spádová ZSJ" není totéž co "spádová ZŠ" — to je dáno vyhláškou OZV.
           Tento odhad je proxy pro demografický tlak mimo spádový nárok.
"""

import json
import math
from pathlib import Path

SCHOOLS_JSON = Path(__file__).parent.parent / "web" / "data" / "praha10.json"
ZSJ_INPUT = Path(__file__).parent / "data" / "zsj_demographics.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "catchment_demand.json"

RADIUS_KM = 1.5  # polomer pro přiřazení ZSJ ke škole


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Vzdálenost v km (Haversine formula)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def main() -> None:
    if not ZSJ_INPUT.exists():
        print(f"❌ {ZSJ_INPUT} nenalezen — spusť nejdřív download_sldb_zsj.py")
        return

    schools_data = json.loads(SCHOOLS_JSON.read_text(encoding="utf-8"))
    zsj_data = json.loads(ZSJ_INPUT.read_text(encoding="utf-8"))

    schools = [s for s in schools_data["schools"] if s.get("lat") and s.get("lon") and s.get("redizo")]
    zsj_list = [z for z in zsj_data["zsj"] if z.get("centroid_lat") and z.get("centroid_lon")]

    print(f"Školy s GPS: {len(schools)}, ZSJ s centroidy: {len(zsj_list)}")

    results = {}
    for school in schools:
        redizo = school["redizo"]
        slat, slon = school["lat"], school["lon"]

        in_radius = []
        demand = 0
        for zsj in zsj_list:
            dist = haversine(slat, slon, zsj["centroid_lat"], zsj["centroid_lon"])
            if dist <= RADIUS_KM:
                in_radius.append(zsj["zsj_kod"])
                demand += zsj.get("count_age_6", 0)

        results[redizo] = {
            "school_id": school["id"],
            "school_name": school["name"],
            "demand_age6": demand,
            "zsj_count": len(in_radius),
            "zsj_codes": in_radius,
        }
        print(f"  {school['id']}: {len(in_radius)} ZSJ v {RADIUS_KM}km, demand_age6={demand}")

    output = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "radius_km": RADIUS_KM,
        "schools": results,
    }
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Výstup: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
