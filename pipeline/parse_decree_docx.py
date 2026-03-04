#!/usr/bin/env python3
"""
Lokito — Parser spádových vyhlášek Praha (DOCX formát 2025)
Converts OZV č. 19/2025 (pandoc-extracted markdown) into structured JSON.

Input:  Markdown file extracted from DOCX via:
        pandoc vyhlaska-c.-19.docx -t markdown -o vyhlaska19.md
Output: JSON with schools[] and rules[] — same schema as parse_decree.py

Format of source markdown:
  **Městská část Praha N**             ← district header
  **[School Name]{.underline}**        ← school header
  Ulice                                ← whole street
  Ulice č. 1--8                        ← range
  Ulice č. 1--23 lichá                 ← range + parity
  Ulice č. 11 a vyšší                  ← open-ended
  Ulice vyjma č. 30, 32 a 45          ← exclusion
  Ulice lichá                          ← whole parity
  Ulice -- lichá                       ← whole parity (dash variant)
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from collections import Counter
from datetime import datetime


# ── Regex patterns ──────────────────────────────────────────────────────────

RE_DISTRICT = re.compile(r'^\*\*Městská část (Praha \d+[a-zA-Z]*)\*\*\s*$')
RE_SCHOOL = re.compile(r'^\*\*\[(.+?)\]\{\.underline\}\*\*\s*$')


# ── Step 1: Extract raw (school, street_spec) pairs from markdown ────────────

def _preprocess_lines(lines: list[str]) -> list[str]:
    """
    Join multi-line markdown elements:
      - School headers: **[Name part1\npart2]{.underline}**
      - Any line ending with '**[' continuation not closed on same line
    Also joins trailing street-spec continuations (handled later per-entry).
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        # Multi-line school header: starts with **[ but doesn't close on same line
        if stripped.startswith('**[') and ']{.underline}**' not in stripped:
            # Join with following lines until we find the closing
            combined = stripped
            i += 1
            while i < len(lines):
                next_stripped = lines[i].rstrip('\n').strip()
                combined = combined + ' ' + next_stripped
                i += 1
                if ']{.underline}**' in next_stripped:
                    break
            result.append(combined)
            continue

        result.append(stripped)
        i += 1
    return result


_PARITY_ONLY = re.compile(
    r'^(lichá|sudá|všechna\s+(sudá|lichá))\s*$', re.IGNORECASE
)
_RANGE_ONLY = re.compile(r'^\d[\d\s]*[-–][\s\d]+\d\s*$')


def _is_continuation_line(prev: str, curr: str) -> bool:
    """
    Decide if curr is a continuation of the previous street-spec line.
    Very conservative — only true when curr cannot possibly be a new street entry.

    Valid continuations:
      1. curr is ONLY a parity word: "lichá", "sudá", "všechna sudá"
      2. curr is ONLY a number range: "84-106" (after prev ends with "č.")
      3. prev ends with ',' AND curr starts with a number-spec keyword
      4. prev ends with 'č.' (incomplete č. spec) AND curr starts with digit
    """
    curr_s = curr.strip()
    prev_s = prev.rstrip()

    # Case 1: pure parity word → always a continuation of previous spec
    if _PARITY_ONLY.match(curr_s):
        return True

    # Case 2: pure number/range → continuation only if prev ends with 'č.'
    if _RANGE_ONLY.match(curr_s):
        if re.search(r'č\.?\s*$', prev_s):
            return True

    # Case 3: prev ends with comma → curr is next segment of same spec
    if prev_s.endswith(','):
        if re.match(r'^(lichá\b|sudá\b|všechna\b|\d)', curr_s, re.IGNORECASE):
            return True

    # Case 4: prev ends with 'č.' → curr is the number part
    if re.search(r'č\.\s*$', prev_s):
        if re.match(r'^\d', curr_s):
            return True

    return False


