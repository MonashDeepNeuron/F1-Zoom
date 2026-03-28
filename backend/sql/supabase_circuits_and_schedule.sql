-- Run this in Supabase SQL Editor (Postgres).
-- It creates/updates:
-- 1) circuits metadata table (with weekend_format)
-- 2) race_events table (one row per GP weekend)
-- 3) race_sessions table (session start time stored as UTC timestamptz)

create table if not exists public.circuits (
  id bigserial primary key,
  code text not null unique,
  file_slug text not null unique,
  title text not null,
  subtitle text not null,
  flag text not null,
  timezone_name text not null,
  weekend_format text not null check (weekend_format in ('normal', 'sprint')),
  length_km numeric(6,3) not null,
  laps integer not null,
  corners integer not null,
  distance_km numeric(7,3) not null,
  created_at timestamptz not null default now()
);

create table if not exists public.race_events (
  id bigserial primary key,
  season integer not null,
  round integer not null,
  circuit_id bigint not null references public.circuits(id) on delete restrict,
  grand_prix_name text not null,
  created_at timestamptz not null default now(),
  unique (season, round),
  unique (season, circuit_id)
);

create table if not exists public.race_sessions (
  id bigserial primary key,
  race_event_id bigint not null references public.race_events(id) on delete cascade,
  session_type text not null constraint race_sessions_session_type_check check (
    session_type in (
      'practice_1',
      'practice_2',
      'practice_3',
      'sprint_qualifying',
      'qualifying',
      'sprint',
      'race'
    )
  ),
  session_start_utc timestamptz not null,
  session_end_utc timestamptz not null,
  created_at timestamptz not null default now(),
  unique (race_event_id, session_type)
);

-- Backward-compatible upgrades for already-created tables.
alter table public.circuits
  add column if not exists timezone_name text;

update public.circuits
set timezone_name = case code
  when 'Melbourne' then 'Australia/Melbourne'
  when 'Shanghai' then 'Asia/Shanghai'
  when 'Suzuka' then 'Asia/Tokyo'
  when 'Sakhir' then 'Asia/Bahrain'
  when 'Jeddah' then 'Asia/Riyadh'
  when 'Miami' then 'America/New_York'
  when 'Montreal' then 'America/Toronto'
  when 'Monaco' then 'Europe/Monaco'
  when 'Catalunya' then 'Europe/Madrid'
  when 'Austria' then 'Europe/Vienna'
  when 'Silverstone' then 'Europe/London'
  when 'Spa' then 'Europe/Brussels'
  when 'Hungary' then 'Europe/Budapest'
  when 'Zandvoort' then 'Europe/Amsterdam'
  when 'Monza' then 'Europe/Rome'
  when 'Madrid' then 'Europe/Madrid'
  when 'Baku' then 'Asia/Baku'
  when 'Singapore' then 'Asia/Singapore'
  when 'Austin' then 'America/Chicago'
  when 'MexicoCity' then 'America/Mexico_City'
  when 'SaoPaulo' then 'America/Sao_Paulo'
  when 'LasVegas' then 'America/Los_Angeles'
  when 'Qatar' then 'Asia/Qatar'
  when 'YasMarina' then 'Asia/Dubai'
  else timezone_name
end
where timezone_name is null;

alter table public.circuits
  add column if not exists weekend_format text;

update public.circuits
set weekend_format = 'normal'
where weekend_format is null;

alter table public.circuits
  drop constraint if exists circuits_weekend_format_check;

alter table public.circuits
  add constraint circuits_weekend_format_check check (weekend_format in ('normal', 'sprint'));

alter table public.circuits
  alter column weekend_format set not null;

alter table public.circuits
  alter column timezone_name set not null;

delete from public.race_sessions
where session_type = 'sprint_shootout';

-- Migrate separate date/time columns → single timestamptz (idempotent).
alter table public.race_sessions
  add column if not exists session_start_utc timestamptz;

alter table public.race_sessions
  add column if not exists session_end_utc timestamptz;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'race_sessions'
      and column_name = 'session_date_aest'
  ) and exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'race_sessions'
      and column_name = 'session_time_aest'
  ) then
    execute $sql$
      update public.race_sessions rs
      set session_start_utc =
        (rs.session_date_aest + rs.session_time_aest)::timestamp
        at time zone coalesce(c.timezone_name, 'Australia/Melbourne')
      from public.race_events re
      join public.circuits c on c.id = re.circuit_id
      where rs.race_event_id = re.id
        and rs.session_start_utc is null
        and rs.session_date_aest is not null
        and rs.session_time_aest is not null
    $sql$;
  end if;
