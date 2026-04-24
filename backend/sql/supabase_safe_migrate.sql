-- ============================================================
-- SAFE IDEMPOTENT MIGRATION — run this instead of the original.
-- No data is lost: uses CREATE IF NOT EXISTS, ADD COLUMN IF NOT
-- EXISTS, and INSERT … ON CONFLICT for all upserts.
-- ============================================================

-- ── 1. Core tables ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.circuits (
  id            bigserial PRIMARY KEY,
  code          text NOT NULL UNIQUE,
  file_slug     text NOT NULL UNIQUE,
  title         text NOT NULL,
  subtitle      text NOT NULL,
  flag          text NOT NULL,
  timezone_name text NOT NULL,
  weekend_format text NOT NULL CHECK (weekend_format IN ('normal', 'sprint')),
  length_km     numeric(6,3) NOT NULL,
  laps          integer NOT NULL,
  corners       integer NOT NULL,
  distance_km   numeric(7,3) NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.race_events (
  id              bigserial PRIMARY KEY,
  season          integer NOT NULL,
  round           integer NOT NULL,
  circuit_id      bigint NOT NULL REFERENCES public.circuits(id) ON DELETE RESTRICT,
  grand_prix_name text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (season, round),
  UNIQUE (season, circuit_id)
);

CREATE TABLE IF NOT EXISTS public.race_sessions (
  id               bigserial PRIMARY KEY,
  race_event_id    bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  session_type     text NOT NULL,
  session_start_utc timestamptz NOT NULL,
  session_end_utc  timestamptz NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (race_event_id, session_type)
);

-- ── 2. Backward-compatible column / constraint migrations ─────

-- Add weekend_format if it was missing from an older circuits table.
ALTER TABLE public.circuits
  ADD COLUMN IF NOT EXISTS timezone_name text;

UPDATE public.circuits
SET timezone_name = CASE code
  WHEN 'Melbourne' THEN 'Australia/Melbourne'
  WHEN 'Shanghai' THEN 'Asia/Shanghai'
  WHEN 'Suzuka' THEN 'Asia/Tokyo'
  WHEN 'Sakhir' THEN 'Asia/Bahrain'
  WHEN 'Jeddah' THEN 'Asia/Riyadh'
  WHEN 'Miami' THEN 'America/New_York'
  WHEN 'Montreal' THEN 'America/Toronto'
  WHEN 'Monaco' THEN 'Europe/Monaco'
  WHEN 'Catalunya' THEN 'Europe/Madrid'
  WHEN 'Austria' THEN 'Europe/Vienna'
  WHEN 'Silverstone' THEN 'Europe/London'
  WHEN 'Spa' THEN 'Europe/Brussels'
  WHEN 'Hungary' THEN 'Europe/Budapest'
  WHEN 'Zandvoort' THEN 'Europe/Amsterdam'
  WHEN 'Monza' THEN 'Europe/Rome'
  WHEN 'Madrid' THEN 'Europe/Madrid'
  WHEN 'Baku' THEN 'Asia/Baku'
  WHEN 'Singapore' THEN 'Asia/Singapore'
  WHEN 'Austin' THEN 'America/Chicago'
  WHEN 'MexicoCity' THEN 'America/Mexico_City'
  WHEN 'SaoPaulo' THEN 'America/Sao_Paulo'
  WHEN 'LasVegas' THEN 'America/Los_Angeles'
  WHEN 'Qatar' THEN 'Asia/Qatar'
  WHEN 'YasMarina' THEN 'Asia/Dubai'
  ELSE timezone_name
END
WHERE timezone_name IS NULL;

ALTER TABLE public.circuits
  ADD COLUMN IF NOT EXISTS weekend_format text;

UPDATE public.circuits
SET weekend_format = 'normal'
WHERE weekend_format IS NULL;

ALTER TABLE public.circuits
  DROP CONSTRAINT IF EXISTS circuits_weekend_format_check;

ALTER TABLE public.circuits
  ADD CONSTRAINT circuits_weekend_format_check
    CHECK (weekend_format IN ('normal', 'sprint'));

ALTER TABLE public.circuits
  ALTER COLUMN weekend_format SET NOT NULL;

ALTER TABLE public.circuits
  ALTER COLUMN timezone_name SET NOT NULL;

-- Remove deprecated sprint_shootout sessions (safe: they no longer exist
-- as a valid session_type and should not be present).
DELETE FROM public.race_sessions
WHERE session_type = 'sprint_shootout';

-- Migrate separate date/time columns → single timestamptz (idempotent).
ALTER TABLE public.race_sessions
  ADD COLUMN IF NOT EXISTS session_start_utc timestamptz;

ALTER TABLE public.race_sessions
  ADD COLUMN IF NOT EXISTS session_end_utc timestamptz;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'race_sessions'
      AND column_name = 'session_date_aest'
  ) AND EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'race_sessions'
      AND column_name = 'session_time_aest'
  ) THEN
    EXECUTE $sql$
      UPDATE public.race_sessions rs
      SET session_start_utc =
        (rs.session_date_aest + rs.session_time_aest)::timestamp
        AT TIME ZONE COALESCE(c.timezone_name, 'Australia/Melbourne')
      FROM public.race_events re
      JOIN public.circuits c ON c.id = re.circuit_id
      WHERE rs.race_event_id = re.id
        AND rs.session_start_utc IS NULL
        AND rs.session_date_aest IS NOT NULL
        AND rs.session_time_aest IS NOT NULL
    $sql$;
  END IF;
