/**
 * Data loader — reads parsed decree JSON.
 *
 * Currently: loads from local JSON file.
 * Future: will load from Supabase.
 */

import { DecreeData } from "./types";
import fs from "fs";
import path from "path";

const cache = new Map<string, DecreeData>();

/**
 * Load decree data for a given municipality (cached in memory after first load).
 * Server-side only. Each municipality has its own JSON file: data/{id}.json
 */
export function getDecreeData(municipalityId = "praha10"): DecreeData {
  if (cache.has(municipalityId)) return cache.get(municipalityId)!;

  const safe = municipalityId.replace(/[^a-z0-9-]/g, "");
  const filePath = path.join(process.cwd(), "data", `${safe}.json`);
  const raw = fs.readFileSync(filePath, "utf-8");
  const data = JSON.parse(raw) as DecreeData;
  cache.set(municipalityId, data);

  return data;
}

/**
 * Get list of available municipalities based on JSON files present in data/.
 * Adding a new district is as simple as dropping a new JSON file.
 */
export function getAvailableMunicipalities(): { id: string; name: string }[] {
  const dataDir = path.join(process.cwd(), "data");
  try {
    return fs
      .readdirSync(dataDir)
      .filter((f) => f.endsWith(".json") && f !== "reports.json")
      .map((f) => {
        const id = f.replace(".json", "");
        const data = getDecreeData(id);
        return { id, name: data.metadata.municipality };
      });
  } catch {
    return [{ id: "praha10", name: "Praha 10" }];
  }
}
