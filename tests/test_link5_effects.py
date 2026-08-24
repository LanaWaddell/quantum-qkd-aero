"""Tests for LINK-5 (docs/LINK_5_PLAN.md, v2 approved, §4 tests 1-15).

Covers the source partition (``SourceObservables``, ``qkd.link``) and its
composition/validation/bridge-rejection machinery in ``ChannelStack`` /
``apply_link_state``, plus the three new detector/source effects
(``MuFluctuationEffect``, ``DetectorAfterpulsingEffect``,
``DetectorDeadTimeEffect``, ``qkd.effects``). Tests 14 and 15 are not
separate pytest functions: test 14's "frozen-hash/captured-fixture/LINK-1-4
tests pass unmodified" half is exercised by the same ``pytest`` invocation
that collects this file (``tests/test_link.py``, ``tests/test_link3_effects.py``,
``tests/test_link4_effects.py``, ``tests/test_effects.py``, and every other
existing test file are untouched by this PR); its "default emission
byte-identical" half is the dedicated regression test near the bottom of
this file. Test 15 (full suite green) is reported outside pytest by the
invocation that runs the whole suite.

Statistical oracle tolerance bands (test 2) are derived analytically from
normal/log-normal sample-mean and sample-variance theory *before* the seed
is pinned -- see the comments at the assertion for the derivation -- so the
band cannot be chosen against the realized draw. Per plan §4 test 2's note,
the ``exp(mu_log + sigma_log^2/2) == 1`` identity is retained (implicitly,
via the sigma_log_sq/mu_log relation asserted below) but is near-tautological
*alone*; it is not used here as the sole check -- the independently
hand-computed oracle and the seeded-moment bands are the load-bearing
assertions.
"""

from __future__ import annotations

import dataclasses
import json
import math
import statistics
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import qkd
from qkd.effects import DetectorAfterpulsingEffect, DetectorDeadTimeEffect, MuFluctuationEffect
from qkd.link import (
    ChannelObservables,
    ChannelStack,
    DetectorObservables,
    DuplicateEffectIdError,
    EffectEvaluationContext,
    EffectiveLinkState,
    InvalidObservableError,
    LinkObservables,
    PassGeometry,
    SeedRequiredError,
    SingleContributorConflictError,
    SourceObservables,
    UnsupportedLinkObservableError,
    apply_link_state,
)
from qkd.mission import MissionConfig, simulate_pass
from qkd.run import _build_results
from qkd.schema import validate_results_schema
from qkd.signals import ChannelState, DetectorParams


# ---------------------------------------------------------------------------
# Test-only fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ConstantGeometryProvider:
    """Ignores ``t``; always returns the same geometry (only ``t_s`` varies)."""

    geometry: PassGeometry

    def at(self, t: float) -> PassGeometry:
        return replace(self.geometry, t_s=t)


@dataclass(frozen=True)
class _MockSourceEffect:
    """Minimal user effect emitting a fixed ``source.intensity_factor``."""

    effect_id: str
    intensity_factor: float = 1.0
    unit_mean_fading_fields: object = None

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(source=SourceObservables(intensity_factor=self.intensity_factor))


@dataclass(frozen=True)
class _MockUnitMeanEffect:
    """Minimal user effect exposing arbitrary channel/source values and declaration.

    Both fields default to identity so a test can set only the one it cares
    about; used for the LINK-5 partition-aware same-effect cross-check
    (plan §4 test 7).
    """

    effect_id: str
    transmittance_factor: float = 1.0
    intensity_factor: float = 1.0
    unit_mean_fading_fields: object = None

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=self.transmittance_factor),
            source=SourceObservables(intensity_factor=self.intensity_factor),
        )


@dataclass(frozen=True)
class _MockDetectorFieldEffect:
    """Minimal user effect emitting fixed ``afterpulse_prob``/``dead_time_s``."""

    effect_id: str
    afterpulse_prob: float = 0.0
    dead_time_s: float = 0.0

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(
            detector=DetectorObservables(
                afterpulse_prob=self.afterpulse_prob, dead_time_s=self.dead_time_s
            )
        )


def _channel_state(**overrides) -> ChannelState:
    base = dict(
        transmittance=0.8,
        werner_p=0.9,
        intrinsic_qber=0.01,
        dark_count_prob=1e-6,
        slant_range_km=550.0,
        elevation_deg=90.0,
    )
    base.update(overrides)
    return ChannelState(**base)