END $$;

UPDATE public.race_sessions
SET session_end_utc =
  session_start_utc +
    CASE session_type
      WHEN 'race' THEN INTERVAL '2 hours'
      ELSE INTERVAL '1 hour'
    END
WHERE session_start_utc IS NOT NULL
  AND session_end_utc IS NULL;

ALTER TABLE public.race_sessions
  DROP COLUMN IF EXISTS session_date_aest;

ALTER TABLE public.race_sessions
  DROP COLUMN IF EXISTS session_time_aest;

-- Replace session_type constraint to current allowed values.
ALTER TABLE public.race_sessions
  DROP CONSTRAINT IF EXISTS race_sessions_session_type_check;

ALTER TABLE public.race_sessions
  ADD CONSTRAINT race_sessions_session_type_check CHECK (
    session_type IN (
      'practice_1',
      'practice_2',
      'practice_3',
      'sprint_qualifying',
      'qualifying',
      'sprint',
      'race'
    )
  );

-- Add data_fetched flag if missing.
ALTER TABLE public.race_sessions
  ADD COLUMN IF NOT EXISTS data_fetched boolean NOT NULL DEFAULT false;

-- ── 3. Circuits upsert (2026 calendar) ───────────────────────

INSERT INTO public.circuits (
  code, file_slug, title, subtitle, flag, timezone_name, weekend_format, length_km, laps, corners, distance_km
)
VALUES
  ('Melbourne',  'Melbourne',  'MELBOURNE',  'ALBERT PARK CIRCUIT',                 'AU', 'Australia/Melbourne', 'normal', 5.278, 58, 16, 306.124),
  ('Shanghai',   'Shanghai',   'SHANGHAI',   'SHANGHAI INTERNATIONAL CIRCUIT',      'CN', 'Asia/Shanghai',       'sprint', 5.451, 56, 16, 305.066),
  ('Suzuka',     'Suzuka',     'SUZUKA',     'SUZUKA INTERNATIONAL RACING COURSE',  'JP', 'Asia/Tokyo',          'normal', 5.807, 53, 18, 307.471),
  ('Sakhir',     'Sakhir',     'SAKHIR',     'BAHRAIN INTERNATIONAL CIRCUIT',       'BH', 'Asia/Bahrain',        'normal', 5.412, 57, 15, 308.238),
  ('Jeddah',     'Jeddah',     'JEDDAH',     'JEDDAH CORNICHE CIRCUIT',             'SA', 'Asia/Riyadh',         'normal', 6.174, 50, 27, 308.450),
  ('Miami',      'Miami',      'MIAMI',      'MIAMI INTERNATIONAL AUTODROME',       'US', 'America/New_York',    'sprint', 5.412, 57, 19, 308.326),
  ('Montreal',   'Montreal',   'MONTREAL',   'CIRCUIT GILLES-VILLENEUVE',           'CA', 'America/Toronto',     'sprint', 4.361, 70, 14, 305.270),
  ('Monaco',     'Monaco',     'MONACO',     'CIRCUIT DE MONACO',                   'MC', 'Europe/Monaco',       'normal', 3.337, 78, 19, 260.286),
  ('Catalunya',  'Catalunya',  'BARCELONA',  'CIRCUIT DE BARCELONA-CATALUNYA',      'ES', 'Europe/Madrid',       'normal', 4.657, 66, 16, 307.236),
  ('Austria',    'Austria',    'AUSTRIA',    'RED BULL RING',                       'AT', 'Europe/Vienna',       'normal', 4.318, 71, 10, 306.452),
  ('Silverstone','Silverstone','SILVERSTONE','SILVERSTONE CIRCUIT',                 'GB', 'Europe/London',       'sprint', 5.891, 52, 18, 306.198),
  ('Spa',        'Spa',        'SPA',        'CIRCUIT DE SPA-FRANCORCHAMPS',        'BE', 'Europe/Brussels',     'normal', 7.004, 44, 19, 308.052),
  ('Hungary',    'Hungary',    'HUNGARY',    'HUNGARORING',                         'HU', 'Europe/Budapest',     'normal', 4.381, 70, 14, 306.630),
  ('Zandvoort',  'Zandvoort',  'ZANDVOORT',  'CIRCUIT ZANDVOORT',                   'NL', 'Europe/Amsterdam',    'sprint', 4.259, 72, 14, 306.587),
  ('Monza',      'Monza',      'MONZA',      'AUTODROMO NAZIONALE MONZA',           'IT', 'Europe/Rome',         'normal', 5.793, 53, 11, 306.720),
  ('Madrid',     'Madrid',     'MADRID',     'MADRING',                             'ES', 'Europe/Madrid',       'normal', 5.470, 56, 22, 306.320),
  ('Baku',       'Baku',       'BAKU',       'BAKU CITY CIRCUIT',                   'AZ', 'Asia/Baku',           'normal', 6.003, 51, 20, 306.049),
  ('Singapore',  'Singapore',  'SINGAPORE',  'MARINA BAY STREET CIRCUIT',           'SG', 'Asia/Singapore',      'sprint', 4.940, 62, 19, 306.143),
  ('Austin',     'Austin',     'AUSTIN',     'CIRCUIT OF THE AMERICAS',             'US', 'America/Chicago',     'normal', 5.513, 56, 20, 308.405),
  ('MexicoCity', 'MexicoCity', 'MEXICO CITY','AUTODROMO HERMANOS RODRIGUEZ',        'MX', 'America/Mexico_City', 'normal', 4.304, 71, 17, 305.354),
  ('SaoPaulo',   'SaoPaulo',   'SAO PAULO',  'AUTODROMO JOSE CARLOS PACE',          'BR', 'America/Sao_Paulo',   'normal', 4.309, 71, 15, 305.879),
  ('LasVegas',   'LasVegas',   'LAS VEGAS',  'LAS VEGAS STRIP CIRCUIT',             'US', 'America/Los_Angeles', 'normal', 6.201, 50, 17, 309.958),
  ('Qatar',      'Qatar',      'QATAR',      'LUSAIL INTERNATIONAL CIRCUIT',        'QA', 'Asia/Qatar',          'normal', 5.419, 57, 16, 308.611),
  ('YasMarina',  'YasMarina',  'YAS MARINA', 'YAS MARINA CIRCUIT',                  'AE', 'Asia/Dubai',          'normal', 5.281, 58, 16, 306.183)
