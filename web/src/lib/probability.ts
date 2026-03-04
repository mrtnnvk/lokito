/**
 * Probability module — server-side only.
 * Načítá předpočítané artefakty z Supabase a sestavuje ProbabilityData
 * pro nespádové ZŠ v nearby listu.
 */

import { supabase } from "./supabase";
import type { ProbabilityData, ProbabilityBand, ProbabilityConfidence } from "./types";

const SHOW_PROBABILITY = process.env.NEXT_PUBLIC_SHOW_PROBABILITY === "true";

const DISCLAIMER = "Toto není právní nárok na přijetí. Jde o orientační odhad.";

// ── Supabase row type (subset) ─────────────────────────────────────────────
interface ArtifactRow {
  school_id: string;
  score: number;
  band: string;
  confidence: string;
  explain_static: string[];
  model_version: string;
  data_version: string;
}

/**
 * Dávkově načte probability artefakty pro seznam school_id z Supabase.
 * Vrátí prázdnou mapu, pokud je feature flag vypnutý nebo Supabase selže.
 */
export async function fetchProbabilityArtifacts(
  schoolIds: string[]
): Promise<Map<string, ArtifactRow>> {
  if (!SHOW_PROBABILITY || schoolIds.length === 0) {
    return new Map();
  }

  const { data, error } = await supabase
    .from("probability_artifacts")
    .select(
      "school_id, score, band, confidence, explain_static, model_version, data_version"
    )
    .in("school_id", schoolIds)
    .eq("is_active", true);

  if (error) {
    console.error("[probability] Supabase chyba:", error.message);
    return new Map();
  }

  return new Map((data as ArtifactRow[]).map((row) => [row.school_id, row]));
}

/**
 * Sestaví finální ProbabilityData pro jednu školu.
 * Přidává dynamický důvod na základě vzdálenosti (computed at request time).
 */
export function buildProbabilityData(
  artifact: ArtifactRow,
  distance_km: number
): ProbabilityData {
  const explain = [...(artifact.explain_static ?? [])];

  // Dynamický důvod: vzdálenost (závisí na adrese uživatele, ne na škole samotné)
  if (distance_km > 1.5) {
    explain.push(`Škola je vzdálená ${distance_km.toFixed(1)} km`);
  } else if (distance_km > 0.5) {
    explain.push(`Škola je v dosahu do ${distance_km.toFixed(1)} km`);
  } else {
    explain.push("Škola je velmi blízko (do 0,5 km)");
  }

  return {
    score: artifact.score,
    band: artifact.band as ProbabilityBand,
    confidence: artifact.confidence as ProbabilityConfidence,
    explain: explain.slice(0, 3),    // max 3 důvody celkem
    model_version: artifact.model_version,
    data_version: artifact.data_version,
    disclaimer: DISCLAIMER,
  };
}