def extract_section(md_text: str, district: str) -> list[tuple[str, str]]:
    """
    Extract (school_name, street_spec) pairs for the given district.
    district: e.g. "Praha 10"
    """
    raw_lines = md_text.splitlines()
    lines = _preprocess_lines(raw_lines)

    in_district = False
    current_school = None
    pairs = []

    # We'll collect raw lines for each school and join continuations
    pending_spec_lines: list[str] = []

    def flush_pending():
        """Join accumulated spec lines and append to pairs."""
        if pending_spec_lines and current_school:
            combined = ' '.join(pending_spec_lines).strip()
            if combined:
                pairs.append((current_school, combined))
        pending_spec_lines.clear()

    for line in lines:
        line = line.strip()

        # Check for district header
        m_district = RE_DISTRICT.match(line)
        if m_district:
            if m_district.group(1) == district:
                in_district = True
                current_school = None
            elif in_district:
                # We've moved to a different district — stop
                flush_pending()
                break
            continue

        if not in_district:
            continue

        # Skip empty lines (but they can signal end of wrapped entry)
        if not line:
            continue

        # Check for school header
        m_school = RE_SCHOOL.match(line)
        if m_school:
            flush_pending()
            current_school = m_school.group(1).strip()
            continue

        if current_school is None:
            continue

        # Determine if this line is a continuation of the previous entry.
        # Must be VERY specific — Czech street names often end in -á/-a and
        # some (náměstí, nábřeží) start with lowercase.
        if pending_spec_lines:
            prev = pending_spec_lines[-1]
            is_continuation = _is_continuation_line(prev, line)
            if is_continuation:
                pending_spec_lines[-1] = prev.rstrip() + ' ' + line
                continue

        # Flush previous entry and start new one
        flush_pending()
        pending_spec_lines.append(line)

    # Flush last pending
    flush_pending()

    return pairs


# ── Step 2: School name normalization ────────────────────────────────────────

def normalize_school_name(name: str) -> str:
    """Normalize whitespace and strip trailing org type."""
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove trailing ", příspěvková organizace"
    name = re.sub(r',?\s*příspěvková organizace\s*$', '', name, flags=re.IGNORECASE).strip()
    return name


def school_id_from_name(name: str) -> str:
    """Generate a stable slug ID from school name."""
    norm = normalize_school_name(name)

    # Remove "Základní škola" prefix variants
    short = re.sub(r'^Základní škola\s*', '', norm, flags=re.IGNORECASE).strip()
    # Remove named part before Praha if it's a named school (e.g. "Eden,")
    # Keep named part for named schools (Eden, Karla Čapka, Solidarita)
    # Remove Praha N
    short = re.sub(r',?\s*Praha\s*\d+[a-zA-Z]*\s*,?\s*', ' ', short)
    # Remove house numbers (e.g. "1035/6", "39/1987")
    short = re.sub(r'\d+/\d+', '', short)
    short = re.sub(r'\s+', ' ', short).strip().strip(' ,')

    # Transliterate Czech chars to ASCII
    nfkd = unicodedata.normalize('NFKD', short)
    ascii_str = ''.join(c for c in nfkd if not unicodedata.combining(c))

    slug = re.sub(r'[^a-zA-Z0-9]+', '-', ascii_str.lower()).strip('-')
    return f"zs-{slug}" if slug else "zs-unknown"


# ── Step 3: Parse street specifications ─────────────────────────────────────

def normalize_street_name(text: str) -> str:
    """
    Extract street name from spec, stopping at number spec delimiter.
    Handles: "Ulice č. ...", "Ulice lichá", "Ulice sudá",
             "Ulice -- lichá", "Ulice vyjma ...", "Ulice sudá č. ..."
    """
    s = text.strip().rstrip('.')

    # Patterns that mark where the number spec starts
    delimiters = [
        r'\s+vyjma\b',
        r'\s*--\s*(?:lichá|sudá)',
        r'\s+(?:lichá|sudá)\s*(?:č\.|$)',
        r'\s+(?:lichá|sudá)\s*\d',
        r'\s*č\.\s*\d',
        r'\s+(?:lichá|sudá)$',
        r'\s+sudá\s+č\.',
        r'\s+lichá\s+č\.',
    ]

    earliest = len(s)
    for pat in delimiters:
        m = re.search(pat, s, re.IGNORECASE)
        if m and m.start() < earliest:
            earliest = m.start()

    street = s[:earliest].strip().rstrip(' -–,.')
    return street


def parse_a_vyssi(text: str) -> tuple[int, None] | None:
    """Parse 'č. X a vyšší' → (X, None). Returns None if no match."""
    m = re.search(r'č\.\s*(\d+)\s+a\s+vyšší', text, re.IGNORECASE)
    if m:
        return int(m.group(1)), None
    return None


