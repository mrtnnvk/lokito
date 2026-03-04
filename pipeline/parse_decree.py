#!/usr/bin/env python3
"""
Lokito — Parser spádových vyhlášek Praha 10
Converts PDF decree into structured JSON rules.

Input:  PDF with table (street | school)
Output: JSON with schools[] and rules[]
"""

import pdfplumber
import json
import re
import sys
import unicodedata
from pathlib import Path
from collections import Counter


# ── Step 1: Extract raw rows from PDF table ──────────────────────────

def extract_raw_rows(pdf_path: str) -> list[tuple[str, str]]:
    """Extract (street_spec, school_name) tuples from PDF."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row and len(row) >= 2 and row[0] and row[1]:
                        street = row[0].strip()
                        school = row[1].strip()
                        if street and school:
                            rows.append((street, school))
    return rows


# ── Step 2: Normalize school names ───────────────────────────────────

def normalize_school_name(name: str) -> str:
    """Fix common inconsistencies in school names."""
    # Fix missing spaces (e.g. "Praha10" → "Praha 10")
    name = re.sub(r'Praha\s*(\d)', r'Praha \1', name)
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # Apply known aliases (typos/inconsistencies in decree)
    SCHOOL_ALIASES = {
        'Základní škola, Praha 10, Nad U Roháčových kasáren 19/1381':
            'Základní škola, Praha 10, U Roháčových kasáren 19/1381',
        'Základní škola, Praha 10, U Vršovického nádraží 1':
            'Základní škola, Praha 10, U Vršovického nádraží 1/950',
    }
    return SCHOOL_ALIASES.get(name, name)


def school_id_from_name(name: str) -> str:
    """Generate a stable ID from school name."""
    # Extract the street part of school address
    # E.g. "Základní škola, Praha 10, Nad Vodovodem 81/460" → "nad-vodovodem"
    # Or "Základní škola Eden, Praha 10, Vladivostocká 6/1035" → "eden-vladivostocka"

    name_norm = normalize_school_name(name)

    # Remove "Základní škola" prefix and "Praha 10"
    short = re.sub(r'^Základní škola\s*', '', name_norm, flags=re.IGNORECASE)
    short = re.sub(r',?\s*Praha\s*\d+\s*,?\s*', ' ', short)

    # Remove house numbers
    short = re.sub(r'\d+/\d+', '', short)
    short = re.sub(r'\s+', ' ', short).strip()
    short = short.strip(' ,')

    # Transliterate Czech chars
    nfkd = unicodedata.normalize('NFKD', short)
    ascii_str = ''.join(c for c in nfkd if not unicodedata.combining(c))

    # Slugify
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', ascii_str.lower()).strip('-')

    return f"zs-{slug}" if slug else "zs-unknown"


# ── Step 3: Parse street specifications ──────────────────────────────

def normalize_street_name(raw: str) -> str:
    """Extract and normalize street name from the spec."""
    # Remove everything after first delimiter that starts number spec
    # Delimiters: " - ", " – ", " -", " č.", "-č."

    street = raw.strip()

    # Remove trailing period
    street = street.rstrip('.')

    # Find where the number specification starts
    # Try various patterns
    patterns = [
        r'\s*[-–]\s*(?:lichá|sudá|č\.?\s|kromě|všechna|od\s)',
        r'\s*[-–]\s*č\.\s*\d',
        r'\s+[-–]\s+č\.',
        r'\s*č\.\s*\d',  # "Dukelská č.11"
    ]

    for pattern in patterns:
        m = re.search(pattern, street, re.IGNORECASE)
        if m:
            street = street[:m.start()]
            break

    return street.strip().rstrip(' -–,.')


def parse_number_list(text: str) -> list[int]:
    """Parse a list of numbers from text like '1, 2 - 8, 15, 17'.
    Returns expanded list of individual numbers."""
    numbers = []
    text = text.strip()

    # Fix common OCR issues: letter 'l' instead of '1'
    text = re.sub(r'\bl\b', '1', text)

    # Split by comma or semicolon
    parts = re.split(r'[,;]\s*', text)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Range: "2 - 8" or "2–8"
        range_match = re.match(r'(\d+)\s*[-–]\s*(\d+)', part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            numbers.extend(range(start, end + 1))
            continue

        # Single number
        num_match = re.match(r'(\d+)', part)
        if num_match:
            numbers.append(int(num_match.group(1)))

    return numbers


def parse_street_spec(raw_spec: str) -> list[dict]:
    """Parse a street specification into one or more rules.

    Returns list of rule dicts with keys:
        street, parity, numbers, range_from, range_to,
        specific_numbers, exclude_numbers, raw
    """
    spec = raw_spec.strip().rstrip('.')
    street = normalize_street_name(spec)

    # Get the number part (everything after street name)
    number_part = spec[len(street):].strip()
    number_part = re.sub(r'^[\s\-–,]+', '', number_part).strip()

    # If no number specification → whole street
    if not number_part:
        return [{
            'street': street,
            'parity': 'all',
            'range_from': None,
            'range_to': None,
            'specific_numbers': None,
            'exclude_numbers': None,
            'raw': raw_spec
        }]

    rules = []

    # ── Handle "kromě" (except) ──
    krome_match = re.search(r'kromě\s+č\.?\s*([\d/,\s]+)', number_part, re.IGNORECASE)
    if krome_match:
        exclude_nums = []
        for n in re.findall(r'\d+', krome_match.group(1)):
            exclude_nums.append(int(n))
        rules.append({
            'street': street,
            'parity': 'all',
            'range_from': None,
            'range_to': None,
            'specific_numbers': None,
            'exclude_numbers': exclude_nums,
            'raw': raw_spec
        })
        return rules

    # ── Handle "lichá" and "sudá" patterns ──
    has_licha = bool(re.search(r'lichá', number_part, re.IGNORECASE))
    has_suda = bool(re.search(r'sudá|sudé', number_part, re.IGNORECASE))

    if has_licha or has_suda:
        # Split into odd/even sections
        # Try to split by "sudá" keyword
        sections = re.split(r'[;,]\s*(?=(?:sudá|lichá|všechna\s+(?:sudá|lichá)))',
                           number_part, flags=re.IGNORECASE)

        # If that didn't work well, try another split
        if len(sections) == 1 and has_licha and has_suda:
            sections = re.split(r'(?=sudá|lichá)', number_part, flags=re.IGNORECASE)
            sections = [s.strip().strip(',-;') for s in sections if s.strip()]

        for section in sections:
            section = section.strip().strip(',-;').strip()
            if not section:
                continue

            # Determine parity of this section
            if re.search(r'lichá', section, re.IGNORECASE):
                parity = 'odd'
            elif re.search(r'sudá|sudé', section, re.IGNORECASE):
                parity = 'even'
            else:
                parity = 'all'

            # Check for "všechna" (all) or "čísla" without numbers → whole parity
            if re.search(r'všechna\s+(?:sudá|lichá)\s+(?:čísla|č\.?)\s*$', section, re.IGNORECASE):
                rules.append({
                    'street': street,
                    'parity': parity,
                    'range_from': None,
                    'range_to': None,
                    'specific_numbers': None,
                    'exclude_numbers': None,
                    'raw': raw_spec
                })
                continue

            if re.search(r'(?:lichá|sudá|sudé)\s+(?:čísla|č\.?)\s*$', section, re.IGNORECASE):
                rules.append({
                    'street': street,
                    'parity': parity,
                    'range_from': None,
                    'range_to': None,
                    'specific_numbers': None,
                    'exclude_numbers': None,
                    'raw': raw_spec
                })
                continue

            # Check for "od č. X" (from number X onwards)
            od_match = re.search(r'od\s+č\.?\s*(\d+)', section, re.IGNORECASE)
            if od_match:
                rules.append({
                    'street': street,
                    'parity': parity,
                    'range_from': int(od_match.group(1)),
                    'range_to': 9999,  # open-ended
                    'specific_numbers': None,
                    'exclude_numbers': None,
                    'raw': raw_spec
                })
                continue

            # Extract numbers from section
            # Remove the parity keyword and "č." prefix
            nums_text = re.sub(r'^.*?(?:lichá|sudá|sudé)\s*(?:č\.?\s*)?', '', section, flags=re.IGNORECASE)
            nums_text = re.sub(r'^č\.?\s*', '', nums_text).strip()

            if not nums_text or not re.search(r'\d', nums_text):
                # No numbers found — entire parity
                rules.append({
                    'street': street,
                    'parity': parity,
                    'range_from': None,
                    'range_to': None,
                    'specific_numbers': None,
                    'exclude_numbers': None,
                    'raw': raw_spec
                })
                continue

            # Parse numbers — could be ranges and individual numbers
            numbers = parse_number_list(nums_text)

            if not numbers:
                rules.append({
                    'street': street,
                    'parity': parity,
                    'range_from': None,
                    'range_to': None,
                    'specific_numbers': None,
                    'exclude_numbers': None,
                    'raw': raw_spec
                })
                continue

            # Filter by parity
            if parity == 'odd':
                numbers = [n for n in numbers if n % 2 == 1]
            elif parity == 'even':
                numbers = [n for n in numbers if n % 2 == 0]

            if numbers:
                rules.append({
                    'street': street,
                    'parity': parity,
                    'range_from': min(numbers),
                    'range_to': max(numbers),
                    'specific_numbers': sorted(set(numbers)),
                    'exclude_numbers': None,
                    'raw': raw_spec
                })

        if rules:
            return rules

    # ── Handle plain number specs (no parity keyword) ──
    # "č. 3", "č. 22, 24", "č. 1 - 7", "č. 1 - 12, 16, 18"
    nums_text = re.sub(r'^č\.?\s*', '', number_part).strip()
    nums_text = re.sub(r'^[\s\-–]+', '', nums_text).strip()

    # Handle slash notation (č. 12/516) — take only the orientační (first) number
    nums_text = re.sub(r'(\d+)/\d+', r'\1', nums_text)

    numbers = parse_number_list(nums_text)

    if numbers:
        rules.append({
            'street': street,
            'parity': 'all',
            'range_from': min(numbers),
            'range_to': max(numbers),
            'specific_numbers': sorted(set(numbers)),
            'exclude_numbers': None,
            'raw': raw_spec
        })
    else:
        # Fallback — treat as whole street
        rules.append({
            'street': street,
            'parity': 'all',
            'range_from': None,
            'range_to': None,
            'specific_numbers': None,
            'exclude_numbers': None,
            'raw': raw_spec
        })

    return rules


# ── Step 4: Build output ─────────────────────────────────────────────

def build_output(pdf_path: str) -> dict:
    """Main pipeline: PDF → structured JSON."""

    raw_rows = extract_raw_rows(pdf_path)
    print(f"Extracted {len(raw_rows)} raw rows from PDF")

    # Collect unique schools
    school_names = set()
    for _, school in raw_rows:
        school_names.add(normalize_school_name(school))

    schools = []
    school_id_map = {}
    for name in sorted(school_names):
        sid = school_id_from_name(name)
        # Handle duplicate IDs
        if sid in school_id_map:
            sid = sid + "-2"
        school_id_map[sid] = name
        schools.append({
            'id': sid,
            'name': name,
            'address': '',  # to be filled from RÚIAN/geocoding
            'lat': None,
            'lon': None,
            'redizo': None,
            'municipality': 'praha-10'
        })

    # Reverse map: name → id
    name_to_id = {v: k for k, v in school_id_map.items()}

    # Parse all rules
    all_rules = []
    parse_errors = []

    for street_spec, school_name in raw_rows:
        school_name_norm = normalize_school_name(school_name)
        school_id = name_to_id.get(school_name_norm)

        if not school_id:
            parse_errors.append({
                'type': 'unknown_school',
                'raw': f"{street_spec} | {school_name}",
                'detail': f"School not found: {school_name_norm}"
            })
            continue

        try:
            parsed_rules = parse_street_spec(street_spec)
            for rule in parsed_rules:
                all_rules.append({
                    'school_id': school_id,
                    'street': rule['street'],
                    'parity': rule['parity'],
                    'range_from': rule['range_from'],
                    'range_to': rule['range_to'],
                    'specific_numbers': rule['specific_numbers'],
                    'exclude_numbers': rule['exclude_numbers'],
                    'number_type': 'orientační',
                    'municipality': 'praha-10',
                    'raw': rule['raw']
                })
        except Exception as e:
            parse_errors.append({
                'type': 'parse_error',
                'raw': street_spec,
                'detail': str(e)
            })

    print(f"Generated {len(all_rules)} rules for {len(schools)} schools")
    if parse_errors:
        print(f"⚠ {len(parse_errors)} parse errors:")
        for err in parse_errors:
            print(f"  [{err['type']}] {err['raw']}: {err['detail']}")

    return {
        'metadata': {
            'municipality': 'Praha 10',
            'municipality_id': 'praha-10',
            'decree_title': 'Spádové obvody základních škol městské části Praha 10 podle ulic',
            'valid_from': '2015-01-01',
            'source_url': 'https://praha10.cz/Portals/0/Spadove%20oblasti%201_1_2015_1.pdf',
            'parsed_at': None,  # will be set at runtime
            'total_rows': len(raw_rows),
            'total_rules': len(all_rules),
            'total_schools': len(schools),
        },
        'schools': schools,
        'rules': all_rules,
        'parse_errors': parse_errors
    }


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from datetime import datetime

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else 'data/raw/spadove_praha10.pdf'
    output_path = sys.argv[2] if len(sys.argv) > 2 else 'data/parsed/praha10.json'

    print(f"Parsing: {pdf_path}")
    result = build_output(pdf_path)
    result['metadata']['parsed_at'] = datetime.now().isoformat()

    # Ensure output dir exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nOutput: {output_path}")
    print(f"Schools: {result['metadata']['total_schools']}")
    print(f"Rules:   {result['metadata']['total_rules']}")

    # Summary by school
    print("\n── Rules per school ──")
    school_counts = Counter(r['school_id'] for r in result['rules'])
    for sid, count in school_counts.most_common():
        school_name = next(s['name'] for s in result['schools'] if s['id'] == sid)
        print(f"  {count:4d}  {school_name}")

    # Show some stats about rule types
    whole_street = sum(1 for r in result['rules'] if r['range_from'] is None and r['exclude_numbers'] is None)
    with_range = sum(1 for r in result['rules'] if r['range_from'] is not None)
    with_exclude = sum(1 for r in result['rules'] if r['exclude_numbers'] is not None)

    print(f"\n── Rule types ──")
    print(f"  Whole street:      {whole_street}")
    print(f"  With number range: {with_range}")
    print(f"  With exclusion:    {with_exclude}")
