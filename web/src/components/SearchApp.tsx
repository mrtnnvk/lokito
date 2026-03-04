"use client";

import { useState, useCallback } from "react";
import AddressInput from "./AddressInput";
import SchoolResult from "./SchoolResult";
import dynamic from "next/dynamic";
import type { MatchResponse } from "@/lib/types";
import { Alert, AlertDescription } from "@/components/ui/alert";

// Leaflet must be loaded client-side only
const MapView = dynamic(() => import("./MapView"), { ssr: false });

interface SearchAppProps {
  streets: string[];
}

export default function SearchApp({ streets }: SearchAppProps) {
  const [result, setResult] = useState<MatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(
    async (street: string, number: number) => {
      setLoading(true);
      setError(null);
      setResult(null);

      try {
        const res = await fetch("/api/match", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ street, number, municipality: "praha-10" }),
        });

        const data = await res.json();

        if (!res.ok) {
          setError(data.error || "Nastala chyba při vyhledávání.");
          return;
        }

        setResult(data);
      } catch {
        setError("Nepodařilo se spojit se serverem.");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return (
    <div className="space-y-6">
      <AddressInput streets={streets} onSearch={handleSearch} loading={loading} />

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {result && (
        <>
          <SchoolResult response={result} />

          <div className="h-80 rounded-lg overflow-hidden border border-gray-200 shadow-sm">
            <MapView response={result} />
          </div>
        </>
      )}
    </div>
  );
}