end $$;

update public.race_sessions
set session_end_utc =
  session_start_utc +
    case session_type
      when 'race' then interval '2 hours'
      else interval '1 hour'
    end
where session_start_utc is not null
  and session_end_utc is null;

alter table public.race_sessions
  drop column if exists session_date_aest;

alter table public.race_sessions
  drop column if exists session_time_aest;

alter table public.race_sessions
  drop constraint if exists race_sessions_session_type_check;

alter table public.race_sessions
  add constraint race_sessions_session_type_check check (
    session_type in (
      'practice_1',
      'practice_2',
      'practice_3',
      'sprint_qualifying',
      'qualifying',
      'sprint',
      'race'
    )
  );

-- 2026 circuits (all rounds in screenshot), with weekend format.
insert into public.circuits (
  code, file_slug, title, subtitle, flag, timezone_name, weekend_format, length_km, laps, corners, distance_km
)
values
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
on conflict (code) do update set
  file_slug = excluded.file_slug,
  title = excluded.title,
  subtitle = excluded.subtitle,
  flag = excluded.flag,
  timezone_name = excluded.timezone_name,
  weekend_format = excluded.weekend_format,
  length_km = excluded.length_km,
  laps = excluded.laps,
  corners = excluded.corners,
  distance_km = excluded.distance_km;

-- Re-seed 2026 events from scratch so the schedule is exact and idempotent.
delete from public.race_events
where season = 2026;

insert into public.race_events (season, round, circuit_id, grand_prix_name)
select
  2026,
  r.round,
  c.id,
  r.grand_prix_name
from (
  values
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
) as r(round, circuit_code, grand_prix_name)
join public.circuits c on c.code = r.circuit_code;

-- Insert all 2026 session times as UTC using each circuit's local timezone.
insert into public.race_sessions (race_event_id, session_type, session_start_utc, session_end_utc)
select
  e.id,
  s.session_type,
  s.session_start_local::timestamp at time zone c.timezone_name,
  (s.session_start_local::timestamp at time zone c.timezone_name) +
    case s.session_type
      when 'race' then interval '2 hours'
      else interval '1 hour'
    end