def _detector_params(**overrides) -> DetectorParams:
    base = dict(detection_efficiency=0.5, dark_count_prob=1e-6)
    base.update(overrides)
    return DetectorParams(**base)


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _raising_rng_for(purpose, index=None):
    raise AssertionError(
        "sample_index validation must raise before any RNG stream is requested"
    )


class _FixedDrawRNG:
    """Stub RNG exposing only ``.normal`` -- returns a caller-fixed draw."""

    def __init__(self, value: float) -> None:
        self._value = value

    def normal(self, loc: float, scale: float) -> float:
        return self._value


def _noop_geom() -> PassGeometry:
    return PassGeometry(t_s=0.0, elevation_deg=None, slant_range_km=None)


# ---------------------------------------------------------------------------
# 1. Backward compatibility: identity source on existing-style construction;
#    all prior-lane tests pass unmodified (the rest of this file's peers)
# ---------------------------------------------------------------------------


def test_existing_style_construction_carries_identity_source():
    channel = ChannelObservables(transmittance_factor=0.5)
    detector = DetectorObservables(efficiency_factor=0.6)

    observables = LinkObservables(channel=channel, detector=detector)
    assert observables.source == SourceObservables()
    assert observables.source.intensity_factor == 1.0

    state = EffectiveLinkState(channel=channel, detector=detector)
    assert state.source == SourceObservables()
    assert state.source.intensity_factor == 1.0

    # Constructor calls unchanged (no new required positional argument).
    LinkObservables()
    EffectiveLinkState(channel=ChannelObservables(), detector=DetectorObservables())


# ---------------------------------------------------------------------------
# 2. sigma_log_sq/sigma_log/mu_log vs independently hand-computed values;
#    seeded moments within predeclared analytic bands
# ---------------------------------------------------------------------------


def test_mu_fluctuation_law_parameters_and_sample_moments_within_analytic_bands():
    relative_sigma = 0.08
    n = 5000
    seed = 20260811

    # Independent hand-computed oracle (plan §2.1 formula), fixed before any
    # sample is drawn -- deliberately *not* derived by calling the effect's
    # own helper (plan §4 test 2).
    expected_sigma_log_sq = math.log(1.0 + relative_sigma**2)
    expected_sigma_log = math.sqrt(expected_sigma_log_sq)
    expected_mu_log = -expected_sigma_log_sq / 2.0

    effect = MuFluctuationEffect(relative_sigma=relative_sigma)
    assert effect.sigma_log_sq == pytest.approx(expected_sigma_log_sq, abs=1e-12)
    assert effect.sigma_log == pytest.approx(expected_sigma_log, abs=1e-12)
    assert effect.mu_log == pytest.approx(expected_mu_log, abs=1e-12)
    # The exp(mu_log + sigma_log^2/2) == 1 identity holds by the unit-mean
    # normalization but is near-tautological alone (plan §4 test 2 note):
    # it is checked here only as a consistency cross-check, not a
    # substitute for the independent hand-computed oracle above.
    assert math.exp(effect.mu_log + effect.sigma_log**2 / 2.0) == pytest.approx(1.0, abs=1e-12)

    geom = _noop_geom()
    provider = _ConstantGeometryProvider(geom)
    stack = ChannelStack([effect], provider, seed=seed)
    factors = [
        stack.evaluate(float(idx), sample_index=idx).source.intensity_factor
        for idx in range(n)
    ]
    log_samples = [math.log(f) for f in factors]

    # Analytic tolerance bands, derived from normal-sample statistics
    # *before* drawing (never chosen against the realized sample): for N
    # i.i.d. draws of X ~ N(mu_log, sigma_log^2), the sample mean has
    # standard error sigma_log/sqrt(N); the (N-1)-denominator sample
    # variance has standard error sigma_log^2 * sqrt(2/(N-1)) (large-N
    # normal approximation to the scaled chi-square(N-1) distribution). A
    # 5-standard-error band keeps false-failure probability negligible
    # while still catching a materially wrong implementation.
    tol_mean_log = 5.0 * expected_sigma_log / math.sqrt(n)
    tol_var_log = 5.0 * expected_sigma_log**2 * math.sqrt(2.0 / (n - 1))
    # factor = exp(X) is log-normal with mu=mu_log, sigma=sigma_log; since
    # mu_log = -sigma_log^2/2 by the unit-mean normalization, E[factor] = 1
    # and Var[factor] = exp(sigma_log^2) - 1 (standard log-normal moment
    # identities).
    var_factor = math.exp(expected_sigma_log**2) - 1.0
    tol_mean_factor = 5.0 * math.sqrt(var_factor / n)

    sample_mean_log = statistics.fmean(log_samples)
    sample_var_log = statistics.variance(log_samples)
    sample_mean_factor = statistics.fmean(factors)

    # Realized seed=20260811, n=5000: sample_mean_log ~= -0.002674 (band
    # +/-0.005648 around expected -0.003190); sample_var_log ~= 0.006426
    # (band +/-0.000638 around expected 0.006380); sample_mean_factor ~=
    # 1.000531 (band +/-0.005657 around expected 1.0) -- all comfortably
    # inside their predeclared bands.
    assert sample_mean_log == pytest.approx(expected_mu_log, abs=tol_mean_log)
    assert sample_var_log == pytest.approx(expected_sigma_log_sq, abs=tol_var_log)
    assert sample_mean_factor == pytest.approx(1.0, abs=tol_mean_factor)