def parse_spec_segment(segment: str, street: str, raw: str) -> list[dict] | None:
    """
    Parse one segment of a number spec (possibly with parity and range).
    Returns list of rule dicts or None if segment is empty/irrelevant.

    Segment examples (street name already stripped):
      "č. 1--8"
      "č. 1--23 lichá"
      "č. 11 a vyšší"
      "č. 45 a vyšší lichá"
      "lichá"
      "sudá"
      "-- lichá"
      "sudá č. 2-44"
      "lichá č. 11-63"
      "vyjma č. 30, 32 a 45"
      "vyjma č. 61-67 lichá, č. 76-84 sudá"
      "č. 1-59 lichá, č. 2--22 sudá"   ← multiple segments handled upstream
    """
    seg = segment.strip().lstrip('-, ').strip()
    if not seg:
        return None

    rules = []

    # ── "vyjma" (except) ────────────────────────────────────────────────────
    if re.search(r'\bvyjma\b', seg, re.IGNORECASE):
        # Everything after "vyjma" is the excluded spec
        vyjma_part = re.sub(r'^.*?\bvyjma\b\s*', '', seg, flags=re.IGNORECASE).strip()
        exclude_nums = _parse_exclude_spec(vyjma_part)
        rules.append({
            'street': street,
            'parity': 'all',
            'range_from': None,
            'range_to': None,
            'specific_numbers': None,
            'exclude_numbers': exclude_nums if exclude_nums else None,
            'raw': raw
        })
        return rules

    # ── Determine parity ────────────────────────────────────────────────────
    has_licha = bool(re.search(r'\blichá\b', seg, re.IGNORECASE))
    has_suda = bool(re.search(r'\bsudá\b', seg, re.IGNORECASE))

    # Handle "všechna sudá" / "všechna lichá"
    if re.search(r'všechna\s+(?:sudá|lichá)', seg, re.IGNORECASE):
        p = 'even' if re.search(r'sudá', seg, re.IGNORECASE) else 'odd'
        rules.append(_make_parity_rule(street, p, None, None, raw))
        return rules

    # Pure parity with no numbers: "lichá", "sudá", "-- lichá", "-- sudá"
    cleaned = re.sub(r'^-+\s*', '', seg).strip()
    if re.fullmatch(r'(?:lichá|sudá)', cleaned, re.IGNORECASE):
        parity = 'odd' if re.search(r'lichá', cleaned, re.IGNORECASE) else 'even'
        rules.append(_make_parity_rule(street, parity, None, None, raw))
        return rules

    # ── "a vyšší" (open-ended upper) ───────────────────────────────────────
    # Forms: "č. X a vyšší", "č. X a vyšší lichá", "č. X a vyšší sudá"
    # Also parity-first: "lichá č. X a vyšší" — handled below

    # ── Split on "č." to find sub-specs ────────────────────────────────────
    # Segments like "sudá č. 2-44" or "č. 1-23 lichá" or "č. 45 a vyšší lichá"

    # Normalize double-dash to single range separator
    seg_norm = re.sub(r'--', '-', seg)

    # Check for parity-before-number: "sudá č. X" or "lichá č. X"
    # This happens in specs like "sudá č. 2-44, lichá č. 11-63"
    # We only handle the CURRENT segment here (already split by caller)
    parity_first = re.match(
        r'^(sudá|lichá)\s+č\.\s*(.*)',
        seg_norm.strip(),
        re.IGNORECASE
    )
    if parity_first:
        parity = 'even' if parity_first.group(1).lower() == 'sudá' else 'odd'
        rest = parity_first.group(2).strip()
        rule = _parse_number_rest(rest, parity, street, raw)
        if rule:
            rules.append(rule)
        return rules

    # Standard: "č. ..."
    std_match = re.match(r'^č\.\s*(.*)', seg_norm.strip(), re.IGNORECASE)
    if std_match:
        rest = std_match.group(1).strip()
        # Detect trailing parity
        parity = 'all'
        rest_no_parity = rest
        trailing_parity = re.search(r'\s+(lichá|sudá)\s*$', rest, re.IGNORECASE)
        if trailing_parity:
            parity = 'odd' if trailing_parity.group(1).lower() == 'lichá' else 'even'
            rest_no_parity = rest[:trailing_parity.start()].strip()

        rule = _parse_number_rest(rest_no_parity, parity, street, raw)
        if rule:
            rules.append(rule)
        return rules

    # No "č." prefix at all — may be parity alone or unrecognized
    if has_licha or has_suda:
        parity = 'odd' if has_licha else 'even'
        rules.append(_make_parity_rule(street, parity, None, None, raw))
        return rules

    # Fallback: whole street
    rules.append(_make_parity_rule(street, 'all', None, None, raw))
    return rules