from (
  values
    (1,  'practice_1',         '2026-03-06 12:30'),
    (1,  'practice_2',         '2026-03-06 16:00'),
    (1,  'practice_3',         '2026-03-07 12:30'),
    (1,  'qualifying',         '2026-03-07 16:00'),
    (1,  'race',               '2026-03-08 15:00'),
    (2,  'practice_1',         '2026-03-13 14:30'),
    (2,  'sprint_qualifying',  '2026-03-13 18:30'),
    (2,  'sprint',             '2026-03-14 14:00'),
    (2,  'qualifying',         '2026-03-14 18:00'),
    (2,  'race',               '2026-03-15 18:00'),
    (3,  'practice_1',         '2026-03-27 13:30'),
    (3,  'practice_2',         '2026-03-27 17:00'),
    (3,  'practice_3',         '2026-03-28 13:30'),
    (3,  'qualifying',         '2026-03-28 17:00'),
    (3,  'race',               '2026-03-29 16:00'),
    (4,  'practice_1',         '2026-04-10 21:30'),
    (4,  'practice_2',         '2026-04-11 01:00'),
    (4,  'practice_3',         '2026-04-11 22:30'),
    (4,  'qualifying',         '2026-04-12 02:00'),
    (4,  'race',               '2026-04-13 01:00'),
    (5,  'practice_1',         '2026-04-17 23:30'),
    (5,  'practice_2',         '2026-04-18 03:00'),
    (5,  'practice_3',         '2026-04-18 23:30'),
    (5,  'qualifying',         '2026-04-19 03:00'),
    (5,  'race',               '2026-04-20 03:00'),
    (6,  'practice_1',         '2026-05-02 02:30'),
    (6,  'sprint_qualifying',  '2026-05-02 06:30'),
    (6,  'sprint',             '2026-05-03 02:00'),
    (6,  'qualifying',         '2026-05-03 06:00'),
    (6,  'race',               '2026-05-04 06:00'),
    (7,  'practice_1',         '2026-05-23 02:30'),
    (7,  'sprint_qualifying',  '2026-05-23 06:30'),
    (7,  'sprint',             '2026-05-24 02:00'),
    (7,  'qualifying',         '2026-05-24 06:00'),
    (7,  'race',               '2026-05-25 06:00'),
    (8,  'practice_1',         '2026-06-05 21:30'),
    (8,  'practice_2',         '2026-06-06 01:00'),
    (8,  'practice_3',         '2026-06-06 20:30'),
    (8,  'qualifying',         '2026-06-07 00:00'),
    (8,  'race',               '2026-06-07 23:00'),
    (9,  'practice_1',         '2026-06-12 21:30'),
    (9,  'practice_2',         '2026-06-13 01:00'),
    (9,  'practice_3',         '2026-06-13 20:30'),
    (9,  'qualifying',         '2026-06-14 00:00'),
    (9,  'race',               '2026-06-14 23:00'),
    (10, 'practice_1',         '2026-06-26 21:30'),
    (10, 'practice_2',         '2026-06-27 01:00'),
    (10, 'practice_3',         '2026-06-27 20:30'),
    (10, 'qualifying',         '2026-06-28 00:00'),
    (10, 'race',               '2026-06-28 23:00'),
    (11, 'practice_1',         '2026-07-03 21:30'),
    (11, 'sprint_qualifying',  '2026-07-04 01:30'),
    (11, 'sprint',             '2026-07-04 21:00'),
    (11, 'qualifying',         '2026-07-05 01:00'),
    (11, 'race',               '2026-07-06 00:00'),
    (12, 'practice_1',         '2026-07-17 21:30'),
    (12, 'practice_2',         '2026-07-18 01:00'),
    (12, 'practice_3',         '2026-07-18 20:30'),
    (12, 'qualifying',         '2026-07-19 00:00'),
    (12, 'race',               '2026-07-19 23:00'),
    (13, 'practice_1',         '2026-07-24 21:30'),
    (13, 'practice_2',         '2026-07-25 01:00'),
    (13, 'practice_3',         '2026-07-25 20:30'),
    (13, 'qualifying',         '2026-07-26 00:00'),
    (13, 'race',               '2026-07-26 23:00'),
    (14, 'practice_1',         '2026-08-21 20:30'),
    (14, 'sprint_qualifying',  '2026-08-22 00:30'),
    (14, 'sprint',             '2026-08-22 20:00'),
    (14, 'qualifying',         '2026-08-23 00:00'),
    (14, 'race',               '2026-08-23 23:00'),
    (15, 'practice_1',         '2026-09-04 20:30'),
    (15, 'practice_2',         '2026-09-05 00:00'),
    (15, 'practice_3',         '2026-09-05 20:30'),
    (15, 'qualifying',         '2026-09-06 00:00'),
    (15, 'race',               '2026-09-06 23:00'),
    (16, 'practice_1',         '2026-09-11 21:30'),
    (16, 'practice_2',         '2026-09-12 01:00'),
    (16, 'practice_3',         '2026-09-12 20:30'),
    (16, 'qualifying',         '2026-09-13 00:00'),
    (16, 'race',               '2026-09-13 23:00'),
    (17, 'practice_1',         '2026-09-24 18:30'),
    (17, 'practice_2',         '2026-09-24 22:00'),
    (17, 'practice_3',         '2026-09-25 18:30'),
    (17, 'qualifying',         '2026-09-25 22:00'),
    (17, 'race',               '2026-09-26 21:00'),
    (18, 'practice_1',         '2026-10-09 19:30'),
    (18, 'sprint_qualifying',  '2026-10-09 23:30'),
    (18, 'sprint',             '2026-10-10 20:00'),
    (18, 'qualifying',         '2026-10-11 00:00'),
    (18, 'race',               '2026-10-11 23:00'),
    (19, 'practice_1',         '2026-10-24 04:30'),
    (19, 'practice_2',         '2026-10-24 08:00'),
    (19, 'practice_3',         '2026-10-25 04:30'),
    (19, 'qualifying',         '2026-10-25 08:00'),
    (19, 'race',               '2026-10-26 07:00'),
    (20, 'practice_1',         '2026-10-31 05:30'),
    (20, 'practice_2',         '2026-10-31 09:00'),
    (20, 'practice_3',         '2026-11-01 04:30'),
    (20, 'qualifying',         '2026-11-01 08:00'),
    (20, 'race',               '2026-11-02 07:00'),
    (21, 'practice_1',         '2026-11-07 02:30'),
    (21, 'practice_2',         '2026-11-07 06:00'),
    (21, 'practice_3',         '2026-11-08 01:30'),
    (21, 'qualifying',         '2026-11-08 05:00'),
    (21, 'race',               '2026-11-09 04:00'),
    (22, 'practice_1',         '2026-11-20 11:30'),
    (22, 'practice_2',         '2026-11-20 15:00'),
    (22, 'practice_3',         '2026-11-21 11:30'),
    (22, 'qualifying',         '2026-11-21 15:00'),
    (22, 'race',               '2026-11-22 15:00'),
    (23, 'practice_1',         '2026-11-28 00:30'),
    (23, 'practice_2',         '2026-11-28 04:00'),
    (23, 'practice_3',         '2026-11-29 01:30'),
    (23, 'qualifying',         '2026-11-29 05:00'),
    (23, 'race',               '2026-11-30 03:00'),
    (24, 'practice_1',         '2026-12-04 20:30'),
    (24, 'practice_2',         '2026-12-05 00:00'),
    (24, 'practice_3',         '2026-12-05 21:30'),
    (24, 'qualifying',         '2026-12-06 01:00'),
    (24, 'race',               '2026-12-07 00:00')
) as s(round, session_type, session_start_local)
join public.race_events e
  on e.season = 2026
 and e.round = s.round
