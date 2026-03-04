/**
 * Lokito — Matching Engine
 *
 * Core logic: given a street name and house number,
 * find the matching catchment school from decree rules.
 *
 * Priority system: specific numbers > ranges > whole parity > whole street.
 */

import { Rule, School, MatchResult, NearbySchool } from "./types";
import { normalizeStreet } from "./normalize";

interface ScoredMatch {
  specificity: number;
  rule: Rule;
}

/**
 * Find the catchment school for a given address.
 */
export function matchAddress(
  rules: Rule[],
  schools: School[],
  street: string,
  number: number
): MatchResult {
  const streetNorm = normalizeStreet(street);
  const matches: ScoredMatch[] = [];

  for (const rule of rules) {
    const ruleStreetNorm = normalizeStreet(rule.street);
    if (ruleStreetNorm !== streetNorm) continue;

    // Check exclusions
    if (rule.exclude_numbers?.includes(number)) continue;

    // Check parity
    if (rule.parity === "odd" && number % 2 === 0) continue;
    if (rule.parity === "even" && number % 2 === 1) continue;

    let specificity = 0;

    // Whole street or whole parity (no number restriction)
    if (rule.range_from === null && rule.range_to === null) {
      specificity = rule.parity === "all" ? 1 : 2;
      matches.push({ specificity, rule });
      continue;
    }

    // Specific numbers listed
    if (rule.specific_numbers && rule.specific_numbers.length > 0) {
      if (rule.specific_numbers.includes(number)) {
        specificity = 10 + (100 - Math.min(rule.specific_numbers.length, 100));
        matches.push({ specificity, rule });
      }
      continue;
    }

    // Range check (range_to = null means open-ended "a vyšší")
    if (rule.range_from !== null && number >= rule.range_from) {
      if (rule.range_to === null || number <= rule.range_to) {
        const rangeSize = rule.range_to !== null
          ? rule.range_to - rule.range_from
          : 9999; // open-ended = low specificity
        specificity = 5 + Math.max(0, 50 - rangeSize);
        matches.push({ specificity, rule });
      }
    }
  }

  if (matches.length === 0) {
    return {
      matched: false,
      school: null,
      reason: `Adresa "${street} ${number}" nebyla nalezena ve spádové vyhlášce.`,
      decree_ref: "",
      raw_rule: null,
    };
  }

  // Sort by specificity (highest first)
  matches.sort((a, b) => b.specificity - a.specificity);
  const bestRule = matches[0].rule;
  const school = schools.find((s) => s.id === bestRule.school_id) ?? null;

  // Build human-readable reason
  const reason = buildReason(bestRule, school);

  return {
    matched: true,
    school,
    reason,
    decree_ref: `Spádová vyhláška Praha 10`,
    raw_rule: bestRule.raw,
  };
}

function buildReason(rule: Rule, school: School | null): string {
  const schoolName = school?.name ?? "Neznámá škola";
  const street = rule.street;

  if (rule.range_from === null && rule.exclude_numbers === null) {
    if (rule.parity === "all") {
      return `Ulice ${street} celá spadá pod ${schoolName}.`;
    }
    const parityText = rule.parity === "odd" ? "lichá čísla" : "sudá čísla";
    return `Ulice ${street} (${parityText}) spadá pod ${schoolName}.`;
  }

  if (rule.exclude_numbers) {
    return `Ulice ${street} (kromě č. ${rule.exclude_numbers.join(", ")}) spadá pod ${schoolName}.`;
  }

  if (rule.specific_numbers && rule.specific_numbers.length <= 5) {
    return `Ulice ${street}, č. ${rule.specific_numbers.join(", ")} spadá pod ${schoolName}.`;
  }

  const parityText =
    rule.parity === "odd" ? "lichá " :
    rule.parity === "even" ? "sudá " : "";
  const rangeText = rule.range_to !== null
    ? `${rule.range_from}–${rule.range_to}`
    : `${rule.range_from} a vyšší`;
  return `Ulice ${street}, ${parityText}č. ${rangeText} spadá pod ${schoolName}.`;
}

/**
 * Calculate distance between two points (Haversine formula).
 * Returns distance in kilometers.
 */
function haversineKm(
  lat1: number, lon1: number,
  lat2: number, lon2: number
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
    Math.cos((lat2 * Math.PI) / 180) *
    Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Find N nearest schools to given coordinates.
 */
export function findNearbySchools(
  schools: School[],
  lat: number,
  lon: number,
  count: number = 5,
  excludeId?: string
): NearbySchool[] {
  return schools
    .filter((s) => s.lat !== null && s.lon !== null && s.id !== excludeId)
    .map((s) => ({
      ...s,
      distance_km: haversineKm(lat, lon, s.lat!, s.lon!),
    }))
    .sort((a, b) => a.distance_km - b.distance_km)
    .slice(0, count);
}
