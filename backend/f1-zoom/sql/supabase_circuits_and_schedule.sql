-- Run this in Supabase SQL Editor (Postgres).
-- It creates/updates:
-- 1) circuits metadata table (with weekend_format)
-- 2) race_events table (one row per GP weekend)
-- 3) race_sessions table (AEST date/time per session)

create table if not exists public.circuits (
  id bigserial primary key,
  code text not null unique,
  file_slug text not null unique,
  title text not null,
  subtitle text not null,
  flag text not null,
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
  session_date_aest date,
  session_time_aest time without time zone,
  created_at timestamptz not null default now(),
  unique (race_event_id, session_type)
);

-- Backward-compatible upgrades for already-created tables.
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

delete from public.race_sessions
where session_type = 'sprint_shootout';

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
  code, file_slug, title, subtitle, flag, weekend_format, length_km, laps, corners, distance_km
)
values
  ('Melbourne',  'Melbourne',  'MELBOURNE',  'ALBERT PARK CIRCUIT',                 'AU', 'normal', 5.278, 58, 16, 306.124),
  ('Shanghai',   'Shanghai',   'SHANGHAI',   'SHANGHAI INTERNATIONAL CIRCUIT',      'CN', 'sprint', 5.451, 56, 16, 305.066),
  ('Suzuka',     'Suzuka',     'SUZUKA',     'SUZUKA INTERNATIONAL RACING COURSE',  'JP', 'normal', 5.807, 53, 18, 307.471),
  ('Sakhir',     'Sakhir',     'SAKHIR',     'BAHRAIN INTERNATIONAL CIRCUIT',       'BH', 'normal', 5.412, 57, 15, 308.238),
  ('Jeddah',     'Jeddah',     'JEDDAH',     'JEDDAH CORNICHE CIRCUIT',             'SA', 'normal', 6.174, 50, 27, 308.450),
  ('Miami',      'Miami',      'MIAMI',      'MIAMI INTERNATIONAL AUTODROME',       'US', 'sprint', 5.412, 57, 19, 308.326),
  ('Montreal',   'Montreal',   'MONTREAL',   'CIRCUIT GILLES-VILLENEUVE',           'CA', 'sprint', 4.361, 70, 14, 305.270),
  ('Monaco',     'Monaco',     'MONACO',     'CIRCUIT DE MONACO',                    'MC', 'normal', 3.337, 78, 19, 260.286),
  ('Catalunya',  'Catalunya',  'BARCELONA',  'CIRCUIT DE BARCELONA-CATALUNYA',      'ES', 'normal', 4.657, 66, 16, 307.236),
  ('Austria',    'Austria',    'AUSTRIA',    'RED BULL RING',                        'AT', 'normal', 4.318, 71, 10, 306.452),
  ('Silverstone','Silverstone','SILVERSTONE','SILVERSTONE CIRCUIT',                  'GB', 'sprint', 5.891, 52, 18, 306.198),
  ('Spa',        'Spa',        'SPA',        'CIRCUIT DE SPA-FRANCORCHAMPS',         'BE', 'normal', 7.004, 44, 19, 308.052),
  ('Hungary',    'Hungary',    'HUNGARY',    'HUNGARORING',                           'HU', 'normal', 4.381, 70, 14, 306.630),
  ('Zandvoort',  'Zandvoort',  'ZANDVOORT',  'CIRCUIT ZANDVOORT',                     'NL', 'sprint', 4.259, 72, 14, 306.587),
  ('Monza',      'Monza',      'MONZA',      'AUTODROMO NAZIONALE MONZA',            'IT', 'normal', 5.793, 53, 11, 306.720),
  ('Madrid',     'Madrid',     'MADRID',     'MADRING',                               'ES', 'normal', 5.470, 56, 22, 306.320),
  ('Baku',       'Baku',       'BAKU',       'BAKU CITY CIRCUIT',                     'AZ', 'normal', 6.003, 51, 20, 306.049),
  ('Singapore',  'Singapore',  'SINGAPORE',  'MARINA BAY STREET CIRCUIT',             'SG', 'sprint', 4.940, 62, 19, 306.143),
  ('Austin',     'Austin',     'AUSTIN',     'CIRCUIT OF THE AMERICAS',              'US', 'normal', 5.513, 56, 20, 308.405),
  ('MexicoCity', 'MexicoCity', 'MEXICO CITY','AUTODROMO HERMANOS RODRIGUEZ',         'MX', 'normal', 4.304, 71, 17, 305.354),
  ('SaoPaulo',   'SaoPaulo',   'SAO PAULO',  'AUTODROMO JOSE CARLOS PACE',           'BR', 'normal', 4.309, 71, 15, 305.879),
  ('LasVegas',   'LasVegas',   'LAS VEGAS',  'LAS VEGAS STRIP CIRCUIT',              'US', 'normal', 6.201, 50, 17, 309.958),
  ('Qatar',      'Qatar',      'QATAR',      'LUSAIL INTERNATIONAL CIRCUIT',         'QA', 'normal', 5.419, 57, 16, 308.611),
  ('YasMarina',  'YasMarina',  'YAS MARINA', 'YAS MARINA CIRCUIT',                    'AE', 'normal', 5.281, 58, 16, 306.183)
