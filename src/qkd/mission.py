"""Mission-level composition for the verified Phase 2B physics modules.

This module owns composition only: channel-state profiles -> decoy BB84 ->
background coherence -> teleportation fidelity, with satellite pass geometry as
one caller. It introduces no new physics and performs no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from qkd.bb84 import run_decoy_bb84
from qkd.channel import channel_state, resolved_atmosphere_config
from qkd.coherence import effective_werner_p_for_sky
from qkd.detection import (
    GateWindowRequiredError,
    LinkModeError,
    PdtConfig,
    ReceiverEveNotSupportedError,
    ReceiverInputs,
    ReceiverModel,
    _assert_pdt_memory_invariant,
    classify_and_order_pdt_stack,
    compute_receiver_block,
    compute_receiver_block_pdt,
    extract_receiver_inputs,
    validate_grid_and_block_duration,
    validate_pdt_guards,
)
from qkd.effects import (
    AtmosphericAbsorptionEffect,
    DetectorQuantumEfficiencyEffect,
    GeometricLossEffect,
    SystemEfficiencyEffect,
)
from qkd.fibre import DEFAULT_FIBRE, fibre_channel_state
from qkd.link import (
    ChannelEffect,
    ChannelStack,
    ControlBoundsError,
    DuplicateControlNameError,
    TableGeometryProvider,
    UndeclaredControlError,
    apply_link_state,
)
from qkd.orbit import satellite_pass
from qkd.provenance import Provenance
from qkd.replay import build_manifest
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
class LinkReceiverProfile:
    """The ``profile.link_receiver`` diagnostic extension (plan Appendix A.3.2)."""

    secure_key_rate_per_signal_pulse: list[float]
    availability: list[float]
    pi: tuple[float, float, float]


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
    link_receiver: LinkReceiverProfile | None = None
    link_provenance: str | None = None


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
    secure_key_yield_bits: float | None
    mean_fidelity: float
    classical_bound: float
    werner_p_source: float
    pulse_repetition_rate_hz: float
    link_receiver: LinkReceiverProfile | None = None


def simulate_pass(
    config: MissionConfig | None = None,
    *,
    eve=None,
    link_effects: Sequence[ChannelEffect] | None = None,
    link_seed: int | None = None,
    link_controls: Mapping[str, float] | None = None,
    receiver: ReceiverModel | None = None,
    link_mode: str = "sampled",
    pdt_config: PdtConfig | None = None,
) -> PassResult:
    """Compose the honest pass from already-verified module functions.

    **LINK-6a activation (plan §3.1, frozen surface).** ``receiver``,
    ``link_mode``, and ``pdt_config`` are keyword-only additions, all
    defaulting to inactive. ``receiver=None`` (the default) is the legacy
    path below, **byte-identical** -- no new LINK-6a code executes on it.
    ``receiver=ReceiverModel(...)`` activates the §1 receiver chain;
    ``link_mode="pdt"`` additionally requires ``pdt_config`` and consumes
    the PDT chain (plan §5).

    **Stack-always (LINK-2, ``docs/LINK_2_PLAN.md`` §5, binding).** The
    existing satellite system/atmospheric/geometric/detector-efficiency
    factors are themselves migrated production ``ChannelEffect``s
    (:mod:`qkd.effects`), assembled by :func:`_production_link_effects` in a
    parity-pinned order and evaluated through the LINK-1 bridge
    (``qkd.link.apply_link_state``) on every call -- there is no longer a
    separate non-stack code path. ``link_effects`` (LINK-1's opt-in seam,
    ADR-0003 §3.6/§7.1) supplies *additional* user effects appended after
    the four production effects; ``link_effects=None`` (the default) and
    ``link_effects=[]`` both mean "production effects only" and are
    byte-identical to each other and to pre-LINK-2 default behaviour (LINK-2
    plan §2.2, certified by ``tests/test_effects.py`` test 1's in-process
    parity oracle). A user effect whose ``effect_id`` collides with one of
    the four reserved production ids fails via LINK-1's existing
    ``DuplicateEffectIdError``.

    Flow: builds its one ``SatellitePass`` exactly as before; wraps that
    exact object in ``qkd.link.TableGeometryProvider`` (no second geometry
    object, R2); resolves atmosphere configuration via the single shared
    ``qkd.channel.resolved_atmosphere_config`` resolver; assembles the
    production effects plus any user ``link_effects`` into one
    ``qkd.link.ChannelStack``; builds base channel states via
    ``channel_state(..., eta_override=1.0)`` and a base detector via
    ``dataclasses.replace(cfg.detector, detection_efficiency=1.0)`` so the
    stack's left-associated product folds onto an identity base
    (``1.0 * x == x`` exactly); evaluates the stack once per existing pass
    sample with an explicit ``sample_index``; folds via the unchanged
    ``apply_link_state``; and continues through the unchanged
    profile/result/emission pipeline.
    """

    if eve is not None:
        if receiver is not None:
            raise ReceiverEveNotSupportedError(
                "receiver and eve are mutually exclusive in LINK-6a (plan §1.2); "
                "receiver-aware Eve integration is a later PR."
            )
        raise NotImplementedError("Eve injection is out of scope for Phase 2B-6b.")

    if link_mode not in ("sampled", "pdt"):
        raise LinkModeError(f"link_mode must be 'sampled' or 'pdt'; got {link_mode!r}.")
    if link_mode == "pdt":
        if receiver is None:
            raise LinkModeError("link_mode='pdt' requires receiver to be provided (plan §3.1).")
        if pdt_config is None:
            raise LinkModeError("link_mode='pdt' requires pdt_config to be provided (plan §3.1).")
    elif pdt_config is not None:
        raise LinkModeError("pdt_config is only valid when link_mode='pdt' (plan §3.1).")

    cfg = config or MissionConfig()
    _validate_config(cfg)

    pass_geometry = satellite_pass(
        samples=cfg.samples,
        altitude_km=cfg.altitude_km,
        peak_elevation_deg=cfg.peak_elevation_deg,
        horizon_elevation_deg=cfg.horizon_elevation_deg,
    )

    resolved_atmosphere = resolved_atmosphere_config(cfg.atmosphere)
    provider = TableGeometryProvider(pass_geometry)
    effects: list[ChannelEffect] = _production_link_effects(
        resolved_atmosphere, cfg.detector
    ) + list(link_effects or [])

    if receiver is None:
        # ---- Legacy path (byte-identical; plan §3.1 rule 1). ----
        stack = ChannelStack(effects, provider, seed=link_seed)

        base_channel_states = [
            channel_state(
                elevation_deg=elevation_deg,
                slant_range_km=slant_range_km,
                atmosphere=cfg.atmosphere,
                eta_override=1.0,
            )
            for elevation_deg, slant_range_km in zip(
                pass_geometry.elevation_deg,
                pass_geometry.slant_range_km,
            )
        ]
        base_detector = replace(cfg.detector, detection_efficiency=1.0)

        channel_states, detector = _apply_link_stack(
            pass_geometry=pass_geometry,
            stack=stack,
            channel_states=base_channel_states,
            detector=base_detector,
            link_controls=link_controls,
        )

        profile = simulate_profile(
            pass_geometry.time_s,
            channel_states,
            intensities=cfg.intensities,
            n_pulses=cfg.n_pulses,
            detector=detector,
            pulse_repetition_rate_hz=cfg.pulse_repetition_rate_hz,
            sky_condition=cfg.sky_condition,
        )

        return _pass_result_from_profile(pass_geometry, profile, cfg)

    # ---- Receiver-active path (LINK-6a, plan §1-§5). ----
    return _simulate_pass_receiver_active(
        cfg=cfg,
        pass_geometry=pass_geometry,
        resolved_atmosphere=resolved_atmosphere,
        provider=provider,
        effects=effects,
        link_effects=list(link_effects or []),
        link_seed=link_seed,
        link_controls=link_controls,
        receiver=receiver,
        link_mode=link_mode,
        pdt_config=pdt_config,
    )


def _production_link_effects(
    resolved_atmosphere: Mapping[str, object], detector: DetectorParams
) -> list[ChannelEffect]:
    """Assemble the four fixed-ID production effects, in the parity-pinned order.

    **The only place** the four reserved production ``effect_id``s
    (``system_efficiency``, ``atmospheric_absorption``, ``geometric_loss``,
    ``detector_qe``) and their registration order are assembled
    (``docs/LINK_2_PLAN.md`` §5, binding). Order matters: ``ChannelStack``
    folds ``transmittance_factor`` as a left-associated product starting
    from ``1.0``, so registering
    ``[system_efficiency, atmospheric_absorption, geometric_loss]`` in that
    order reproduces ``((1.0 * s) * a) * g == (s * a) * g`` bitwise -- the
    plan §2.2 parity contract. ``detector_qe`` folds independently into
    ``efficiency_factor`` and is order-insensitive with respect to the
    channel-side product, but is kept last, after the three channel-side
    effects, as the pinned canonical order.

    A future production-effect insertion (e.g. a LINK-3 Doppler effect) must
    not be spliced into the existing four without a new parity argument
    written down first (plan §7 risk register) -- appending after
    ``geometric_loss`` and before any user ``link_effects`` is the default
    presumption, not an automatic license to skip re-deriving parity.
    """

    return [
        SystemEfficiencyEffect(system_efficiency=resolved_atmosphere["system_efficiency"]),
        AtmosphericAbsorptionEffect(
            zenith_optical_depth=resolved_atmosphere["zenith_optical_depth"]
        ),
        GeometricLossEffect(
            beam_divergence_urad=resolved_atmosphere["beam_divergence_urad"],
            rx_aperture_m=resolved_atmosphere["rx_aperture_m"],
        ),
        DetectorQuantumEfficiencyEffect(detection_efficiency=detector.detection_efficiency),
    ]


def _apply_link_stack(
    *,
    pass_geometry,
    stack: ChannelStack,
    channel_states: list[ChannelState],
    detector: DetectorParams,
    link_controls: Mapping[str, float] | None,
) -> tuple[list[ChannelState], DetectorParams]:
    """Evaluate ``stack`` at the mission's own pass samples and fold it in.

    The mission shares a single ``DetectorParams`` across every sample in a
    pass profile (``simulate_profile`` takes one ``detector``, not a
    per-sample list). LINK-2's production effects are all time-constant on
    the detector side (plan §5), so this guard never fires for them; it is
    retained unchanged from LINK-1 for any user effect that would vary
    ``efficiency_factor`` by time -- raising rather than silently collapsing
    a genuinely sample-varying detector efficiency down to one arbitrary
    sample.
    """

    new_channel_states: list[ChannelState] = []
    resolved_detector: DetectorParams | None = None
    for sample_index, (t, base_channel) in enumerate(
        zip(pass_geometry.time_s, channel_states)
    ):
        state = stack.evaluate(t, controls=link_controls, sample_index=sample_index)
        new_channel, new_detector = apply_link_state(
            state, channel=base_channel, detector=detector
        )
        new_channel_states.append(new_channel)
        if resolved_detector is None:
            resolved_detector = new_detector
        elif new_detector.detection_efficiency != resolved_detector.detection_efficiency:
            raise ValueError(
                "link_effects produced a sample-varying detector efficiency; "
                "simulate_pass shares one DetectorParams across the whole "
                "pass profile and cannot represent per-sample detector "
                "variation (LINK-1 scope; see LINK_1_PLAN.md)."
            )

    return new_channel_states, resolved_detector if resolved_detector is not None else detector


# ---------------------------------------------------------------------------
# LINK-6a -- receiver-active pass composition (plan §1-§5). New code paths
# only; the legacy ``receiver=None`` branch above never calls into any of
# this (byte-identity, plan §3.1 rule 1).
# ---------------------------------------------------------------------------


def _validate_and_partition_controls(
    link_controls: Mapping[str, float] | None,
    union_registry: Mapping[str, object],
    stack_names: set[str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Validate the caller's complete control mapping once against the union
    registry (plan §2 R4), then partition it by owner."""

    resolved: dict[str, float] = dict(link_controls) if link_controls else {}
    for name, value in resolved.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Control {name!r} value must be a finite number.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"Control {name!r} value must be finite.")
        if name not in union_registry:
            raise UndeclaredControlError(f"Undeclared control: {name!r}.")
        spec = union_registry[name]
        lower, upper = spec.bounds
        if numeric_value < lower or numeric_value > upper:
            raise ControlBoundsError(
                f"Control {name!r} ({spec.description or spec.unit}) value "
                f"{numeric_value} is outside static bounds [{lower}, {upper}]."
            )
    stack_controls = {name: value for name, value in resolved.items() if name in stack_names}
    receiver_controls = {
        name: value for name, value in resolved.items() if name not in stack_names
    }
    return stack_controls, receiver_controls