def _parse_number_rest(rest: str, parity: str, street: str, raw: str) -> dict | None:
    """
    Parse the number part after 'č.' (parity already determined).
    rest: e.g. "1-8", "11 a vyšší", "24, 26 a 61-115", "1-31"
    """
    rest = rest.strip()
    # Strip any trailing parity keyword that may have leaked in
    rest = re.sub(r'\s+(lichá|sudá)\s*$', '', rest, flags=re.IGNORECASE).strip()

    # "a vyšší" — open-ended
    m_vyssi = re.match(r'(\d+)\s+a\s+vyšší', rest, re.IGNORECASE)
    if m_vyssi:
        return {
            'street': street,
            'parity': parity,
            'range_from': int(m_vyssi.group(1)),
            'range_to': None,  # open-ended
            'specific_numbers': None,
            'exclude_numbers': None,
            'raw': raw
        }

    # Parse number list (may contain ranges and individual numbers)
    numbers = _parse_number_list(rest)
    if not numbers:
        return _make_parity_rule(street, parity, None, None, raw)

    # Filter by parity
    if parity == 'odd':
        numbers = [n for n in numbers if n % 2 == 1]
    elif parity == 'even':
        numbers = [n for n in numbers if n % 2 == 0]

    if not numbers:
        return None

    return {
        'street': street,
        'parity': parity,
        'range_from': min(numbers),
        'range_to': max(numbers),
        'specific_numbers': sorted(set(numbers)),
        'exclude_numbers': None,
        'raw': raw
    }


def _make_parity_rule(street, parity, range_from, range_to, raw):
    return {
        'street': street,
        'parity': parity,
        'range_from': range_from,
        'range_to': range_to,
        'specific_numbers': None,
        'exclude_numbers': None,
        'raw': raw
    }


