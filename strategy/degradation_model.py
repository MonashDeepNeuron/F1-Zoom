"""
Per-compound tyre degradation model + pit-loss lookup.

Design goals (from the spec): explainable, small-data-friendly, no RL / deep
nets. This is a hierarchical (empirical-Bayes shrinkage) estimator, which is the
small-data-robust cousin of the mixed-effects regression the spec allows.

For each compound we estimate three things from driver_race_stints:

  1. pace_offset(compound)  — how many seconds slower than the fastest compound
     this tyre is, computed *within each race* and then averaged (so absolute
     lap-time differences between circuits cancel out).
  2. deg_slope(compound)    — net seconds-per-lap trend over a stint, shrunk
     toward the global mean so sparse compounds borrow strength.
  3. typical_length(compound) — the stint length beyond which the tyre falls off;
     past it a quadratic "cliff" penalty is applied so over-long stints are
     correctly punished and pit windows come out realistic.

A stint's modelled lap time at tyre age ``k`` (laps on the tyre) is::

    laptime(k) = base_ref + pace_offset(c) + deg_slope(c) * k + cliff(c, k)

``base_ref`` is a per-race anchor that cancels when comparing plans for the same
race, so the model is used for *relative* plan scoring.

Pit loss is per-circuit and is precomputed into
``track_strategy_profiles.pit_loss_baseline`` by build_profiles.py (historical
green-flag pit laps vs the clean baseline). The simulator reads it from there;
``DEFAULT_PIT_LOSS_S`` is the fallback when a circuit has no profile yet.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import DRY_COMPOUNDS

# Shrinkage strength: a compound with this many "virtual" observations of the
# global mean. Small => trust the compound's own sample; large => pull to global.
_SHRINK_K = 8.0

# Fallback pit loss (seconds) when a circuit has no track_strategy_profiles row.
DEFAULT_PIT_LOSS_S = 22.0

# Sensible priors used when a compound is entirely absent from the data, so the
# enumerator never crashes on a fresh database. Offsets in seconds vs the soft;
# slopes in seconds/lap. Deliberately conservative and clearly labelled assumed.
_COMPOUND_PRIORS: dict[str, dict[str, float]] = {
    "SOFT": {"offset": 0.0, "slope": 0.10, "length": 18.0},
    "MEDIUM": {"offset": 0.5, "slope": 0.06, "length": 28.0},
    "HARD": {"offset": 1.0, "slope": 0.04, "length": 38.0},
}

# Cliff penalty grows quadratically once a stint runs past its typical length.
_CLIFF_PER_LAP_SQ = 0.015  # seconds per (lap-over-typical)^2


@dataclass
class _CompoundFit:
    compound: str
    pace_offset: float
    deg_slope: float
    typical_length: float
    n_stints: int
    assumed: bool = False  # True if backed by priors, not data


@dataclass
class DegradationModel:
    """Fitted per-compound degradation model. Build via ``DegradationModel.fit``."""

    compounds: dict[str, _CompoundFit] = field(default_factory=dict)
    global_slope: float = 0.06
    n_stints_total: int = 0
    n_races: int = 0

    # ── fitting ────────────────────────────────────────────────────────────

    @classmethod
    def fit(cls, stints: list[dict[str, Any]]) -> "DegradationModel":
        """Fit from a list of driver_race_stints rows (dicts)."""
        usable = [
            s for s in stints
            if s.get("compound") and s.get("degradation_slope") is not None
        ]

        # Global mean slope (shrinkage target).
        all_slopes = [float(s["degradation_slope"]) for s in usable]
        global_slope = statistics.fmean(all_slopes) if all_slopes else 0.06

        # Within-race pace offsets: for each race, compound mean clean-air pace
        # minus the fastest compound mean in that race.
        by_race: dict[Any, list[dict[str, Any]]] = {}
        for s in usable:
            by_race.setdefault(s.get("race_event_id"), []).append(s)

        offset_samples: dict[str, list[float]] = {}
        for race_stints in by_race.values():
            comp_pace: dict[str, list[float]] = {}
            for s in race_stints:
                cap = s.get("clean_air_pace")
                if cap is None:
                    continue
                comp_pace.setdefault(s["compound"], []).append(float(cap))
            comp_mean = {c: statistics.fmean(v) for c, v in comp_pace.items() if v}
            if not comp_mean:
                continue
            fastest = min(comp_mean.values())
            for c, m in comp_mean.items():
                offset_samples.setdefault(c, []).append(m - fastest)

        # Per-compound aggregates with empirical-Bayes shrinkage on the slope.
        slope_by_comp: dict[str, list[float]] = {}
        length_by_comp: dict[str, list[float]] = {}
        for s in usable:
            slope_by_comp.setdefault(s["compound"], []).append(float(s["degradation_slope"]))
            if s.get("pit_ended") and s.get("stint_length"):
                length_by_comp.setdefault(s["compound"], []).append(float(s["stint_length"]))

        compounds: dict[str, _CompoundFit] = {}
        observed = set(slope_by_comp) | set(offset_samples)
        for c in observed:
            slopes = slope_by_comp.get(c, [])
            n = len(slopes)
            sample_slope = statistics.fmean(slopes) if slopes else global_slope
            shrunk_slope = (n * sample_slope + _SHRINK_K * global_slope) / (n + _SHRINK_K)

            offsets = offset_samples.get(c, [])
            pace_offset = statistics.fmean(offsets) if offsets else _prior(c, "offset")

            lengths = length_by_comp.get(c, [])
            # p75 of planned stint lengths = "typical" before the cliff.
            typical = _percentile(lengths, 0.75) if lengths else _prior(c, "length")

            compounds[c] = _CompoundFit(
                compound=c,
                pace_offset=round(pace_offset, 4),
                deg_slope=round(shrunk_slope, 5),
                typical_length=round(typical, 1),
                n_stints=n,
            )

        # Ensure the three dry compounds always exist (fall back to priors).
        for c in DRY_COMPOUNDS:
            if c not in compounds:
                compounds[c] = _CompoundFit(
                    compound=c,
                    pace_offset=_prior(c, "offset"),
                    deg_slope=_prior(c, "slope"),
                    typical_length=_prior(c, "length"),
                    n_stints=0,
                    assumed=True,
                )

        return cls(
            compounds=compounds,
            global_slope=round(global_slope, 5),
            n_stints_total=len(usable),
            n_races=len(by_race),
        )

    # ── prediction ──────────────────────────────────────────────────────────

    def lap_time_delta(self, compound: str, tyre_age: int) -> float:
        """
        Modelled lap-time *delta* (seconds, relative to base_ref) for a tyre of
        the given compound at the given age in laps. Used to integrate stint cost.
        """
        fit = self.compounds.get(compound) or self.compounds.get("MEDIUM")
        if fit is None:  # pathological: nothing fitted at all
            return tyre_age * 0.06
        delta = fit.pace_offset + fit.deg_slope * tyre_age
        over = tyre_age - fit.typical_length
        if over > 0:
            delta += _CLIFF_PER_LAP_SQ * over * over
        return delta

    def stint_cost(self, compound: str, stint_length: int) -> float:
        """Cumulative modelled time (sum of lap deltas) for a stint of this length."""
        return sum(self.lap_time_delta(compound, age) for age in range(stint_length))

    def is_assumed(self, compound: str) -> bool:
        fit = self.compounds.get(compound)
        return fit.assumed if fit else True

    def summary(self) -> dict[str, Any]:
        """Compact, human-readable fit summary for reasoning_inputs / dataCoverage."""
        return {
            "nStints": self.n_stints_total,
            "nRaces": self.n_races,
            "globalSlope": self.global_slope,
            "compounds": {
                c: {
                    "paceOffsetS": f.pace_offset,
                    "degSlopeSPerLap": f.deg_slope,
                    "typicalStintLen": f.typical_length,
                    "nStints": f.n_stints,
                    "assumed": f.assumed,
                }
                for c, f in self.compounds.items()
            },
        }


# ── helpers ────────────────────────────────────────────────────────────────

def _prior(compound: str, key: str) -> float:
    return _COMPOUND_PRIORS.get(compound, _COMPOUND_PRIORS["MEDIUM"])[key]


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = q * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def resolve_pit_loss(profile: Optional[dict[str, Any]]) -> tuple[float, bool]:
    """
    Return (pit_loss_seconds, assumed). Uses the circuit's modelled
    pit_loss_baseline when present, else the global fallback.
    """
    if profile and profile.get("pit_loss_baseline") is not None:
        return float(profile["pit_loss_baseline"]), False
    return DEFAULT_PIT_LOSS_S, True
