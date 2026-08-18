"""LINK-6a: QKD receiver model, gated detection, and PDT consumption.

Implements ``docs/LINK_6A_PLAN.md`` (v2.3.1) §1, §2, §5. This module owns
the *declared QKD receiver model* (§0, S4): a low-level gated-detection
utility (noise mapping, shared-history afterpulse model, common dead-time
availability) wrapped around the existing, unmodified public estimator
entry points ``qkd.bb84.run_decoy_bb84`` / ``qkd.bb84.estimate_decoy_bounds``
/ ``qkd.bb84.secure_key_rate``. ``bb84.py`` is never modified or
reimplemented (plan §1.2, C3 -- reuse, not reproduce).

Physics equations are frozen by the plan (§1.3, §1.5, §1.2) and reproduced
here verbatim in code; do not "fix" or retune any constant -- see the plan's
§12 numerical anchor.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np

from qkd.bb84 import (
    _relative_y1_shortfall,
    estimate_decoy_bounds,
    run_decoy_bb84,
    secure_key_rate,
)
from qkd.effects import LogNormalLaw
from qkd.link import ChannelEffect, ControlSpec, EffectiveLinkState
from qkd.signals import ChannelState, DetectorParams


# ---------------------------------------------------------------------------
# Named constants (plan §1.1, §2, §5 -- referenced by name, never inlined)
# ---------------------------------------------------------------------------

PI_SUM_TOLERANCE = 1e-9
MIN_GATE_WINDOW_S = 1e-12
PDT_TAIL_TOLERANCE = 1e-9
PDT_MEMORY_RATIO = 20
PDT_BLOCK_RATIO = 50
PDT_GRID_UNIFORMITY_REL_TOL = 1e-9
PDT_BLOCK_BINDING_REL_TOL = 1e-6


# ---------------------------------------------------------------------------
# Exceptions (fail-loud boundaries, named per plan §8/§4/§5/§3.1)
# ---------------------------------------------------------------------------


class DetectionError(ValueError):
    """Base class for LINK-6a receiver/PDT binding-rule violations."""


class ReceiverConfigError(DetectionError):
    """Raised for an invalid :class:`ReceiverModel` construction (§1.1)."""


class ReceiverEveNotSupportedError(DetectionError):
    """Raised when ``receiver`` and ``eve`` are both supplied (§1.2 -- mutually exclusive in 6a)."""


class GateWindowRequiredError(DetectionError):
    """Raised when a non-identity rate observable is consumed without ``gate_window_s`` (§2)."""


class AfterpulseCascadeDomainError(DetectionError):
    """Raised outside the consumer domain ``0 <= p_ap < 1`` (§1.3, R5 edge domains)."""


class LinkModeError(DetectionError):
    """Raised for invalid ``link_mode``/``receiver``/``pdt_config`` activation combinations (§3.1)."""


class PdtInadmissibleEffectError(DetectionError):
    """Raised when a non-allowlisted ``effect_id`` is active in PDT mode (§5, closed-world allowlist)."""


class PdtLawEffectNotLastError(DetectionError):
    """Raised when the single admitted law effect is not the last stack member (§5, C2)."""


class PdtBlockDurationMismatchError(DetectionError):
    """Raised when ``PdtConfig.block_duration_s`` does not match the profile grid width (§5, C1)."""


class PdtGridNonUniformError(DetectionError):
    """Raised when the profile time grid is not uniform to ``PDT_GRID_UNIFORMITY_REL_TOL`` (§5, C1)."""


class PdtGuardError(DetectionError):
    """Raised when the PDT memory or stationarity guard is violated (§5, R3)."""


class PdtNPulsesExceedsTrainError(DetectionError):
    """Raised when ``n_pulses > pulse_repetition_rate_hz * block_duration_s`` (§5)."""


class PdtSampleVaryingMemoryError(DetectionError):
    """Raised when ``dead_time_s``/``afterpulse_prob`` vary across PDT samples (§5, R3).

    The memory guard (``validate_pdt_guards``) is evaluated **once**, from a
    single sample's ``dead_time_s``; that is only justified if the value
    the guard checked is the value every sample actually uses. All
    PDT-admissible effects that own these two fields
    (``detector_dead_time``, ``detector_afterpulsing``) are declared
    time-constant "ignores context" owners, so this should never fire in
    practice -- it is a structural backstop, not a workaround.
    """


class PdtTailToleranceExceededError(DetectionError):
    """Raised when the unphysical tail mass ``P(eta_base * f > 1)`` exceeds ``PDT_TAIL_TOLERANCE`` (§5, R2)."""


class PdtNodeUnphysicalError(DetectionError):
    """Raised when any quadrature node has ``eta_base * f_i > 1`` (§5, R2 -- no node is ever clipped)."""


# ---------------------------------------------------------------------------
# §5 -- PDT admissibility allowlist (closed-world, by stable effect_id)
# ---------------------------------------------------------------------------

PDT_ADMISSIBLE_EFFECTS: dict[str, str] = {
    "system_efficiency": "deterministic",
    "atmospheric_absorption": "deterministic",
    "geometric_loss": "deterministic",
    "detector_qe": "deterministic",
    "doppler_shift": "deterministic",
    "pointing_loss": "deterministic",
    "detector_afterpulsing": "deterministic",
    "detector_dead_time": "deterministic",
    "background_light": "deterministic",
    "detector_dark_rate": "deterministic",
    "scintillation_fading": "law",
}
"""Frozen mapping ``effect_id -> {"deterministic", "law"}`` (plan §5, table).