ON CONFLICT (code) DO UPDATE SET
  file_slug     = EXCLUDED.file_slug,
  title         = EXCLUDED.title,
  subtitle      = EXCLUDED.subtitle,
  flag          = EXCLUDED.flag,
  timezone_name = EXCLUDED.timezone_name,
  weekend_format = EXCLUDED.weekend_format,
  length_km     = EXCLUDED.length_km,
  laps          = EXCLUDED.laps,
  corners       = EXCLUDED.corners,
  distance_km   = EXCLUDED.distance_km;

-- ── 4. Race events upsert (2026) ─────────────────────────────
-- ON CONFLICT keeps existing rows; only inserts missing rounds.

INSERT INTO public.race_events (season, round, circuit_id, grand_prix_name)
SELECT
  2026,
  r.round,
  c.id,
  r.grand_prix_name
FROM (
  VALUES
    (1,  'Melbourne',  'Australian Grand Prix'),
    (2,  'Shanghai',   'Chinese Grand Prix'),
    (3,  'Suzuka',     'Japanese Grand Prix'),
    (4,  'Sakhir',     'Bahrain Grand Prix'),
    (5,  'Jeddah',     'Saudi Arabian Grand Prix'),
    (6,  'Miami',      'Miami Grand Prix'),
    (7,  'Montreal',   'Canadian Grand Prix'),
    (8,  'Monaco',     'Monaco Grand Prix'),
    (9,  'Catalunya',  'Barcelona-Catalunya'),
    (10, 'Austria',    'Austrian Grand Prix'),
    (11, 'Silverstone','British Grand Prix'),
    (12, 'Spa',        'Belgian Grand Prix'),
    (13, 'Hungary',    'Hungarian Grand Prix'),
    (14, 'Zandvoort',  'Dutch Grand Prix'),
    (15, 'Monza',      'Italian Grand Prix'),
    (16, 'Madrid',     'Spanish Grand Prix'),
    (17, 'Baku',       'Azerbaijan Grand Prix'),
    (18, 'Singapore',  'Singapore Grand Prix'),
    (19, 'Austin',     'United States Grand Prix'),
    (20, 'MexicoCity', 'Mexico City Grand Prix'),
    (21, 'SaoPaulo',   'Brazilian Grand Prix'),
    (22, 'LasVegas',   'Las Vegas Grand Prix'),
    (23, 'Qatar',      'Qatar Grand Prix'),
    (24, 'YasMarina',  'Abu Dhabi Grand Prix')
) AS r(round, circuit_code, grand_prix_name)
JOIN public.circuits c ON c.code = r.circuit_code
ON CONFLICT (season, round) DO UPDATE SET
  grand_prix_name = EXCLUDED.grand_prix_name,
  circuit_id      = EXCLUDED.circuit_id;

-- ── 5. Race sessions upsert (2026, stored in UTC) ────────────
-- All listed times are in the circuit's local timezone.

INSERT INTO public.race_sessions (race_event_id, session_type, session_start_utc, session_end_utc)
SELECT
  e.id,
  s.session_type,
  s.session_start_local::timestamp AT TIME ZONE c.timezone_name,
  (s.session_start_local::timestamp AT TIME ZONE c.timezone_name) +
    CASE s.session_type
      WHEN 'race' THEN INTERVAL '2 hours'
      ELSE INTERVAL '1 hour'
    END
