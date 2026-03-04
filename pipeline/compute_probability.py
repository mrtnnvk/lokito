#!/usr/bin/env python3
"""
Vypočítá pravděpodobnost přijetí (chance_score) pro každou spádovou ZŠ Prahy 10.

MODEL V0 — používá pouze kapacitu školy (z MŠMT rejstříku):
  supply       = kapacita školy
  enrolled     = 0.85 × supply  (odhad; reálná data přidá V1 z MŠMT výkonových dat)
  free_spots   = supply - enrolled = 0.15 × supply

  demand_static = odhad poptávky na Praze 10 uniformně rozdělené
                = Praha 10 ~1070 dětí ve věku 6 let (ČSÚ 2021) / 14 škol ≈ 76
                (V1 nahradí reálnou ZSJ prostorovou poptávkou z build_catchment_map.py)

  pressure_index = demand_static / max(free_spots, 1)
  raw_score      = 100 - pressure_index × 40
  score          = clamp(raw_score, 5, 95)

MODEL V1 (pokud existuje catchment_demand.json):
  demand = demand_age6 ze ZSJ dosahu (prostorová poptávka)
  → přesnější, confidence = "medium"

Výstup: pipeline/data/probability_artifacts.json
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHOOLS_JSON = Path(__file__).parent.parent / "web" / "data" / "praha10.json"
CAPACITY_RAW = Path(__file__).parent / "data" / "capacity_raw.json"
CATCHMENT_DEMAND = Path(__file__).parent / "data" / "catchment_demand.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "probability_artifacts.json"

MODEL_VERSION = "v0.1"

# V0 konstanty
ENROLLMENT_RATE = 0.85          # konzervativní odhad využití kapacity
DEMAND_P10_AGE6 = 1070          # ČSÚ 2021: děti věk 6 v Praze 10
SCHOOLS_COUNT = 14              # počet spádových ZŠ P10
DEMAND_STATIC_PER_SCHOOL = DEMAND_P10_AGE6 / SCHOOLS_COUNT  # ≈ 76.4

# Thresholdy pro band
BAND_HIGH_THRESHOLD = 70
BAND_MEDIUM_THRESHOLD = 40

# Kapacita default (pokud MŠMT nenalezl)
KAPACITA_DEFAULT = 400
KAPACITA_AVERAGE_P10 = 450     # průměr Praha 10 ZŠ (odhad)


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def score_to_band(score: int) -> str:
    if score >= BAND_HIGH_THRESHOLD:
        return "high"
    if score >= BAND_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def build_explain(
    pressure_index: float,
    free_spots: int | None,
    kapacita: int | None,
    use_v1_demand: bool,
) -> list[str]:
    """Generuje statické důvody (bez vzdálenosti — ta se přidá za runtime v API)."""
    reasons = []

    if use_v1_demand:
        if pressure_index > 1.5:
            reasons.append("Oblast má vysoký počet dětí v odpovídajícím věku")
        elif pressure_index < 0.7:
            reasons.append("Oblast má nízký počet dětí v odpovídajícím věku")

    if free_spots is not None:
        if free_spots < 15:
            reasons.append("Škola má málo volných míst (proxy odhad)")
        elif free_spots > 80:
            reasons.append("Škola má nadprůměrný počet volných míst (proxy odhad)")

    if kapacita is not None:
        if kapacita > KAPACITA_AVERAGE_P10 * 1.3:
            reasons.append("Škola má nadprůměrnou kapacitu")
        elif kapacita < KAPACITA_AVERAGE_P10 * 0.7:
            reasons.append("Škola má podprůměrnou kapacitu")

    # Fallback vysvětlení vždy přítomné
    if not reasons:
        reasons.append("Odhad vychází z kapacity školy dle MŠMT rejstříku")
    if not use_v1_demand:
        reasons.append("Prostorová poptávka není zahrnutá (plánována ve V1)")

    return reasons[:3]  # max 3 statické důvody


def main() -> None:
    if not CAPACITY_RAW.exists():
        print(f"❌ {CAPACITY_RAW} nenalezen — spusť nejdřív download_msmt_capacity.py")
        sys.exit(1)

    schools_data = json.loads(SCHOOLS_JSON.read_text(encoding="utf-8"))
    capacity_data = json.loads(CAPACITY_RAW.read_text(encoding="utf-8"))

    # V1: prostorová poptávka (nepovinná)
    use_v1_demand = CATCHMENT_DEMAND.exists()
    catchment: dict = {}
    if use_v1_demand:
        catchment = json.loads(CATCHMENT_DEMAND.read_text(encoding="utf-8")).get("schools", {})
        print("📍 V1 mode: používám ZSJ prostorovou poptávku z catchment_demand.json")
    else:
        print("📊 V0 mode: používám uniformní odhad poptávky (demand_static)")

    data_version = capacity_data.get("data_version", "msmt-2025")
    if use_v1_demand:
        data_version += "+sldb2021-zsj"
        confidence_base = "medium"
    else:
        confidence_base = "low"

    results: dict[str, dict] = {}

    for school in schools_data["schools"]:
        school_id = school["id"]
        redizo = school.get("redizo")

        if not redizo:
            print(f"  ⚠️ {school_id}: chybí REDIZO, přeskakuji")
            continue

        # Kapacita z MŠMT
        cap_entry = capacity_data["schools"].get(redizo, {})
        kapacita: int | None = cap_entry.get("kapacita")

        if kapacita is None:
            print(f"  ⚠️ {school_id}: kapacita nenalezena, použit default {KAPACITA_DEFAULT}")
            kapacita_used = KAPACITA_DEFAULT
            kapacita_is_default = True
        else:
            kapacita_used = kapacita
            kapacita_is_default = False

        enrolled = round(ENROLLMENT_RATE * kapacita_used)
        free_spots = max(kapacita_used - enrolled, 0)

        # Poptávka
        if use_v1_demand and redizo in catchment:
            demand = catchment[redizo].get("demand_age6", DEMAND_STATIC_PER_SCHOOL)
        else:
            demand = DEMAND_STATIC_PER_SCHOOL

        pressure_index = demand / max(free_spots, 1)
        raw_score = 100.0 - pressure_index * 40.0
        score = int(clamp(raw_score, 5, 95))
        band = score_to_band(score)

        explain = build_explain(pressure_index, free_spots, kapacita, use_v1_demand)

        confidence_note = (
            f"V0: odhad využití kapacity {int(ENROLLMENT_RATE*100)}%; "
            f"poptávka {'ze ZSJ SLDB 2021 (odhadnutý věk 6)' if use_v1_demand else 'uniformní P10/14 škol'}; "
            f"bez historické kalibrace."
        )
        if kapacita_is_default:
            confidence_note += f" Kapacita není v rejstříku, použit default {KAPACITA_DEFAULT}."

        results[school_id] = {
            "school_id": school_id,
            "redizo": redizo,
            "kapacita": kapacita,
            "kapacita_is_default": kapacita_is_default,
            "enrolled_estimate": enrolled,
            "free_spots_proxy": free_spots,
            "demand_age6": round(demand),
            "pressure_index": round(pressure_index, 3),
            "score": score,
            "band": band,
            "confidence": confidence_base,
            "explain_static": explain,
            "model_version": MODEL_VERSION,
            "data_version": data_version,
            "confidence_note": confidence_note,
        }

        print(
            f"  {school_id}: kapacita={kapacita_used}, free={free_spots}, "
            f"demand≈{round(demand)}, pi={pressure_index:.2f}, "
            f"score={score} [{band}]"
        )

    output = {
        "model_version": MODEL_VERSION,
        "data_version": data_version,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "mode": "v1-zsj" if use_v1_demand else "v0-static",
        "confidence_note": (
            "Nízká spolehlivost: odhad využití 85%, bez historických zápisových dat."
            " Slouží jako orientační informace, není právním nárokem."
        ),
        "schools": results,
    }

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ Výstup: {OUTPUT_PATH}")
    print(f"   Model: {MODEL_VERSION}, data: {data_version}, mode: {output['mode']}")
    print(f"   Školy: {len(results)}")

    # Quick sanity check
    bands = {"high": 0, "medium": 0, "low": 0}
    for r in results.values():
        bands[r["band"]] += 1
    print(f"   Distribuce: {bands}")


if __name__ == "__main__":
    main()