join public.circuits c
  on c.id = e.circuit_id;

-- ── Track history (past race winners per circuit) ──────────────────────

drop table if exists public.track_history;

create table public.track_history (
  id bigserial primary key,
  circuit_id bigint not null references public.circuits(id) on delete restrict,
  year integer not null,
  winner text not null,
  created_at timestamptz not null default now(),
  unique (circuit_id, year)
);

delete from public.track_history;

insert into public.track_history (circuit_id, year, winner)
select c.id, h.year, h.winner
from (
  values
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
) as h(circuit_code, year, winner)
join public.circuits c on c.code = h.circuit_code;

-- ── data_fetched flag on race_sessions ────────────────────────────────
alter table public.race_sessions
  add column if not exists data_fetched boolean not null default false;

-- ── RPC: find sessions that ended but haven't been fetched yet ────────
CREATE OR REPLACE FUNCTION get_pending_sessions(cutoff timestamptz)
RETURNS TABLE (
  session_id bigint,
  session_type text,
  season integer,
  round integer,
  grand_prix_name text,
  circuit_code text
) AS $$
  SELECT
    rs.id AS session_id,
    rs.session_type,
    re.season,
    re.round,
    re.grand_prix_name,
    c.code AS circuit_code
  FROM race_sessions rs
  JOIN race_events re ON re.id = rs.race_event_id
  JOIN circuits c ON c.id = re.circuit_id
  WHERE rs.data_fetched = false
    AND rs.session_end_utc < cutoff
  ORDER BY rs.session_start_utc;
$$ LANGUAGE sql;

-- ── Predictions table ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.predictions (
  id bigserial PRIMARY KEY,
  race_event_id bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  driver_code text NOT NULL,
  team text NOT NULL,
  predicted_position integer NOT NULL,
  prediction_score numeric(10, 6),
  grid_position integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (race_event_id, driver_code)
);

-- ── Pipeline tables (drop + recreate to ensure correct types) ────────
-- Laps depends on driver_race_entries, so drop in reverse dependency order.
DROP TABLE IF EXISTS public.laps CASCADE;
DROP TABLE IF EXISTS public.driver_race_entries CASCADE;
DROP TABLE IF EXISTS public.teams CASCADE;
DROP TABLE IF EXISTS public.drivers CASCADE;

-- ── Drivers table ─────────────────────────────────────────────────────
CREATE TABLE public.drivers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_code text NOT NULL UNIQUE,
  full_name text,
  driver_number integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── Teams table ──────────────────────────────────────────────────────
CREATE TABLE public.teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  team_name text NOT NULL,
  season integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (team_name, season)
);