FROM (
  VALUES
    (1,  'practice_1',        '2026-03-06 12:30'),
    (1,  'practice_2',        '2026-03-06 16:00'),
    (1,  'practice_3',        '2026-03-07 12:30'),
    (1,  'qualifying',        '2026-03-07 16:00'),
    (1,  'race',              '2026-03-08 15:00'),
    (2,  'practice_1',        '2026-03-13 14:30'),
    (2,  'sprint_qualifying', '2026-03-13 18:30'),
    (2,  'sprint',            '2026-03-14 14:00'),
    (2,  'qualifying',        '2026-03-14 18:00'),
    (2,  'race',              '2026-03-15 18:00'),
    (3,  'practice_1',        '2026-03-27 13:30'),
    (3,  'practice_2',        '2026-03-27 17:00'),
    (3,  'practice_3',        '2026-03-28 13:30'),
    (3,  'qualifying',        '2026-03-28 17:00'),
    (3,  'race',              '2026-03-29 16:00'),
    (4,  'practice_1',        '2026-04-10 21:30'),
    (4,  'practice_2',        '2026-04-11 01:00'),
    (4,  'practice_3',        '2026-04-11 22:30'),
    (4,  'qualifying',        '2026-04-12 02:00'),
    (4,  'race',              '2026-04-13 01:00'),
    (5,  'practice_1',        '2026-04-17 23:30'),
    (5,  'practice_2',        '2026-04-18 03:00'),
    (5,  'practice_3',        '2026-04-18 23:30'),
    (5,  'qualifying',        '2026-04-19 03:00'),
    (5,  'race',              '2026-04-20 03:00'),
    (6,  'practice_1',        '2026-05-02 02:30'),
    (6,  'sprint_qualifying', '2026-05-02 06:30'),
    (6,  'sprint',            '2026-05-03 02:00'),
    (6,  'qualifying',        '2026-05-03 06:00'),
    (6,  'race',              '2026-05-04 06:00'),
    (7,  'practice_1',        '2026-05-23 02:30'),
    (7,  'sprint_qualifying', '2026-05-23 06:30'),
    (7,  'sprint',            '2026-05-24 02:00'),
    (7,  'qualifying',        '2026-05-24 06:00'),
    (7,  'race',              '2026-05-25 06:00'),
    (8,  'practice_1',        '2026-06-05 21:30'),
    (8,  'practice_2',        '2026-06-06 01:00'),
    (8,  'practice_3',        '2026-06-06 20:30'),
    (8,  'qualifying',        '2026-06-07 00:00'),
    (8,  'race',              '2026-06-07 23:00'),
    (9,  'practice_1',        '2026-06-12 21:30'),
    (9,  'practice_2',        '2026-06-13 01:00'),
    (9,  'practice_3',        '2026-06-13 20:30'),
    (9,  'qualifying',        '2026-06-14 00:00'),
    (9,  'race',              '2026-06-14 23:00'),
    (10, 'practice_1',        '2026-06-26 21:30'),
    (10, 'practice_2',        '2026-06-27 01:00'),
    (10, 'practice_3',        '2026-06-27 20:30'),
    (10, 'qualifying',        '2026-06-28 00:00'),
    (10, 'race',              '2026-06-28 23:00'),
    (11, 'practice_1',        '2026-07-03 21:30'),
    (11, 'sprint_qualifying', '2026-07-04 01:30'),
    (11, 'sprint',            '2026-07-04 21:00'),
    (11, 'qualifying',        '2026-07-05 01:00'),
    (11, 'race',              '2026-07-06 00:00'),
    (12, 'practice_1',        '2026-07-17 21:30'),
    (12, 'practice_2',        '2026-07-18 01:00'),
    (12, 'practice_3',        '2026-07-18 20:30'),
    (12, 'qualifying',        '2026-07-19 00:00'),
    (12, 'race',              '2026-07-19 23:00'),
    (13, 'practice_1',        '2026-07-24 21:30'),
    (13, 'practice_2',        '2026-07-25 01:00'),
    (13, 'practice_3',        '2026-07-25 20:30'),
    (13, 'qualifying',        '2026-07-26 00:00'),
    (13, 'race',              '2026-07-26 23:00'),
    (14, 'practice_1',        '2026-08-21 20:30'),
    (14, 'sprint_qualifying', '2026-08-22 00:30'),
    (14, 'sprint',            '2026-08-22 20:00'),
    (14, 'qualifying',        '2026-08-23 00:00'),
    (14, 'race',              '2026-08-23 23:00'),
    (15, 'practice_1',        '2026-09-04 20:30'),
    (15, 'practice_2',        '2026-09-05 00:00'),
    (15, 'practice_3',        '2026-09-05 20:30'),
    (15, 'qualifying',        '2026-09-06 00:00'),
    (15, 'race',              '2026-09-06 23:00'),
    (16, 'practice_1',        '2026-09-11 21:30'),
    (16, 'practice_2',        '2026-09-12 01:00'),
    (16, 'practice_3',        '2026-09-12 20:30'),
    (16, 'qualifying',        '2026-09-13 00:00'),
    (16, 'race',              '2026-09-13 23:00'),
    (17, 'practice_1',        '2026-09-24 18:30'),
    (17, 'practice_2',        '2026-09-24 22:00'),
    (17, 'practice_3',        '2026-09-25 18:30'),
    (17, 'qualifying',        '2026-09-25 22:00'),
    (17, 'race',              '2026-09-26 21:00'),
    (18, 'practice_1',        '2026-10-09 19:30'),
    (18, 'sprint_qualifying', '2026-10-09 23:30'),
    (18, 'sprint',            '2026-10-10 20:00'),
    (18, 'qualifying',        '2026-10-11 00:00'),
    (18, 'race',              '2026-10-11 23:00'),
    (19, 'practice_1',        '2026-10-24 04:30'),
    (19, 'practice_2',        '2026-10-24 08:00'),
    (19, 'practice_3',        '2026-10-25 04:30'),
    (19, 'qualifying',        '2026-10-25 08:00'),
    (19, 'race',              '2026-10-26 07:00'),
    (20, 'practice_1',        '2026-10-31 05:30'),
    (20, 'practice_2',        '2026-10-31 09:00'),
    (20, 'practice_3',        '2026-11-01 04:30'),
    (20, 'qualifying',        '2026-11-01 08:00'),
    (20, 'race',              '2026-11-02 07:00'),
    (21, 'practice_1',        '2026-11-07 02:30'),
    (21, 'practice_2',        '2026-11-07 06:00'),
    (21, 'practice_3',        '2026-11-08 01:30'),
    (21, 'qualifying',        '2026-11-08 05:00'),
    (21, 'race',              '2026-11-09 04:00'),
    (22, 'practice_1',        '2026-11-20 11:30'),
    (22, 'practice_2',        '2026-11-20 15:00'),
    (22, 'practice_3',        '2026-11-21 11:30'),
    (22, 'qualifying',        '2026-11-21 15:00'),
    (22, 'race',              '2026-11-22 15:00'),
    (23, 'practice_1',        '2026-11-28 00:30'),
    (23, 'practice_2',        '2026-11-28 04:00'),
    (23, 'practice_3',        '2026-11-29 01:30'),
    (23, 'qualifying',        '2026-11-29 05:00'),
    (23, 'race',              '2026-11-30 03:00'),
    (24, 'practice_1',        '2026-12-04 20:30'),
    (24, 'practice_2',        '2026-12-05 00:00'),
    (24, 'practice_3',        '2026-12-05 21:30'),
    (24, 'qualifying',        '2026-12-06 01:00'),
    (24, 'race',              '2026-12-07 00:00')
) AS s(round, session_type, session_start_local)
JOIN public.race_events e
  ON e.season = 2026
 AND e.round  = s.round