# ---------------------------------------------------------------------------
# 3. Epoch-common contract: one draw per epoch; hypothetical fold scales all
#    nonzero settings identically; exact zero preserved
# ---------------------------------------------------------------------------


def test_epoch_common_one_draw_scales_all_settings_identically_and_preserves_zero():
    geom = _noop_geom()
    provider = _ConstantGeometryProvider(geom)
    effect = MuFluctuationEffect(relative_sigma=0.15)
    stack = ChannelStack([effect], provider, seed=2026)

    # One draw per epoch (sample_index): re-evaluating the same index is the
    # same draw (LINK-4-style replay contract, shared machinery).
    epoch_a = stack.evaluate(0.0, sample_index=3).source.intensity_factor
    epoch_a_repeat = stack.evaluate(1.0, sample_index=3).source.intensity_factor
    assert epoch_a == epoch_a_repeat

    epoch_b = stack.evaluate(2.0, sample_index=4).source.intensity_factor

    # Pure unit test (pre-LINK-6, plan §4 test 3): a hypothetical fold of
    # the epoch-common factor onto nominal intensity settings -- this
    # module implements no such fold (LINK-6 scope), but the declared
    # semantics (plan §1.3, verbatim) require that whichever fold is
    # eventually written, it scales every nonzero setting by the *same*
    # one factor and leaves exact zero untouched.
    nominal_settings = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}
    folded_epoch_a = {
        name: (0.0 if value == 0.0 else value * epoch_a) for name, value in nominal_settings.items()
    }
    assert folded_epoch_a["signal"] == pytest.approx(0.5 * epoch_a)
    assert folded_epoch_a["decoy"] == pytest.approx(0.1 * epoch_a)
    assert folded_epoch_a["vacuum"] == 0.0  # exact zero preserved, not epoch_a * 0.0 by float path

    # A nonzero nominal "vacuum" setting would be scaled like every other
    # setting -- only a *true* (exactly zero) vacuum setting is exempt.
    nonzero_vacuum_folded = 1e-9 * epoch_a
    assert nonzero_vacuum_folded != 0.0 or epoch_a == 0.0

    # Different epoch, different draw (empirical tripwire, not proof).
    assert epoch_b != epoch_a


# ---------------------------------------------------------------------------
# 4. Not-exposed check: intensity_factor reachable through no DetectorParams,
#    ChannelState, or current estimator path
# ---------------------------------------------------------------------------


def test_intensity_factor_not_reachable_through_detector_params_channel_state_or_estimator():
    channel_field_names = {f.name for f in dataclasses.fields(ChannelState)}
    detector_field_names = {f.name for f in dataclasses.fields(DetectorParams)}
    assert "intensity_factor" not in channel_field_names
    assert "intensity_factor" not in detector_field_names

    # Broader structural check: no production module outside the LINK
    # layer itself (qkd.link / qkd.effects, where the field is legitimately
    # defined and used) mentions the field at all -- there is no back door.
    qkd_dir = Path(qkd.__file__).parent
    # LINK-7 §13 addendum: authorized consumption path.
    excluded = {"link.py", "effects.py", "detection.py", "mission.py", "replay.py"}
    checked_any = False
    for path in qkd_dir.glob("*.py"):
        if path.name in excluded:
            continue
        checked_any = True
        assert "intensity_factor" not in path.read_text(), (
            f"{path.name} unexpectedly references intensity_factor -- the "
            "current estimator path must not reach it."
        )
    assert checked_any

    # And the bridge's identity path returns exactly the untouched base
    # channel/detector -- neither of which carries the field either.
    identity_state = EffectiveLinkState(
        channel=ChannelObservables(), detector=DetectorObservables()
    )
    new_channel, new_detector = apply_link_state(
        identity_state, channel=_channel_state(), detector=_detector_params()
    )
    assert "intensity_factor" not in {f.name for f in dataclasses.fields(new_channel)}
    assert "intensity_factor" not in {f.name for f in dataclasses.fields(new_detector)}


