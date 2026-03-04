#!/usr/bin/env python3
"""
Validate parsed Prague 10 school catchment rules.
Tests matching logic against known addresses.
"""

import json
import unicodedata
import re


def normalize_for_compare(s: str) -> str:
    """Normalize street name for comparison: lowercase, strip diacritics, collapse whitespace."""
    s = s.strip().lower()
    # Normalize unicode
    nfkd = unicodedata.normalize('NFKD', s)
    ascii_str = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Collapse whitespace and strip punctuation
    ascii_str = re.sub(r'[.\-–,]+', ' ', ascii_str)
    ascii_str = re.sub(r'\s+', ' ', ascii_str).strip()
    return ascii_str


def match_address(rules: list, street: str, number: int) -> list[dict]:
    """Find matching rules for a given address.
    Returns list of matching rules, prioritized by specificity.
    Most specific rule wins (specific number > range > whole parity > whole street)."""

    street_norm = normalize_for_compare(street)
    matches = []

    for rule in rules:
        rule_street_norm = normalize_for_compare(rule['street'])

        if rule_street_norm != street_norm:
            continue

        # Check exclusions first
        if rule.get('exclude_numbers') and number in rule['exclude_numbers']:
            continue

        # Check parity
        parity = rule['parity']
        if parity == 'odd' and number % 2 == 0:
            continue
        if parity == 'even' and number % 2 == 1:
            continue

        # Determine match type and specificity score
        # Higher score = more specific = higher priority
        specificity = 0

        if rule['range_from'] is None and rule['range_to'] is None:
            # Whole street or whole parity
            specificity = 1 if parity == 'all' else 2
            matches.append((specificity, rule))
            continue

        # If specific numbers are listed, use those
        if rule.get('specific_numbers'):
            if number in rule['specific_numbers']:
                # Small specific set = very specific
                specificity = 10 + (100 - min(len(rule['specific_numbers']), 100))
                matches.append((specificity, rule))
            continue

        # Range check (range_to = None means open-ended "a vyšší")
        if rule['range_from'] is not None and number >= rule['range_from']:
            if rule['range_to'] is None or number <= rule['range_to']:
                range_size = (rule['range_to'] - rule['range_from']
                              if rule['range_to'] is not None else 9999)
                specificity = 5 + max(0, 50 - range_size)
                matches.append((specificity, rule))

    if not matches:
        return []

    # Sort by specificity (highest first) and return
    matches.sort(key=lambda x: x[0], reverse=True)

    # Return only the most specific match(es)
    # If multiple matches have the same top specificity, return all of them
    top_specificity = matches[0][0]
    top_matches = [rule for spec, rule in matches if spec == top_specificity]

    return top_matches