Membership -- not type inspection -- decides PDT admissibility (no attempt
to infer whether an arbitrary effect is stochastic). ``pointing_jitter``,
``mu_fluctuation``, and every custom/unregistered ``effect_id`` are not
members and are rejected at admission.
"""


# ---------------------------------------------------------------------------
# §1.1 -- ReceiverModel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReceiverModel:
    """The receiver activation switch (plan §1.1, §3.1).

    ``pi`` is the explicit ``(pi_signal, pi_decoy, pi_vacuum)`` selection
    tuple: each strictly positive, summing to 1 within
    :data:`PI_SUM_TOLERANCE`. ``operating_convention`` names the §1.4
    calibrated-pair convention; the only value LINK-6a defines is
    ``"next_live_gate_v1"``.
    """

    pi: tuple[float, float, float]
    operating_convention: str = "next_live_gate_v1"

    def __post_init__(self) -> None:
        if len(self.pi) != 3:
            raise ReceiverConfigError(
                f"pi must be a 3-tuple (signal, decoy, vacuum); got {self.pi!r}."
            )
        signal, decoy, vacuum = self.pi
        for name, value in (
            ("pi_signal", signal),
            ("pi_decoy", decoy),
            ("pi_vacuum", vacuum),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ReceiverConfigError(
                    f"{name} must be finite and strictly positive; got {value!r}."
                )
        total = signal + decoy + vacuum
        if abs(total - 1.0) > PI_SUM_TOLERANCE:
            raise ReceiverConfigError(
                f"pi must sum to 1 within PI_SUM_TOLERANCE={PI_SUM_TOLERANCE}; got {total!r}."
            )
        if self.operating_convention != "next_live_gate_v1":
            raise ReceiverConfigError(
                "operating_convention must be 'next_live_gate_v1'; got "
                f"{self.operating_convention!r}."
            )

    @property
    def pi_signal(self) -> float:
        return self.pi[0]

    @property
    def pi_decoy(self) -> float:
        return self.pi[1]

    @property
    def pi_vacuum(self) -> float:
        return self.pi[2]

    def controls(self, pulse_repetition_rate_hz: float) -> tuple[ControlSpec, ...]:
        """Declare ``gate_window_s`` (plan §2) -- a period-coupled bound.

        Unlike :class:`qkd.link.Controllable` (a zero-argument protocol used
        by :class:`qkd.link.ChannelStack` for its own effects), the
        receiver's control bound is model-coupled to
        ``pulse_repetition_rate_hz`` (``mission.MissionConfig``), so this
        method takes it explicitly; mission-level union-registry assembly
        (``qkd.mission``, plan §2 R4) calls it directly rather than through
        the stack's internal effect loop.
        """

        upper = 1.0 / pulse_repetition_rate_hz
        return (
            ControlSpec(
                name="gate_window_s",
                unit="s",
                bounds=(MIN_GATE_WINDOW_S, upper),
                description=(
                    "Detector coincidence/acceptance gate window (LINK-6a plan §2)."
                ),
            ),
        )


# ---------------------------------------------------------------------------
# §3 -- ReceiverInputs / extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReceiverInputs:
    """The exact per-sample consumed-field set (plan §3): four detector-side observables."""

    background_rate_hz: float
    dark_count_rate_hz: float
    afterpulse_prob: float
    dead_time_s: float


def extract_receiver_inputs(
    state: EffectiveLinkState,
) -> tuple[ReceiverInputs, EffectiveLinkState]:
    """Split ``state`` into the receiver-consumed fields and the residual (plan §3).

    The residual retains every other field of ``state`` unchanged (including
    ``source`` and the channel/detector fields the receiver does not
    consume) so ``qkd.link.apply_link_state`` continues to reject any other
    non-identity observable exactly as before -- no field is "consumed"
    merely because rejection was skipped.
    """

    inputs = ReceiverInputs(
        background_rate_hz=state.channel.background_rate_hz,
        dark_count_rate_hz=state.detector.dark_count_rate_hz,
        afterpulse_prob=state.detector.afterpulse_prob,
        dead_time_s=state.detector.dead_time_s,
    )
    residual = EffectiveLinkState(
        channel=replace(state.channel, background_rate_hz=0.0),
        detector=replace(
            state.detector,
            dark_count_rate_hz=0.0,
            afterpulse_prob=0.0,
            dead_time_s=0.0,
        ),
        source=state.source,
    )
    return inputs, residual


# ---------------------------------------------------------------------------
# §1.5 -- ReceiverBlockResult (A.3.1, all fields required)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReceiverBlockResult:
    """One block's receiver-aware statistics (plan Appendix A.3.1, frozen)."""

    gains: dict[str, float]
    qber_per_intensity: dict[str, float]
    y1_lower_bound: float
    e1_upper_bound: float
    q1: float
    availability: float
    secure_key_rate_per_signal_pulse: float
    secure_key_rate_per_pulse: float
    sifted_key_length: int
    decoy_anomaly_score: float
    p_noise: float
    p_bg: float
    p_dk: float
    a: float
    q_bar_reg: float
    r_click_hz: float