# ---------------------------------------------------------------------------
# 5. R4 numerics: huge-but-finite relative_sigma fails at construction;
#    non-finite sampled factor cannot be emitted; composed-product overflow
#    rejected; relative_sigma=0 draws, requires seed+index, factor == 1.0
# ---------------------------------------------------------------------------


def test_mu_fluctuation_huge_but_finite_relative_sigma_fails_at_construction():
    huge_but_finite = 1.0e200
    assert math.isfinite(huge_but_finite)  # the input itself is finite
    with pytest.raises(ValueError, match="sigma_log_sq"):
        MuFluctuationEffect(relative_sigma=huge_but_finite)


def test_mu_fluctuation_rejects_non_finite_sampled_factor_before_emitting():
    effect = MuFluctuationEffect(relative_sigma=0.1)
    geom = _noop_geom()
    # A stubbed RNG forces an extreme draw (X=1000) that exp() cannot
    # represent -- exercising evaluate()'s own finiteness check
    # independently of any real sampling distribution.
    context = EffectEvaluationContext(
        controls={}, sample_index=0, rng_for=lambda purpose: _FixedDrawRNG(1000.0)
    )
    with pytest.raises(ValueError, match="not finite"):
        effect.evaluate(0.0, geom, context=context)


def test_composed_source_product_overflow_rejected():
    geom = _noop_geom()
    provider = _ConstantGeometryProvider(geom)
    huge = _MockSourceEffect(
        effect_id="huge_a", intensity_factor=1.0e200, unit_mean_fading_fields=("intensity_factor",)
    )
    huge_2 = _MockSourceEffect(
        effect_id="huge_b", intensity_factor=1.0e200, unit_mean_fading_fields=("intensity_factor",)
    )
    assert math.isfinite(1.0e200 * 1.0e200) is False  # the product itself already overflows
    stack = ChannelStack([huge, huge_2], provider)
    with pytest.raises(InvalidObservableError, match="Composed source.intensity_factor"):
        stack.evaluate(0.0, sample_index=0)


def test_mu_fluctuation_zero_variance_still_draws_requires_seed_and_index_factor_is_one():
    effect = MuFluctuationEffect(relative_sigma=0.0)
    assert effect.sigma_log_sq == 0.0
    assert effect.sigma_log == 0.0

    geom = _noop_geom()
    provider = _ConstantGeometryProvider(geom)

    # Requires a resolved seed (stochastic by contract, even at zero variance).
    stack_no_seed = ChannelStack([effect], provider)
    with pytest.raises(SeedRequiredError):
        stack_no_seed.evaluate(0.0, sample_index=0)

    # Requires an explicit sample_index.
    context = EffectEvaluationContext(controls={}, sample_index=None, rng_for=_raising_rng_for)
    with pytest.raises(ValueError, match="sample_index"):
        effect.evaluate(0.0, geom, context=context)

    # With both supplied, the factor is exactly 1.0 (a scale-0 normal draw).
    stack = ChannelStack([effect], provider, seed=1)
    for idx in range(5):
        state = stack.evaluate(float(idx), sample_index=idx)
        assert state.source.intensity_factor == 1.0


# ---------------------------------------------------------------------------
# 6. intensity_factor product composition (hand-computed, same-order) with
#    composed result validated finite/>=0
# ---------------------------------------------------------------------------