on conflict (code) do update set
  file_slug = excluded.file_slug,
  title = excluded.title,
  subtitle = excluded.subtitle,
  flag = excluded.flag,
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

-- Insert all 2026 AEST session times exactly as provided.
insert into public.race_sessions (race_event_id, session_type, session_date_aest, session_time_aest)
select
  e.id,
  s.session_type,
  s.session_date_aest,
  s.session_time_aest
from (
  values
    (1,  'practice_1',         '2026-03-06'::date, '12:30'::time),
    (1,  'practice_2',         '2026-03-06'::date, '16:00'::time),
    (1,  'practice_3',         '2026-03-07'::date, '12:30'::time),
    (1,  'qualifying',         '2026-03-07'::date, '16:00'::time),
    (1,  'race',               '2026-03-08'::date, '15:00'::time),
    (2,  'practice_1',         '2026-03-13'::date, '14:30'::time),
    (2,  'sprint_qualifying',  '2026-03-13'::date, '18:30'::time),
    (2,  'sprint',             '2026-03-14'::date, '14:00'::time),
    (2,  'qualifying',         '2026-03-14'::date, '18:00'::time),
    (2,  'race',               '2026-03-15'::date, '18:00'::time),
    (3,  'practice_1',         '2026-03-27'::date, '13:30'::time),
    (3,  'practice_2',         '2026-03-27'::date, '17:00'::time),
    (3,  'practice_3',         '2026-03-28'::date, '13:30'::time),
    (3,  'qualifying',         '2026-03-28'::date, '17:00'::time),
    (3,  'race',               '2026-03-29'::date, '16:00'::time),
    (4,  'practice_1',         '2026-04-10'::date, '21:30'::time),
    (4,  'practice_2',         '2026-04-11'::date, '01:00'::time),
    (4,  'practice_3',         '2026-04-11'::date, '22:30'::time),
    (4,  'qualifying',         '2026-04-12'::date, '02:00'::time),
    (4,  'race',               '2026-04-13'::date, '01:00'::time),
    (5,  'practice_1',         '2026-04-17'::date, '23:30'::time),
    (5,  'practice_2',         '2026-04-18'::date, '03:00'::time),
    (5,  'practice_3',         '2026-04-18'::date, '23:30'::time),
    (5,  'qualifying',         '2026-04-19'::date, '03:00'::time),
    (5,  'race',               '2026-04-20'::date, '03:00'::time),
    (6,  'practice_1',         '2026-05-02'::date, '02:30'::time),
    (6,  'sprint_qualifying',  '2026-05-02'::date, '06:30'::time),
    (6,  'sprint',             '2026-05-03'::date, '02:00'::time),
    (6,  'qualifying',         '2026-05-03'::date, '06:00'::time),
    (6,  'race',               '2026-05-04'::date, '06:00'::time),
    (7,  'practice_1',         '2026-05-23'::date, '02:30'::time),
    (7,  'sprint_qualifying',  '2026-05-23'::date, '06:30'::time),
    (7,  'sprint',             '2026-05-24'::date, '02:00'::time),
    (7,  'qualifying',         '2026-05-24'::date, '06:00'::time),
    (7,  'race',               '2026-05-25'::date, '06:00'::time),
    (8,  'practice_1',         '2026-06-05'::date, '21:30'::time),
    (8,  'practice_2',         '2026-06-06'::date, '01:00'::time),
    (8,  'practice_3',         '2026-06-06'::date, '20:30'::time),
    (8,  'qualifying',         '2026-06-07'::date, '00:00'::time),
    (8,  'race',               '2026-06-07'::date, '23:00'::time),
    (9,  'practice_1',         '2026-06-12'::date, '21:30'::time),
    (9,  'practice_2',         '2026-06-13'::date, '01:00'::time),
    (9,  'practice_3',         '2026-06-13'::date, '20:30'::time),
    (9,  'qualifying',         '2026-06-14'::date, '00:00'::time),
    (9,  'race',               '2026-06-14'::date, '23:00'::time),
    (10, 'practice_1',         '2026-06-26'::date, '21:30'::time),
    (10, 'practice_2',         '2026-06-27'::date, '01:00'::time),
    (10, 'practice_3',         '2026-06-27'::date, '20:30'::time),
    (10, 'qualifying',         '2026-06-28'::date, '00:00'::time),
    (10, 'race',               '2026-06-28'::date, '23:00'::time),
    (11, 'practice_1',         '2026-07-03'::date, '21:30'::time),
    (11, 'sprint_qualifying',  '2026-07-04'::date, '01:30'::time),
    (11, 'sprint',             '2026-07-04'::date, '21:00'::time),
    (11, 'qualifying',         '2026-07-05'::date, '01:00'::time),
    (11, 'race',               '2026-07-06'::date, '00:00'::time),
    (12, 'practice_1',         '2026-07-17'::date, '21:30'::time),
    (12, 'practice_2',         '2026-07-18'::date, '01:00'::time),
    (12, 'practice_3',         '2026-07-18'::date, '20:30'::time),
    (12, 'qualifying',         '2026-07-19'::date, '00:00'::time),
    (12, 'race',               '2026-07-19'::date, '23:00'::time),
    (13, 'practice_1',         '2026-07-24'::date, '21:30'::time),
    (13, 'practice_2',         '2026-07-25'::date, '01:00'::time),
    (13, 'practice_3',         '2026-07-25'::date, '20:30'::time),
    (13, 'qualifying',         '2026-07-26'::date, '00:00'::time),
    (13, 'race',               '2026-07-26'::date, '23:00'::time),
    (14, 'practice_1',         '2026-08-21'::date, '20:30'::time),
    (14, 'sprint_qualifying',  '2026-08-22'::date, '00:30'::time),
    (14, 'sprint',             '2026-08-22'::date, '20:00'::time),
    (14, 'qualifying',         '2026-08-23'::date, '00:00'::time),
    (14, 'race',               '2026-08-23'::date, '23:00'::time),
    (15, 'practice_1',         '2026-09-04'::date, '20:30'::time),
    (15, 'practice_2',         '2026-09-05'::date, '00:00'::time),
    (15, 'practice_3',         '2026-09-05'::date, '20:30'::time),
    (15, 'qualifying',         '2026-09-06'::date, '00:00'::time),
    (15, 'race',               '2026-09-06'::date, '23:00'::time),
    (16, 'practice_1',         '2026-09-11'::date, '21:30'::time),
    (16, 'practice_2',         '2026-09-12'::date, '01:00'::time),
    (16, 'practice_3',         '2026-09-12'::date, '20:30'::time),
    (16, 'qualifying',         '2026-09-13'::date, '00:00'::time),
    (16, 'race',               '2026-09-13'::date, '23:00'::time),
    (17, 'practice_1',         '2026-09-24'::date, '18:30'::time),
    (17, 'practice_2',         '2026-09-24'::date, '22:00'::time),
    (17, 'practice_3',         '2026-09-25'::date, '18:30'::time),
    (17, 'qualifying',         '2026-09-25'::date, '22:00'::time),
    (17, 'race',               '2026-09-26'::date, '21:00'::time),
    (18, 'practice_1',         '2026-10-09'::date, '19:30'::time),
    (18, 'sprint_qualifying',  '2026-10-09'::date, '23:30'::time),
    (18, 'sprint',             '2026-10-10'::date, '20:00'::time),
    (18, 'qualifying',         '2026-10-11'::date, '00:00'::time),
    (18, 'race',               '2026-10-11'::date, '23:00'::time),
    (19, 'practice_1',         '2026-10-24'::date, '04:30'::time),
    (19, 'practice_2',         '2026-10-24'::date, '08:00'::time),
    (19, 'practice_3',         '2026-10-25'::date, '04:30'::time),
    (19, 'qualifying',         '2026-10-25'::date, '08:00'::time),
    (19, 'race',               '2026-10-26'::date, '07:00'::time),
    (20, 'practice_1',         '2026-10-31'::date, '05:30'::time),
    (20, 'practice_2',         '2026-10-31'::date, '09:00'::time),
    (20, 'practice_3',         '2026-11-01'::date, '04:30'::time),
    (20, 'qualifying',         '2026-11-01'::date, '08:00'::time),
    (20, 'race',               '2026-11-02'::date, '07:00'::time),
    (21, 'practice_1',         '2026-11-07'::date, '02:30'::time),
    (21, 'practice_2',         '2026-11-07'::date, '06:00'::time),
    (21, 'practice_3',         '2026-11-08'::date, '01:30'::time),
    (21, 'qualifying',         '2026-11-08'::date, '05:00'::time),
    (21, 'race',               '2026-11-09'::date, '04:00'::time),
    (22, 'practice_1',         '2026-11-20'::date, '11:30'::time),
    (22, 'practice_2',         '2026-11-20'::date, '15:00'::time),
    (22, 'practice_3',         '2026-11-21'::date, '11:30'::time),
    (22, 'qualifying',         '2026-11-21'::date, '15:00'::time),
    (22, 'race',               '2026-11-22'::date, '15:00'::time),
    (23, 'practice_1',         '2026-11-28'::date, '00:30'::time),
    (23, 'practice_2',         '2026-11-28'::date, '04:00'::time),
    (23, 'practice_3',         '2026-11-29'::date, '01:30'::time),
    (23, 'qualifying',         '2026-11-29'::date, '05:00'::time),
    (23, 'race',               '2026-11-30'::date, '03:00'::time),
    (24, 'practice_1',         '2026-12-04'::date, '20:30'::time),
    (24, 'practice_2',         '2026-12-05'::date, '00:00'::time),
    (24, 'practice_3',         '2026-12-05'::date, '21:30'::time),
    (24, 'qualifying',         '2026-12-06'::date, '01:00'::time),
    (24, 'race',               '2026-12-07'::date, '00:00'::time)
) as s(round, session_type, session_date_aest, session_time_aest)
join public.race_events e
  on e.season = 2026
 and e.round = s.round;

-- Quick check.
-- select
--   e.season,
--   e.round,
--   c.title as circuit,
--   c.weekend_format,
--   e.grand_prix_name,
--   s.session_type,
--   s.session_date_aest,
--   s.session_time_aest
-- from public.race_events e
-- join public.circuits c on c.id = e.circuit_id
-- join public.race_sessions s on s.race_event_id = e.id
-- where e.season = 2026
-- order by e.round, s.session_date_aest, s.session_time_aest;
