"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface ReportDialogProps {
  open: boolean;
  onClose: () => void;
  query: {
    street: string;
    number: number;
    municipality: string;
  };
  matchedSchoolName: string | null;
}

type State = "idle" | "loading" | "success" | "error";

export default function ReportDialog({
  open,
  onClose,
  query,
  matchedSchoolName,
}: ReportDialogProps) {
  const [note, setNote] = useState("");
  const [state, setState] = useState<State>("idle");

  const handleSubmit = async () => {
    setState("loading");
    try {
      const res = await fetch("/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          street: query.street,
          number: query.number,
          municipality: query.municipality,
          matched_school: matchedSchoolName,
          note: note.trim(),
        }),
      });
      if (!res.ok) throw new Error();
      setState("success");
      setNote("");
    } catch {
      setState("error");
    }
  };

  const handleClose = () => {
    setState("idle");
    setNote("");
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nahlásit nesrovnalost</DialogTitle>
          <DialogDescription>
            Adresa:{" "}
            <span className="font-medium text-gray-900">
              {query.street} {query.number}
            </span>
            {matchedSchoolName && (
              <>
                {" · "}přiřazená škola:{" "}
                <span className="font-medium text-gray-900">
                  {matchedSchoolName}
                </span>
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        {state === "success" ? (
          <div className="py-4 text-center text-green-700">
            <p className="font-medium">Díky za hlášení!</p>
            <p className="text-sm text-gray-500 mt-1">
              Nesrovnalost jsme zaznamenali a prověříme ji.
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <Label htmlFor="report-note">
                Co je špatně? <span className="text-gray-400">(volitelné)</span>
              </Label>
              <Textarea
                id="report-note"
                placeholder="Např. moje adresa patří pod jinou školu, číslo popisné je ve vyhlášce chybně…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={4}
                maxLength={1000}
              />
            </div>
            {state === "error" && (
              <p className="text-sm text-red-600">
                Odeslání se nezdařilo. Zkuste to prosím znovu.
              </p>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>
                Zrušit
              </Button>
              <Button onClick={handleSubmit} disabled={state === "loading"}>
                {state === "loading" ? "Odesílám…" : "Odeslat"}
              </Button>
            </DialogFooter>
          </>
        )}

        {state === "success" && (
          <DialogFooter>
            <Button onClick={handleClose}>Zavřít</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