def test_intensity_factor_product_composition_hand_computed_same_order():
    geom = _noop_geom()
    provider = _ConstantGeometryProvider(geom)

    mu = MuFluctuationEffect(relative_sigma=0.05)
    mock = _MockSourceEffect(effect_id="mock_source", intensity_factor=0.7)

    mu_only_stack = ChannelStack([mu], provider, seed=555)
    mock_only_stack = ChannelStack([mock], provider)
    combined_stack = ChannelStack([mu, mock], provider, seed=555)

    mu_factor = mu_only_stack.evaluate(0.0, sample_index=0).source.intensity_factor
    mock_factor = mock_only_stack.evaluate(0.0, sample_index=0).source.intensity_factor
    combined_state = combined_stack.evaluate(0.0, sample_index=0)
    combined_factor = combined_state.source.intensity_factor

    # Same-order left-associated product -- ChannelStack's own composition
    # rule, mirroring transmittance_factor's (plan §1.4).
    assert combined_factor == pytest.approx(mu_factor * mock_factor, rel=0.0, abs=1e-12)
    assert math.isfinite(combined_factor) and combined_factor >= 0.0


# ---------------------------------------------------------------------------
# 7. Declarations: intensity_factor declarable; unrecognized/malformed
#    rejected; partition-aware same-effect cross-check; mixed-stack
#    effect-specificity; LINK-4 transmittance behaviour unchanged;
#    audit_record() unchanged
# ---------------------------------------------------------------------------


def test_construction_accepts_intensity_factor_declaration():
    provider = _ConstantGeometryProvider(_noop_geom())
    effect = _MockSourceEffect(
        effect_id="mock", intensity_factor=1.8, unit_mean_fading_fields=("intensity_factor",)
    )
    stack = ChannelStack([effect], provider)
    state = stack.evaluate(0.0, sample_index=0)
    assert state.source.intensity_factor == 1.8


def test_construction_rejects_unrecognized_and_malformed_declarations_unchanged():
    provider = _ConstantGeometryProvider(_noop_geom())

    unrecognized = _MockSourceEffect(
        effect_id="mock", unit_mean_fading_fields=("not_a_real_field",)
    )
    with pytest.raises(ValueError, match="unrecognized"):
        ChannelStack([unrecognized], provider)

    bare_string = _MockSourceEffect(effect_id="mock", unit_mean_fading_fields="intensity_factor")
    with pytest.raises(ValueError, match="bare string"):
        ChannelStack([bare_string], provider)


def test_partition_aware_same_effect_cross_check():
    provider = _ConstantGeometryProvider(_noop_geom())

    # Declaring only intensity_factor does not relax transmittance_factor
    # on the same effect: an out-of-domain transmittance_factor=1.5 still
    # raises.
    intensity_only = _MockUnitMeanEffect(
        effect_id="mock_intensity_only",
        transmittance_factor=1.5,
        intensity_factor=2.0,
        unit_mean_fading_fields=("intensity_factor",),
    )
    stack_a = ChannelStack([intensity_only], provider)
    with pytest.raises(InvalidObservableError, match="channel.transmittance_factor"):
        stack_a.evaluate(0.0, sample_index=0)

    # And vice versa: declaring only transmittance_factor does not relax
    # intensity_factor on the same effect.
    transmittance_only = _MockUnitMeanEffect(
        effect_id="mock_transmittance_only",
        transmittance_factor=1.5,
        intensity_factor=2.0,
        unit_mean_fading_fields=("transmittance_factor",),
    )
    stack_b = ChannelStack([transmittance_only], provider)
    with pytest.raises(InvalidObservableError, match="source.intensity_factor"):
        stack_b.evaluate(0.0, sample_index=0)

    # Declaring both relaxes both, on the same effect.
    both = _MockUnitMeanEffect(
        effect_id="mock_both",
        transmittance_factor=1.5,
        intensity_factor=2.0,
        unit_mean_fading_fields=("transmittance_factor", "intensity_factor"),
    )
    stack_c = ChannelStack([both], provider)
    state_c = stack_c.evaluate(0.0, sample_index=0)
    assert state_c.channel.transmittance_factor == 1.5
    assert state_c.source.intensity_factor == 2.0


def test_mixed_stack_effect_specificity_and_undeclared_partner_rejected():
    provider = _ConstantGeometryProvider(_noop_geom())

    declared = _MockSourceEffect(
        effect_id="declared_mock",
        intensity_factor=1.9,
        unit_mean_fading_fields=("intensity_factor",),
    )
    undeclared = _MockSourceEffect(effect_id="undeclared_mock", intensity_factor=1.5)

    mixed_stack = ChannelStack([declared, undeclared], provider)
    with pytest.raises(InvalidObservableError) as excinfo:
        mixed_stack.evaluate(0.0, sample_index=0)
    assert "undeclared_mock" in str(excinfo.value)