# ---------------------------------------------------------------------------
# §1.2 -- Noise mapping
# ---------------------------------------------------------------------------


def compute_noise_probabilities(
    *,
    detection_efficiency: float,
    y0: float,
    receiver_inputs: ReceiverInputs,
    gate_window_s: float | None,
) -> tuple[float, float, float]:
    """Return ``(p_bg, p_dk, p_noise)`` per the §1.2 gated-noise mapping.

    Raises :class:`GateWindowRequiredError` when a non-identity rate
    observable would be consumed but ``gate_window_s`` is ``None`` (plan §2,
    "no silent default").
    """

    r_bg = receiver_inputs.background_rate_hz
    r_dk = receiver_inputs.dark_count_rate_hz
    if (r_bg != 0.0 or r_dk != 0.0) and gate_window_s is None:
        raise GateWindowRequiredError(
            "gate_window_s is required whenever the receiver path consumes a "
            "non-identity background_rate_hz or dark_count_rate_hz (plan §2); "
            "supply it via link_controls."
        )
    gw = gate_window_s if gate_window_s is not None else 0.0
    p_bg = 1.0 - math.exp(-detection_efficiency * r_bg * gw)
    p_dk = 1.0 - math.exp(-r_dk * gw)
    if p_bg == 0.0 and p_dk == 0.0:
        # Exact parity anchor (plan §1.2): "p_noise ≡ y0 exactly when both
        # rates are zero" -- the general formula below is only
        # mathematically, not bit-, exact here (1-(1-y0) != y0 in float64
        # for small y0), so short-circuit rather than let cancellation
        # perturb the value away from y0.
        p_noise = y0
    else:
        p_noise = 1.0 - (1.0 - y0) * (1.0 - p_bg) * (1.0 - p_dk)
    return p_bg, p_dk, p_noise


