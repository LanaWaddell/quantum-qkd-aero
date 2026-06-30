"""Mission-level composition for the verified Phase 2B physics modules.

This module owns composition only: channel-state profiles -> decoy BB84 ->
background coherence -> teleportation fidelity, with satellite pass geometry as
one caller. It introduces no new physics and performs no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from qkd.bb84 import run_decoy_bb84
from qkd.channel import channel_state
from qkd.coherence import effective_werner_p_for_sky
from qkd.fibre import DEFAULT_FIBRE, fibre_channel_state
from qkd.orbit import satellite_pass
from qkd.provenance import Provenance
from qkd.signals import ChannelState, DetectorParams
from qkd.teleportation import teleportation_fidelity


PULSE_REPETITION_RATE_HZ = 1.0e8
"""Illustrative transmitter clock rate in pulses/s.

This is a hardware-layer parameter, not a physical constant. It is held fixed
for mission calculations so future optimization cannot trivially improve yield
by increasing the transmitter clock.
"""

INTENSITIES = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
DEFAULT_N_PULSES = 1_000_000
DEFAULT_SKY_CONDITION = "night"


def _default_fibre_lengths() -> list[float]:
    return [float(length_km) for length_km in range(0, 221, 5)]


def _default_detector() -> DetectorParams:
    return DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0e-6)


@dataclass(frozen=True)
class MissionConfig:
    """Small bundle of illustrative inputs for the default pass composition."""

    samples: int = 1000
    altitude_km: float = 550.0
    peak_elevation_deg: float = 90.0
    horizon_elevation_deg: float = 10.0
    atmosphere: dict | None = None
    detector: DetectorParams = field(default_factory=_default_detector)
    intensities: dict[str, float] = field(default_factory=lambda: dict(INTENSITIES))
    n_pulses: int = DEFAULT_N_PULSES
    pulse_repetition_rate_hz: float = PULSE_REPETITION_RATE_HZ
    sky_condition: str = DEFAULT_SKY_CONDITION


@dataclass(frozen=True)
class FibreSweepConfig:
    """Illustrative inputs for a dark-fibre length sweep."""

    lengths_km: list[float] = field(default_factory=_default_fibre_lengths)
    fibre: dict | None = None
    detector: DetectorParams = field(default_factory=_default_detector)
    intensities: dict[str, float] = field(default_factory=lambda: dict(INTENSITIES))
    n_pulses: int = DEFAULT_N_PULSES
    pulse_repetition_rate_hz: float = PULSE_REPETITION_RATE_HZ


@dataclass(frozen=True)
class PassResult:
    time_s: list[float]
    elevation_deg: list[float]
    slant_range_km: list[float]
    transmittance: list[float]
    loss_db: list[float]
    secure_key_rate_per_pulse: list[float]
    effective_werner_p: list[float]
    fidelity: list[float]
    min_loss_db: float
    min_loss_index: int
    secure_key_yield_bits: float
    mean_fidelity: float
    classical_bound: float
    werner_p_source: float
    pulse_repetition_rate_hz: float
    mission: dict[str, object]
    provenance: dict[str, str]


@dataclass(frozen=True)
class SecureDistanceBracket:
    last_positive_length_km: float | None
    last_positive_secure_key_rate_per_pulse: float | None
    first_non_positive_length_km: float | None
    first_non_positive_secure_key_rate_per_pulse: float | None


@dataclass(frozen=True)
class FibreSweepResult:
    length_km: list[float]
    transmittance: list[float]
    loss_db: list[float]
    secure_key_rate_per_pulse: list[float]
    effective_werner_p: list[float]
    fidelity: list[float]
    min_loss_db: float
    min_loss_index: int
    secure_key_yield_bits: float
    mean_fidelity: float
    classical_bound: float
    werner_p_source: float
    pulse_repetition_rate_hz: float
    max_secure_distance_km: float | None
    secure_distance_bracket: SecureDistanceBracket
    mission: dict[str, object]
    provenance: dict[str, str]


@dataclass(frozen=True)
class ProfileResult:
    axis_values: list[float]
    transmittance: list[float]
    loss_db: list[float]
    secure_key_rate_per_pulse: list[float]
    effective_werner_p: list[float]
    fidelity: list[float]
    min_loss_db: float
    min_loss_index: int
    secure_key_yield_bits: float
    mean_fidelity: float
    classical_bound: float
    werner_p_source: float
    pulse_repetition_rate_hz: float


def simulate_pass(config: MissionConfig | None = None, *, eve=None) -> PassResult:
    """Compose the honest pass from already-verified module functions."""

    if eve is not None:
        raise NotImplementedError("Eve injection is out of scope for Phase 2B-6b.")

    cfg = config or MissionConfig()
    _validate_config(cfg)

    pass_geometry = satellite_pass(
        samples=cfg.samples,
        altitude_km=cfg.altitude_km,
        peak_elevation_deg=cfg.peak_elevation_deg,
        horizon_elevation_deg=cfg.horizon_elevation_deg,
    )
    channel_states = [
        channel_state(
            elevation_deg=elevation_deg,
            slant_range_km=slant_range_km,
            atmosphere=cfg.atmosphere,
        )
        for elevation_deg, slant_range_km in zip(
            pass_geometry.elevation_deg,
            pass_geometry.slant_range_km,
        )
    ]

    profile = simulate_profile(
        pass_geometry.time_s,
        channel_states,
        intensities=cfg.intensities,
        n_pulses=cfg.n_pulses,
        detector=cfg.detector,
        pulse_repetition_rate_hz=cfg.pulse_repetition_rate_hz,
        sky_condition=cfg.sky_condition,
    )

    return _pass_result_from_profile(pass_geometry, profile, cfg)


def simulate_fibre_sweep(config: FibreSweepConfig | None = None) -> FibreSweepResult:
    """Compose a dark-fibre length sweep using the medium-neutral profile core."""

    cfg = config or FibreSweepConfig()
    _validate_fibre_config(cfg)

    fibre_config = _resolved_fibre_config(cfg)
    channel_states = [
        fibre_channel_state(length_km, fibre=fibre_config)
        for length_km in cfg.lengths_km
    ]
    profile = simulate_profile(
        cfg.lengths_km,
        channel_states,
        intensities=cfg.intensities,
        n_pulses=cfg.n_pulses,
        detector=cfg.detector,
        pulse_repetition_rate_hz=cfg.pulse_repetition_rate_hz,
        sky_condition=DEFAULT_SKY_CONDITION,
    )

    return _fibre_result_from_profile(profile, cfg, fibre_config)


def simulate_profile(
    axis_values: list[float],
    channel_states: list[ChannelState],
    *,
    intensities: dict[str, float],
    n_pulses: int,
    detector: DetectorParams,
    pulse_repetition_rate_hz: float,
    sky_condition: str,
) -> ProfileResult:
    """Compose an honest medium-neutral channel-state profile."""

    if len(axis_values) != len(channel_states):
        raise ValueError("axis_values and channel_states must have the same length.")
    if not channel_states:
        raise ValueError("axis_values and channel_states must be non-empty.")

    werner_p_source = _single_werner_source(channel_states)
    transmittance = [state.transmittance for state in channel_states]
    loss_db = [_channel_loss_db(eta) for eta in transmittance]
    min_loss_index = min(range(len(loss_db)), key=loss_db.__getitem__)
    min_loss_db = loss_db[min_loss_index]

    bb84_results = [
        run_decoy_bb84(
            state,
            intensities,
            n_pulses,
            detector,
            eve=None,
        )
        for state in channel_states
    ]
    secure_key_rate_per_pulse = [result.secure_key_rate for result in bb84_results]

    effective_werner_p = [
        effective_werner_p_for_sky(
            eta,
            werner_p_source,
            detector.detection_efficiency,
            sky_condition=sky_condition,
        )
        for eta in transmittance
    ]
    teleportation_results = [teleportation_fidelity(p_eff) for p_eff in effective_werner_p]
    fidelity = [result.fidelity for result in teleportation_results]
    classical_bound = teleportation_results[0].classical_bound

    secure_key_yield_bits = _integrate_yield_bits(
        axis_values,
        secure_key_rate_per_pulse,
        pulse_repetition_rate_hz,
    )
    mean_fidelity = sum(fidelity) / len(fidelity)

    return ProfileResult(
        axis_values=list(axis_values),
        transmittance=transmittance,
        loss_db=loss_db,
        secure_key_rate_per_pulse=secure_key_rate_per_pulse,
        effective_werner_p=effective_werner_p,
        fidelity=fidelity,
        min_loss_db=min_loss_db,
        min_loss_index=min_loss_index,
        secure_key_yield_bits=secure_key_yield_bits,
        mean_fidelity=mean_fidelity,
        classical_bound=classical_bound,
        werner_p_source=werner_p_source,
        pulse_repetition_rate_hz=pulse_repetition_rate_hz,
    )


def _pass_result_from_profile(
    pass_geometry,
    profile: ProfileResult,
    config: MissionConfig,
) -> PassResult:
    return PassResult(
        time_s=profile.axis_values,
        elevation_deg=pass_geometry.elevation_deg,
        slant_range_km=pass_geometry.slant_range_km,
        transmittance=profile.transmittance,
        loss_db=profile.loss_db,
        secure_key_rate_per_pulse=profile.secure_key_rate_per_pulse,
        effective_werner_p=profile.effective_werner_p,
        fidelity=profile.fidelity,
        min_loss_db=profile.min_loss_db,
        min_loss_index=profile.min_loss_index,
        secure_key_yield_bits=profile.secure_key_yield_bits,
        mean_fidelity=profile.mean_fidelity,
        classical_bound=profile.classical_bound,
        werner_p_source=profile.werner_p_source,
        pulse_repetition_rate_hz=profile.pulse_repetition_rate_hz,
        mission=_mission_inputs(config),
        provenance=_default_provenance(),
    )


def _fibre_result_from_profile(
    profile: ProfileResult,
    config: FibreSweepConfig,
    fibre_config: dict,
) -> FibreSweepResult:
    bracket = _secure_distance_bracket(
        profile.axis_values,
        profile.secure_key_rate_per_pulse,
    )
    return FibreSweepResult(
        length_km=profile.axis_values,
        transmittance=profile.transmittance,
        loss_db=profile.loss_db,
        secure_key_rate_per_pulse=profile.secure_key_rate_per_pulse,
        effective_werner_p=profile.effective_werner_p,
        fidelity=profile.fidelity,
        min_loss_db=profile.min_loss_db,
        min_loss_index=profile.min_loss_index,
        secure_key_yield_bits=profile.secure_key_yield_bits,
        mean_fidelity=profile.mean_fidelity,
        classical_bound=profile.classical_bound,
        werner_p_source=profile.werner_p_source,
        pulse_repetition_rate_hz=profile.pulse_repetition_rate_hz,
        max_secure_distance_km=bracket.last_positive_length_km,
        secure_distance_bracket=bracket,
        mission=_fibre_mission_inputs(config, fibre_config),
        provenance=_fibre_provenance(),
    )


def _validate_config(config: MissionConfig) -> None:
    if config.n_pulses < 0:
        raise ValueError("n_pulses must be non-negative.")
    if config.pulse_repetition_rate_hz < 0.0:
        raise ValueError("pulse_repetition_rate_hz must be non-negative.")


def _validate_fibre_config(config: FibreSweepConfig) -> None:
    if len(config.lengths_km) < 2:
        raise ValueError("lengths_km must contain at least two samples.")
    if any(length_km < 0.0 for length_km in config.lengths_km):
        raise ValueError("lengths_km must be non-negative.")
    if any(
        current <= previous
        for previous, current in zip(config.lengths_km, config.lengths_km[1:])
    ):
        raise ValueError("lengths_km must be strictly increasing.")
    if config.n_pulses < 0:
        raise ValueError("n_pulses must be non-negative.")
    if config.pulse_repetition_rate_hz < 0.0:
        raise ValueError("pulse_repetition_rate_hz must be non-negative.")


def _resolved_fibre_config(config: FibreSweepConfig) -> dict:
    fibre_config = dict(DEFAULT_FIBRE)
    if config.fibre:
        fibre_config.update(config.fibre)
    return fibre_config


def _single_werner_source(channel_states) -> float:
    werner_p_source = channel_states[0].werner_p
    for state in channel_states[1:]:
        if not math.isclose(state.werner_p, werner_p_source, rel_tol=0.0, abs_tol=1e-15):
            raise ValueError("werner_p_source must remain a single channel/source constant.")
    return werner_p_source


def _channel_loss_db(eta: float) -> float:
    if eta <= 0.0:
        return math.inf
    return -10.0 * math.log10(eta)


def _integrate_yield_bits(
    time_s: list[float],
    secure_key_rate_per_pulse: list[float],
    pulse_repetition_rate_hz: float,
) -> float:
    if len(time_s) < 2:
        return 0.0
    sample_width_s = (time_s[-1] - time_s[0]) / (len(time_s) - 1)
    return sum(
        rate * pulse_repetition_rate_hz * sample_width_s
        for rate in secure_key_rate_per_pulse
    )


def _secure_distance_bracket(
    lengths_km: list[float],
    secure_key_rate_per_pulse: list[float],
) -> SecureDistanceBracket:
    positive_indices = [
        index
        for index, rate in enumerate(secure_key_rate_per_pulse)
        if rate > 0.0
    ]
    if not positive_indices:
        return SecureDistanceBracket(None, None, lengths_km[0], secure_key_rate_per_pulse[0])

    last_positive_index = positive_indices[-1]
    first_non_positive_index = next(
        (
            index
            for index in range(last_positive_index + 1, len(secure_key_rate_per_pulse))
            if secure_key_rate_per_pulse[index] <= 0.0
        ),
        None,
    )

    return SecureDistanceBracket(
        last_positive_length_km=lengths_km[last_positive_index],
        last_positive_secure_key_rate_per_pulse=secure_key_rate_per_pulse[last_positive_index],
        first_non_positive_length_km=(
            None if first_non_positive_index is None else lengths_km[first_non_positive_index]
        ),
        first_non_positive_secure_key_rate_per_pulse=(
            None
            if first_non_positive_index is None
            else secure_key_rate_per_pulse[first_non_positive_index]
        ),
    )


def _mission_inputs(config: MissionConfig) -> dict[str, object]:
    return {
        "pulse_repetition_rate_hz": config.pulse_repetition_rate_hz,
        "intensities": dict(config.intensities),
        "detector": {
            "detection_efficiency": config.detector.detection_efficiency,
            "dark_count_prob": config.detector.dark_count_prob,
            "error_correction_efficiency": config.detector.error_correction_efficiency,
        },
        "sky_condition": config.sky_condition,
    }


def _fibre_mission_inputs(
    config: FibreSweepConfig,
    fibre_config: dict,
) -> dict[str, object]:
    return {
        "pulse_repetition_rate_hz": config.pulse_repetition_rate_hz,
        "intensities": dict(config.intensities),
        "detector": {
            "detection_efficiency": config.detector.detection_efficiency,
            "dark_count_prob": config.detector.dark_count_prob,
            "error_correction_efficiency": config.detector.error_correction_efficiency,
        },
        "sky_condition": DEFAULT_SKY_CONDITION,
        "fibre": dict(fibre_config),
    }


def _default_provenance() -> dict[str, str]:
    return {
        "link.medium": Provenance.ILLUSTRATIVE.value,
        "link.topology": Provenance.ILLUSTRATIVE.value,
        "link.protocol": Provenance.ILLUSTRATIVE.value,
        "teleportation.frames": Provenance.DERIVED.value,
        "teleportation.average_fidelity": Provenance.DERIVED.value,
        "teleportation.classical_limit": Provenance.ANALYTIC.value,
        "teleportation.plot": Provenance.DERIVED.value,
        "summary.headline_key_yield": Provenance.DERIVED.value,
        "summary.headline_fidelity": Provenance.DERIVED.value,
        "profile.axis.name": Provenance.ILLUSTRATIVE.value,
        "profile.axis.values": Provenance.SIMULATED.value,
        "profile.transmittance": Provenance.SIMULATED.value,
        "profile.loss_db": Provenance.DERIVED.value,
        "profile.secure_key_rate_per_pulse": Provenance.SIMULATED.value,
        "profile.effective_werner_p": Provenance.SIMULATED.value,
        "profile.fidelity": Provenance.SIMULATED.value,
        "profile.aggregates.min_loss_db": Provenance.DERIVED.value,
        "profile.aggregates.min_loss_axis_value": Provenance.DERIVED.value,
        "profile.aggregates.secure_key_yield_bits": Provenance.DERIVED.value,
        "profile.aggregates.mean_fidelity": Provenance.DERIVED.value,
        "geometry.elevation_deg": Provenance.SIMULATED.value,
        "geometry.slant_range_km": Provenance.SIMULATED.value,
        "geometry.min_loss.elevation_deg": Provenance.DERIVED.value,
        "geometry.min_loss.slant_range_km": Provenance.DERIVED.value,
        "mission.pulse_repetition_rate_hz": Provenance.ILLUSTRATIVE.value,
        "mission.intensities.signal": Provenance.ILLUSTRATIVE.value,
        "mission.intensities.decoy": Provenance.ILLUSTRATIVE.value,
        "mission.intensities.vacuum": Provenance.ILLUSTRATIVE.value,
        "mission.detector.detection_efficiency": Provenance.ILLUSTRATIVE.value,
        "mission.detector.dark_count_prob": Provenance.ILLUSTRATIVE.value,
        "mission.detector.error_correction_efficiency": Provenance.ILLUSTRATIVE.value,
        "mission.sky_condition": Provenance.ILLUSTRATIVE.value,
    }


def _fibre_provenance() -> dict[str, str]:
    return {
        "link.medium": Provenance.ILLUSTRATIVE.value,
        "link.topology": Provenance.ILLUSTRATIVE.value,
        "link.protocol": Provenance.ILLUSTRATIVE.value,
        "teleportation.frames": Provenance.DERIVED.value,
        "teleportation.average_fidelity": Provenance.DERIVED.value,
        "teleportation.classical_limit": Provenance.ANALYTIC.value,
        "teleportation.plot": Provenance.DERIVED.value,
        "summary.headline_key_yield": Provenance.DERIVED.value,
        "summary.headline_fidelity": Provenance.DERIVED.value,
        "summary.headline_max_secure_distance": Provenance.DERIVED.value,
        "profile.axis.name": Provenance.ILLUSTRATIVE.value,
        "profile.axis.values": Provenance.SIMULATED.value,
        "profile.transmittance": Provenance.SIMULATED.value,
        "profile.loss_db": Provenance.DERIVED.value,
        "profile.secure_key_rate_per_pulse": Provenance.SIMULATED.value,
        "profile.effective_werner_p": Provenance.SIMULATED.value,
        "profile.fidelity": Provenance.SIMULATED.value,
        "profile.aggregates.min_loss_db": Provenance.DERIVED.value,
        "profile.aggregates.min_loss_axis_value": Provenance.DERIVED.value,
        "profile.aggregates.secure_key_yield_bits": Provenance.DERIVED.value,
        "profile.aggregates.mean_fidelity": Provenance.DERIVED.value,
        "profile.aggregates.max_secure_distance_km": Provenance.DERIVED.value,
        "profile.aggregates.secure_distance_bracket.last_positive_length_km": (
            Provenance.DERIVED.value
        ),
        "profile.aggregates.secure_distance_bracket.last_positive_secure_key_rate_per_pulse": (
            Provenance.DERIVED.value
        ),
        "profile.aggregates.secure_distance_bracket.first_non_positive_length_km": (
            Provenance.DERIVED.value
        ),
        "profile.aggregates.secure_distance_bracket.first_non_positive_secure_key_rate_per_pulse": (
            Provenance.DERIVED.value
        ),
        "mission.pulse_repetition_rate_hz": Provenance.ILLUSTRATIVE.value,
        "mission.intensities.signal": Provenance.ILLUSTRATIVE.value,
        "mission.intensities.decoy": Provenance.ILLUSTRATIVE.value,
        "mission.intensities.vacuum": Provenance.ILLUSTRATIVE.value,
        "mission.detector.detection_efficiency": Provenance.ILLUSTRATIVE.value,
        "mission.detector.dark_count_prob": Provenance.ILLUSTRATIVE.value,
        "mission.detector.error_correction_efficiency": Provenance.ILLUSTRATIVE.value,
        "mission.sky_condition": Provenance.ILLUSTRATIVE.value,
        "mission.fibre.attenuation_db_km": Provenance.ILLUSTRATIVE.value,
        "mission.fibre.fixed_loss_db": Provenance.ILLUSTRATIVE.value,
        "mission.fibre.intrinsic_qber": Provenance.ILLUSTRATIVE.value,
        "mission.fibre.dark_count_prob": Provenance.ILLUSTRATIVE.value,
        "mission.fibre.werner_p": Provenance.ILLUSTRATIVE.value,
    }