def test_link4_transmittance_declaration_behaviour_unchanged():
    # Same assertions as LINK-4's own declared-effect test, byte-for-byte
    # in spirit: a bare-string / unrecognized-name declaration on the
    # channel side still raises exactly as before the LINK-5 partition
    # extension.
    provider = _ConstantGeometryProvider(_noop_geom())

    bare_string = _MockUnitMeanEffect(
        effect_id="mock", transmittance_factor=1.0, unit_mean_fading_fields="transmittance_factor"
    )
    with pytest.raises(ValueError, match="bare string"):
        ChannelStack([bare_string], provider)

    unrecognized = _MockUnitMeanEffect(
        effect_id="mock", unit_mean_fading_fields=("not_a_real_field",)
    )
    with pytest.raises(ValueError, match="unrecognized"):
        ChannelStack([unrecognized], provider)

    declared = _MockUnitMeanEffect(
        effect_id="mock", transmittance_factor=1.5, unit_mean_fading_fields=("transmittance_factor",)
    )
    stack = ChannelStack([declared], provider)
    state = stack.evaluate(0.0, sample_index=0)
    assert state.channel.transmittance_factor == 1.5
    assert state.source.intensity_factor == 1.0  # untouched identity


def test_audit_record_unchanged_by_source_partition():
    provider = _ConstantGeometryProvider(_noop_geom())
    effect = _MockSourceEffect(
        effect_id="mock_source", intensity_factor=1.4, unit_mean_fading_fields=("intensity_factor",)
    )
    stack = ChannelStack([effect], provider)

    record = stack.audit_record(controls={})
    payload = json.loads(record)
    # Still exactly the three documented keys -- no source-partition leak
    # into the audit payload (plan §1.4: audit_record() unchanged).
    assert set(payload.keys()) == {"controls", "link_seed", "effect_ids"}
    assert payload["effect_ids"] == ["mock_source"]

    # Evaluating (which reads observables.source) does not change the
    # audit record -- it is computed purely from effect_ids/controls/seed.
    stack.evaluate(0.0, sample_index=0)
    assert stack.audit_record(controls={}) == record


# ---------------------------------------------------------------------------
# 8. Strict default [0, 1] for undeclared intensity_factor; declared
#    unit-mean factor > 1 accepted (finite >= 0)
# ---------------------------------------------------------------------------


def test_undeclared_intensity_factor_strict_default_zero_one():
    provider = _ConstantGeometryProvider(_noop_geom())
    effect = _MockSourceEffect(effect_id="mock", intensity_factor=1.2)
    stack = ChannelStack([effect], provider)
    with pytest.raises(InvalidObservableError, match=r"source\.intensity_factor"):
        stack.evaluate(0.0, sample_index=0)


def test_declared_intensity_factor_above_one_accepted():
    provider = _ConstantGeometryProvider(_noop_geom())
    effect = _MockSourceEffect(
        effect_id="mock", intensity_factor=1.2, unit_mean_fading_fields=("intensity_factor",)
    )
    stack = ChannelStack([effect], provider)
    state = stack.evaluate(0.0, sample_index=0)
    assert state.source.intensity_factor == 1.2


# ---------------------------------------------------------------------------
# 9. sample_index=None raises naming sample_index; bit-identical replay
#    across repetition/order/fresh stacks; different indices differ
# ---------------------------------------------------------------------------


def test_mu_fluctuation_raises_when_sample_index_is_none():
    context = EffectEvaluationContext(controls={}, sample_index=None, rng_for=_raising_rng_for)
    effect = MuFluctuationEffect(relative_sigma=0.1)
    with pytest.raises(ValueError, match="sample_index"):
        effect.evaluate(0.0, _noop_geom(), context=context)


def test_mu_fluctuation_replay_bit_identical_across_repetition_order_and_fresh_stacks():
    geom = _noop_geom()
    provider = _ConstantGeometryProvider(geom)
    seed = 4747

    def make_effect():
        return MuFluctuationEffect(relative_sigma=0.1)

    stack_a = ChannelStack([make_effect()], provider, seed=seed)
    state_repeat_1 = stack_a.evaluate(1.0, sample_index=3)
    state_repeat_2 = stack_a.evaluate(1.0, sample_index=3)
    assert state_repeat_1 == state_repeat_2

    stack_b = ChannelStack([make_effect()], provider, seed=seed)  # fresh instance
    state_fresh = stack_b.evaluate(1.0, sample_index=3)
    assert state_fresh == state_repeat_1

    stack_c = ChannelStack([make_effect()], provider, seed=seed)  # out-of-order
    stack_c.evaluate(1.0, sample_index=5)
    state_out_of_order = stack_c.evaluate(1.0, sample_index=3)
    assert state_out_of_order == state_repeat_1

    # Different index differs -- an empirical stream-separation tripwire
    # (plan §3), never proof of the independence model.
    state_other_index = stack_a.evaluate(1.0, sample_index=4)
    assert state_other_index != state_repeat_1


