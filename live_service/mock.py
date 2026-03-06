"""Mock qualifying session that generates realistic F1 live timing data."""

from __future__ import annotations

import asyncio
import math
import os
import random
import re
from typing import Any

DRIVERS = [
    {"num": "1",  "tla": "VER", "name": "Max VERSTAPPEN",    "team": "Red Bull Racing",  "color": "3671C6", "tier": 1},
    {"num": "30", "tla": "LAW", "name": "Liam LAWSON",       "team": "Red Bull Racing",  "color": "3671C6", "tier": 2},
    {"num": "16", "tla": "LEC", "name": "Charles LECLERC",   "team": "Ferrari",          "color": "E80020", "tier": 1},
    {"num": "44", "tla": "HAM", "name": "Lewis HAMILTON",    "team": "Ferrari",          "color": "E80020", "tier": 1},
    {"num": "4",  "tla": "NOR", "name": "Lando NORRIS",      "team": "McLaren",          "color": "FF8000", "tier": 1},
    {"num": "81", "tla": "PIA", "name": "Oscar PIASTRI",     "team": "McLaren",          "color": "FF8000", "tier": 1},
    {"num": "63", "tla": "RUS", "name": "George RUSSELL",    "team": "Mercedes",         "color": "27F4D2", "tier": 2},
    {"num": "12", "tla": "ANT", "name": "Kimi ANTONELLI",    "team": "Mercedes",         "color": "27F4D2", "tier": 2},
    {"num": "14", "tla": "ALO", "name": "Fernando ALONSO",   "team": "Aston Martin",     "color": "229971", "tier": 2},
    {"num": "18", "tla": "STR", "name": "Lance STROLL",      "team": "Aston Martin",     "color": "229971", "tier": 3},
    {"num": "23", "tla": "ALB", "name": "Alexander ALBON",   "team": "Williams",         "color": "64C4FF", "tier": 3},
    {"num": "55", "tla": "SAI", "name": "Carlos SAINZ",      "team": "Williams",         "color": "64C4FF", "tier": 2},
    {"num": "10", "tla": "GAS", "name": "Pierre GASLY",      "team": "Alpine",           "color": "0093CC", "tier": 3},
    {"num": "43", "tla": "COL", "name": "Franco COLAPINTO",  "team": "Alpine",           "color": "0093CC", "tier": 3},
    {"num": "27", "tla": "HUL", "name": "Nico HULKENBERG",   "team": "Audi",             "color": "999999", "tier": 3},
    {"num": "5",  "tla": "BOR", "name": "Gabriel BORTOLETO", "team": "Audi",             "color": "999999", "tier": 3},
    {"num": "22", "tla": "TSU", "name": "Yuki TSUNODA",      "team": "Racing Bulls",     "color": "6692FF", "tier": 2},
    {"num": "6",  "tla": "HAD", "name": "Isack HADJAR",      "team": "Racing Bulls",     "color": "6692FF", "tier": 3},
    {"num": "31", "tla": "OCO", "name": "Esteban OCON",      "team": "Haas F1 Team",     "color": "B6BABD", "tier": 3},
    {"num": "87", "tla": "BEA", "name": "Oliver BEARMAN",    "team": "Haas F1 Team",     "color": "B6BABD", "tier": 3},
    {"num": "11", "tla": "PER", "name": "Sergio Perez",      "team": "Cadillac F1 Team", "color": "C4A230", "tier": 3},
    {"num": "77", "tla": "BOT", "name": "Valterri Bottas",   "team": "Cadillac F1 Team", "color": "C4A230", "tier": 3},
]

COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]

BASE_SECTORS = [28.200, 34.800, 24.500]
TIER_OFFSETS = {1: 0.0, 2: 0.25, 3: 0.50}
SEGMENTS_PER_SECTOR = 8
SECTOR_BOUNDARIES = [0.0, 0.36, 0.68, 1.0]

TICK_INTERVAL = 0.25
FLYING_LAP_TICKS = 352
OUT_LAP_TICKS = 440
IN_LAP_TICKS = 380
PIT_WAIT_MIN = 40
PIT_WAIT_MAX = 160

STATUS_NONE = 0
STATUS_YELLOW = 2048
STATUS_GREEN = 2049
STATUS_PURPLE = 2051


def _deep_merge(base: Any, update: Any) -> Any:
    if isinstance(base, dict) and isinstance(update, dict):
        merged = dict(base)
        for k, v in update.items():
            merged[k] = _deep_merge(merged[k], v) if k in merged else v
        return merged
    return update


