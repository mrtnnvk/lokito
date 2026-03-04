# Lokito

**Do jaké základní školy vaše dítě spádově patří?**

Lokito je civic-tech nástroj, který rodičům v ČR pomáhá zjistit spádovou základní školu podle adresy bydliště.

## Stav projektu

- [x] Data pipeline — parser PDF spádových vyhlášek
- [x] Matching engine — určení školy podle ulice a čísla
- [x] Web aplikace (Next.js + TypeScript)
- [ ] Geokódování škol (GPS souřadnice)
- [ ] Napojení na Supabase
- [ ] Deployment na Vercel

## Spuštění lokálně

```bash
cd web
npm install
npm run dev
```

Otevřete http://localhost:3000

## Struktura

```
lokito/
├── pipeline/               # Offline zpracování dat
│   ├── parse_decree.py     # PDF vyhláška → JSON
│   ├── validate.py         # Validace + matching engine (Python)
│   └── data/
│       ├── raw/            # Stažená PDF
│       └── parsed/         # Výstupní JSON
├── web/                    # Next.js aplikace
│   ├── src/
│   │   ├── app/            # Pages + API routes
│   │   ├── components/     # React komponenty
│   │   └── lib/            # Matching engine, typy, normalizace
│   └── data/               # JSON data pro runtime
└── README.md
```

## Data pipeline

Parser vyhlášky (Python):

```bash
cd pipeline
pip install pdfplumber
python parse_decree.py data/raw/spadove_praha10.pdf data/parsed/praha10.json
```

Validace:

```bash
python validate.py
```

## Technologie

- **Frontend:** Next.js 15, React 19, TypeScript, Tailwind CSS
- **Mapa:** Leaflet + OpenStreetMap
- **Data:** JSON (lokálně), plánovaně Supabase (Postgres)
- **Hosting:** plánovaně Vercel
- **Pipeline:** Python + pdfplumber

## Licence

MIT
