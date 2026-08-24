"""Synthetic scalar traces for the separately simulable ADAPT-1 monitor."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .observables import ObservableContractError, observable_spec
from .references import CommittedReference, ReferenceContractError, parse_canonical_utc


class TraceContractError(ValueError):
    """Raised when a trace violates its structural or time contract."""


def _trace_timestamp(value: object, field_name: str) -> datetime:
    try:
        return parse_canonical_utc(value, field_name)
    except ReferenceContractError as exc:
        raise TraceContractError(str(exc)) from exc


def _format_utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class ChannelStateTrace:
    """One monitorable observable sampled at an exact integer-microsecond cadence.

    ``window_end_utc`` is the inclusive timestamp of the final retained sample.
    """

    trace_id: str
    link_id: str
    observable_name: str
    window_start_utc: str
    window_end_utc: str
    sample_interval_us: int
    values: tuple[float, ...]
    provenance: str = "synthetic"

    def __post_init__(self) -> None:
        for name in ("trace_id", "link_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise TraceContractError(f"{name} must be a non-empty string.")
        try:
            observable_spec(self.observable_name, require_monitorable=True)
        except ObservableContractError as exc:
            raise TraceContractError(str(exc)) from exc
        start = _trace_timestamp(self.window_start_utc, "window_start_utc")
        end = _trace_timestamp(self.window_end_utc, "window_end_utc")
        if isinstance(self.sample_interval_us, bool) or not isinstance(self.sample_interval_us, int):
            raise TraceContractError("sample_interval_us must be an integer.")
        if self.sample_interval_us < 1:
            raise TraceContractError("sample_interval_us must be at least 1.")
        if not isinstance(self.values, tuple) or not self.values:
            raise TraceContractError("values must be a non-empty tuple[float, ...].")
        normalized = []
        for index, value in enumerate(self.values):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TraceContractError(f"values[{index}] must be a real number.")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise TraceContractError(f"values[{index}] must be finite.")
            normalized.append(numeric)
        object.__setattr__(self, "values", tuple(normalized))
        if self.provenance != "synthetic":
            raise TraceContractError("ADAPT-1 provenance must be 'synthetic'.")
        expected_end = start + timedelta(
            microseconds=(len(self.values) - 1) * self.sample_interval_us
        )
        if end != expected_end:
            raise TraceContractError(
                "window_end_utc must equal the inclusive final-sample timestamp: "
                "window_start_utc + (len(values)-1)*sample_interval_us."
            )


def _rng(seed: int) -> np.random.Generator:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise TraceContractError("seed must be a non-negative integer.")
    return np.random.default_rng(seed)


def _draw_values(
    reference: CommittedReference,
    rng: np.random.Generator,
    *,
    n_steps: int,
    f_true: float,
    q_true: float,
    r_true: float,
) -> np.ndarray:
    if n_steps < 1:
        raise TraceContractError("n_steps must be positive.")
    if abs(f_true) >= 1.0:
        raise TraceContractError("synthetic generators require |f_true| < 1.")
    if q_true < 0.0 or r_true < 0.0:
        raise TraceContractError("synthetic variances must be non-negative.")
    model = reference.model
    stationary_variance = q_true / (1.0 - f_true * f_true)
    state = float(rng.normal(0.0, math.sqrt(stationary_variance)))
    values = np.empty(n_steps, dtype=float)
    for index in range(n_steps):
        state = f_true * state + float(rng.normal(0.0, math.sqrt(q_true)))
        noise = float(rng.normal(0.0, math.sqrt(r_true)))
        values[index] = model.h * state + noise
    return values


def _trace(
    reference: CommittedReference,
    values: np.ndarray,
    *,
    trace_id: str,
    link_id: str,
    window_start_utc: str,
    sample_interval_us: int,
) -> ChannelStateTrace:
    start = _trace_timestamp(window_start_utc, "window_start_utc")
    end = start + timedelta(microseconds=(len(values) - 1) * sample_interval_us)
    return ChannelStateTrace(
        trace_id=trace_id,
        link_id=link_id,
        observable_name=reference.observable_name,
        window_start_utc=window_start_utc,
        window_end_utc=_format_utc(end),
        sample_interval_us=sample_interval_us,
        values=tuple(float(value) for value in values),
    )


def generate_reference_consistent_trace(
    reference: CommittedReference,
    *,
    trace_id: str,
    link_id: str,
    window_start_utc: str,
    sample_interval_us: int,
    seed: int,
    n_steps: int | None = None,
) -> ChannelStateTrace:
    """Draw a trace from the committed scalar reference law."""

    count = reference.calibration.effective_n if n_steps is None else n_steps
    model = reference.model
    values = _draw_values(
        reference,
        _rng(seed),
        n_steps=count,
        f_true=model.f,
        q_true=model.q,
        r_true=model.r,
    )
    return _trace(
        reference,
        values,
        trace_id=trace_id,
        link_id=link_id,
        window_start_utc=window_start_utc,
        sample_interval_us=sample_interval_us,
    )


def generate_matched_law_trace(**kwargs) -> ChannelStateTrace:
    """Draw an independent same-law replacement trace, never a recorded replay."""

    return generate_reference_consistent_trace(**kwargs)


def generate_variance_inflated_trace(
    reference: CommittedReference,
    *,
    r_factor: float,
    trace_id: str,
    link_id: str,
    window_start_utc: str,
    sample_interval_us: int,
    seed: int,
    n_steps: int | None = None,
) -> ChannelStateTrace:
    """Draw from the reference dynamics with scaled observation-noise variance."""

    if not math.isfinite(r_factor) or r_factor <= 0.0:
        raise TraceContractError("r_factor must be finite and strictly positive.")
    count = reference.calibration.effective_n if n_steps is None else n_steps
    model = reference.model
    values = _draw_values(
        reference,
        _rng(seed),
        n_steps=count,
        f_true=model.f,
        q_true=model.q,
        r_true=model.r * r_factor,
    )
    return _trace(
        reference,
        values,
        trace_id=trace_id,
        link_id=link_id,
        window_start_utc=window_start_utc,
        sample_interval_us=sample_interval_us,
    )


def generate_law_shifted_trace(
    reference: CommittedReference,
    *,
    f_true: float,
    trace_id: str,
    link_id: str,
    window_start_utc: str,
    sample_interval_us: int,
    seed: int,
    n_steps: int | None = None,
) -> ChannelStateTrace:
    """Draw wrong dynamics while preserving the reference state marginal variance."""

    model = reference.model
    if abs(model.f) >= 1.0:
        raise TraceContractError("law-shift generator requires a stationary reference model.")
    if not math.isfinite(f_true) or abs(f_true) >= 1.0:
        raise TraceContractError("f_true must be finite with |f_true| < 1.")
    stationary_variance = model.q / (1.0 - model.f * model.f)
    q_true = stationary_variance * (1.0 - f_true * f_true)
    count = reference.calibration.effective_n if n_steps is None else n_steps
    values = _draw_values(
        reference,
        _rng(seed),
        n_steps=count,
        f_true=f_true,
        q_true=q_true,
        r_true=model.r,
    )
    return _trace(
        reference,
        values,
        trace_id=trace_id,
        link_id=link_id,
        window_start_utc=window_start_utc,
        sample_interval_us=sample_interval_us,
    )


def generate_quasiperiodic_drift_trace(
    reference: CommittedReference,
    *,
    amplitude: float,
    step_deg: float,
    trace_id: str,
    link_id: str,
    window_start_utc: str,
    sample_interval_us: int,
    seed: int,
    n_steps: int | None = None,
) -> ChannelStateTrace:
    """Add a deterministic phase rotation to a seeded reference-law trace."""

    if not math.isfinite(amplitude) or amplitude < 0.0:
        raise TraceContractError("amplitude must be finite and non-negative.")
    if not math.isfinite(step_deg):
        raise TraceContractError("step_deg must be finite.")
    count = reference.calibration.effective_n if n_steps is None else n_steps
    generator = _rng(seed)
    phase = float(generator.uniform(0.0, 1.0))
    model = reference.model
    values = _draw_values(
        reference,
        generator,
        n_steps=count,
        f_true=model.f,
        q_true=model.q,
        r_true=model.r,
    )
    step_cycles = step_deg / 360.0
    indices = np.arange(count, dtype=float)
    values += amplitude * np.sin(2.0 * math.pi * (phase + indices * step_cycles))
    return _trace(
        reference,
        values,
        trace_id=trace_id,
        link_id=link_id,
        window_start_utc=window_start_utc,
        sample_interval_us=sample_interval_us,
    )


__all__ = [
    "ChannelStateTrace",
    "TraceContractError",
    "generate_law_shifted_trace",
    "generate_matched_law_trace",
    "generate_quasiperiodic_drift_trace",
    "generate_reference_consistent_trace",
    "generate_variance_inflated_trace",
]
