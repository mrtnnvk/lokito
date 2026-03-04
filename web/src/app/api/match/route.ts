import { NextRequest, NextResponse } from "next/server";
import { getDecreeData } from "@/lib/data";
import { matchAddress, findNearbySchools } from "@/lib/matching";
import { fetchProbabilityArtifacts, buildProbabilityData } from "@/lib/probability";
import { MatchResponse } from "@/lib/types";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { street, number, municipality = "praha-10" } = body;

    // Validate input
    if (!street || typeof street !== "string") {
      return NextResponse.json(
        { error: "Chybí název ulice." },
        { status: 400 }
      );
    }

    const num = parseInt(number, 10);
    if (isNaN(num) || num < 1) {
      return NextResponse.json(
        { error: "Neplatné číslo domu." },
        { status: 400 }
      );
    }

    const data = getDecreeData();

    // Filter rules by municipality
    const municipalityRules = data.rules.filter(
      (r) => r.municipality === municipality
    );

    if (municipalityRules.length === 0) {
      return NextResponse.json(
        { error: `Městská část "${municipality}" není v systému.` },
        { status: 404 }
      );
    }

    // Match address
    const result = matchAddress(
      municipalityRules,
      data.schools,
      street,
      num
    );

    // Find nearby schools (if we have coordinates for the matched school)
    let nearby = findNearbySchools(
      data.schools.filter((s) => s.municipality === municipality),
      result.school?.lat ?? 50.07,  // default to Praha 10 center
      result.school?.lon ?? 14.47,
      5,
      result.school?.id
    );

    // Připojit probability data (jen pokud je feature flag zapnutý)
    if (process.env.NEXT_PUBLIC_SHOW_PROBABILITY === "true" && nearby.length > 0) {
      const schoolIds = nearby.map((s) => s.id);
      const artifacts = await fetchProbabilityArtifacts(schoolIds);
      nearby = nearby.map((school) => {
        const artifact = artifacts.get(school.id);
        if (!artifact) return school;
        return {
          ...school,
          probability: buildProbabilityData(artifact, school.distance_km),
        };
      });
    }

    const response: MatchResponse = {
      result,
      nearby,
      query: { street, number: num, municipality },
    };

    return NextResponse.json(response);
  } catch (err) {
    console.error("Match error:", err);
    return NextResponse.json(
      { error: "Interní chyba serveru." },
      { status: 500 }
    );
  }
}
