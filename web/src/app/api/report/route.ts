import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const REPORTS_FILE = path.join(process.cwd(), "data", "reports.json");

interface Report {
  id: string;
  created_at: string;
  street: string;
  number: number;
  municipality: string;
  matched_school: string | null;
  note: string;
}

function loadReports(): Report[] {
  if (!fs.existsSync(REPORTS_FILE)) return [];
  try {
    return JSON.parse(fs.readFileSync(REPORTS_FILE, "utf-8"));
  } catch {
    return [];
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { street, number, municipality, matched_school, note } = body;

    if (!street || typeof number !== "number") {
      return NextResponse.json({ error: "Neplatná data." }, { status: 400 });
    }

    const report: Report = {
      id: crypto.randomUUID(),
      created_at: new Date().toISOString(),
      street,
      number,
      municipality: municipality ?? "praha-10",
      matched_school: matched_school ?? null,
      note: typeof note === "string" ? note.slice(0, 1000) : "",
    };

    const reports = loadReports();
    reports.push(report);
    fs.writeFileSync(REPORTS_FILE, JSON.stringify(reports, null, 2), "utf-8");

    return NextResponse.json({ ok: true, id: report.id });
  } catch (err) {
    console.error("Report error:", err);
    return NextResponse.json({ error: "Interní chyba." }, { status: 500 });
  }
}