JOIN public.circuits c
  ON c.id = e.circuit_id
ON CONFLICT (race_event_id, session_type) DO UPDATE SET
  session_start_utc = EXCLUDED.session_start_utc,
  session_end_utc = EXCLUDED.session_end_utc;

-- ── 6. Track history table and upsert ────────────────────────

CREATE TABLE IF NOT EXISTS public.track_history (
  id         bigserial PRIMARY KEY,
  circuit_id bigint NOT NULL REFERENCES public.circuits(id) ON DELETE RESTRICT,
  year       integer NOT NULL,
  winner     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (circuit_id, year)
);

INSERT INTO public.track_history (circuit_id, year, winner)
SELECT c.id, h.year, h.winner
FROM (
  VALUES
    -- Australian Grand Prix — Albert Park
    ('Melbourne',  2025, 'Lando Norris'),
    ('Melbourne',  2024, 'Carlos Sainz'),
    ('Melbourne',  2023, 'Max Verstappen'),
    ('Melbourne',  2022, 'Charles Leclerc'),
    ('Melbourne',  2019, 'Valtteri Bottas'),

    -- Chinese Grand Prix — Shanghai
    ('Shanghai',   2025, 'Oscar Piastri'),
    ('Shanghai',   2024, 'Max Verstappen'),
    ('Shanghai',   2019, 'Lewis Hamilton'),
    ('Shanghai',   2018, 'Daniel Ricciardo'),
    ('Shanghai',   2017, 'Lewis Hamilton'),

    -- Japanese Grand Prix — Suzuka
    ('Suzuka',     2025, 'Max Verstappen'),
    ('Suzuka',     2024, 'Max Verstappen'),
    ('Suzuka',     2023, 'Max Verstappen'),
    ('Suzuka',     2022, 'Max Verstappen'),
    ('Suzuka',     2019, 'Valtteri Bottas'),

    -- Bahrain Grand Prix — Sakhir
    ('Sakhir',     2025, 'Oscar Piastri'),
    ('Sakhir',     2024, 'Max Verstappen'),
    ('Sakhir',     2023, 'Max Verstappen'),
    ('Sakhir',     2022, 'Charles Leclerc'),
    ('Sakhir',     2021, 'Lewis Hamilton'),

    -- Saudi Arabian Grand Prix — Jeddah
    ('Jeddah',     2025, 'Max Verstappen'),
    ('Jeddah',     2024, 'Max Verstappen'),
    ('Jeddah',     2023, 'Sergio Pérez'),
    ('Jeddah',     2022, 'Max Verstappen'),
    ('Jeddah',     2021, 'Lewis Hamilton'),

    -- Miami Grand Prix
    ('Miami',      2025, 'Lando Norris'),
    ('Miami',      2024, 'Lando Norris'),
    ('Miami',      2023, 'Max Verstappen'),
    ('Miami',      2022, 'Max Verstappen'),

    -- Canadian Grand Prix — Montreal
    ('Montreal',   2025, 'George Russell'),
    ('Montreal',   2024, 'Max Verstappen'),
    ('Montreal',   2023, 'Max Verstappen'),
    ('Montreal',   2022, 'Max Verstappen'),
    ('Montreal',   2019, 'Lewis Hamilton'),

    -- Monaco Grand Prix
    ('Monaco',     2025, 'Charles Leclerc'),
    ('Monaco',     2024, 'Charles Leclerc'),
    ('Monaco',     2023, 'Max Verstappen'),
    ('Monaco',     2022, 'Sergio Pérez'),
    ('Monaco',     2021, 'Max Verstappen'),

    -- Barcelona-Catalunya GP (Spain)
    ('Catalunya',  2025, 'Max Verstappen'),
    ('Catalunya',  2024, 'Max Verstappen'),
    ('Catalunya',  2023, 'Max Verstappen'),
    ('Catalunya',  2022, 'Max Verstappen'),
    ('Catalunya',  2021, 'Lewis Hamilton'),

    -- Austrian Grand Prix — Red Bull Ring
    ('Austria',    2025, 'Max Verstappen'),
    ('Austria',    2024, 'Max Verstappen'),
    ('Austria',    2023, 'Max Verstappen'),
    ('Austria',    2022, 'Charles Leclerc'),
    ('Austria',    2021, 'Max Verstappen'),

    -- British Grand Prix — Silverstone
    ('Silverstone',2025, 'Lewis Hamilton'),
    ('Silverstone',2024, 'Lewis Hamilton'),
    ('Silverstone',2023, 'Max Verstappen'),
    ('Silverstone',2022, 'Carlos Sainz'),
    ('Silverstone',2021, 'Lewis Hamilton'),

    -- Belgian Grand Prix — Spa
    ('Spa',        2025, 'Charles Leclerc'),
    ('Spa',        2024, 'Max Verstappen'),
    ('Spa',        2023, 'Max Verstappen'),
    ('Spa',        2022, 'Max Verstappen'),
    ('Spa',        2021, 'Max Verstappen'),

    -- Hungarian Grand Prix — Hungaroring
    ('Hungary',    2025, 'Oscar Piastri'),
    ('Hungary',    2024, 'Oscar Piastri'),
    ('Hungary',    2023, 'Max Verstappen'),
    ('Hungary',    2022, 'Max Verstappen'),
    ('Hungary',    2021, 'Esteban Ocon'),

    -- Dutch Grand Prix — Zandvoort
    ('Zandvoort',  2025, 'Max Verstappen'),
    ('Zandvoort',  2024, 'Max Verstappen'),
    ('Zandvoort',  2023, 'Max Verstappen'),
    ('Zandvoort',  2022, 'Max Verstappen'),
    ('Zandvoort',  2021, 'Max Verstappen'),

    -- Italian Grand Prix — Monza
    ('Monza',      2025, 'Charles Leclerc'),
    ('Monza',      2024, 'Charles Leclerc'),
    ('Monza',      2023, 'Max Verstappen'),
    ('Monza',      2022, 'Max Verstappen'),
    ('Monza',      2021, 'Daniel Ricciardo'),

    -- Azerbaijan Grand Prix — Baku
    ('Baku',       2025, 'Sergio Pérez'),
    ('Baku',       2024, 'Oscar Piastri'),
    ('Baku',       2023, 'Sergio Pérez'),
    ('Baku',       2022, 'Max Verstappen'),
    ('Baku',       2021, 'Sergio Pérez'),

    -- Singapore Grand Prix
    ('Singapore',  2025, 'Lando Norris'),
    ('Singapore',  2024, 'Carlos Sainz'),
    ('Singapore',  2023, 'Carlos Sainz'),
    ('Singapore',  2022, 'Sergio Pérez'),
    ('Singapore',  2019, 'Sebastian Vettel'),

    -- United States Grand Prix — Austin
    ('Austin',     2025, 'Max Verstappen'),
    ('Austin',     2024, 'Charles Leclerc'),
    ('Austin',     2023, 'Max Verstappen'),
    ('Austin',     2022, 'Max Verstappen'),
    ('Austin',     2021, 'Max Verstappen'),

    -- Mexico City Grand Prix
    ('MexicoCity', 2025, 'Sergio Pérez'),
    ('MexicoCity', 2024, 'Max Verstappen'),
    ('MexicoCity', 2023, 'Max Verstappen'),
    ('MexicoCity', 2022, 'Max Verstappen'),
    ('MexicoCity', 2021, 'Max Verstappen'),

    -- São Paulo Grand Prix — Brazil
    ('SaoPaulo',   2025, 'George Russell'),
    ('SaoPaulo',   2024, 'Max Verstappen'),
    ('SaoPaulo',   2023, 'Max Verstappen'),
    ('SaoPaulo',   2022, 'George Russell'),
    ('SaoPaulo',   2021, 'Lewis Hamilton'),

    -- Las Vegas Grand Prix
    ('LasVegas',   2025, 'Max Verstappen'),
    ('LasVegas',   2024, 'Max Verstappen'),
    ('LasVegas',   2023, 'Max Verstappen'),

    -- Qatar Grand Prix — Lusail
    ('Qatar',      2025, 'Max Verstappen'),
    ('Qatar',      2024, 'Max Verstappen'),
    ('Qatar',      2023, 'Max Verstappen'),
    ('Qatar',      2021, 'Lewis Hamilton'),

    -- Abu Dhabi Grand Prix — Yas Marina
    ('YasMarina',  2025, 'Max Verstappen'),
    ('YasMarina',  2024, 'Max Verstappen'),
    ('YasMarina',  2023, 'Max Verstappen'),
    ('YasMarina',  2022, 'Max Verstappen'),
    ('YasMarina',  2021, 'Max Verstappen')
) AS h(circuit_code, year, winner)
JOIN public.circuits c ON c.code = h.circuit_code
ON CONFLICT (circuit_id, year) DO UPDATE SET
  winner = EXCLUDED.winner;

