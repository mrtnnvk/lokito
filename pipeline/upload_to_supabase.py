#!/usr/bin/env python3
"""
Nahraje všechna data do Supabase:
  1. municipalities (1 řádek — Praha 10)
  2. schools (14 řádků)
  3. rules (537 řádků, v dávkách)
  4. probability_artifacts (14 řádků)

Požaduje: pip install supabase
Env vars: SUPABASE_URL, SUPABASE_SERVICE_KEY
  (Service key, ne anon key — potřeba pro write přístup)
"""

import json
import os
import sys
from pathlib import Path

try:
    from supabase import create_client, Client
except ImportError:
    print("Nainstaluj: pip install supabase")
    sys.exit(1)

SCHOOLS_JSON = Path(__file__).parent.parent / "web" / "data" / "praha10.json"
ARTIFACTS_JSON = Path(__file__).parent / "data" / "probability_artifacts.json"

BATCH_SIZE = 100  # pro rules tabulku


def get_client() -> "Client":
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("❌ Nastav env vars: SUPABASE_URL a SUPABASE_SERVICE_KEY")
        print("   export SUPABASE_URL=https://xxxx.supabase.co")
        print("   export SUPABASE_SERVICE_KEY=eyJ...")
        sys.exit(1)
    return create_client(url, key)


def upsert(client: "Client", table: str, rows: list[dict], conflict_key: str) -> None:
    if not rows:
        return
    # Supabase upsert: on conflict do update
    resp = client.table(table).upsert(rows, on_conflict=conflict_key).execute()
    if hasattr(resp, "error") and resp.error:
        print(f"  ❌ {table}: {resp.error}")
    else:
        print(f"  ✅ {table}: {len(rows)} řádků")


def upsert_in_batches(client: "Client", table: str, rows: list[dict], conflict_key: str) -> None:
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        resp = client.table(table).upsert(batch, on_conflict=conflict_key).execute()
        if hasattr(resp, "error") and resp.error:
            print(f"  ❌ {table} batch {i}-{i+len(batch)}: {resp.error}")
        else:
            total += len(batch)
    print(f"  ✅ {table}: {total} řádků")


def main() -> None:
    client = get_client()

    data = json.loads(SCHOOLS_JSON.read_text(encoding="utf-8"))
    meta = data.get("metadata", {})
    schools = data.get("schools", [])
    rules = data.get("rules", [])

    # ── 1. municipalities ──────────────────────────────────────────
    print("Nahrávám municipalities...")
    muni_row = {
        "id": meta.get("municipality_id", "praha-10"),
        "name": meta.get("municipality", "Praha 10"),
        "decree_title": meta.get("decree_title"),
        "valid_from": meta.get("valid_from"),
        "source_url": meta.get("source_url"),
        "parsed_at": meta.get("parsed_at"),
        "total_rules": meta.get("total_rules"),
        "total_schools": meta.get("total_schools"),
    }
    upsert(client, "municipalities", [muni_row], "id")

    # ── 2. schools ─────────────────────────────────────────────────
    print("Nahrávám schools...")
    school_rows = [
        {
            "id": s["id"],
            "municipality_id": s.get("municipality", "praha-10"),
            "name": s["name"],
            "address": s.get("address"),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
            "redizo": s.get("redizo"),
            "founder_type": s.get("founder_type"),
            "website": s.get("website"),
            "phone": s.get("phone"),
            "email": s.get("email"),
        }
        for s in schools
    ]
    upsert(client, "schools", school_rows, "id")

    # ── 3. rules ───────────────────────────────────────────────────
    print(f"Nahrávám rules ({len(rules)} řádků v dávkách po {BATCH_SIZE})...")
    rule_rows = [
        {
            "id": i,
            "school_id": r.get("school_id"),
            "street": r.get("street"),
            "parity": r.get("parity"),
            "range_from": r.get("range_from"),
            "range_to": r.get("range_to"),
            "specific_numbers": r.get("specific_numbers"),
            "exclude_numbers": r.get("exclude_numbers"),
            "number_type": r.get("number_type"),
            "municipality": r.get("municipality"),
            "raw": r.get("raw"),
        }
        for i, r in enumerate(rules)
    ]
    upsert_in_batches(client, "rules", rule_rows, "id")

    # ── 4. probability_artifacts ───────────────────────────────────
    if not ARTIFACTS_JSON.exists():
        print("⚠️  probability_artifacts.json nenalezen — přeskakuji (spusť compute_probability.py)")
    else:
        print("Nahrávám probability_artifacts...")
        artifacts_data = json.loads(ARTIFACTS_JSON.read_text(encoding="utf-8"))
        artifact_rows = []
        for school_id, a in artifacts_data["schools"].items():
            artifact_rows.append({
                "school_id": school_id,
                "model_version": a["model_version"],
                "data_version": a["data_version"],
                "computed_at": artifacts_data["computed_at"],
                "kapacita": a.get("kapacita"),
                "enrolled": a.get("enrolled_estimate"),
                "free_spots_proxy": a.get("free_spots_proxy"),
                "demand_age6": a.get("demand_age6"),
                "pressure_index": a.get("pressure_index"),
                "score": a.get("score"),
                "band": a.get("band"),
                "confidence": a.get("confidence"),
                "explain_static": a.get("explain_static", []),
                "is_active": True,
                "confidence_note": a.get("confidence_note"),
            })
        upsert(client, "probability_artifacts", artifact_rows, "school_id,model_version")

    print("\n✅ Upload hotov!")


if __name__ == "__main__":
    main()
