-- Lokito — Supabase schema
-- Verze: 001_initial_schema
-- Spustit: Supabase dashboard → SQL editor → New query → vložit + Run

-- ── municipalities ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS municipalities (
  id              TEXT PRIMARY KEY,          -- "praha-10"
  name            TEXT,
  decree_title    TEXT,
  valid_from      DATE,
  source_url      TEXT,
  parsed_at       TEXT,
  total_rules     INT,
  total_schools   INT
);

-- ── schools ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schools (
  id              TEXT PRIMARY KEY,          -- "zs-eden" apod.
  municipality_id TEXT REFERENCES municipalities(id),
  name            TEXT NOT NULL,
  address         TEXT,
  lat             DOUBLE PRECISION,
  lon             DOUBLE PRECISION,
  redizo          TEXT UNIQUE,
  founder_type    TEXT,                      -- "public" | "private" | "church"
  website         TEXT,
  phone           TEXT,
  email           TEXT
);

-- ── rules ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rules (
  id              INT PRIMARY KEY,
  school_id       TEXT REFERENCES schools(id),
  street          TEXT,
  parity          TEXT,                      -- "all" | "even" | "odd"
  range_from      INT,
  range_to        INT,
  specific_numbers INT[],
  exclude_numbers  INT[],
  number_type     TEXT,
  municipality    TEXT,
  raw             TEXT
);
CREATE INDEX IF NOT EXISTS rules_school_idx ON rules(school_id);
CREATE INDEX IF NOT EXISTS rules_street_idx ON rules(street);

-- ── probability_artifacts ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS probability_artifacts (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  school_id        TEXT REFERENCES schools(id),
  model_version    TEXT NOT NULL,            -- "v0.1"
  data_version     TEXT NOT NULL,            -- "msmt2025+sldb2021"
  computed_at      TIMESTAMPTZ,
  kapacita         INT,
  enrolled         INT,
  free_spots_proxy INT,
  demand_age6      INT,
  pressure_index   DOUBLE PRECISION,
  score            SMALLINT,                 -- 0–100
  band             TEXT,                     -- "low" | "medium" | "high"
  confidence       TEXT,                     -- "low" | "medium" | "high" | "calibrated"
  explain_static   TEXT[],
  is_active        BOOLEAN DEFAULT true,
  confidence_note  TEXT,
  UNIQUE (school_id, model_version)
);
CREATE INDEX IF NOT EXISTS prob_school_active_idx ON probability_artifacts(school_id, is_active);

-- ── Row Level Security ───────────────────────────────────────────────────────
ALTER TABLE municipalities       ENABLE ROW LEVEL SECURITY;
ALTER TABLE schools               ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE probability_artifacts ENABLE ROW LEVEL SECURITY;

-- Veřejné čtení (anon key smí SELECT)
CREATE POLICY "public_read" ON municipalities        FOR SELECT USING (true);
CREATE POLICY "public_read" ON schools               FOR SELECT USING (true);
CREATE POLICY "public_read" ON rules                 FOR SELECT USING (true);
CREATE POLICY "public_read" ON probability_artifacts FOR SELECT USING (is_active = true);

-- Zápis jen service key (policies pro INSERT/UPDATE/DELETE — pouze service role)
-- Supabase service key obchází RLS automaticky, takže extra policy není nutná.
-- Pokud potřebuješ explicitní: CREATE POLICY "service_write" ON ... USING (auth.role() = 'service_role');