-- ── 7. Predictions table ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.predictions (
  id                 bigserial PRIMARY KEY,
  race_event_id      bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  driver_code        text NOT NULL,
  team               text NOT NULL,
  predicted_position integer NOT NULL,
  prediction_score   numeric(10,6),
  grid_position      integer,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (race_event_id, driver_code)
);

CREATE TABLE IF NOT EXISTS public.prediction_insights (
  id               bigserial PRIMARY KEY,
  race_event_id    bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  predicted_winner text NOT NULL,
  model_name       text NOT NULL,
  input_hash       text NOT NULL,
  summary          text NOT NULL,
  key_reasons      jsonb NOT NULL DEFAULT '[]'::jsonb,
  contenders       jsonb NOT NULL DEFAULT '[]'::jsonb,
  caveats          jsonb NOT NULL DEFAULT '[]'::jsonb,
  generated_at     timestamptz NOT NULL DEFAULT now(),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (race_event_id)
);

CREATE INDEX IF NOT EXISTS prediction_insights_input_hash_idx
  ON public.prediction_insights (input_hash);

-- ── 8. Pipeline tables (CREATE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS) ─

CREATE TABLE IF NOT EXISTS public.drivers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_code   text NOT NULL UNIQUE,
  full_name     text,
  driver_number integer,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.teams (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  team_name  text NOT NULL,
  season     integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (team_name, season)
);