# ---------------------------------------------------------------------------
# §1.3/§1.5 -- shared-history afterpulse model and common-dead-time availability
# ---------------------------------------------------------------------------


def shared_history_afterpulse(
    gains: Mapping[str, float],
    qber_per_intensity: Mapping[str, float],
    pi: tuple[float, float, float],
    p_ap: float,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], float, float, float]:
    """The §1.3 mean-field afterpulse chain. Returns ``(Q', E', T', a, Q_bar, Q_bar_reg)``."""

    if not (0.0 <= p_ap < 1.0):
        raise AfterpulseCascadeDomainError(
            f"afterpulse_prob must be in [0, 1) (consumer domain, plan §1.3 R5); got {p_ap!r}."
        )
    pi_signal, pi_decoy, pi_vacuum = pi
    q_bar = pi_signal * gains["signal"] + pi_decoy * gains["decoy"] + pi_vacuum * gains["vacuum"]
    denominator = 1.0 - p_ap * (1.0 - q_bar)
    if denominator <= 0.0:
        raise AfterpulseCascadeDomainError(
            f"p_ap * (1 - Q_bar) = {p_ap * (1.0 - q_bar)!r} >= 1; the afterpulse "
            "cascade diverges (plan §1.3 validity condition)."
        )
    q_bar_reg = q_bar / denominator
    a = p_ap * q_bar_reg

    q_prime: dict[str, float] = {}
    t_prime: dict[str, float] = {}
    e_prime: dict[str, float] = {}
    for name, q_x in gains.items():
        if a == 0.0:
            # Exact parity anchor (plan §8 Gate-A parity): no afterpulse
            # contribution -> pass through the base statistics bit-for-bit
            # rather than recomputing through 1-(1-q_x)*(1-a) etc., which is
            # only mathematically (not bit-) exact under cancellation.
            q_prime[name] = q_x
            t_prime[name] = qber_per_intensity[name] * q_x
            e_prime[name] = qber_per_intensity[name]
            continue
        t_x = qber_per_intensity[name] * q_x
        qp = 1.0 - (1.0 - q_x) * (1.0 - a)
        tp = t_x + 0.5 * (1.0 - q_x) * a
        q_prime[name] = qp
        t_prime[name] = tp
        e_prime[name] = (tp / qp) if qp != 0.0 else 0.0

    return q_prime, e_prime, t_prime, a, q_bar, q_bar_reg


def click_availability(
    pulse_repetition_rate_hz: float,
    q_bar_reg: float,
    dead_time_s: float,
) -> tuple[float, float]:
    """Return ``(R_click, A)`` per plan §1.5 (``R_click = f_rep * Q_bar_reg`` exactly)."""

    r_click = pulse_repetition_rate_hz * q_bar_reg
    if dead_time_s == 0.0:
        # Exact parity anchor: no dead time -> full availability, bit-exact
        # (also true of 1.0/(1.0+r_click*0.0) in IEEE754, but made explicit
        # per plan §8 Gate-A parity rather than relying on that identity).
        availability = 1.0
    else:
        availability = 1.0 / (1.0 + r_click * dead_time_s)
    return r_click, availability


# ---------------------------------------------------------------------------
# §1 -- sampled-mode per-block receiver chain
# ---------------------------------------------------------------------------