def _simulate_pass_receiver_active(
    *,
    cfg: MissionConfig,
    pass_geometry,
    resolved_atmosphere: Mapping[str, object],
    provider: TableGeometryProvider,
    effects: list[ChannelEffect],
    link_effects: list[ChannelEffect],
    link_seed: int | None,
    link_controls: Mapping[str, float] | None,
    receiver: ReceiverModel,
    link_mode: str,
    pdt_config: PdtConfig | None,
) -> PassResult:
    law_effect = None
    tau_mem_s: float | None = None

    if link_mode == "pdt":
        law_effect, prefix_effects = classify_and_order_pdt_stack(effects)
        validate_grid_and_block_duration(pass_geometry.time_s, pdt_config.block_duration_s)
        # Deterministic-prefix path (plan §5, C2): seed=None is deliberate --
        # any admitted effect that nevertheless requests randomness raises
        # SeedRequiredError (defense in depth).
        stack = ChannelStack(prefix_effects, provider, seed=None)
    else:
        stack = ChannelStack(effects, provider, seed=link_seed)

    union_registry: dict[str, object] = dict(stack.control_specs)
    for spec in receiver.controls(cfg.pulse_repetition_rate_hz):
        if spec.name in union_registry:
            raise DuplicateControlNameError(
                f"Duplicate control name across stack and receiver: {spec.name!r}."
            )
        union_registry[spec.name] = spec
    stack_names = set(stack.control_specs)

    stack_controls, receiver_controls = _validate_and_partition_controls(
        link_controls, union_registry, stack_names
    )
    gate_window_s = receiver_controls.get("gate_window_s")
    filter_sigma_hz = receiver_controls.get("filter_sigma_hz")
    doppler_residual_fraction = receiver_controls.get("doppler_residual_fraction")

    base_channel_states = [
        channel_state(
            elevation_deg=elevation_deg,
            slant_range_km=slant_range_km,
            atmosphere=cfg.atmosphere,
            eta_override=1.0,
        )
        for elevation_deg, slant_range_km in zip(
            pass_geometry.elevation_deg,
            pass_geometry.slant_range_km,
        )
    ]
    base_detector = replace(cfg.detector, detection_efficiency=1.0)

    channel_states: list[ChannelState] = []
    receiver_inputs_list: list[ReceiverInputs] = []
    detector: DetectorParams | None = None
    for sample_index, (t, base_channel) in enumerate(
        zip(pass_geometry.time_s, base_channel_states)
    ):
        state = stack.evaluate(t, controls=stack_controls, sample_index=sample_index)
        inputs, residual = extract_receiver_inputs(state)
        new_channel, new_detector = apply_link_state(
            residual, channel=base_channel, detector=base_detector
        )
        channel_states.append(new_channel)
        receiver_inputs_list.append(inputs)
        if detector is None:
            detector = new_detector
        elif new_detector.detection_efficiency != detector.detection_efficiency:
            raise ValueError(
                "link_effects produced a sample-varying detector efficiency; "
                "the receiver-active path shares one detector across the whole "
                "pass profile (same restriction as the legacy path)."
            )

    if link_mode == "pdt":
        # The memory guard below is evaluated once, from sample 0's
        # dead_time_s; that is only justified if every sample agrees.
        _assert_pdt_memory_invariant(receiver_inputs_list)
        tau_mem_s = validate_pdt_guards(
            pdt_config,
            dead_time_s=receiver_inputs_list[0].dead_time_s,
            pulse_repetition_rate_hz=cfg.pulse_repetition_rate_hz,
            n_pulses=cfg.n_pulses,
            block_duration_s=pdt_config.block_duration_s,
        )

    profile = _simulate_profile_receiver(
        pass_geometry.time_s,
        channel_states,
        detector=detector,
        intensities=cfg.intensities,
        n_pulses=cfg.n_pulses,
        pi=receiver.pi,
        pulse_repetition_rate_hz=cfg.pulse_repetition_rate_hz,
        sky_condition=cfg.sky_condition,
        receiver_inputs_list=receiver_inputs_list,
        gate_window_s=gate_window_s,
        filter_sigma_hz=filter_sigma_hz,
        doppler_residual_fraction=doppler_residual_fraction,
        source_linewidth_sigma_hz=receiver.source_linewidth_sigma_hz,
        link_mode=link_mode,
        law_effect=law_effect,
        provider=provider,
    )

    manifest_json = build_manifest(
        mission_config=cfg,
        resolved_atmosphere=resolved_atmosphere,
        link_effects=link_effects,
        link_seed=link_seed,
        link_controls=link_controls,
        receiver=receiver,
        link_mode=link_mode,
        pdt_config=pdt_config,
        tau_mem_s=tau_mem_s,
    )

    return _pass_result_from_profile(pass_geometry, profile, cfg, link_provenance=manifest_json)


