"""
Strategy simulator — the data-driven engine. No LLM involvement.

Pipeline:
  1. Enumerate viable plans (1-stop and 2-stop) over the available compounds,
     respecting the Pirelli dry rule that at least two different compounds are
     used.
  2. For each plan, find the optimal stint split deterministically using
     O(1) lookups against precomputed cumulative stint costs, and emit a pit
     *window* (range) around each optimal stop lap.
  3. Monte Carlo the top candidates across SC / VSC / red-flag / weather
     scenarios drawn from Bayesian-smoothed track priors, scoring each by
     expected race time AND robustness (variance across scenarios).
  4. Assemble a StrategyOutput: headline + alternatives, safety-car plan,
     weather sensitivity, beneficiaries, risk factors, confidence, data
     coverage, and explicit assumptions. Degrades gracefully by report stage.

Determinism: the RNG is seeded from the input hash so the same inputs always
produce the same report (consistent with input_hash caching).
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from .degradation_model import DegradationModel, resolve_pit_loss
from .models import (
    DRY_COMPOUNDS,
    AlternativeStrategy,
    Beneficiary,
    DataCoverage,
    HeadlineStrategy,
    PitWindow,
    ReportStage,
    SafetyCarPlan,
    SafetyCarScenario,
    StrategyOutput,
    WeatherScenario,
    WeatherSensitivity,
)

MODEL_VERSION = "strategy-sim-1.0.0"

# Tuning constants (documented; all explainable).
_MIN_STINT = 5
_MC_RUNS = 600
_TOP_CANDIDATES = 5          # plans carried into Monte Carlo
_ROBUSTNESS_LAMBDA = 0.5     # weight on std-dev in the combined score
_SC_PIT_SAVING_FRAC = 0.55   # fraction of pit loss saved by stopping under SC
_VSC_PIT_SAVING_FRAC = 0.30
_SC_MISS_PENALTY_FRAC = 0.25 # relative loss if a SC falls and you cannot use it
_RAIN_PENALTY_S = 45.0       # cost of an unplanned dry->wet reaction

# Stage -> base confidence before data-coverage adjustments.
_STAGE_BASE_CONFIDENCE = {
    ReportStage.PRE_WEEKEND: 0.45,
    ReportStage.POST_PRACTICE: 0.62,
    ReportStage.POST_QUALIFYING: 0.78,
}


# ── inputs ──────────────────────────────────────────────────────────────────

@dataclass
class SimulationInputs:
    race_event_id: int
    circuit_id: Optional[int]
    total_laps: int
    report_stage: ReportStage

    deg_model: DegradationModel
    profile: Optional[dict[str, Any]] = None          # track_strategy_profiles row
    entries: list[dict[str, Any]] = field(default_factory=list)  # driver_race_entries

    available_compounds: tuple[str, ...] = DRY_COMPOUNDS
    weather_rain_probability: Optional[float] = None  # caller override
    grid_penalties: Optional[dict[str, int]] = None
    ref_lap_time_s: Optional[float] = None            # anchor for absolute race time

    def cache_payload(self) -> dict[str, Any]:
        """Stable dict used for the input_hash (and to seed the RNG)."""
        return {
            "raceEventId": self.race_event_id,
            "circuitId": self.circuit_id,
            "totalLaps": self.total_laps,
            "reportStage": self.report_stage.value,
            "modelVersion": MODEL_VERSION,
            "availableCompounds": list(self.available_compounds),
            "weatherRainProbability": self.weather_rain_probability,
            "gridPenalties": self.grid_penalties or {},
            "profile": _profile_for_hash(self.profile),
            "degSummary": self.deg_model.summary(),
            "entriesFingerprint": _entries_fingerprint(self.entries),
            "refLapTime": self.ref_lap_time_s,
        }


# ── internal plan representation ─────────────────────────────────────────────

@dataclass
class _Plan:
    compounds: tuple[str, ...]
    stops: tuple[int, ...]          # cumulative lap at each stop (target laps)
    stint_lengths: tuple[int, ...]
    det_time: float                 # deterministic delta-time (lower is better)
    pit_loss: float
    expected_time: float = 0.0
    robustness: float = 0.0
    combined: float = 0.0

    @property
    def num_stops(self) -> int:
        return len(self.stops)


# ── public entry point ────────────────────────────────────────────────────────

def simulate(inputs: SimulationInputs) -> tuple[StrategyOutput, str]:
    """
    Run the simulation. Returns (StrategyOutput, input_hash).
    """
    payload = inputs.cache_payload()
    input_hash = hashlib.sha256(
        _stable_json(payload).encode("utf-8")
    ).hexdigest()
    rng = np.random.default_rng(int(input_hash[:16], 16))

    L = inputs.total_laps
    pit_loss, pit_loss_assumed = resolve_pit_loss(inputs.profile)
    priors = _smoothed_priors(inputs.profile)
    rain_prob = _resolve_rain_probability(inputs)

    # 1-2. enumerate + optimise.
    plans = _enumerate_plans(inputs, L, pit_loss)
    if not plans:
        raise RuntimeError("No viable strategy plans could be enumerated.")

    plans.sort(key=lambda p: p.det_time)
    candidates = plans[:_TOP_CANDIDATES]

    # 3. Monte Carlo the candidates.
    for plan in candidates:
        _monte_carlo(plan, L, pit_loss, priors, rain_prob, inputs, rng)
    candidates.sort(key=lambda p: p.combined)

    headline = candidates[0]
    alternatives = _pick_alternatives(headline, candidates[1:])

    # 4. assemble output.
    anchor = (inputs.ref_lap_time_s or 0.0) * L

    output = StrategyOutput(
        report_stage=inputs.report_stage,
        race_event_id=inputs.race_event_id,
        model_version=MODEL_VERSION,
        headline_strategy=_to_headline(headline, L, pit_loss, priors, inputs, anchor),
        alternative_strategies=[
            _to_alternative(p, headline, L, anchor) for p in alternatives
        ],
        safety_car_plan=_safety_car_plan(headline, L, pit_loss, priors, inputs),
        weather_sensitivity=_weather_sensitivity(rain_prob, inputs),
        beneficiaries=_beneficiaries(inputs, priors),
        risk_factors=_risk_factors(headline, candidates, priors, rain_prob, inputs, pit_loss_assumed),
        confidence=_confidence(inputs, candidates, pit_loss_assumed),
        data_coverage=_data_coverage(inputs, pit_loss_assumed),
        assumptions=_assumptions(inputs, pit_loss_assumed, rain_prob),
    )
    return output, input_hash


# ── enumeration + optimisation ───────────────────────────────────────────────

def _enumerate_plans(inputs: SimulationInputs, L: int, pit_loss: float) -> list[_Plan]:
    deg = inputs.deg_model
    compounds = [c for c in inputs.available_compounds if c in DRY_COMPOUNDS] or list(DRY_COMPOUNDS)

    # Precompute cumulative stint cost per compound: cum[c][k] for k = 0..L.
    cum: dict[str, list[float]] = {}
    for c in compounds:
        arr = [0.0] * (L + 1)
        running = 0.0
        for k in range(1, L + 1):
            running += deg.lap_time_delta(c, k - 1)
            arr[k] = running
        cum[c] = arr

    plans: list[_Plan] = []

    # 1-stop: ordered pairs of distinct compounds.
    for c1, c2 in itertools.permutations(compounds, 2):
        best = _best_one_stop(c1, c2, L, cum, pit_loss)
        if best:
            plans.append(best)

    # 2-stop: ordered triples using >= 2 distinct compounds.
    for combo in itertools.product(compounds, repeat=3):
        if len(set(combo)) < 2:
            continue
        best = _best_two_stop(combo, L, cum, pit_loss)
        if best:
            plans.append(best)

    return plans


def _best_one_stop(c1, c2, L, cum, pit_loss) -> Optional[_Plan]:
    best: Optional[_Plan] = None
    for a in range(_MIN_STINT, L - _MIN_STINT + 1):
        cost = cum[c1][a] + cum[c2][L - a] + pit_loss
        if best is None or cost < best.det_time:
            best = _Plan(
                compounds=(c1, c2),
                stops=(a,),
                stint_lengths=(a, L - a),
                det_time=cost,
                pit_loss=pit_loss,
            )
    return best


def _best_two_stop(combo, L, cum, pit_loss) -> Optional[_Plan]:
    c1, c2, c3 = combo
    best: Optional[_Plan] = None
    # a = first stop lap, b = second stop lap.
    for a in range(_MIN_STINT, L - 2 * _MIN_STINT + 1):
        cost_a = cum[c1][a]
        for b in range(a + _MIN_STINT, L - _MIN_STINT + 1):
            cost = cost_a + cum[c2][b - a] + cum[c3][L - b] + 2 * pit_loss
            if best is None or cost < best.det_time:
                best = _Plan(
                    compounds=combo,
                    stops=(a, b),
                    stint_lengths=(a, b - a, L - b),
                    det_time=cost,
                    pit_loss=pit_loss,
                )
    return best


# ── Monte Carlo ───────────────────────────────────────────────────────────────

def _monte_carlo(plan, L, pit_loss, priors, rain_prob, inputs, rng) -> None:
    window_half = _window_half(L)
    sc_p, vsc_p, red_p = priors["sc"], priors["vsc"], priors["red"]

    sc_hit = rng.random(_MC_RUNS) < sc_p
    sc_lap = rng.integers(1, L + 1, size=_MC_RUNS)
    vsc_hit = rng.random(_MC_RUNS) < vsc_p
    vsc_lap = rng.integers(1, L + 1, size=_MC_RUNS)
    rain_hit = rng.random(_MC_RUNS) < rain_prob
    # Degradation execution noise grows with the number of stops and assumed data.
    noise_sd = 0.8 + 0.6 * plan.num_stops
    deg_noise = rng.normal(0.0, noise_sd, size=_MC_RUNS)

    times = np.full(_MC_RUNS, plan.det_time, dtype=float) + deg_noise

    for i in range(_MC_RUNS):
        if sc_hit[i]:
            times[i] += _event_adjustment(
                plan.stops, sc_lap[i], window_half, pit_loss, _SC_PIT_SAVING_FRAC
            )
        if vsc_hit[i]:
            times[i] += _event_adjustment(
                plan.stops, vsc_lap[i], window_half, pit_loss, _VSC_PIT_SAVING_FRAC
            )
        if rain_hit[i]:
            times[i] += _RAIN_PENALTY_S

    plan.expected_time = float(times.mean())
    plan.robustness = float(times.std())
    plan.combined = plan.expected_time + _ROBUSTNESS_LAMBDA * plan.robustness


def _event_adjustment(stops, event_lap, window_half, pit_loss, saving_frac) -> float:
    """
    If a stop can be taken cheaply within the event window, save part of the pit
    loss; otherwise the field gets the cheap stop and we lose a little relatively.
    """
    for stop in stops:
        if abs(stop - event_lap) <= window_half:
            return -saving_frac * pit_loss
    return _SC_MISS_PENALTY_FRAC * saving_frac * pit_loss


# ── output assembly ────────────────────────────────────────────────────────────

def _to_pit_windows(plan, L) -> list[PitWindow]:
    half = _window_half(L)
    windows = []
    for i, stop in enumerate(plan.stops):
        windows.append(
            PitWindow(
                stop_number=i + 1,
                earliest_lap=max(_MIN_STINT, stop - half),
                latest_lap=min(L - _MIN_STINT, stop + half),
                target_lap=stop,
                in_compound=plan.compounds[i + 1],
            )
        )
    return windows


def _to_headline(plan, L, pit_loss, priors, inputs, anchor) -> HeadlineStrategy:
    deg = inputs.deg_model
    reasoning = [
        f"{plan.num_stops}-stop minimises modelled race time "
        f"({plan.expected_time:+.1f}s vs base), best of "
        f"{len(plan.compounds)} compound sequence options.",
        "Compound order " + "→".join(plan.compounds)
        + " balances pace offset against degradation slope.",
        f"Pit loss modelled at {pit_loss:.1f}s per stop"
        + ("" if not deg.is_assumed(plan.compounds[0]) else " (some compound data assumed).") ,
        f"Safety-car prior {priors['sc']:.0%}, VSC prior {priors['vsc']:.0%} "
        f"factored into pit-window robustness.",
    ]
    return HeadlineStrategy(
        num_stops=plan.num_stops,
        compound_sequence=list(plan.compounds),
        pit_windows=_to_pit_windows(plan, L),
        expected_race_time_s=round(anchor + plan.expected_time, 2),
        robustness_s=round(plan.robustness, 2),
        reasoning_inputs=reasoning,
    )


def _to_alternative(plan, headline, L, anchor) -> AlternativeStrategy:
    delta = plan.expected_time - headline.expected_time
    note = None
    if plan.num_stops != headline.num_stops:
        note = f"{plan.num_stops}-stop alternative; trades flexibility for {abs(delta):.1f}s."
    return AlternativeStrategy(
        num_stops=plan.num_stops,
        compound_sequence=list(plan.compounds),
        pit_windows=_to_pit_windows(plan, L),
        time_delta_s=round(delta, 2),
        note=note,
    )


def _pick_alternatives(headline, rest) -> list[_Plan]:
    """Top 2 alternatives with a compound sequence distinct from the headline."""
    out: list[_Plan] = []
    seen = {headline.compounds}
    for p in rest:
        if p.compounds in seen:
            continue
        seen.add(p.compounds)
        out.append(p)
        if len(out) == 2:
            break
    return out


def _safety_car_plan(headline, L, pit_loss, priors, inputs) -> SafetyCarPlan:
    half = _window_half(L)
    scenarios = []
    for label, lo, hi in (("SC laps 10-20", 10, 20), ("SC laps 30-40", 30, 40)):
        lo, hi = min(lo, L), min(hi, L)
        mid = (lo + hi) // 2
        usable = any(abs(stop - mid) <= half + 5 for stop in headline.stops)
        if usable:
            swing = -_SC_PIT_SAVING_FRAC * pit_loss
            action = (
                f"Pit inside the SC window — a planned stop falls near lap {mid}, "
                f"so react and bank roughly {abs(swing):.0f}s."
            )
        else:
            swing = _SC_MISS_PENALTY_FRAC * _SC_PIT_SAVING_FRAC * pit_loss
            action = (
                f"Hold track position — no planned stop is near lap {mid}; pitting "
                f"early sacrifices tyre offset, expect to concede ~{swing:.0f}s relatively."
            )
        scenarios.append(
            SafetyCarScenario(
                window_label=label,
                deploy_lap_start=lo,
                deploy_lap_end=hi,
                recommended_action=action,
                time_swing_s=round(swing, 1),
                changes_headline=not usable,
            )
        )
    return SafetyCarPlan(
        scenarios=scenarios,
        summary=(
            f"With a {priors['sc']:.0%} safety-car prior at this circuit, the headline "
            "plan's pit windows are positioned to capitalise on a mid-race deployment."
        ),
    )


def _weather_sensitivity(rain_prob, inputs) -> WeatherSensitivity:
    base = rain_prob
    # Confidence drop if the forecast flips wet: dry plans become moot.
    drop_if_rain = min(0.6, 0.35 + 0.25 * base)
    scenarios = [
        WeatherScenario(
            rain_probability=p,
            confidence_drop=round(min(0.6, 0.1 + 0.7 * p), 2),
            note=(
                "Dry plan holds" if p < 0.25
                else "Crossover risk — keep an intermediate plan ready" if p < 0.55
                else "Likely wet — dry strategy superseded"
            ),
        )
        for p in (0.1, 0.3, 0.6)
    ]
    return WeatherSensitivity(
        base_rain_probability=round(base, 2),
        confidence_drop_if_rain=round(drop_if_rain, 2),
        scenarios=scenarios,
        note=(
            "Weather forecast supplied by caller." if inputs.weather_rain_probability is not None
            else "No forecast supplied; assumed a dry race with low rain probability."
        ),
    )


def _beneficiaries(inputs, priors) -> list[Beneficiary]:
    profile = inputs.profile or {}
    overtaking = _num(profile.get("overtaking_difficulty"), 0.5)
    undercut = _num(profile.get("undercut_strength"), 0.5)
    tpi = _num(profile.get("track_position_importance"), 0.5)

    out: list[Beneficiary] = []
    if overtaking >= 0.6 or tpi >= 0.6:
        out.append(Beneficiary(
            grid_positions="P1-P4",
            expected_gain="protects positions",
            reason=(
                f"High overtaking difficulty ({overtaking:.0%}) makes track position "
                "decisive; front-runners gain most by controlling the pit window."
            ),
        ))
    if undercut >= 0.55:
        out.append(Beneficiary(
            grid_positions="P5-P10",
            expected_gain="+1 to +2 places",
            reason=(
                f"Strong undercut ({undercut:.0%}) lets the chasing midfield jump "
                "rivals by stopping at the early edge of the window."
            ),
        ))
    if overtaking < 0.45:
        out.append(Beneficiary(
            grid_positions="P11-P16",
            expected_gain="strategy upside",
            reason=(
                f"Low overtaking difficulty ({overtaking:.0%}) lets cars starting "
                "outside the points use an offset compound plan to make places on track."
            ),
        ))
    if not out:
        out.append(Beneficiary(
            grid_positions="midfield",
            expected_gain="marginal",
            reason="Balanced circuit profile; no grid band has a decisive strategic edge.",
        ))
    return out


def _risk_factors(headline, candidates, priors, rain_prob, inputs, pit_loss_assumed) -> list[str]:
    risks: list[str] = []
    if priors["sc"] >= 0.5:
        risks.append(f"High safety-car prior ({priors['sc']:.0%}) can swing optimal pit timing.")
    if priors["red"] >= 0.2:
        risks.append(f"Elevated red-flag prior ({priors['red']:.0%}) may reset the strategy entirely.")
    if rain_prob >= 0.3:
        risks.append(f"Rain probability {rain_prob:.0%}: dry plan may be superseded by a wet call.")
    if len(candidates) >= 2 and (candidates[1].combined - headline.combined) < 1.0:
        risks.append("Top two plans are within ~1s modelled — execution and SC luck decide.")
    if inputs.deg_model.is_assumed(headline.compounds[0]):
        risks.append("Degradation for at least one chosen compound is assumed, not data-backed.")
    if pit_loss_assumed:
        risks.append("Pit-loss baseline for this circuit is assumed (no historical pit data).")
    if inputs.report_stage == ReportStage.PRE_WEEKEND:
        risks.append("Pre-weekend: grid and live degradation not yet known; windows are indicative.")
    if not risks:
        risks.append("No dominant risk factor; the headline plan is robust across modelled scenarios.")
    return risks


def _confidence(inputs, candidates, pit_loss_assumed) -> float:
    conf = _STAGE_BASE_CONFIDENCE[inputs.report_stage]
    deg = inputs.deg_model
    if deg.n_stints_total < 200:
        conf -= 0.08
    if deg.is_assumed(candidates[0].compounds[0]):
        conf -= 0.08
    if inputs.profile is None:
        conf -= 0.10
    if pit_loss_assumed:
        conf -= 0.05
    # Penalise when the field of plans is very tightly bunched (ambiguous).
    if len(candidates) >= 2 and (candidates[1].combined - candidates[0].combined) < 0.5:
        conf -= 0.05
    return round(max(0.05, min(0.95, conf)), 2)


def _data_coverage(inputs, pit_loss_assumed) -> DataCoverage:
    available, assumed = [], []
    (available if inputs.profile else assumed).append("track_strategy_profile")
    (available if not pit_loss_assumed else assumed).append("circuit pit-loss baseline")
    (available if inputs.deg_model.n_stints_total else assumed).append("historical stint degradation")

    has_practice = any(e.get("driver_clean_air_pace") is not None for e in inputs.entries)
    has_grid = any(e.get("qualifying_final_grid_pos") is not None for e in inputs.entries)

    if inputs.report_stage in (ReportStage.POST_PRACTICE, ReportStage.POST_QUALIFYING):
        (available if has_practice else assumed).append("this-weekend long-run pace")
    if inputs.report_stage == ReportStage.POST_QUALIFYING:
        (available if has_grid else assumed).append("confirmed grid positions")

    (available if inputs.grid_penalties else assumed).append("grid penalties")
    (available if inputs.weather_rain_probability is not None else assumed).append("weather forecast")

    return DataCoverage(
        available_inputs=available,
        assumed_inputs=assumed,
        notes=(
            f"Degradation model fitted on {inputs.deg_model.n_stints_total} stints "
            f"across {inputs.deg_model.n_races} races."
        ),
    )


def _assumptions(inputs, pit_loss_assumed, rain_prob) -> list[str]:
    out = []
    if set(inputs.available_compounds) == set(DRY_COMPOUNDS):
        out.append("Assumed the standard SOFT/MEDIUM/HARD allocation is available (no nomination feed).")
    if inputs.weather_rain_probability is None:
        out.append(f"Assumed a dry race (rain probability {rain_prob:.0%}).")
    if inputs.profile is None:
        out.append("No track strategy profile found; used global priors for SC/VSC/red-flag rates.")
    if pit_loss_assumed:
        out.append("Used the global default pit loss; circuit-specific pit data was unavailable.")
    if inputs.report_stage == ReportStage.PRE_WEEKEND:
        out.append("Pre-weekend stage: no live practice degradation or confirmed grid used.")
    out.append("Plans are field-level (not per-driver); per-car traffic effects are averaged.")
    return out


# ── priors / helpers ───────────────────────────────────────────────────────────

def _smoothed_priors(profile: Optional[dict[str, Any]]) -> dict[str, float]:
    """
    Bayesian-smoothed event priors. When a profile exists, blend its rate with a
    weak global prior (Beta-style smoothing) so single-race circuits aren't 0/1.
    """
    GLOBAL = {"sc": 0.40, "vsc": 0.30, "red": 0.10}
    if not profile:
        return GLOBAL

    n = profile.get("sample_races") or 0
    pseudo = 4.0  # strength of the global prior
    out = {}
    for key, col in (("sc", "sc_prior"), ("vsc", "vsc_prior"), ("red", "red_flag_prior")):
        raw = profile.get(col)
        if raw is None:
            out[key] = GLOBAL[key]
        else:
            out[key] = (n * float(raw) + pseudo * GLOBAL[key]) / (n + pseudo)
    return out


def _resolve_rain_probability(inputs: SimulationInputs) -> float:
    if inputs.weather_rain_probability is not None:
        return float(inputs.weather_rain_probability)
    return 0.10


def _window_half(L: int) -> int:
    return max(2, round(0.04 * L))


def _num(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _profile_for_hash(profile: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not profile:
        return {}
    keys = (
        "overtaking_difficulty", "track_position_importance", "undercut_strength",
        "pit_loss_baseline", "sc_prior", "vsc_prior", "red_flag_prior", "sample_races",
    )
    return {k: profile.get(k) for k in keys}


def _entries_fingerprint(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in sorted(entries, key=lambda x: x.get("driver_code") or ""):
        out.append({
            "d": e.get("driver_code"),
            "g": e.get("qualifying_final_grid_pos"),
            "cap": e.get("driver_clean_air_pace"),
            "fp3": e.get("fp3_pos"),
        })
    return out


def _stable_json(payload: dict[str, Any]) -> str:
    import json
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
