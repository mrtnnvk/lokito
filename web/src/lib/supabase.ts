/**
 * Supabase client — server-side only.
 * Nepoužívat v klientských komponentech ("use client").
 * Proměnné jsou bez NEXT_PUBLIC_ prefixu → nedostupné v browseru.
 */
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  // V dev módu jen varování; v produkci build selže explicitně
  if (process.env.NODE_ENV === "production") {
    throw new Error("SUPABASE_URL nebo SUPABASE_ANON_KEY nejsou nastaveny.");
  }
}

export const supabase = createClient(
  supabaseUrl ?? "http://localhost:54321",
  supabaseKey ?? "placeholder"
);