def _load_track(track_dir: str, track_name: str) -> list[tuple[float, float]]:
    path = os.path.join(track_dir, f"{track_name}.js")
    if not os.path.exists(path):
        return [(300 * math.cos(2 * math.pi * i / 500), 200 * math.sin(2 * math.pi * i / 500)) for i in range(500)]
    with open(path) as f:
        content = f.read()
    m = re.search(r"`([\s\S]*?)`", content)
    csv_text = m.group(1) if m else content
    pts: list[tuple[float, float]] = []
    for line in csv_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                pts.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return pts


def _fmt_lap(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:06.3f}"


def _fmt_sector(seconds: float) -> str:
    return f"{seconds:.3f}"


class DriverState:
    def __init__(self, info: dict, start_tick: int) -> None:
        self.info = info
        self.num: str = info["num"]
        self.tier: int = info["tier"]
        self.phase = "pit"
        self.track_progress = 0.0
        self.current_sector = 0
        self.segments_done = [0, 0, 0]
        self.sector_times: list[float | None] = [None, None, None]
        self.sector_start_tick = 0
        self.best_sectors: list[float | None] = [None, None, None]
        self.best_lap_time: float | None = None
        self.last_lap_time: float | None = None
        self.laps_completed = 0
        self.pit_exit_tick = start_tick
        self.stint_index = 0
        self.compound: str = random.choice(COMPOUNDS)

    def gen_sector_time(self, idx: int) -> float:
        base = BASE_SECTORS[idx]
        return base + TIER_OFFSETS[self.tier] + random.gauss(0, 0.08) + random.gauss(0, 0.12)


