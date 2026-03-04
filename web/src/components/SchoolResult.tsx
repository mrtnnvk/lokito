"use client";

import { useState } from "react";
import type { MatchResponse } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import ReportDialog from "./ReportDialog";
import EmailLink from "./EmailLink";
import ChanceBadge from "./ChanceBadge";

const SHOW_PROBABILITY = process.env.NEXT_PUBLIC_SHOW_PROBABILITY === "true";

interface SchoolResultProps {
  response: MatchResponse;
}

export default function SchoolResult({ response }: SchoolResultProps) {
  const { result, nearby, query } = response;
  const [reportOpen, setReportOpen] = useState(false);

  const reportButton = (
    <button
      className="underline font-medium"
      onClick={() => setReportOpen(true)}
    >
      nahlaste nesrovnalost
    </button>
  );

  if (!result.matched) {
    return (
      <>
        <Alert className="border-amber-200 bg-amber-50 text-amber-800">
          <AlertTitle className="text-amber-800">Adresa nenalezena</AlertTitle>
          <AlertDescription className="text-amber-700">
            {result.reason}
            <p className="text-sm text-amber-600 mt-2">
              Zkontrolujte prosím název ulice a číslo orientační.
              Pokud si myslíte, že jde o chybu,{" "}
              {reportButton}.
            </p>
          </AlertDescription>
        </Alert>
        <ReportDialog
          open={reportOpen}
          onClose={() => setReportOpen(false)}
          query={query}
          matchedSchoolName={null}
        />
      </>
    );
  }

  const school = result.school!;

  return (
    <div className="space-y-4">
      {/* Main result */}
      <Card className="border-green-200 bg-green-50">
        <CardHeader className="pb-2">
          <p className="text-sm text-green-600 font-medium">Vaše spádová škola</p>
          <CardTitle className="flex items-start gap-2 text-xl text-gray-900">
            <span>🏫</span>
            <span>{school.name}</span>
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2 mt-1">
            {school.founder_type === "private" && (
              <Badge className="bg-purple-100 text-purple-800 border-purple-200 hover:bg-purple-100">
                soukromá
              </Badge>
            )}
            {school.founder_type === "church" && (
              <Badge className="bg-yellow-100 text-yellow-800 border-yellow-200 hover:bg-yellow-100">
                církevní
              </Badge>
            )}
            {(school.founder_type === "public" || school.founder_type === null) && (
              <Badge className="bg-blue-100 text-blue-800 border-blue-200 hover:bg-blue-100">
                státní
              </Badge>
            )}
            {/* Nárok na přijetí — právní status spádové ZŠ, vždy zobrazit */}
            <Badge className="bg-green-100 text-green-800 border-green-200 hover:bg-green-100">
              ✓ Nárok na přijetí
            </Badge>
          </div>
          {school.address && (
            <p className="text-gray-600 text-sm">{school.address}</p>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
            {school.website && (
              <a
                href={school.website.startsWith("http") ? school.website : `https://${school.website}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 underline"
              >
                {school.website.replace(/^https?:\/\//, "")}
              </a>
            )}
            {school.phone && (
              <a href={`tel:${school.phone}`} className="text-sm text-gray-600">
                {school.phone}
              </a>
            )}
            <EmailLink email={school.email} />
            {school.redizo && (
              <a
                href={`https://rejstrik-skol.msmt.cz/?redizo=${school.redizo}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-gray-500 underline"
              >
                MŠMT rejstřík
              </a>
            )}
          </div>
        </CardHeader>
        <CardContent className="border-t border-green-200 pt-4">
          <p className="text-sm text-gray-700">
            <span className="font-medium">Proč tato škola?</span>{" "}
            {result.reason}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Zdroj: {result.decree_ref}
            {" · "}
            <button
              className="underline"
              onClick={() => setReportOpen(true)}
            >
              nahlásit nesrovnalost
            </button>
          </p>
        </CardContent>
      </Card>

      {/* Nearby schools */}
      {nearby.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <p className="text-sm font-medium text-gray-500">
              Další školy v okolí (informativně)
            </p>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {nearby.map((s) => (
                <li key={s.id} className="text-sm">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-700 flex-1 min-w-0 pr-2">{s.name}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      {s.distance_km > 0 && (
                        <Badge variant="secondary" className="whitespace-nowrap">
                          {s.distance_km.toFixed(1)} km
                        </Badge>
                      )}
                      {SHOW_PROBABILITY && s.probability && (
                        <ChanceBadge probability={s.probability} compact />
                      )}
                    </div>
                  </div>
                  {SHOW_PROBABILITY && s.probability && (
                    <ChanceBadge probability={s.probability} />
                  )}
                </li>
              ))}
            </ul>
            <p className="text-xs text-gray-400 mt-3">
              Tyto školy nejsou vaše spádové. Můžete se do nich přihlásit,
              ale nemáte na přijetí právní nárok.
            </p>
          </CardContent>
        </Card>
      )}

      <ReportDialog
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        query={query}
        matchedSchoolName={school.name}
      />
    </div>
  );
}