def compute_receiver_block(
    *,
    channel: ChannelState,
    detector: DetectorParams,
    intensities: Mapping[str, float],
    n_pulses: int,
    pi: tuple[float, float, float],
    receiver_inputs: ReceiverInputs,
    gate_window_s: float | None,
    pulse_repetition_rate_hz: float,
    q: float = 0.5,
) -> ReceiverBlockResult:
    """The complete §1 receiver chain for one sampled block (base-statistics reuse route, C3)."""

    y0 = detector.dark_count_prob
    p_bg, p_dk, p_noise = compute_noise_probabilities(
        detection_efficiency=detector.detection_efficiency,
        y0=y0,
        receiver_inputs=receiver_inputs,
        gate_window_s=gate_window_s,
    )
    detector_eff = replace(detector, dark_count_prob=p_noise)
    base = run_decoy_bb84(channel, intensities, n_pulses, detector_eff, eve=None, q=q)

    q_prime, e_prime, _t_prime, a, _q_bar, q_bar_reg = shared_history_afterpulse(
        base.gains, base.qber_per_intensity, pi, receiver_inputs.afterpulse_prob
    )
    r_click, availability = click_availability(
        pulse_repetition_rate_hz, q_bar_reg, receiver_inputs.dead_time_s
    )

    return _finish_receiver_block(
        q_prime=q_prime,
        e_prime=e_prime,
        availability=availability,
        intensities=intensities,
        n_pulses=n_pulses,
        pi=pi,
        detector=detector,
        q=q,
        p_noise=p_noise,
        p_bg=p_bg,
        p_dk=p_dk,
        a=a,
        q_bar_reg=q_bar_reg,
        r_click_hz=r_click,
    )


def _finish_receiver_block(
    *,
    q_prime: Mapping[str, float],
    e_prime: Mapping[str, float],
    availability: float,
    intensities: Mapping[str, float],
    n_pulses: int,
    pi: tuple[float, float, float],
    detector: DetectorParams,
    q: float,
    p_noise: float,
    p_bg: float,
    p_dk: float,
    a: float,
    q_bar_reg: float,
    r_click_hz: float,
) -> ReceiverBlockResult:
    """Shared estimator-call tail for both sampled and PDT block results (plan §1.2/§1.5, §5)."""

    y1_lower_bound, e1_upper_bound = estimate_decoy_bounds(
        gains=dict(q_prime), qber_per_intensity=dict(e_prime), intensities=intensities
    )
    mu = intensities["signal"]
    q1 = y1_lower_bound * mu * math.exp(-mu)
    pi_signal = pi[0]

    rate_signal = secure_key_rate(
        q_prime["signal"],
        e_prime["signal"],
        q1,
        e1_upper_bound,
        q=q,
        error_correction_efficiency=detector.error_correction_efficiency,
    )
    rate_per_signal_pulse = availability * rate_signal
    rate_per_pulse = pi_signal * rate_per_signal_pulse
    sifted_key_length = round(n_pulses * pi_signal * q * availability * q_prime["signal"])
    decoy_anomaly_score = _relative_y1_shortfall(y1_lower_bound, y1_lower_bound)

    return ReceiverBlockResult(
        gains=dict(q_prime),
        qber_per_intensity=dict(e_prime),
        y1_lower_bound=y1_lower_bound,
        e1_upper_bound=e1_upper_bound,
        q1=q1,
        availability=availability,
        secure_key_rate_per_signal_pulse=rate_per_signal_pulse,
        secure_key_rate_per_pulse=rate_per_pulse,
        sifted_key_length=sifted_key_length,
        decoy_anomaly_score=decoy_anomaly_score,
        p_noise=p_noise,
        p_bg=p_bg,
        p_dk=p_dk,
        a=a,
        q_bar_reg=q_bar_reg,
        r_click_hz=r_click_hz,
    )