# ---------------------------------------------------------------------------
# 10. SeedRequiredError without link_seed, including the zero-variance
#     effect (stochastic by contract)
# ---------------------------------------------------------------------------


def test_seed_required_error_without_link_seed():
    provider = _ConstantGeometryProvider(_noop_geom())
    effect = MuFluctuationEffect(relative_sigma=0.2)
    stack = ChannelStack([effect], provider)  # seed=None (default)
    with pytest.raises(SeedRequiredError):
        stack.evaluate(0.0, sample_index=0)


def test_seed_required_error_for_zero_variance_effect_too():
    provider = _ConstantGeometryProvider(_noop_geom())
    effect = MuFluctuationEffect(relative_sigma=0.0)  # stochastic by contract
    stack = ChannelStack([effect], provider)
    with pytest.raises(SeedRequiredError):
        stack.evaluate(0.0, sample_index=0)


# ---------------------------------------------------------------------------
# 11. Static domains: afterpulse_prob boundaries 0/1 accepted, dead_time_s=0
#     accepted; NaN/+-inf/negatives rejected at construction
# ---------------------------------------------------------------------------


def test_afterpulsing_and_dead_time_construction_accepts_boundaries():
    DetectorAfterpulsingEffect(afterpulse_prob=0.0)
    DetectorAfterpulsingEffect(afterpulse_prob=1.0)
    DetectorDeadTimeEffect(dead_time_s=0.0)
    # Documented: parameter acceptance is not a claim that every later
    # detector law is well-defined at every boundary (plan §4 test 11) --
    # LINK-5 assigns no throughput/afterpulse law at all (plan §2.2, §2.3).


@pytest.mark.parametrize("afterpulse_prob", [float("nan"), float("inf"), float("-inf"), -0.01, 1.01])
def test_afterpulsing_construction_rejects_invalid_domain(afterpulse_prob):
    with pytest.raises(ValueError):
        DetectorAfterpulsingEffect(afterpulse_prob=afterpulse_prob)


@pytest.mark.parametrize("dead_time_s", [float("nan"), float("inf"), float("-inf"), -1e-9])
def test_dead_time_construction_rejects_invalid_domain(dead_time_s):
    with pytest.raises(ValueError):
        DetectorDeadTimeEffect(dead_time_s=dead_time_s)


# ---------------------------------------------------------------------------
# 12. Real afterpulsing/dead-time + distinct-ID nonzero mock => single-
#     contributor conflict; afterpulse + dead-time contributors coexist;
#     values pass through unchanged; duplicate fixed IDs collide
# ---------------------------------------------------------------------------


def test_second_nonzero_afterpulse_contributor_conflicts():
    provider = _ConstantGeometryProvider(_noop_geom())
    real = DetectorAfterpulsingEffect(afterpulse_prob=0.05)
    mock = _MockDetectorFieldEffect(effect_id="mock_afterpulse", afterpulse_prob=0.02)
    stack = ChannelStack([real, mock], provider)
    with pytest.raises(SingleContributorConflictError):
        stack.evaluate(0.0, sample_index=0)


def test_second_nonzero_dead_time_contributor_conflicts():
    provider = _ConstantGeometryProvider(_noop_geom())
    real = DetectorDeadTimeEffect(dead_time_s=50e-9)
    mock = _MockDetectorFieldEffect(effect_id="mock_dead_time", dead_time_s=25e-9)
    stack = ChannelStack([real, mock], provider)
    with pytest.raises(SingleContributorConflictError):
        stack.evaluate(0.0, sample_index=0)


def test_afterpulse_and_dead_time_contributors_coexist_values_unchanged():
    provider = _ConstantGeometryProvider(_noop_geom())
    afterpulse = DetectorAfterpulsingEffect(afterpulse_prob=0.03)
    dead_time = DetectorDeadTimeEffect(dead_time_s=40e-9)
    stack = ChannelStack([afterpulse, dead_time], provider)

    state = stack.evaluate(0.0, sample_index=0)
    # Passed through unchanged (single-contributor fields, not "composed" --
    # plan §2, LINK-1 pattern).
    assert state.detector.afterpulse_prob == 0.03
    assert state.detector.dead_time_s == 40e-9