def _simulate_profile_receiver(
    axis_values: list[float],
    channel_states: list[ChannelState],
    *,
    detector: DetectorParams,
    intensities: dict[str, float],
    n_pulses: int,
    pi: tuple[float, float, float],
    pulse_repetition_rate_hz: float,
    sky_condition: str,
    receiver_inputs_list: list[ReceiverInputs],
    gate_window_s: float | None,
    filter_sigma_hz: float | None,
    doppler_residual_fraction: float | None,
    source_linewidth_sigma_hz: float,
    link_mode: str,
    law_effect,
    provider: TableGeometryProvider,
) -> ProfileResult:
    """Receiver-active analogue of :func:`simulate_profile` (temporal axis only).

    Reuses the same werner_p/loss/fidelity helpers as the legacy profile
    core; only the per-sample key-rate computation is replaced by the §1/§5
    receiver chain (Appendix A -- every other emitted field is unchanged).
    """

    werner_p_source = _single_werner_source(channel_states)
    transmittance = [state.transmittance for state in channel_states]
    loss_db = [_channel_loss_db(eta) for eta in transmittance]
    min_loss_index = min(range(len(loss_db)), key=loss_db.__getitem__)
    min_loss_db = loss_db[min_loss_index]

    blocks = []
    if link_mode == "sampled":
        for channel, inputs in zip(channel_states, receiver_inputs_list):
            blocks.append(
                compute_receiver_block(
                    channel=channel,
                    detector=detector,
                    intensities=intensities,
                    n_pulses=n_pulses,
                    pi=pi,
                    receiver_inputs=inputs,
                    gate_window_s=gate_window_s,
                    pulse_repetition_rate_hz=pulse_repetition_rate_hz,
                    filter_sigma_hz=filter_sigma_hz,
                    doppler_residual_fraction=doppler_residual_fraction,
                    source_linewidth_sigma_hz=source_linewidth_sigma_hz,
                )
            )
    else:
        for t, channel, inputs in zip(axis_values, channel_states, receiver_inputs_list):
            geom = provider.at(t)
            law = law_effect.stationary_law(geom)
            blocks.append(
                compute_receiver_block_pdt(
                    law=law,
                    channel_base=channel,
                    detector=detector,
                    intensities=intensities,
                    n_pulses=n_pulses,
                    pi=pi,
                    receiver_inputs=inputs,
                    gate_window_s=gate_window_s,
                    pulse_repetition_rate_hz=pulse_repetition_rate_hz,
                    filter_sigma_hz=filter_sigma_hz,
                    doppler_residual_fraction=doppler_residual_fraction,
                    source_linewidth_sigma_hz=source_linewidth_sigma_hz,
                )
            )

    secure_key_rate_per_pulse = [block.secure_key_rate_per_pulse for block in blocks]
    per_signal = [block.secure_key_rate_per_signal_pulse for block in blocks]
    availability = [block.availability for block in blocks]

    effective_werner_p = [
        effective_werner_p_for_sky(
            eta, werner_p_source, detector.detection_efficiency, sky_condition=sky_condition
        )
        for eta in transmittance
    ]
    teleportation_results = [teleportation_fidelity(p_eff) for p_eff in effective_werner_p]
    fidelity = [result.fidelity for result in teleportation_results]
    classical_bound = teleportation_results[0].classical_bound

    secure_key_yield_bits = _integrate_yield_bits(
        axis_values, secure_key_rate_per_pulse, pulse_repetition_rate_hz
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
        link_receiver=LinkReceiverProfile(
            secure_key_rate_per_signal_pulse=per_signal,
            availability=availability,
            pi=pi,
        ),
    )