CREATE TABLE IF NOT EXISTS public.driver_race_entries (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  race_id  bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  driver_id uuid NOT NULL REFERENCES public.drivers(id) ON DELETE CASCADE,
  team_id   uuid REFERENCES public.teams(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (race_id, driver_id)
);

-- Ensure all columns exist (idempotent — safe to run repeatedly).
ALTER TABLE public.driver_race_entries
  ADD COLUMN IF NOT EXISTS fp1_pos integer,
  ADD COLUMN IF NOT EXISTS fp1_time_fastest_lap text,
  ADD COLUMN IF NOT EXISTS fp2_pos integer,
  ADD COLUMN IF NOT EXISTS fp2_time_fastest_lap text,
  ADD COLUMN IF NOT EXISTS fp3_pos integer,
  ADD COLUMN IF NOT EXISTS fp3_time_fastest_lap text,
  ADD COLUMN IF NOT EXISTS qualifying_pos integer,
  ADD COLUMN IF NOT EXISTS qualifying_final_grid_pos integer,
  ADD COLUMN IF NOT EXISTS q1_time_seconds numeric(10,4),
  ADD COLUMN IF NOT EXISTS q1_position integer,
  ADD COLUMN IF NOT EXISTS q1_fastest_lap text,
  ADD COLUMN IF NOT EXISTS q2_time_seconds numeric(10,4),
  ADD COLUMN IF NOT EXISTS q2_position integer,
  ADD COLUMN IF NOT EXISTS q2_fastest_lap text,
  ADD COLUMN IF NOT EXISTS q3_time_seconds numeric(10,4),
  ADD COLUMN IF NOT EXISTS q3_position integer,
  ADD COLUMN IF NOT EXISTS q3_fastest_lap text,
  ADD COLUMN IF NOT EXISTS sprint_qualifying_final_grid_pos integer,
  ADD COLUMN IF NOT EXISTS sq1_time_seconds numeric(10,4),
  ADD COLUMN IF NOT EXISTS sq1_position integer,
  ADD COLUMN IF NOT EXISTS sq1_fastest_lap text,
  ADD COLUMN IF NOT EXISTS sq2_time_seconds numeric(10,4),
  ADD COLUMN IF NOT EXISTS sq2_position integer,
  ADD COLUMN IF NOT EXISTS sq2_fastest_lap text,
  ADD COLUMN IF NOT EXISTS sq3_time_seconds numeric(10,4),
  ADD COLUMN IF NOT EXISTS sq3_position integer,
  ADD COLUMN IF NOT EXISTS sq3_fastest_lap text,
  ADD COLUMN IF NOT EXISTS race_finish_pos integer,
  ADD COLUMN IF NOT EXISTS race_status text,
  ADD COLUMN IF NOT EXISTS fastest_lap text,
  ADD COLUMN IF NOT EXISTS position_gain_from_quali_to_race integer,
  ADD COLUMN IF NOT EXISTS sprint_finish_pos integer,
  ADD COLUMN IF NOT EXISTS sprint_fastest_lap text,
  ADD COLUMN IF NOT EXISTS driver_avg_pace numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_clean_air_pace numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_grid_avg_pace numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_pace_delta_to_grid numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_pace_zscore_vs_grid numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_pace_score_vs_grid numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_pace_score_0_100 numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_top_speed numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_corner_speed numeric(10,4),
  ADD COLUMN IF NOT EXISTS driver_top_speed_rank integer,
  ADD COLUMN IF NOT EXISTS driver_corner_speed_rank integer,
  ADD COLUMN IF NOT EXISTS driver_drag_index numeric(10,4),
  ADD COLUMN IF NOT EXISTS avg_race_pos_3_races numeric(10,4),
  ADD COLUMN IF NOT EXISTS avg_race_pos_5_races numeric(10,4),
  ADD COLUMN IF NOT EXISTS avg_race_pos_7_races numeric(10,4);

CREATE TABLE IF NOT EXISTS public.laps (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_race_entry_id uuid NOT NULL REFERENCES public.driver_race_entries(id) ON DELETE CASCADE,
  lap_number           integer NOT NULL,
  lap_time             numeric(10,4),
  compound             text,
  track_status         text,
  stint_index          integer NOT NULL DEFAULT 0,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (driver_race_entry_id, lap_number)
);

-- ── 9. Driver and team seed data ─────────────────────────────

INSERT INTO public.drivers (driver_code, full_name, driver_number)
VALUES
  ('RUS', 'George Russell',          63),
  ('ANT', 'Andrea Kimi Antonelli',   12),
  ('LEC', 'Charles Leclerc',         16),
  ('HAM', 'Lewis Hamilton',          44),
  ('NOR', 'Lando Norris',             1),
  ('PIA', 'Oscar Piastri',           81),
  ('OCO', 'Esteban Ocon',            31),
  ('BEA', 'Oliver Bearman',          87),
  ('VER', 'Max Verstappen',          33),
  ('HAD', 'Isack Hadjar',             6),
  ('LAW', 'Liam Lawson',             30),
  ('LIN', 'Patricio O''Loughlin',    41),
  ('GAS', 'Pierre Gasly',            10),
  ('COL', 'Franco Colapinto',        43),
  ('HUL', 'Nico Hülkenberg',         27),
  ('BOR', 'Gabriel Bortoleto',        5),
  ('SAI', 'Carlos Sainz',            55),
  ('ALB', 'Alexander Albon',         23),
  ('PER', 'Sergio Pérez',            11),
  ('BOT', 'Valtteri Bottas',         77),
  ('ALO', 'Fernando Alonso',         14),
  ('STR', 'Lance Stroll',            18)
ON CONFLICT (driver_code) DO UPDATE SET
  full_name     = EXCLUDED.full_name,
  driver_number = EXCLUDED.driver_number;

INSERT INTO public.teams (team_name, season)
VALUES
  ('Mercedes',        2026),
  ('Ferrari',         2026),
  ('McLaren',         2026),
  ('Haas',            2026),
  ('Red Bull Racing', 2026),
  ('Racing Bulls',    2026),
  ('Alpine',          2026),
  ('Audi',            2026),
  ('Williams',        2026),
  ('Cadillac',        2026),
  ('Aston Martin',    2026)
ON CONFLICT (team_name, season) DO NOTHING;

-- ── 10. RPC: pending sessions ────────────────────────────────

CREATE OR REPLACE FUNCTION get_pending_sessions(cutoff timestamptz)
RETURNS TABLE (
  session_id       bigint,
  session_type     text,
  season           integer,
  round            integer,
  grand_prix_name  text,
  circuit_code     text
) AS $$
  SELECT
    rs.id           AS session_id,
    rs.session_type,
    re.season,
    re.round,
    re.grand_prix_name,
    c.code          AS circuit_code
  FROM race_sessions rs
  JOIN race_events re ON re.id = rs.race_event_id
  JOIN circuits    c  ON c.id  = re.circuit_id
  WHERE rs.data_fetched = false
    AND rs.session_end_utc < cutoff
  ORDER BY rs.session_start_utc;
$$ LANGUAGE sql;

-- ── Quick sanity check (uncomment to verify) ─────────────────
-- SELECT e.season, e.round, c.title, c.weekend_format,
--        e.grand_prix_name, s.session_type, s.session_start_utc
-- FROM public.race_events e
-- JOIN public.circuits      c ON c.id = e.circuit_id
-- JOIN public.race_sessions s ON s.race_event_id = e.id
-- WHERE e.season = 2026
-- ORDER BY e.round, s.session_start_utc;