-- ── Driver race entries (one row per driver per race weekend) ────────
CREATE TABLE public.driver_race_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  race_id bigint NOT NULL REFERENCES public.race_events(id) ON DELETE CASCADE,
  driver_id uuid NOT NULL REFERENCES public.drivers(id) ON DELETE CASCADE,
  team_id uuid REFERENCES public.teams(id) ON DELETE SET NULL,

  -- Practice positions and fastest laps
  fp1_pos integer,
  fp1_time_fastest_lap text,
  fp2_pos integer,
  fp2_time_fastest_lap text,
  fp3_pos integer,
  fp3_time_fastest_lap text,

  -- Qualifying
  qualifying_pos integer,
  qualifying_final_grid_pos integer,
  q1_time_seconds numeric(10, 4),
  q1_position integer,
  q1_fastest_lap text,
  q2_time_seconds numeric(10, 4),
  q2_position integer,
  q2_fastest_lap text,
  q3_time_seconds numeric(10, 4),
  q3_position integer,
  q3_fastest_lap text,

  -- Sprint qualifying
  sprint_qualifying_final_grid_pos integer,
  sq1_time_seconds numeric(10, 4),
  sq1_position integer,
  sq1_fastest_lap text,
  sq2_time_seconds numeric(10, 4),
  sq2_position integer,
  sq2_fastest_lap text,
  sq3_time_seconds numeric(10, 4),
  sq3_position integer,
  sq3_fastest_lap text,

  -- Race result
  race_finish_pos integer,
  race_status text,
  fastest_lap text,
  position_gain_from_quali_to_race integer,

  -- Sprint result
  sprint_finish_pos integer,
  sprint_fastest_lap text,

  -- Derived pace metrics (populated by analysis pipeline)
  driver_avg_pace numeric(10, 4),
  driver_clean_air_pace numeric(10, 4),
  driver_grid_avg_pace numeric(10, 4),
  driver_pace_delta_to_grid numeric(10, 4),
  driver_pace_zscore_vs_grid numeric(10, 4),
  driver_pace_score_vs_grid numeric(10, 4),
  driver_pace_score_0_100 numeric(10, 4),
  driver_top_speed numeric(10, 4),
  driver_corner_speed numeric(10, 4),
  driver_top_speed_rank integer,
  driver_corner_speed_rank integer,
  driver_drag_index numeric(10, 4),
  avg_race_pos_3_races numeric(10, 4),
  avg_race_pos_5_races numeric(10, 4),
  avg_race_pos_7_races numeric(10, 4),

  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (race_id, driver_id)
);

-- ── Laps (lap-by-lap data per driver per race) ──────────────────────
CREATE TABLE public.laps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_race_entry_id uuid NOT NULL REFERENCES public.driver_race_entries(id) ON DELETE CASCADE,
  lap_number integer NOT NULL,
  lap_time numeric(10, 4),
  compound text,
  track_status text,
  stint_index integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (driver_race_entry_id, lap_number)
);

-- ── Seed 2026 drivers ────────────────────────────────────────────────
INSERT INTO public.drivers (driver_code, full_name, driver_number)
VALUES
  ('RUS', 'George Russell',     63),
  ('ANT', 'Andrea Kimi Antonelli', 12),
  ('LEC', 'Charles Leclerc',    16),
  ('HAM', 'Lewis Hamilton',     44),
  ('NOR', 'Lando Norris',       1),
  ('PIA', 'Oscar Piastri',      81),
  ('OCO', 'Esteban Ocon',       31),
  ('BEA', 'Oliver Bearman',     87),
  ('VER', 'Max Verstappen',     33),
  ('HAD', 'Isack Hadjar',       6),
  ('LAW', 'Liam Lawson',        30),
  ('LIN', 'Patricio O''Loughlin', 41),
  ('GAS', 'Pierre Gasly',       10),
  ('COL', 'Franco Colapinto',   43),
  ('HUL', 'Nico Hülkenberg',    27),
  ('BOR', 'Gabriel Bortoleto',  5),
  ('SAI', 'Carlos Sainz',       55),
  ('ALB', 'Alexander Albon',    23),
  ('PER', 'Sergio Pérez',       11),
  ('BOT', 'Valtteri Bottas',    77),
  ('ALO', 'Fernando Alonso',    14),
  ('STR', 'Lance Stroll',       18)
ON CONFLICT (driver_code) DO UPDATE SET
  full_name = EXCLUDED.full_name,
  driver_number = EXCLUDED.driver_number;

-- ── Seed 2026 teams ─────────────────────────────────────────────────
INSERT INTO public.teams (team_name, season)
VALUES
  ('Mercedes',           2026),
  ('Ferrari',            2026),
  ('McLaren',            2026),
  ('Haas',               2026),
  ('Red Bull Racing',    2026),
  ('Racing Bulls',       2026),
  ('Alpine',             2026),
  ('Audi',               2026),
  ('Williams',           2026),
  ('Cadillac',           2026),
  ('Aston Martin',       2026)
ON CONFLICT (team_name, season) DO NOTHING;

-- Quick check.
-- select
--   e.season,
--   e.round,
--   c.title as circuit,
--   c.weekend_format,
--   e.grand_prix_name,
--   s.session_type,
--   s.session_start_utc
-- from public.race_events e
-- join public.circuits c on c.id = e.circuit_id
-- join public.race_sessions s on s.race_event_id = e.id
-- where e.season = 2026
-- order by e.round, s.session_start_utc;