def _link_receiver_provenance() -> dict[str, str]:
    """A.4 -- the exact seven-leaf provenance map for ``profile.link_receiver``."""

    return {
        "profile.link_receiver.secure_key_rate_per_signal_pulse": Provenance.SIMULATED.value,
        "profile.link_receiver.availability": Provenance.SIMULATED.value,
        "profile.link_receiver.pi.signal": Provenance.ILLUSTRATIVE.value,
        "profile.link_receiver.pi.decoy": Provenance.ILLUSTRATIVE.value,
        "profile.link_receiver.pi.vacuum": Provenance.ILLUSTRATIVE.value,
        "profile.link_receiver.units.secure_key_rate_per_signal_pulse": (
            Provenance.ILLUSTRATIVE.value
        ),
        "profile.link_receiver.units.availability": Provenance.ILLUSTRATIVE.value,
    }


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
        integrate_yield=False,
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
    integrate_yield: bool = True,
) -> ProfileResult:
    """Compose an honest medium-neutral channel-state profile.

    ``integrate_yield`` is for temporal axes only: it integrates
    bits/pulse over a pulse clock and sample duration. Distance sweeps keep
    secure-key rate as their figure of merit instead.
    """

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

    secure_key_yield_bits = (
        _integrate_yield_bits(
            axis_values,
            secure_key_rate_per_pulse,
            pulse_repetition_rate_hz,
        )
        if integrate_yield
        else None
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
    *,
    link_provenance: str | None = None,
) -> PassResult:
    if profile.secure_key_yield_bits is None:
        raise ValueError("Temporal pass profiles must include secure_key_yield_bits.")
    provenance = _default_provenance()
    if profile.link_receiver is not None:
        provenance.update(_link_receiver_provenance())
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
        provenance=provenance,
        link_receiver=profile.link_receiver,
        link_provenance=link_provenance,
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