# ---------------------------------------------------------------------------
# §5 -- PDT: PdtConfig, admissibility, quadrature, and the per-sample block
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PdtConfig:
    """Required, explicit slow-fading timing (plan §5, R3).

    ``n_pulses`` is the estimator's per-sample statistical block size; on
    PDT runs it is declared a **uniformly distributed expected-count
    subsample of the total protocol pulses in the block** -- its fading
    values are exchangeable, not independent (uniform placement over many
    coherence intervals samples the stationary marginal, which is exactly
    the average the quadrature computes, but pulses within one coherence
    interval remain correlated). LINK-6a computes deterministic asymptotic
    expectations only; it makes no finite-key independence claim, and the
    contiguous-burst reading (``n_pulses`` consecutive pulses at
    ``pulse_repetition_rate_hz``) is explicitly not the model.
    """

    fading_coherence_time_s: float
    block_duration_s: float

    def __post_init__(self) -> None:
        for name, value in (
            ("fading_coherence_time_s", self.fading_coherence_time_s),
            ("block_duration_s", self.block_duration_s),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise PdtGuardError(f"{name} must be finite and > 0; got {value!r}.")


def classify_and_order_pdt_stack(
    effects: Sequence[ChannelEffect],
) -> tuple[ChannelEffect, list[ChannelEffect]]:
    """Validate PDT admissibility and law-last ordering (plan §5, C2). Returns ``(law_effect, prefix)``."""

    law_effects = []
    for effect in effects:
        classification = PDT_ADMISSIBLE_EFFECTS.get(effect.effect_id)
        if classification is None:
            raise PdtInadmissibleEffectError(
                f"Effect {effect.effect_id!r} is not a member of PDT_ADMISSIBLE_EFFECTS; "
                "PDT mode rejects unregistered/non-member effect_ids at admission, "
                "before any evaluation (plan §5)."
            )
        if classification == "law":
            law_effects.append(effect)

    if len(law_effects) != 1:
        raise PdtInadmissibleEffectError(
            "PDT mode requires exactly one 'law' member of PDT_ADMISSIBLE_EFFECTS "
            f"(scintillation_fading); found {len(law_effects)}."
        )
    law_effect = law_effects[0]
    if effects[-1] is not law_effect:
        raise PdtLawEffectNotLastError(
            f"The law effect {law_effect.effect_id!r} must be the last effect in the "
            "composed stack (plan §5, C2)."
        )
    prefix = [effect for effect in effects if effect is not law_effect]
    return law_effect, prefix


def validate_grid_and_block_duration(
    time_s: Sequence[float],
    block_duration_s: float,
) -> float:
    """Validate uniform grid + block-duration binding (plan §5, C1). Returns the grid width."""

    if len(time_s) < 2:
        raise PdtGridNonUniformError(
            "PDT mode requires at least two profile samples to define a grid width."
        )
    widths = [b - a for a, b in zip(time_s, time_s[1:])]
    reference = widths[0]
    if reference == 0.0:
        raise PdtGridNonUniformError("Profile grid width must be nonzero.")
    for width in widths:
        if abs(width - reference) > PDT_GRID_UNIFORMITY_REL_TOL * abs(reference):
            raise PdtGridNonUniformError(
                f"Profile time grid is not uniform to relative tolerance "
                f"{PDT_GRID_UNIFORMITY_REL_TOL}: width {width!r} vs reference {reference!r}."
            )
    if abs(block_duration_s - reference) > PDT_BLOCK_BINDING_REL_TOL * abs(reference):
        raise PdtBlockDurationMismatchError(
            f"PdtConfig.block_duration_s={block_duration_s!r} does not match the "
            f"actual profile grid width={reference!r} within relative tolerance "
            f"{PDT_BLOCK_BINDING_REL_TOL} (plan §5, C1)."
        )
    return reference


def validate_pdt_guards(
    pdt_config: PdtConfig,
    *,
    dead_time_s: float,
    pulse_repetition_rate_hz: float,
    n_pulses: int,
    block_duration_s: float,
) -> float:
    """Memory + stationarity + subsample-consistency guards (plan §5, R3). Returns ``tau_mem_s``."""

    tau_mem_s = dead_time_s + 1.0 / pulse_repetition_rate_hz
    if pdt_config.fading_coherence_time_s < PDT_MEMORY_RATIO * tau_mem_s:
        raise PdtGuardError(
            "PDT memory guard violated: fading_coherence_time_s="
            f"{pdt_config.fading_coherence_time_s!r} < PDT_MEMORY_RATIO * tau_mem_s = "
            f"{PDT_MEMORY_RATIO * tau_mem_s!r} (plan §5, R3)."
        )
    if block_duration_s < PDT_BLOCK_RATIO * pdt_config.fading_coherence_time_s:
        raise PdtGuardError(
            "PDT stationarity guard violated: block_duration_s="
            f"{block_duration_s!r} < PDT_BLOCK_RATIO * fading_coherence_time_s = "
            f"{PDT_BLOCK_RATIO * pdt_config.fading_coherence_time_s!r} (plan §5, R3)."
        )
    if n_pulses > pulse_repetition_rate_hz * block_duration_s:
        raise PdtNPulsesExceedsTrainError(
            f"n_pulses={n_pulses!r} exceeds pulse_repetition_rate_hz * block_duration_s = "
            f"{pulse_repetition_rate_hz * block_duration_s!r} (plan §5)."
        )
    return tau_mem_s


def _assert_pdt_memory_invariant(receiver_inputs_list: Sequence[ReceiverInputs]) -> None:
    """Assert ``dead_time_s``/``afterpulse_prob`` are constant across all PDT samples.

    ``validate_pdt_guards`` evaluates the memory guard once, from a single
    sample's ``dead_time_s`` -- that one-time evaluation is only justified
    if every sample actually uses that same value (plan §5, R3). Raises
    :class:`PdtSampleVaryingMemoryError` naming the first offending index.
    """

    if not receiver_inputs_list:
        return
    reference = receiver_inputs_list[0]
    for index, inputs in enumerate(receiver_inputs_list):
        if inputs.dead_time_s != reference.dead_time_s:
            raise PdtSampleVaryingMemoryError(
                f"dead_time_s varies across PDT samples: sample[{index}]="
                f"{inputs.dead_time_s!r} != sample[0]={reference.dead_time_s!r}; "
                "the memory guard was evaluated once and is no longer justified."
            )
        if inputs.afterpulse_prob != reference.afterpulse_prob:
            raise PdtSampleVaryingMemoryError(
                f"afterpulse_prob varies across PDT samples: sample[{index}]="
                f"{inputs.afterpulse_prob!r} != sample[0]={reference.afterpulse_prob!r}; "
                "the memory guard was evaluated once and is no longer justified."
            )


def gauss_hermite_lognormal_nodes(
    law: LogNormalLaw, n_nodes: int
) -> tuple[np.ndarray, np.ndarray]:
    """Gauss-Hermite nodes/weights for ``E[g(f)]``, ``f = exp(X)``, ``X ~ N(mu_log, sigma_log)``.

    Returns ``(f_i, p_i)`` with ``p_i >= 0`` summing to 1 (a probability
    measure over the quadrature nodes).
    """

    x, w = np.polynomial.hermite.hermgauss(n_nodes)
    f = np.exp(law.mu_log + math.sqrt(2.0) * law.sigma_log * x)
    p = w / math.sqrt(math.pi)
    return f, p


def _standard_normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def validate_tail_and_nodes(
    law: LogNormalLaw, eta_base: float, f_nodes: np.ndarray
) -> float:
    """Enforce the §5 R2 tail/node guards. Returns the analytic tail mass."""

    if eta_base <= 0.0:
        tail_mass = 0.0
    else:
        threshold_x = math.log(1.0 / eta_base)
        z = (threshold_x - law.mu_log) / law.sigma_log
        tail_mass = 1.0 - _standard_normal_cdf(z)
    if tail_mass > PDT_TAIL_TOLERANCE:
        raise PdtTailToleranceExceededError(
            f"Unphysical tail mass P(eta_base * f > 1) = {tail_mass!r} exceeds "
            f"PDT_TAIL_TOLERANCE={PDT_TAIL_TOLERANCE} (plan §5, R2)."
        )
    for f_i in f_nodes:
        if eta_base * float(f_i) > 1.0:
            raise PdtNodeUnphysicalError(
                f"Quadrature node eta_base * f_i = {eta_base * float(f_i)!r} > 1 "
                "(plan §5, R2 -- no node is ever evaluated above physical transmittance)."
            )
    return tail_mass


_INTENSITY_NAMES = ("signal", "decoy", "vacuum")


def compute_receiver_block_pdt(
    *,
    law: LogNormalLaw,
    channel_base: ChannelState,
    detector: DetectorParams,
    intensities: Mapping[str, float],
    n_pulses: int,
    pi: tuple[float, float, float],
    receiver_inputs: ReceiverInputs,
    gate_window_s: float | None,
    pulse_repetition_rate_hz: float,
    q: float = 0.5,
    n_nodes: int = 21,
) -> ReceiverBlockResult:
    """The five-step deterministic-prefix PDT block (plan §5, C2).

    ``channel_base.transmittance`` is ``eta_base(t_k)`` -- the deterministic
    prefix-stack transmittance at this sample, already folded through
    ``qkd.link.apply_link_state``. Each Gauss-Hermite node forms the
    physical node state ``eta_base * f_i`` (never calling the law effect's
    ``evaluate``), and the estimator consumes the availability-weighted
    observed-statistics ratios (plan §5 ratios block).
    """

    eta_base = channel_base.transmittance
    f_nodes, p_nodes = gauss_hermite_lognormal_nodes(law, n_nodes)
    validate_tail_and_nodes(law, eta_base, f_nodes)

    y0 = detector.dark_count_prob
    p_bg, p_dk, p_noise = compute_noise_probabilities(
        detection_efficiency=detector.detection_efficiency,
        y0=y0,
        receiver_inputs=receiver_inputs,
        gate_window_s=gate_window_s,
    )
    detector_eff = replace(detector, dark_count_prob=p_noise)

    sum_p_availability = 0.0
    sum_weighted_q = {name: 0.0 for name in _INTENSITY_NAMES}
    sum_weighted_t = {name: 0.0 for name in _INTENSITY_NAMES}
    sum_p_a = 0.0
    sum_p_q_bar_reg = 0.0
    sum_p_r_click = 0.0

    for f_i, p_i in zip(f_nodes, p_nodes):
        p_i = float(p_i)
        eta_node = eta_base * float(f_i)
        node_channel = replace(channel_base, transmittance=eta_node)
        base = run_decoy_bb84(node_channel, intensities, n_pulses, detector_eff, eve=None, q=q)
        q_prime, e_prime, t_prime, a_i, _q_bar_i, q_bar_reg_i = shared_history_afterpulse(
            base.gains, base.qber_per_intensity, pi, receiver_inputs.afterpulse_prob
        )
        r_click_i, availability_i = click_availability(
            pulse_repetition_rate_hz, q_bar_reg_i, receiver_inputs.dead_time_s
        )
        weight = p_i * availability_i
        sum_p_availability += weight
        for name in _INTENSITY_NAMES:
            sum_weighted_q[name] += weight * q_prime[name]
            sum_weighted_t[name] += weight * t_prime[name]
        sum_p_a += p_i * a_i
        sum_p_q_bar_reg += p_i * q_bar_reg_i
        sum_p_r_click += p_i * r_click_i

    q_hat = {name: sum_weighted_q[name] / sum_p_availability for name in _INTENSITY_NAMES}
    t_hat = {name: sum_weighted_t[name] / sum_p_availability for name in _INTENSITY_NAMES}
    e_hat = {
        name: (t_hat[name] / q_hat[name] if q_hat[name] != 0.0 else 0.0)
        for name in _INTENSITY_NAMES
    }

    return _finish_receiver_block(
        q_prime=q_hat,
        e_prime=e_hat,
        availability=sum_p_availability,
        intensities=intensities,
        n_pulses=n_pulses,
        pi=pi,
        detector=detector,
        q=q,
        p_noise=p_noise,
        p_bg=p_bg,
        p_dk=p_dk,
        a=sum_p_a,
        q_bar_reg=sum_p_q_bar_reg,
        r_click_hz=sum_p_r_click,
    )