def _parse_number_list(text: str) -> list[int]:
    """
    Parse number list like '1, 3, 5', '1-8', '24, 26 a 61-115', '2-- 22'.
    Returns expanded list of integers.
    """
    numbers = []
    # Normalize: replace 'a' (conjunction) with comma, normalize dashes
    text = re.sub(r'\s+a\s+(?=\d)', ', ', text)
    text = re.sub(r'--', '-', text)
    # Handle "2- 22" (space after dash)
    text = re.sub(r'-\s+', '-', text)

    parts = re.split(r'[,;]\s*', text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Range
        m = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start <= end:
                numbers.extend(range(start, end + 1))
            continue
        # Single number
        m2 = re.match(r'^(\d+)$', part)
        if m2:
            numbers.append(int(m2.group(1)))
    return numbers


def _parse_exclude_spec(text: str) -> list[int]:
    """
    Parse the exclusion spec after 'vyjma'.
    Examples: "č. 30, 32 a 45", "č. 2-12 sudá", "č. 61-67 lichá, č. 76-84 sudá"
    Returns list of excluded numbers.
    """
    excluded = []
    text = text.strip()

    # Handle multiple exclusion groups (separated by comma before "č.")
    # e.g. "č. 61-67 lichá, č. 76-84 sudá"
    groups = re.split(r',\s*(?=č\.)', text)
    for group in groups:
        group = group.strip()
        # Remove leading "č."
        group = re.sub(r'^č\.\s*', '', group).strip()
        # Check for parity
        parity_match = re.search(r'\s+(lichá|sudá)\s*$', group, re.IGNORECASE)
        parity = 'all'
        if parity_match:
            parity = 'odd' if parity_match.group(1).lower() == 'lichá' else 'even'
            group = group[:parity_match.start()].strip()

        nums = _parse_number_list(group)
        if parity == 'odd':
            nums = [n for n in nums if n % 2 == 1]
        elif parity == 'even':
            nums = [n for n in nums if n % 2 == 0]
        excluded.extend(nums)

    return sorted(set(excluded))


def parse_street_spec(raw_spec: str) -> list[dict]:
    """
    Main entry: parse a single street spec string into 1+ rule dicts.
    """
    spec = raw_spec.strip()
    # Normalize unicode dashes and whitespace
    spec = spec.replace('\u2013', '-').replace('\u2014', '-')
    spec = re.sub(r'\s+', ' ', spec)

    street = normalize_street_name(spec)

    # Number part = everything after street name
    number_part = spec[len(street):].strip()
    number_part = re.sub(r'^[\s\-–,]+', '', number_part).strip()

    if not number_part:
        # Whole street, all numbers
        return [{
            'street': street, 'parity': 'all',
            'range_from': None, 'range_to': None,
            'specific_numbers': None, 'exclude_numbers': None,
            'raw': raw_spec
        }]

    # ── Split multiple specs joined by comma ────────────────────────────────
    # E.g. "č. 2-58 sudá, č. 1-43 lichá"
    # E.g. "sudá č. 2-44, lichá č. 11-63"
    # E.g. "č. 1-31 lichá, všechna sudá"
    # We split on "," that precede "č." or parity keywords
    # but NOT inside "vyjma" clauses

    if re.search(r'\bvyjma\b', number_part, re.IGNORECASE):
        # Don't split vyjma specs — handle as single unit
        segments = [number_part]
    else:
        # Split on:
        #   ",\s*" followed by "č." + digit  OR parity word OR "všechna"
        #   "\s+a\s+" followed by "č." + digit  (e.g. "lichá a č. 84-106")
        segments = re.split(
            r'(?:,\s*|\s+a\s+)(?=(?:č\.\s*\d|lichá\b|sudá\b|všechna\b))',
            number_part,
            flags=re.IGNORECASE
        )

    rules = []
    for seg in segments:
        result = parse_spec_segment(seg.strip(), street, raw_spec)
        if result:
            rules.extend(result)

    if not rules:
        # Fallback
        rules.append({
            'street': street, 'parity': 'all',
            'range_from': None, 'range_to': None,
            'specific_numbers': None, 'exclude_numbers': None,
            'raw': raw_spec
        })

    return rules


# ── Step 4: Build output JSON ────────────────────────────────────────────────

def build_output(md_path: str, district: str = 'Praha 10',
                 existing_json: str | None = None) -> dict:
    """
    Main pipeline: markdown → structured JSON.
    If existing_json is provided, preserves lat/lon/redizo from existing data.
    """
    with open(md_path, encoding='utf-8') as f:
        md_text = f.read()

    pairs = extract_section(md_text, district)
    print(f"Extracted {len(pairs)} street entries for {district}")

    # Load existing data for coordinate/metadata preservation
    existing_schools_map: dict[str, dict] = {}
    if existing_json and Path(existing_json).exists():
        with open(existing_json, encoding='utf-8') as f:
            existing = json.load(f)
        for s in existing.get('schools', []):
            # Key by normalized address suffix for fuzzy matching
            existing_schools_map[s['id']] = s

    # Collect unique school names
    school_names_raw = [school for school, _ in pairs]
    school_names = []
    seen = set()
    for name in school_names_raw:
        norm = normalize_school_name(name)
        if norm not in seen:
            seen.add(norm)
            school_names.append(norm)

    schools = []
    school_id_map: dict[str, str] = {}  # id → name

    for name in sorted(school_names):
        sid = school_id_from_name(name)
        # Handle duplicates
        original_sid = sid
        counter = 2
        while sid in school_id_map:
            sid = f"{original_sid}-{counter}"
            counter += 1
        school_id_map[sid] = name

        # Try to find matching school in existing data
        # Match by address keywords
        existing_match = _find_existing_school(sid, name, existing_schools_map)

        schools.append({
            'id': sid,
            'name': name,
            'address': existing_match.get('address', '') if existing_match else '',
            'lat': existing_match.get('lat') if existing_match else None,
            'lon': existing_match.get('lon') if existing_match else None,
            'redizo': existing_match.get('redizo') if existing_match else None,
            'municipality': 'praha-10'
        })

    # Reverse map: name → id
    name_to_id = {v: k for k, v in school_id_map.items()}

    # Parse all rules
    all_rules = []
    parse_errors = []
    rule_id = 1

    for school_name_raw, street_spec in pairs:
        school_name = normalize_school_name(school_name_raw)
        school_id = name_to_id.get(school_name)

        if not school_id:
            parse_errors.append({
                'type': 'unknown_school',
                'raw': f"{street_spec} | {school_name_raw}",
                'detail': f"School not found: {school_name}"
            })
            continue

        try:
            parsed_rules = parse_street_spec(street_spec)
            for rule in parsed_rules:
                all_rules.append({
                    'id': rule_id,
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
                rule_id += 1
        except Exception as e:
            parse_errors.append({
                'type': 'parse_error',
                'raw': street_spec,
                'detail': str(e)
            })

    print(f"Generated {len(all_rules)} rules for {len(schools)} schools")
    if parse_errors:
        print(f"⚠  {len(parse_errors)} parse errors:")
        for err in parse_errors:
            print(f"  [{err['type']}] {err.get('raw','?')}: {err['detail']}")

    municipality_id = f"praha-{district.split()[-1].lower()}"

    return {
        'metadata': {
            'municipality': district,
            'municipality_id': municipality_id,
            'decree_title': f'Spádové obvody základních škol — OZV č. 19/2025 hl. m. Prahy',
            'decree_number': '19/2025',
            'valid_from': '2026-01-01',
            'source_url': 'https://sbirkapp.gov.cz/detail/SPPE3FO5TONQKOT6',
            'parsed_at': datetime.now().isoformat(),
            'total_rows': len(pairs),
            'total_rules': len(all_rules),
            'total_schools': len(schools),
        },
        'schools': schools,
        'rules': all_rules,
        'parse_errors': parse_errors
    }


def _find_existing_school(new_sid: str, new_name: str,
                           existing_map: dict) -> dict | None:
    """Try to find a matching school in existing data by ID or address street name."""
    # Direct ID match
    if new_sid in existing_map:
        return existing_map[new_sid]

    # Extract school address street from name (last comma-part that contains a digit)
    parts = new_name.split(',')
    addr_street = None
    for part in reversed(parts):
        part = part.strip()
        if re.search(r'\d', part):
            # Strip house number to get just the street name
            addr_street = re.sub(r'\s+\d.*', '', part).strip().lower()
            break

    if not addr_street:
        return None

    # Match existing schools by street name in their address
    for sid, school in existing_map.items():
        existing_name = school.get('name', '').lower()
        if addr_street in existing_name:
            return school

    return None


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Parse OZV č. 19/2025 markdown → JSON'
    )
    parser.add_argument('md_path', help='Path to pandoc-extracted markdown')
    parser.add_argument('output', help='Output JSON path')
    parser.add_argument('--district', default='Praha 10',
                        help='District to extract (default: Praha 10)')
    parser.add_argument('--existing', default=None,
                        help='Existing JSON to preserve lat/lon/redizo from')
    args = parser.parse_args()

    print(f"Parsing: {args.md_path}  →  district: {args.district}")
    result = build_output(args.md_path, args.district, args.existing)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Output: {args.output}")
    print(f"  Schools: {result['metadata']['total_schools']}")
    print(f"  Rules:   {result['metadata']['total_rules']}")

    print("\n── Rules per school ──")
    counts = Counter(r['school_id'] for r in result['rules'])
    for sid, cnt in counts.most_common():
        name = next(s['name'] for s in result['schools'] if s['id'] == sid)
        print(f"  {cnt:4d}  {name}")

    print("\n── Rule types ──")
    whole = sum(1 for r in result['rules']
                if r['range_from'] is None and r['exclude_numbers'] is None)
    ranged = sum(1 for r in result['rules'] if r['range_from'] is not None)
    excl = sum(1 for r in result['rules'] if r['exclude_numbers'] is not None)
    open_ended = sum(1 for r in result['rules'] if r['range_to'] is None and r['range_from'] is not None)
    print(f"  Whole street:      {whole}")
    print(f"  With number range: {ranged}")
    print(f"  Open-ended (vyšší): {open_ended}")
    print(f"  With exclusion:    {excl}")
    if result['parse_errors']:
        print(f"\n⚠  Parse errors: {len(result['parse_errors'])}")
        for e in result['parse_errors']:
            print(f"  {e}")
