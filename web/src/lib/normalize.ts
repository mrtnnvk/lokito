/**
 * Street name normalization for Czech addresses.
 * Handles diacritics, punctuation, and whitespace variations.
 */

const DIACRITICS_MAP: Record<string, string> = {
  á: "a", č: "c", ď: "d", é: "e", ě: "e", í: "i",
  ň: "n", ó: "o", ř: "r", š: "s", ť: "t", ú: "u",
  ů: "u", ý: "y", ž: "z",
  Á: "a", Č: "c", Ď: "d", É: "e", Ě: "e", Í: "i",
  Ň: "n", Ó: "o", Ř: "r", Š: "s", Ť: "t", Ú: "u",
  Ů: "u", Ý: "y", Ž: "z",
};

export function removeDiacritics(str: string): string {
  return str.replace(/[áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]/g,
    (ch) => DIACRITICS_MAP[ch] || ch
  );
}

/**
 * Normalize a street name for comparison.
 * Lowercases, removes diacritics, collapses whitespace and punctuation.
 */
export function normalizeStreet(street: string): string {
  let s = street.trim().toLowerCase();
  s = removeDiacritics(s);
  // Replace punctuation with space
  s = s.replace(/[.\-–,]+/g, " ");
  // Collapse whitespace
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

/**
 * Get list of unique street names from rules (for autocomplete).
 * Returns original (non-normalized) names, deduplicated.
 */
export function getUniqueStreets(
  rules: { street: string }[]
): string[] {
  const seen = new Set<string>();
  const streets: string[] = [];

  for (const rule of rules) {
    const norm = normalizeStreet(rule.street);
    if (!seen.has(norm)) {
      seen.add(norm);
      streets.push(rule.street);
    }
  }

  return streets.sort((a, b) =>
    a.localeCompare(b, "cs", { sensitivity: "base" })
  );
}