def run_tests(data: dict):
    """Run validation tests."""
    rules = data['rules']
    schools_by_id = {s['id']: s['name'] for s in data['schools']}

    test_cases = [
        # (street, number, expected_school_substring_or_None)
        # ── Celé ulice ──────────────────────────────────────────────────────
        ("Akademická", 5, "Nad Vodovodem"),
        ("Běžná", 1, "Olešská"),
        ("Amurská", 10, "Eden"),

        # ── Redistrikce 2025 (změny oproti vyhlášce 2015) ───────────────────
        # Bélocerkevská: 2015 lichá→U Roháčových, 2025 celá→Jakutská
        ("Bělocerkevská", 7, "Jakutská"),
        ("Bělocerkevská", 30, "Jakutská"),
        # Průběžná: 2025 celá ulice → Gutova (2015 část→Olešská)
        ("Průběžná", 55, "Gutova"),
        ("Průběžná", 3, "Gutova"),
        # Hostýnská: 2025 celá→Hostýnská (2015 vyjma č.12→Nad Vodovodem)
        ("Hostýnská", 12, "Hostýnská"),
        ("Hostýnská", 5, "Hostýnská"),
        # Bulharská: 2025 simplifikace — č.1-24→Kodaňská, č.25-44→U Roháčových
        ("Bulharská", 1, "Kodaňská"),
        ("Bulharská", 20, "Kodaňská"),    # 2025: celý rozsah 1-24 → Kodaňská
        ("Bulharská", 33, "U Roháčových kasáren"),

        # ── Párová sudá/lichá ────────────────────────────────────────────────
        ("Arménská", 5, "U Roháčových kasáren"),
        ("Arménská", 8, "U Roháčových kasáren"),
        ("Bartoškova", 3, "U Vršovického nádraží"),

        # ── Otevřené rozsahy "a vyšší" ──────────────────────────────────────
        ("Karpatská", 8, "Eden"),           # č. 1-10 → Eden
        ("Karpatská", 15, "Jakutská"),      # č. 11 a vyšší → Jakutská
        ("Ruská", 50, "Kodaňská"),          # sudá č. 2-58 → Karla Čapka
        ("Ruská", 47, "Jakutská"),          # lichá č. 45 a vyšší → Jakutská

        # ── Nová škola V Olšinách ────────────────────────────────────────────
        ("V olšinách", 45, "V Olšinách 200/69"),  # lichá č. 43-69

        # ── "vyjma" vyloučení ────────────────────────────────────────────────
        ("U krbu", 30, "Nad Vodovodem"),    # č. 30, 32, 45 specificky
        ("U krbu", 5, "Hostýnská"),         # celá ulice vyjma 30, 32, 45

        # ── Priorita specifické číslo > rozsah > celá ulice ─────────────────
        ("Moskevská", 61, "U Roháčových kasáren"),  # č. 58-94
        ("Moskevská", 3, "Kodaňská"),        # lichá č. 1-57
        ("Moskevská", 4, "U Vršovického nádraží"),  # sudá č. 2-56

        # ── Neexistující adresa ──────────────────────────────────────────────
        ("Neexistující", 1, None),
    ]

    passed = 0
    failed = 0

    print("=" * 80)
    print("VALIDATION TESTS")
    print("=" * 80)

    for street, number, expected_substr in test_cases:
        matches = match_address(rules, street, number)
        school_names = [schools_by_id.get(m['school_id'], '???') for m in matches]

        if expected_substr is None:
            if len(matches) == 0:
                status = "✓ PASS"
                passed += 1
            else:
                status = "✗ FAIL (expected no match)"
                failed += 1
        elif len(matches) == 0:
            status = f"✗ FAIL (no match, expected '{expected_substr}')"
            failed += 1
        elif len(matches) > 1:
            # Multiple matches — check if they all point to same school
            unique_schools = set(m['school_id'] for m in matches)
            if len(unique_schools) == 1 and expected_substr.lower() in school_names[0].lower():
                status = "✓ PASS (multiple rules, same school)"
                passed += 1
            else:
                status = f"✗ FAIL (ambiguous: {len(matches)} matches, {len(unique_schools)} schools)"
                failed += 1
        elif expected_substr.lower() in school_names[0].lower():
            status = "✓ PASS"
            passed += 1
        else:
            status = f"✗ FAIL (got '{school_names[0]}')"
            failed += 1

        school_display = school_names[0] if school_names else "NO MATCH"
        print(f"  {status:50s} | {street} {number} → {school_display}")

    print(f"\n{'=' * 80}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    # Additional checks
    print(f"\n── Coverage check ──")

    # Check for streets that appear multiple times without number restriction
    # (potential data issues)
    from collections import Counter
    whole_streets = [(r['street'], r['school_id']) for r in rules
                     if r['range_from'] is None and r['exclude_numbers'] is None]
    street_counts = Counter(s for s, _ in whole_streets)
    conflicts = {s: c for s, c in street_counts.items() if c > 1}

    if conflicts:
        print(f"\n⚠ Streets with multiple whole-street rules (potential conflicts):")
        for street, count in sorted(conflicts.items()):
            matching = [(s, sid) for s, sid in whole_streets if s == street]
            schools = [schools_by_id.get(sid, '???') for _, sid in matching]
            print(f"  {street}: {count}x → {', '.join(schools)}")
    else:
        print("  No whole-street conflicts found")

    # Check for gaps: streets where some numbers have rules but others might not
    streets_with_numbers = set(r['street'] for r in rules if r['range_from'] is not None)
    streets_with_whole = set(r['street'] for r in rules
                            if r['range_from'] is None and r['exclude_numbers'] is None)

    uncovered = streets_with_numbers - streets_with_whole
    # These streets only have partial coverage — is every number covered?
    print(f"\n  Streets with only partial number coverage: {len(uncovered)}")
    for street in sorted(uncovered):
        street_rules = [r for r in rules if r['street'] == street]
        parities = set(r['parity'] for r in street_rules)
        print(f"    {street}: {len(street_rules)} rules, parities: {parities}")

    return failed == 0


if __name__ == '__main__':
    import sys
    json_path = sys.argv[1] if len(sys.argv) > 1 else 'data/parsed/praha10.json'
    with open(json_path, 'r') as f:
        data = json.load(f)

    success = run_tests(data)
    exit(0 if success else 1)
