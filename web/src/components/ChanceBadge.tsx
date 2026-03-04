import { Badge } from "@/components/ui/badge";
import type { ProbabilityData, ProbabilityBand, ProbabilityConfidence } from "@/lib/types";

interface ChanceBadgeProps {
  probability: ProbabilityData;
  /** compact=true → jen badge s číslem pro inline zobrazení v řádku školy */
  compact?: boolean;
}

const BAND_STYLES: Record<ProbabilityBand, string> = {
  high:   "bg-green-100 text-green-800 border border-green-200 hover:bg-green-100",
  medium: "bg-yellow-100 text-yellow-800 border border-yellow-200 hover:bg-yellow-100",
  low:    "bg-red-100 text-red-800 border border-red-200 hover:bg-red-100",
};

const BAND_LABELS: Record<ProbabilityBand, string> = {
  high:   "Vyšší šance",
  medium: "Střední šance",
  low:    "Nižší šance",
};

const CONFIDENCE_LABELS: Record<ProbabilityConfidence, string> = {
  low:        "orientační",
  medium:     "střední spolehlivost",
  high:       "vysoká spolehlivost",
  calibrated: "ověřená spolehlivost",
};

export default function ChanceBadge({ probability, compact = false }: ChanceBadgeProps) {
  const { score, band, confidence, explain, data_version, disclaimer } = probability;

  if (compact) {
    // Inline verze: jen badge + číslo
    return (
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-xs font-semibold text-gray-600">{score}&nbsp;%</span>
        <Badge className={BAND_STYLES[band]}>{BAND_LABELS[band]}</Badge>
      </div>
    );
  }

  // Rozbalená verze: badge + důvody + metadata + disclaimer
  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 mt-1 space-y-1.5">
      {/* Hlavička */}
      <div className="flex items-center gap-2">
        <Badge className={BAND_STYLES[band]}>{BAND_LABELS[band]}</Badge>
        <span className="text-sm font-semibold text-gray-800">
          Šance na přijetí: {score}&nbsp;%
        </span>
      </div>

      {/* Důvody */}
      {explain.length > 0 && (
        <ul className="text-xs text-gray-600 space-y-0.5 list-disc list-inside">
          {explain.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      )}

      {/* Metadata */}
      <p className="text-xs text-gray-400">
        Spolehlivost: {CONFIDENCE_LABELS[confidence]}
        {" · "}
        Data: {data_version}
      </p>

      {/* Právní upozornění */}
      <p className="text-xs text-amber-700 font-medium">
        ⚠ {disclaimer}
      </p>
    </div>
  );
}