def test_duplicate_fixed_effect_ids_collide():
    provider = _ConstantGeometryProvider(_noop_geom())
    with pytest.raises(DuplicateEffectIdError):
        ChannelStack(
            [
                DetectorAfterpulsingEffect(afterpulse_prob=0.01),
                DetectorAfterpulsingEffect(afterpulse_prob=0.02),
            ],
            provider,
        )
    with pytest.raises(DuplicateEffectIdError):
        ChannelStack(
            [DetectorDeadTimeEffect(dead_time_s=1e-8), DetectorDeadTimeEffect(dead_time_s=2e-8)],
            provider,
        )


# ---------------------------------------------------------------------------
# 13. Direct apply_link_state source-rejection test, plus the three
#     simulate_pass rejections naming source.intensity_factor,
#     detector.afterpulse_prob, detector.dead_time_s
# ---------------------------------------------------------------------------


def test_apply_link_state_rejects_nonidentity_source_intensity_factor_directly():
    state = EffectiveLinkState(
        channel=ChannelObservables(),
        detector=DetectorObservables(),
        source=SourceObservables(intensity_factor=1.3),
    )
    with pytest.raises(UnsupportedLinkObservableError) as excinfo:
        apply_link_state(state, channel=_channel_state(), detector=_detector_params())
    assert "source.intensity_factor" in str(excinfo.value)


def test_apply_link_state_accepts_identity_source():
    state = EffectiveLinkState(
        channel=ChannelObservables(), detector=DetectorObservables(), source=SourceObservables()
    )
    apply_link_state(state, channel=_channel_state(), detector=_detector_params())  # no raise


def test_simulate_pass_rejects_mu_fluctuation_via_bridge():
    cfg = MissionConfig(samples=21)
    effect = MuFluctuationEffect(relative_sigma=0.1)
    with pytest.raises(UnsupportedLinkObservableError, match="source.intensity_factor"):
        simulate_pass(cfg, link_effects=[effect], link_seed=1)


def test_simulate_pass_rejects_detector_afterpulsing_via_bridge():
    cfg = MissionConfig(samples=21)
    effect = DetectorAfterpulsingEffect(afterpulse_prob=0.02)
    with pytest.raises(UnsupportedLinkObservableError, match="detector.afterpulse_prob"):
        simulate_pass(cfg, link_effects=[effect])


def test_simulate_pass_rejects_detector_dead_time_via_bridge():
    cfg = MissionConfig(samples=21)
    effect = DetectorDeadTimeEffect(dead_time_s=50e-9)
    with pytest.raises(UnsupportedLinkObservableError, match="detector.dead_time_s"):
        simulate_pass(cfg, link_effects=[effect])


# ---------------------------------------------------------------------------
# 14. Frozen-hash / captured-fixture / LINK-1-4 regression: default emission
#     byte-identical. (The rest of test 14 -- unmodified existing test files
#     passing -- is exercised by the same pytest invocation that collects
#     this file.)
# ---------------------------------------------------------------------------


def test_default_mission_emission_unaffected_by_link5():
    cfg = MissionConfig(samples=11)
    result_a = simulate_pass(cfg)
    result_b = simulate_pass(cfg)
    payload_a = _build_results(result_a, plot_path="outputs/qkd_teleportation.png")
    payload_b = _build_results(result_b, plot_path="outputs/qkd_teleportation.png")

    assert validate_results_schema(payload_a, deep=True) is True
    assert _canonical_bytes(payload_a) == _canonical_bytes(payload_b)


def test_link_observables_and_effective_link_state_repr_shape_includes_source():
    # Recorded openly (LINK-5 plan §1.1): the internal repr/eq/asdict shape
    # of both classes changes; this pins that the new field is visible in
    # both, in the documented default form.
    observables = LinkObservables()
    state = EffectiveLinkState(channel=ChannelObservables(), detector=DetectorObservables())
    assert "source=SourceObservables" in repr(observables)
    assert "source=SourceObservables" in repr(state)
    assert dataclasses.asdict(observables)["source"] == {"intensity_factor": 1.0}
    assert dataclasses.asdict(state)["source"] == {"intensity_factor": 1.0}
