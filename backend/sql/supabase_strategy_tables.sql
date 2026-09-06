-- ============================================================
-- STRATEGY FEATURE — safe idempotent migration.
-- Adds the three tables that back the pre-race Strategy Report:
--   driver_race_stints       (one row per driver per stint)
--   track_strategy_profiles  (one row per circuit)
--   strategy_reports         (one row per race_event + report_stage)
--
-- Mirrors the conventions in supabase_safe_migrate.sql:
--   * bigserial PKs for the analytics/serving tables
--   * race_events.id (bigint) and drivers.id (uuid) foreign keys
--   * CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS
--   * input_hash index for the cache lookup (as on prediction_insights)
-- Safe to run repeatedly. No data is lost.
-- ============================================================

-- ── 1. driver_race_stints ────────────────────────────────────
-- One row per driver per stint. Source data is the per-lap `laps`
-- table (collapsed per stint). Linked exactly as specified by
-- race_event_id (bigint) + driver_id (uuid); driver_race_entry_id
-- is kept as a convenience pointer back to the per-lap rows.
CREATE TABLE IF NOT EXISTS public.driver_race_stints (
  id                   bigserial PRIMARY KEY,
  race_event_id        bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  driver_id            uuid   NOT NULL REFERENCES public.drivers(id)     ON DELETE CASCADE,
  driver_race_entry_id uuid            REFERENCES public.driver_race_entries(id) ON DELETE CASCADE,

  stint_index          integer NOT NULL,
  compound             text    NOT NULL,            -- SOFT | MEDIUM | HARD | INTERMEDIATE | WET

  lap_window_start     integer NOT NULL,            -- first lap of the stint
  lap_window_end       integer NOT NULL,            -- last lap of the stint
  stint_length         integer NOT NULL,            -- laps completed on the stint

  degradation_slope    numeric(10,5),               -- sec/lap; can be negative (fuel-burn dominated)
  clean_air_pace       numeric(10,4),               -- representative clean-air lap time (s)
  traffic_share        numeric(5,4),                -- fraction of laps in traffic, 0..1
  gap_to_car_ahead     numeric(10,4),               -- mean interval to car ahead (s)

  pit_ended            boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),

  UNIQUE (race_event_id, driver_id, stint_index)
);

CREATE INDEX IF NOT EXISTS driver_race_stints_race_event_idx
  ON public.driver_race_stints (race_event_id);
CREATE INDEX IF NOT EXISTS driver_race_stints_compound_idx
  ON public.driver_race_stints (compound);

-- ── 2. track_strategy_profiles ───────────────────────────────
-- One row per circuit. All "strength/importance/difficulty" metrics
-- are normalised to 0..1. Priors are per-race probabilities (0..1).
CREATE TABLE IF NOT EXISTS public.track_strategy_profiles (
  id                        bigserial PRIMARY KEY,
  circuit_id                bigint NOT NULL REFERENCES public.circuits(id) ON DELETE CASCADE,

  overtaking_difficulty     numeric(5,4),   -- 0 = easy to pass, 1 = very hard
  track_position_importance numeric(5,4),   -- 0..1, how much starting/track position matters
  undercut_strength         numeric(5,4),   -- 0..1, how much an undercut gains

  pit_loss_baseline         numeric(7,3),   -- seconds lost for a green-flag pit stop

  sc_prior                  numeric(5,4),   -- P(>=1 safety car in the race), 0..1
  vsc_prior                 numeric(5,4),   -- P(>=1 virtual safety car), 0..1
  red_flag_prior            numeric(5,4),   -- P(>=1 red flag), 0..1

  sample_races              integer,        -- how many races backed these estimates
  updated_at                timestamptz NOT NULL DEFAULT now(),
  created_at                timestamptz NOT NULL DEFAULT now(),

  UNIQUE (circuit_id)
);

-- ── 3. strategy_reports ──────────────────────────────────────
-- One row per (race_event_id, report_stage). report_json holds the
-- full StrategyOutput schema; summary holds the AI narrative markdown.
-- Cache key is input_hash (mirrors prediction_insights).
CREATE TABLE IF NOT EXISTS public.strategy_reports (
  id             bigserial PRIMARY KEY,
  race_event_id  bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  report_stage   text   NOT NULL CHECK (report_stage IN ('pre_weekend', 'post_practice', 'post_qualifying')),

  model_version  text   NOT NULL,
  input_hash     text   NOT NULL,
  summary        text,                                  -- fan-facing markdown narrative
  report_json    jsonb  NOT NULL DEFAULT '{}'::jsonb,   -- full StrategyOutput

  generated_at   timestamptz NOT NULL DEFAULT now(),
  created_at     timestamptz NOT NULL DEFAULT now(),

  UNIQUE (race_event_id, report_stage)
);

CREATE INDEX IF NOT EXISTS strategy_reports_input_hash_idx
  ON public.strategy_reports (input_hash);
CREATE INDEX IF NOT EXISTS strategy_reports_race_event_idx
  ON public.strategy_reports (race_event_id);
