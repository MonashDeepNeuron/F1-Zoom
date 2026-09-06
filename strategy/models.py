"""
Pydantic models for the pre-race Strategy Report feature.

Three groups live here:
  1. Enums shared across the module (ReportStage, Compound).
  2. Database-row models that mirror the new Supabase tables
     (DriverRaceStint, TrackStrategyProfile) — snake_case, matching columns.
  3. The StrategyOutput tree plus the API request/response models.

The StrategyOutput tree serialises to camelCase (headlineStrategy,
alternativeStrategies, …) so the persisted `report_json` and the API contract
match the field names given in the spec. Build instances with snake_case names
and dump with `by_alias=True` (the helper `to_report_json` does this).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


# ── Enums ────────────────────────────────────────────────────────────────

class ReportStage(str, Enum):
    """Stage of the weekend the report is generated for; drives input availability."""

    PRE_WEEKEND = "pre_weekend"
    POST_PRACTICE = "post_practice"
    POST_QUALIFYING = "post_qualifying"


class Compound(str, Enum):
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"


# Dry-weather slick compounds, softest → hardest. Used for plan enumeration.
DRY_COMPOUNDS: tuple[str, ...] = (Compound.SOFT.value, Compound.MEDIUM.value, Compound.HARD.value)


# ── Database-row models (snake_case, mirror Supabase columns) ─────────────

class DriverRaceStint(BaseModel):
    """One row of public.driver_race_stints."""

    race_event_id: int
    driver_id: str
    driver_race_entry_id: Optional[str] = None
    stint_index: int
    compound: str
    lap_window_start: int
    lap_window_end: int
    stint_length: int
    degradation_slope: Optional[float] = None
    clean_air_pace: Optional[float] = None
    traffic_share: Optional[float] = None
    gap_to_car_ahead: Optional[float] = None
    pit_ended: bool = False


class TrackStrategyProfile(BaseModel):
    """One row of public.track_strategy_profiles."""

    circuit_id: int
    overtaking_difficulty: Optional[float] = None
    track_position_importance: Optional[float] = None
    undercut_strength: Optional[float] = None
    pit_loss_baseline: Optional[float] = None
    sc_prior: Optional[float] = None
    vsc_prior: Optional[float] = None
    red_flag_prior: Optional[float] = None
    sample_races: Optional[int] = None


# ── StrategyOutput tree (camelCase on the wire) ───────────────────────────

class _CamelModel(BaseModel):
    """Base for everything that lands in report_json / the API body."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        ser_json_inf_nan="null",
    )


class PitWindow(_CamelModel):
    """A pit *window* (range of laps), not a single target lap."""

    stop_number: int = Field(description="1 for the first stop, 2 for the second, …")
    earliest_lap: int
    latest_lap: int
    target_lap: int = Field(description="Centre of the window; the modelled optimum.")
    in_compound: str = Field(description="Compound fitted at this stop.")


class StrategyPlan(_CamelModel):
    """A complete plan: compound sequence + the pit windows between stints."""

    num_stops: int
    compound_sequence: list[str]
    pit_windows: list[PitWindow]
    expected_race_time_s: float = Field(description="Mean modelled race time across Monte Carlo runs.")
    robustness_s: float = Field(description="Std dev of race time across scenarios; lower is more robust.")


class HeadlineStrategy(_CamelModel):
    num_stops: int
    compound_sequence: list[str]
    pit_windows: list[PitWindow]
    expected_race_time_s: float
    robustness_s: float
    reasoning_inputs: list[str] = Field(
        default_factory=list,
        description="Data-derived factors that drove this choice (deg, pit loss, SC prior, …).",
    )


class AlternativeStrategy(_CamelModel):
    num_stops: int
    compound_sequence: list[str]
    pit_windows: list[PitWindow]
    time_delta_s: float = Field(description="Modelled time lost vs the headline (optimal) plan, in seconds.")
    note: Optional[str] = None


class SafetyCarScenario(_CamelModel):
    window_label: str = Field(description="e.g. 'SC laps 10-20' or 'SC laps 30-40'.")
    deploy_lap_start: int
    deploy_lap_end: int
    recommended_action: str = Field(description="What the headline plan should do if SC deploys here.")
    time_swing_s: float = Field(description="Modelled net time gained (negative) or lost (positive) vs no SC.")
    changes_headline: bool = Field(description="True if the optimal plan changes under this scenario.")


class SafetyCarPlan(_CamelModel):
    scenarios: list[SafetyCarScenario] = Field(default_factory=list)
    summary: Optional[str] = None


class WeatherScenario(_CamelModel):
    rain_probability: float
    confidence_drop: float = Field(description="Drop in plan confidence (0..1) at this rain probability.")
    note: Optional[str] = None


class WeatherSensitivity(_CamelModel):
    base_rain_probability: float = Field(description="Rain probability assumed for the headline plan.")
    confidence_drop_if_rain: float = Field(description="Confidence drop if the forecast turns to rain.")
    scenarios: list[WeatherScenario] = Field(default_factory=list)
    note: Optional[str] = None


class Beneficiary(_CamelModel):
    grid_positions: str = Field(description="e.g. 'P1-P3', 'P6-P10', 'midfield'.")
    expected_gain: str = Field(description="Qualitative/quantitative gain, e.g. '+1.5 places on average'.")
    reason: str


class DataCoverage(_CamelModel):
    available_inputs: list[str] = Field(default_factory=list)
    assumed_inputs: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class StrategyOutput(_CamelModel):
    """Full structured simulator output. Persisted verbatim as report_json."""

    report_stage: ReportStage
    race_event_id: int
    model_version: str

    headline_strategy: HeadlineStrategy
    alternative_strategies: list[AlternativeStrategy] = Field(default_factory=list)
    safety_car_plan: SafetyCarPlan
    weather_sensitivity: WeatherSensitivity
    beneficiaries: list[Beneficiary] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)

    confidence: float = Field(ge=0.0, le=1.0)
    data_coverage: DataCoverage
    assumptions: list[str] = Field(default_factory=list)


def to_report_json(output: StrategyOutput) -> dict[str, Any]:
    """Serialise StrategyOutput to the camelCase dict stored in strategy_reports.report_json."""
    return output.model_dump(by_alias=True, mode="json")


# ── API request / response models ─────────────────────────────────────────

class WeatherForecastOverride(BaseModel):
    """Optional caller-supplied weather override for the simulation."""

    rain_probability: float = Field(ge=0.0, le=1.0)
    expected_conditions: Optional[str] = None


class StrategyRequest(BaseModel):
    """Body for POST /strategy/next-race."""

    race_event_id: int
    report_stage: ReportStage
    weather_forecast: Optional[WeatherForecastOverride] = None
    grid_penalties: Optional[dict[str, int]] = Field(
        default=None,
        description="Optional map of driver_code -> grid places dropped (known penalties).",
    )
    force_refresh: bool = Field(
        default=False,
        description="Bypass the input_hash cache and regenerate even if inputs are unchanged.",
    )


class StrategyReportResponse(_CamelModel):
    """Response for both POST and GET /strategy/next-race."""

    status: str
    race_event_id: int
    report_stage: ReportStage
    model_version: str
    generated_at: str
    cached: bool
    summary: Optional[str] = None
    report: Optional[StrategyOutput] = None
