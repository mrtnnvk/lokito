// ── Core domain types for Lokito ──

export interface School {
  id: string;
  name: string;
  address: string;
  lat: number | null;
  lon: number | null;
  redizo: string | null;
  municipality: string;
  founder_type: "public" | "private" | "church" | null;
  website: string | null;
  phone: string | null;
  email: string | null;
}

export interface Rule {
  school_id: string;
  street: string;
  parity: "even" | "odd" | "all";
  range_from: number | null;
  range_to: number | null;
  specific_numbers: number[] | null;
  exclude_numbers: number[] | null;
  number_type: string;
  municipality: string;
  raw: string;
}

export interface DecreeData {
  metadata: {
    municipality: string;
    municipality_id: string;
    decree_title: string;
    valid_from: string;
    source_url: string;
    parsed_at: string;
    total_rows: number;
    total_rules: number;
    total_schools: number;
  };
  schools: School[];
  rules: Rule[];
}

export interface MatchResult {
  matched: boolean;
  school: School | null;
  reason: string;
  decree_ref: string;
  raw_rule: string | null;
}

// ── Probability model types ──

export type ProbabilityBand = "low" | "medium" | "high";
export type ProbabilityConfidence = "low" | "medium" | "high" | "calibrated";

export interface ProbabilityData {
  /** Odhadovaná šance přijetí, 0–100. */
  score: number;
  /** Slovní pásmo šance. */
  band: ProbabilityBand;
  /** Spolehlivost modelu (low = V0, calibrated = s historickými daty). */
  confidence: ProbabilityConfidence;
  /** 2–3 lidsky čitelné důvody (CS). */
  explain: string[];
  /** Verze modelu, např. "v0.1". */
  model_version: string;
  /** Verze dat, např. "msmt-2025-09+sldb2021". */
  data_version: string;
  /** Právní upozornění — vždy zobrazit. */
  disclaimer: string;
}

export interface NearbySchool extends School {
  distance_km: number;
  /** Přítomno, pokud je zapnut feature flag NEXT_PUBLIC_SHOW_PROBABILITY=true. */
  probability?: ProbabilityData;
}

export interface MatchResponse {
  result: MatchResult;
  nearby: NearbySchool[];
  query: {
    street: string;
    number: number;
    municipality: string;
  };
}