class MockSession:
    def __init__(self, state_service: Any, track_dir: str, track_name: str) -> None:
        self.ss = state_service
        self.track = _load_track(track_dir, track_name)
        self.track_name = track_name
        self.tick = 0
        self.drivers = [
            DriverState(d, random.randint(4, 20) if i < 6 else random.randint(20, 60) if i < 12 else random.randint(60, 120))
            for i, d in enumerate(DRIVERS)
        ]
        self.overall_best_sectors: list[float | None] = [None, None, None]
        self.overall_best_lap: float | None = None

    # ── initial state ──────────────────────────────────────────────

    def _build_initial(self) -> dict:
        dl: dict = {}
        td: dict = {}
        ts: dict = {}
        ta: dict = {}
        pos: dict = {}

        for idx, ds in enumerate(self.drivers):
            d = ds.info
            dl[d["num"]] = {
                "RacingNumber": d["num"],
                "BroadcastName": d["name"],
                "FullName": d["name"],
                "Tla": d["tla"],
                "TeamName": d["team"],
                "TeamColour": d["color"],
                "Line": idx + 1,
            }
            sectors = [
                {
                    "Value": "",
                    "PreviousValue": "",
                    "Status": 0,
                    "OverallFastest": False,
                    "PersonalFastest": False,
                    "Stopped": False,
                    "Segments": [{"Status": 0} for _ in range(SEGMENTS_PER_SECTOR)],
                }
                for _ in range(3)
            ]
            td[d["num"]] = {
                "Position": str(idx + 1),
                "ShowPosition": True,
                "GapToLeader": "",
                "IntervalToPositionAhead": {"Value": "", "Catching": False},
                "Sectors": sectors,
                "BestLapTime": {"Value": ""},
                "LastLapTime": {"Value": "", "OverallFastest": False, "PersonalFastest": False},
                "NumberOfLaps": 0,
                "InPit": True,
                "PitOut": False,
                "Retired": False,
            }
            ts[d["num"]] = {
                "RacingNumber": d["num"],
                "PersonalBestLapTime": {"Value": ""},
                "BestSectors": [{"Value": ""}, {"Value": ""}, {"Value": ""}],
            }
            ta[d["num"]] = {
                "Stints": [{"Compound": ds.compound, "New": "true", "TotalLaps": 0, "StartLaps": 0}],
            }
            pos[d["num"]] = {"X": round(self.track[0][0], 2), "Y": round(self.track[0][1], 2), "Z": 0, "Status": "OnTrack"}

        return {
            "DriverList": dl,
            "TimingData": {"Lines": td},
            "TimingStats": {"Lines": ts},
            "TimingAppData": {"Lines": ta},
            "SessionInfo": {
                "Meeting": {"Name": "Mock Grand Prix", "Circuit": {"ShortName": self.track_name}},
                "Name": "Qualifying",
                "Type": "Qualifying",
            },
            "SessionStatus": {"Status": "Started"},
            "TrackStatus": {"Status": "1", "Message": "AllClear"},
            "ExtrapolatedClock": {"Remaining": "00:15:00", "Extrapolating": True},
            "LapCount": {"CurrentLap": 0, "TotalLaps": 0},
            "Position": {"Entries": pos},
        }

    # ── track helpers ──────────────────────────────────────────────

    def _pos_at(self, progress: float) -> tuple[float, float]:
        n = len(self.track)
        clamped = max(0.0, min(progress, 0.9999))
        idx_f = clamped * (n - 1)
        i = int(idx_f)
        frac = idx_f - i
        if i >= n - 1:
            return self.track[-1]
        x = self.track[i][0] + frac * (self.track[i + 1][0] - self.track[i][0])
        y = self.track[i][1] + frac * (self.track[i + 1][1] - self.track[i][1])
        return round(x, 2), round(y, 2)

    # ── per-driver tick ────────────────────────────────────────────

    def _tick_driver(self, ds: DriverState) -> dict:
        tu: dict = {}
        pu: dict = {}

        if ds.phase == "pit":
            if self.tick >= ds.pit_exit_tick:
                ds.phase = "out_lap"
                ds.track_progress = 0.0
                ds.sector_times = [None, None, None]
                ds.segments_done = [0, 0, 0]
                ds.current_sector = 0
                ds.sector_start_tick = self.tick
                tu["InPit"] = False
                tu["PitOut"] = True
                sectors_reset: dict = {}
                for s in range(3):
                    segs = {str(sg): {"Status": STATUS_NONE} for sg in range(SEGMENTS_PER_SECTOR)}
                    sectors_reset[str(s)] = {
                        "Value": "", "Status": 0,
                        "OverallFastest": False, "PersonalFastest": False,
                        "Segments": segs,
                    }
                tu["Sectors"] = sectors_reset
            return self._pack(ds, tu, pu)

        speed = {
            "out_lap": 1.0 / OUT_LAP_TICKS,
            "flying": 1.0 / FLYING_LAP_TICKS,
            "in_lap": 1.0 / IN_LAP_TICKS,
        }.get(ds.phase, 0)

        ds.track_progress += speed
        x, y = self._pos_at(ds.track_progress % 1.0)
        pu = {"X": x, "Y": y, "Z": 0, "Status": "OnTrack"}

        if ds.phase == "out_lap":
            if ds.track_progress >= 1.0:
                ds.phase = "flying"
                ds.track_progress = 0.0
                ds.current_sector = 0
                ds.sector_start_tick = self.tick
                ds.segments_done = [0, 0, 0]
                tu["PitOut"] = False
                sectors_reset = {}
                for s in range(3):
                    segs = {str(sg): {"Status": STATUS_NONE} for sg in range(SEGMENTS_PER_SECTOR)}
                    sectors_reset[str(s)] = {
                        "Value": "", "Status": 0,
                        "OverallFastest": False, "PersonalFastest": False,
                        "Segments": segs,
                    }
                tu["Sectors"] = sectors_reset

        elif ds.phase == "flying":
            sec = ds.current_sector
            s_start = SECTOR_BOUNDARIES[sec]
            s_end = SECTOR_BOUNDARIES[sec + 1]
            s_pct = min((ds.track_progress - s_start) / (s_end - s_start), 1.0)
            new_segs = min(int(s_pct * SEGMENTS_PER_SECTOR), SEGMENTS_PER_SECTOR)

            if new_segs > ds.segments_done[sec]:
                seg_u: dict = {}
                for sg in range(ds.segments_done[sec], new_segs):
                    seg_u[str(sg)] = {"Status": STATUS_YELLOW}
                tu.setdefault("Sectors", {})[str(sec)] = {"Segments": seg_u}
                ds.segments_done[sec] = new_segs

            if ds.track_progress >= s_end:
                t = ds.gen_sector_time(sec)
                ds.sector_times[sec] = t
                pb = ds.best_sectors[sec] is None or t < ds.best_sectors[sec]
                ob = self.overall_best_sectors[sec] is None or t < self.overall_best_sectors[sec]
                if pb:
                    ds.best_sectors[sec] = t
                if ob:
                    self.overall_best_sectors[sec] = t

                seg_st = STATUS_PURPLE if ob else (STATUS_GREEN if pb else STATUS_YELLOW)
                all_segs = {str(sg): {"Status": seg_st} for sg in range(SEGMENTS_PER_SECTOR)}
                sec_status = STATUS_PURPLE if ob else (STATUS_GREEN if pb else STATUS_YELLOW)

                tu.setdefault("Sectors", {})[str(sec)] = {
                    "Value": _fmt_sector(t),
                    "Status": sec_status,
                    "OverallFastest": ob,
                    "PersonalFastest": pb and not ob,
                    "Segments": all_segs,
                }

                if sec < 2:
                    ds.current_sector += 1
                    ds.sector_start_tick = self.tick
                else:
                    lap = sum(st for st in ds.sector_times if st is not None)
                    ds.last_lap_time = lap
                    ds.laps_completed += 1
                    pb_lap = ds.best_lap_time is None or lap < ds.best_lap_time
                    ob_lap = self.overall_best_lap is None or lap < self.overall_best_lap
                    if pb_lap:
                        ds.best_lap_time = lap
                    if ob_lap:
                        self.overall_best_lap = lap
                    tu["LastLapTime"] = {
                        "Value": _fmt_lap(lap),
                        "OverallFastest": ob_lap,
                        "PersonalFastest": pb_lap and not ob_lap,
                    }
                    if pb_lap:
                        tu["BestLapTime"] = {"Value": _fmt_lap(ds.best_lap_time)}
                    tu["NumberOfLaps"] = ds.laps_completed
                    ds.phase = "in_lap"
                    ds.track_progress = 0.0

        elif ds.phase == "in_lap":
            if ds.track_progress >= 1.0:
                ds.phase = "pit"
                ds.track_progress = 0.0
                ds.pit_exit_tick = self.tick + random.randint(PIT_WAIT_MIN, PIT_WAIT_MAX)
                tu["InPit"] = True
                pu = {"X": round(self.track[0][0], 2), "Y": round(self.track[0][1], 2), "Z": 0, "Status": "OnTrack"}
                old_compound = ds.compound
                ds.compound = random.choice([c for c in COMPOUNDS if c != old_compound])
                ds.stint_index += 1

        out = self._pack(ds, tu, pu)
        if tu.get("InPit"):
            out["TimingAppData"] = {"Lines": {ds.num: {
                "Stints": {str(ds.stint_index): {
                    "Compound": ds.compound, "New": "true",
                    "TotalLaps": 0, "StartLaps": ds.laps_completed,
                }},
            }}}
        return out

    @staticmethod
    def _pack(ds: DriverState, timing: dict, position: dict) -> dict:
        out: dict = {}
        if timing:
            out["TimingData"] = {"Lines": {ds.num: timing}}
        if position:
            out["Position"] = {"Entries": {ds.num: position}}
        return out

    # ── rankings ───────────────────────────────────────────────────

    def _rankings_update(self) -> dict:
        ranked = sorted(
            self.drivers,
            key=lambda d: d.best_lap_time if d.best_lap_time is not None else 9999,
        )
        leader_t: float | None = None
        prev_t: float | None = None
        td_u: dict = {}

        for pos_idx, ds in enumerate(ranked):
            pos = pos_idx + 1
            entry: dict = {"Position": str(pos)}
            if ds.best_lap_time is not None:
                if leader_t is None:
                    leader_t = ds.best_lap_time
                    entry["GapToLeader"] = ""
                else:
                    entry["GapToLeader"] = f"+{ds.best_lap_time - leader_t:.3f}"
                if prev_t is not None:
                    entry["IntervalToPositionAhead"] = {
                        "Value": f"+{ds.best_lap_time - prev_t:.3f}",
                        "Catching": False,
                    }
                prev_t = ds.best_lap_time
            td_u[ds.num] = entry

        ts_u: dict = {}
        for ds in self.drivers:
            bs = [{"Value": _fmt_sector(ds.best_sectors[s]) if ds.best_sectors[s] else ""} for s in range(3)]
            ts_u[ds.num] = {
                "PersonalBestLapTime": {"Value": _fmt_lap(ds.best_lap_time) if ds.best_lap_time else ""},
                "BestSectors": bs,
            }

        return {
            "TimingData": {"Lines": td_u},
            "TimingStats": {"Lines": ts_u},
        }

    # ── main loop ──────────────────────────────────────────────────

    async def run(self) -> None:
        self.ss.set_initial(self._build_initial())

        while True:
            await asyncio.sleep(TICK_INTERVAL)
            self.tick += 1

            combined: dict = {}
            for ds in self.drivers:
                upd = self._tick_driver(ds)
                if upd:
                    combined = _deep_merge(combined, upd)

            if self.tick % 4 == 0:
                combined = _deep_merge(combined, self._rankings_update())

            if combined:
                await self.ss.broadcast(combined)
