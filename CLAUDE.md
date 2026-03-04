# Lokito — Kontext pro Claude Code

## Co je to
Civic-tech nástroj: rodič zadá adresu → systém určí spádovou ZŠ podle vyhlášky.
MVP pro Prahu 10. Jeden vývojář, side-project.

## Architektura
- **web/** — Next.js 15, App Router, TypeScript, Tailwind CSS v4, Leaflet + OSM
- **pipeline/** — Python (pdfplumber), offline parsování PDF vyhlášek → JSON
- **web/data/praha10.json** — runtime data (537 pravidel, 14 škol, OZV 19/2025)
- **Supabase** — schools, rules, probability_artifacts (14 škol, model v0.1)
- **Vercel** — produkce https://lokito-blush.vercel.app (auto-deploy z GitHub main)

## Klíčová logika
Matching engine (`web/src/lib/matching.ts`):
- Vstup: ulice + číslo orientační
- Pravidla: celá ulice, sudá/lichá, rozsahy, konkrétní čísla, výjimky "kromě"
- Priorita: specifické číslo > rozsah > celá parita > celá ulice
- Referenční testy v `pipeline/validate.py` (26 testů, všechny prošly)

## Datový model
Typy v `web/src/lib/types.ts`. Pravidla mají parity (even/odd/all),
range_from/to, specific_numbers, exclude_numbers.

## Aktuální stav
- [x] Parser PDF vyhlášek (pipeline/)
- [x] Matching engine (TypeScript)
- [x] API route POST /api/match
- [x] Frontend s autocomplete + výsledek + mapa
- [x] GPS souřadnice škol (lat/lon v Supabase)
- [x] Napojení na Supabase (schools, rules, probability_artifacts)
- [x] Deploy na Vercel (auto-deploy z GitHub, rootDirectory=web)
- [x] Phase 2: probability scoring pro nespádové ZŠ (feature flag NEXT_PUBLIC_SHOW_PROBABILITY)

## Konvence
- Čeština v UI a komentářích pro doménovou logiku
- Angličtina v kódu (názvy proměnných, funkcí)
- Commit messages v angličtině

## Omezení
- Nepoužívat Mapy.cz (licence) — jen OSM / Nominatim / ČÚZK
- Nepoužívat spadovostpraha.cz ani Address2Map jako zdroj
- Data vychází výhradně z oficiálních vyhlášek

## Příkazy
```bash
# Web app
cd web && npm install && npm run dev

# Parser
cd pipeline && python parse_decree.py data/raw/spadove_praha10.pdf data/parsed/praha10.json

# Validace
cd pipeline && python validate.py
```
