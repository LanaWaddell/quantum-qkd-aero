"""Acceptance and unit tests for LINK-1 (docs/LINK_1_PLAN.md §9; ADR-0003 §7.1).

Test-only mock effects (``IdentityEffect``, ``MultiplicativeMockEffect``,
``ControlledMockEffect``, ``StochasticMockEffect``) live here, not in
``src/qkd/link.py`` -- the production module ships contracts and runtime only.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from qkd.link import (
    ChannelObservables,
    ChannelStack,
    ControlBoundsError,
    ControlSpec,
    DetectorObservables,
    DuplicateControlNameError,
    DuplicateEffectIdError,
    EffectiveLinkState,
    GeometryTableError,
    InfeasibleControlError,
    InvalidObservableError,
    LinkObservables,
    SeedRequiredError,
    SingleContributorConflictError,
    TableGeometryProvider,
    UndeclaredControlError,
    UnsupportedCorrelatedCompositionError,
    UnsupportedLinkObservableError,
    _child_rng,
    apply_link_state,
)
from qkd.mission import MissionConfig, simulate_pass
from qkd.orbit import satellite_pass
from qkd.run import _build_results
from qkd.schema import validate_results_schema
from qkd.signals import ChannelState, DetectorParams


# ---------------------------------------------------------------------------
# Test-only mock effects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityEffect:
    """Emits only default (identity) observables."""

    effect_id: str = "identity"

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables()


@dataclass(frozen=True)
class MultiplicativeMockEffect:
    """Constant transmittance_factor / efficiency_factor multiplier."""

    effect_id: str
    transmittance_factor: float = 1.0
    efficiency_factor: float = 1.0

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=self.transmittance_factor),
            detector=DetectorObservables(efficiency_factor=self.efficiency_factor),
        )


@dataclass(frozen=True)
class ControlledMockEffect:
    """Declares one control and folds its value into transmittance_factor."""

    effect_id: str
    control_name: str = "mock_control"
    bounds: tuple[float, float] = (0.0, 1.0)
    description: str = "Mock intervention-surface control for LINK-1 tests."
    unit: str = "1"
    feasible: Callable[[EffectiveLinkState], tuple[float, float]] | None = None

    def controls(self) -> tuple[ControlSpec, ...]:
        return (
            ControlSpec(
                name=self.control_name,
                unit=self.unit,
                bounds=self.bounds,
                description=self.description,
                feasible=self.feasible,
            ),
        )

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        value = context.controls.get(self.control_name)
        transmittance_factor = 1.0 if value is None else float(value)
        return LinkObservables(
            channel=ChannelObservables(transmittance_factor=transmittance_factor)
        )


@dataclass(frozen=True)
class StochasticMockEffect:
    """Writes a deterministic-per-(seed, effect_id, purpose, index) draw into one field.

    No mutable state is held between calls (R1): the draw is a pure function
    of ``context.rng_for``, itself a pure function of stack identity.
    """

    effect_id: str
    purpose: str = "draw"
    observable_field: str = "frequency_offset_hz"

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        rng = context.rng_for(self.purpose, context.sample_index)
        draw = float(rng.random())  # in [0, 1)
        return LinkObservables(channel=ChannelObservables(**{self.observable_field: draw}))


@dataclass(frozen=True)
class CorrelatedMockEffect:
    """Emits a nonzero value on a declared-correlated field (R3 fail-loud boundary)."""

    effect_id: str
    observable_field: str
    value: float = 1.0
    correlated_fields: tuple[str, ...] = ()

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(channel=ChannelObservables(**{self.observable_field: self.value}))


@dataclass(frozen=True)
class ConstantObservableEffect:
    """Emits a fixed channel/detector observable pair, for boundary-value tests."""

    effect_id: str
    channel: ChannelObservables = ChannelObservables()
    detector: DetectorObservables = DetectorObservables()

    def evaluate(self, t, geom, *, context) -> LinkObservables:
        return LinkObservables(channel=self.channel, detector=self.detector)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _fast_config() -> MissionConfig:
    return MissionConfig(samples=21)


def _small_pass():
    return satellite_pass(samples=9, altitude_km=550.0, peak_elevation_deg=90.0, horizon_elevation_deg=10.0)


def _provider():
    return TableGeometryProvider(_small_pass())


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


# ---------------------------------------------------------------------------
# 1. None / empty / all-identity byte-identity (§7.1-1)
# ---------------------------------------------------------------------------


def test_none_empty_identity_paths_byte_identical():
    cfg = _fast_config()

    result_none = simulate_pass(cfg)
    result_empty = simulate_pass(cfg, link_effects=[])
    result_identity = simulate_pass(
        cfg, link_effects=[IdentityEffect("id-1"), IdentityEffect("id-2")], link_seed=7
    )

    payload_none = _build_results(result_none, plot_path="outputs/qkd_teleportation.png")
    payload_empty = _build_results(result_empty, plot_path="outputs/qkd_teleportation.png")
    payload_identity = _build_results(result_identity, plot_path="outputs/qkd_teleportation.png")

    bytes_none = _canonical_bytes(payload_none)
    bytes_empty = _canonical_bytes(payload_empty)
    bytes_identity = _canonical_bytes(payload_identity)

    assert bytes_none == bytes_empty == bytes_identity

    for payload in (payload_none, payload_empty, payload_identity):
        assert validate_results_schema(payload, deep=True) is True


# ---------------------------------------------------------------------------
# 2. Multiplicative transmittance effect (§7.1-2)
# ---------------------------------------------------------------------------


def test_multiplicative_effect_scales_transmittance_exactly_once():
    provider = _provider()
    stack = ChannelStack(
        [
            MultiplicativeMockEffect("t1", transmittance_factor=0.5),
            MultiplicativeMockEffect("t2", transmittance_factor=0.4),
        ],
        provider,
    )
    t = _small_pass().time_s[0]
    state = stack.evaluate(t, sample_index=0)

    assert state.channel.transmittance_factor == pytest.approx(0.2, rel=0.0, abs=1e-15)

    base_channel = _channel_state(transmittance=0.8)
    new_channel, _ = apply_link_state(state, channel=base_channel, detector=_detector_params())

    expected = 0.8 * 0.2
    assert new_channel.transmittance == pytest.approx(expected, rel=0.0, abs=1e-15)
    # exactly-once fold: base object left untouched
    assert base_channel.transmittance == 0.8


# ---------------------------------------------------------------------------
# 3. Detector efficiency effect (§7.1-3)
# ---------------------------------------------------------------------------


def test_detector_efficiency_folds_exactly_once():
    provider = _provider()
    stack = ChannelStack(
        [MultiplicativeMockEffect("e1", efficiency_factor=0.8)],
        provider,
    )
    t = _small_pass().time_s[0]
    state = stack.evaluate(t, sample_index=0)

    assert state.detector.efficiency_factor == pytest.approx(0.8, rel=0.0, abs=1e-15)

    base_detector = _detector_params(detection_efficiency=0.5)
    _, new_detector = apply_link_state(state, channel=_channel_state(), detector=base_detector)

    assert new_detector.detection_efficiency == pytest.approx(0.4, rel=0.0, abs=1e-15)
    assert base_detector.detection_efficiency == 0.5


# ---------------------------------------------------------------------------
# 4. Undeclared runtime control rejected (§7.1-4)
# ---------------------------------------------------------------------------


def test_undeclared_runtime_control_rejected():
    provider = _provider()
    stack = ChannelStack([IdentityEffect()], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(UndeclaredControlError):
        stack.evaluate(t, controls={"nonexistent": 0.5}, sample_index=0)


# ---------------------------------------------------------------------------
# 5. Out-of-bounds control rejected, names spec (§7.1-5)
# ---------------------------------------------------------------------------


def test_out_of_bounds_control_rejected_names_spec():
    provider = _provider()
    effect = ControlledMockEffect("ctl", control_name="mock_control", bounds=(0.0, 1.0))
    stack = ChannelStack([effect], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(ControlBoundsError) as excinfo:
        stack.evaluate(t, controls={"mock_control": 5.0}, sample_index=0)

    message = str(excinfo.value)
    assert "mock_control" in message
    assert effect.description in message


# ---------------------------------------------------------------------------
# 6. Infeasible control rejected (named, not clamped) + empty-intersection (§7.1-5 / §7.6)
# ---------------------------------------------------------------------------


def test_infeasible_control_rejected_named_not_clamped():
    provider = _provider()

    def feasible(state: EffectiveLinkState) -> tuple[float, float]:
        return (0.2, 0.3)

    effect = ControlledMockEffect(
        "ctl", control_name="mock_control", bounds=(0.0, 1.0), feasible=feasible
    )
    stack = ChannelStack([effect], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(InfeasibleControlError) as excinfo:
        stack.evaluate(t, controls={"mock_control": 0.5}, sample_index=0)

    message = str(excinfo.value)
    assert "mock_control" in message
    assert "0.2" in message and "0.3" in message


def test_infeasible_control_empty_intersection_rejected():
    provider = _provider()

    def feasible(state: EffectiveLinkState) -> tuple[float, float]:
        return (0.6, 0.7)

    # static bounds [0, 0.5] never intersect feasible [0.6, 0.7]
    effect = ControlledMockEffect(
        "ctl", control_name="mock_control", bounds=(0.0, 0.5), feasible=feasible
    )
    stack = ChannelStack([effect], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(InfeasibleControlError):
        stack.evaluate(t, controls={"mock_control": 0.3}, sample_index=0)


# ---------------------------------------------------------------------------
# 7. Fixed seed replay deterministic (§7.1-6)
# ---------------------------------------------------------------------------


def test_fixed_seed_replay_deterministic():
    provider = _provider()
    stack = ChannelStack([StochasticMockEffect("s1")], provider, seed=123)
    t = _small_pass().time_s[3]

    state_a = stack.evaluate(t, sample_index=3)
    state_b = stack.evaluate(t, sample_index=3)

    assert state_a == state_b


# ---------------------------------------------------------------------------
# 8. Reorder/insert/remove leaves unrelated streams unchanged (§7.1-6)
# ---------------------------------------------------------------------------


def test_effect_reorder_insert_remove_leaves_unrelated_streams_unchanged():
    provider = _provider()
    t = _small_pass().time_s[2]
    seed = 99

    target = StochasticMockEffect("target", purpose="freq", observable_field="frequency_offset_hz")
    other_a = MultiplicativeMockEffect("other-a", transmittance_factor=0.7)
    other_b = MultiplicativeMockEffect("other-b", transmittance_factor=0.3)

    stack_alone = ChannelStack([target], provider, seed=seed)
    stack_before = ChannelStack([other_a, other_b, target], provider, seed=seed)
    stack_after = ChannelStack([target, other_a, other_b], provider, seed=seed)
    stack_between = ChannelStack([other_a, target, other_b], provider, seed=seed)

    freq_alone = stack_alone.evaluate(t, sample_index=2).channel.frequency_offset_hz
    freq_before = stack_before.evaluate(t, sample_index=2).channel.frequency_offset_hz
    freq_after = stack_after.evaluate(t, sample_index=2).channel.frequency_offset_hz
    freq_between = stack_between.evaluate(t, sample_index=2).channel.frequency_offset_hz

    assert freq_alone == freq_before == freq_after == freq_between


# ---------------------------------------------------------------------------
# 9. Fresh stack instances, same seed, identical
# ---------------------------------------------------------------------------


def test_fresh_stack_instances_same_seed_identical():
    provider = _provider()
    t = _small_pass().time_s[1]

    stack_1 = ChannelStack([StochasticMockEffect("s1")], provider, seed=55)
    stack_2 = ChannelStack([StochasticMockEffect("s1")], provider, seed=55)

    assert stack_1.evaluate(t, sample_index=1) == stack_2.evaluate(t, sample_index=1)


# ---------------------------------------------------------------------------
# 10. Indexed samples replay under different call orders
# ---------------------------------------------------------------------------


def test_indexed_samples_replay_under_different_call_orders():
    pass_geometry = _small_pass()
    provider = TableGeometryProvider(pass_geometry)
    effect = StochasticMockEffect("s1")

    stack_forward = ChannelStack([effect], provider, seed=17)
    stack_reverse = ChannelStack([effect], provider, seed=17)

    forward_results = {
        idx: stack_forward.evaluate(pass_geometry.time_s[idx], sample_index=idx)
        for idx in range(4)
    }
    reverse_results = {
        idx: stack_reverse.evaluate(pass_geometry.time_s[idx], sample_index=idx)
        for idx in reversed(range(4))
    }

    assert forward_results == reverse_results


# ---------------------------------------------------------------------------
# 11. Duplicate effect_id rejected
# ---------------------------------------------------------------------------


def test_duplicate_effect_id_rejected():
    provider = _provider()
    with pytest.raises(DuplicateEffectIdError):
        ChannelStack([IdentityEffect("dup"), MultiplicativeMockEffect("dup")], provider)


def test_duplicate_effect_id_rejected_two_instances_of_same_type():
    provider = _provider()
    with pytest.raises(DuplicateEffectIdError):
        ChannelStack([IdentityEffect("dup"), IdentityEffect("dup")], provider)


# ---------------------------------------------------------------------------
# 12. Duplicate control name rejected
# ---------------------------------------------------------------------------


def test_duplicate_control_name_rejected():
    provider = _provider()
    effect_a = ControlledMockEffect("ctl-a", control_name="shared")
    effect_b = ControlledMockEffect("ctl-b", control_name="shared")
    with pytest.raises(DuplicateControlNameError):
        ChannelStack([effect_a, effect_b], provider)


# ---------------------------------------------------------------------------
# 13. Canonical key: no collision with separator characters
# ---------------------------------------------------------------------------


def test_canonical_key_no_collision_with_separator_characters():
    rng_1 = _child_rng(7, "a:b", "c", None)
    rng_2 = _child_rng(7, "a", "b:c", None)

    draw_1 = rng_1.random()
    draw_2 = rng_2.random()

    assert draw_1 != draw_2


def test_canonical_key_stable_and_reproducible():
    rng_a = _child_rng(7, "effect", "purpose", 3)
    rng_b = _child_rng(7, "effect", "purpose", 3)
    assert rng_a.random() == rng_b.random()


# ---------------------------------------------------------------------------
# 14. Bridge rejects unsupported non-identity observable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("background_rate_hz", 10.0),
        ("misalignment_error", 0.1),
        ("frequency_offset_hz", 100.0),
        ("timing_jitter_s", 1e-9),
    ],
)
def test_bridge_rejects_unsupported_nonidentity_channel_observable(field_name, value):
    state = EffectiveLinkState(
        channel=ChannelObservables(**{field_name: value}),
        detector=DetectorObservables(),
    )
    with pytest.raises(UnsupportedLinkObservableError) as excinfo:
        apply_link_state(state, channel=_channel_state(), detector=_detector_params())
    assert field_name in str(excinfo.value)


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("dark_count_rate_hz", 10.0),
        ("afterpulse_prob", 0.1),
        ("dead_time_s", 1e-9),
    ],
)
def test_bridge_rejects_unsupported_nonidentity_detector_observable(field_name, value):
    state = EffectiveLinkState(
        channel=ChannelObservables(),
        detector=DetectorObservables(**{field_name: value}),
    )
    with pytest.raises(UnsupportedLinkObservableError) as excinfo:
        apply_link_state(state, channel=_channel_state(), detector=_detector_params())
    assert field_name in str(excinfo.value)


# ---------------------------------------------------------------------------
# 15. Correlated contribution raises unsupported error (jitter + background)
# ---------------------------------------------------------------------------


def test_correlated_contribution_raises_unsupported_error_background():
    provider = _provider()
    effect = CorrelatedMockEffect(
        "bg",
        observable_field="background_rate_hz",
        value=5.0,
        correlated_fields=("background_rate_hz",),
    )
    stack = ChannelStack([effect], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(UnsupportedCorrelatedCompositionError):
        stack.evaluate(t, sample_index=0)


def test_correlated_contribution_raises_unsupported_error_jitter():
    provider = _provider()
    effect = CorrelatedMockEffect(
        "jit",
        observable_field="timing_jitter_s",
        value=1e-9,
        correlated_fields=("timing_jitter_s",),
    )
    stack = ChannelStack([effect], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(UnsupportedCorrelatedCompositionError):
        stack.evaluate(t, sample_index=0)


# ---------------------------------------------------------------------------
# 16. Second-contributor rejection: misalignment / afterpulse / dead-time
# ---------------------------------------------------------------------------


def test_misalignment_second_contributor_rejected():
    provider = _provider()
    effect_a = ConstantObservableEffect("m1", channel=ChannelObservables(misalignment_error=0.1))
    effect_b = ConstantObservableEffect("m2", channel=ChannelObservables(misalignment_error=0.2))
    stack = ChannelStack([effect_a, effect_b], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(SingleContributorConflictError):
        stack.evaluate(t, sample_index=0)


def test_afterpulse_deadtime_second_contributor_rejected():
    provider = _provider()

    afterpulse_a = ConstantObservableEffect("a1", detector=DetectorObservables(afterpulse_prob=0.05))
    afterpulse_b = ConstantObservableEffect("a2", detector=DetectorObservables(afterpulse_prob=0.02))
    stack_afterpulse = ChannelStack([afterpulse_a, afterpulse_b], provider)

    dead_time_a = ConstantObservableEffect("d1", detector=DetectorObservables(dead_time_s=1e-8))
    dead_time_b = ConstantObservableEffect("d2", detector=DetectorObservables(dead_time_s=2e-8))
    stack_dead_time = ChannelStack([dead_time_a, dead_time_b], provider)

    t = _small_pass().time_s[0]

    with pytest.raises(SingleContributorConflictError):
        stack_afterpulse.evaluate(t, sample_index=0)

    with pytest.raises(SingleContributorConflictError):
        stack_dead_time.evaluate(t, sample_index=0)


# ---------------------------------------------------------------------------
# 17. Invalid observables rejected (parameterized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "channel_kwargs",
    [
        {"transmittance_factor": math.nan},
        {"transmittance_factor": math.inf},
        {"transmittance_factor": -0.1},
        {"transmittance_factor": 1.1},
        {"background_rate_hz": -1.0},
        {"background_rate_hz": math.inf},
        {"misalignment_error": -0.01},
        {"misalignment_error": 1.5},
        {"frequency_offset_hz": math.nan},
        {"timing_jitter_s": -1e-9},
        {"timing_jitter_s": math.inf},
    ],
)
def test_invalid_channel_observables_rejected(channel_kwargs):
    provider = _provider()
    effect = ConstantObservableEffect("bad", channel=ChannelObservables(**channel_kwargs))
    stack = ChannelStack([effect], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(InvalidObservableError):
        stack.evaluate(t, sample_index=0)


@pytest.mark.parametrize(
    "detector_kwargs",
    [
        {"efficiency_factor": math.nan},
        {"efficiency_factor": -0.1},
        {"efficiency_factor": 1.1},
        {"dark_count_rate_hz": -1.0},
        {"afterpulse_prob": -0.01},
        {"afterpulse_prob": 1.5},
        {"dead_time_s": -1e-9},
        {"dead_time_s": math.inf},
    ],
)
def test_invalid_detector_observables_rejected(detector_kwargs):
    provider = _provider()
    effect = ConstantObservableEffect("bad", detector=DetectorObservables(**detector_kwargs))
    stack = ChannelStack([effect], provider)
    t = _small_pass().time_s[0]

    with pytest.raises(InvalidObservableError):
        stack.evaluate(t, sample_index=0)


# ---------------------------------------------------------------------------
# 18. Geometry table validation and out-of-domain query
# ---------------------------------------------------------------------------


def test_geometry_table_validation_and_out_of_domain_query():
    good = _small_pass()

    with pytest.raises(GeometryTableError):
        TableGeometryProvider(
            type(good)(time_s=list(good.time_s), elevation_deg=list(good.elevation_deg[:-1]),
                       slant_range_km=list(good.slant_range_km))
        )

    non_increasing = type(good)(
        time_s=[0.0, 1.0, 1.0, 2.0],
        elevation_deg=[10.0, 20.0, 30.0, 40.0],
        slant_range_km=[100.0, 90.0, 80.0, 70.0],
    )
    with pytest.raises(GeometryTableError):
        TableGeometryProvider(non_increasing)

    non_finite = type(good)(
        time_s=[0.0, 1.0, float("nan")],
        elevation_deg=[10.0, 20.0, 30.0],
        slant_range_km=[100.0, 90.0, 80.0],
    )
    with pytest.raises(GeometryTableError):
        TableGeometryProvider(non_finite)

    provider = TableGeometryProvider(good)
    with pytest.raises(GeometryTableError):
        provider.at(good.time_s[0] - 1.0)
    with pytest.raises(GeometryTableError):
        provider.at(good.time_s[-1] + 1.0)


# ---------------------------------------------------------------------------
# 19. Exact-at-sample-times + snapshot immunity to post-construction mutation
# ---------------------------------------------------------------------------


def test_geometry_provider_exact_at_sample_times():
    pass_geometry = _small_pass()
    provider = TableGeometryProvider(pass_geometry)

    for index, t in enumerate(pass_geometry.time_s):
        geom = provider.at(t)
        assert geom.t_s == t
        assert geom.elevation_deg == pass_geometry.elevation_deg[index]
        assert geom.slant_range_km == pass_geometry.slant_range_km[index]


def test_geometry_provider_snapshot_immune_to_post_construction_mutation():
    pass_geometry = _small_pass()
    provider = TableGeometryProvider(pass_geometry)

    original_first_t = pass_geometry.time_s[0]
    original_first_elevation = pass_geometry.elevation_deg[0]
    pass_geometry.time_s.append(9999.0)
    pass_geometry.elevation_deg.append(-1.0)
    pass_geometry.slant_range_km.append(-1.0)
    pass_geometry.elevation_deg[0] = -999.0

    geom = provider.at(original_first_t)
    assert geom.elevation_deg == original_first_elevation

    with pytest.raises(GeometryTableError):
        provider.at(9999.0)


def test_geometry_provider_interpolates_between_samples_with_correct_t_s():
    pass_geometry = _small_pass()
    provider = TableGeometryProvider(pass_geometry)

    t0, t1 = pass_geometry.time_s[0], pass_geometry.time_s[1]
    mid_t = (t0 + t1) / 2.0
    geom = provider.at(mid_t)

    assert geom.t_s == mid_t
    expected_elevation = (pass_geometry.elevation_deg[0] + pass_geometry.elevation_deg[1]) / 2.0
    assert geom.elevation_deg == pytest.approx(expected_elevation, rel=0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 20. Stack provider wraps mission's own pass (R2 invariant)
# ---------------------------------------------------------------------------


def test_stack_provider_wraps_mission_pass(monkeypatch):
    import qkd.mission as mission_module

    captured = {}
    real_provider_cls = mission_module.TableGeometryProvider

    class RecordingProvider(real_provider_cls):
        def __init__(self, satellite_pass):
            captured["satellite_pass"] = satellite_pass
            super().__init__(satellite_pass)

    monkeypatch.setattr(mission_module, "TableGeometryProvider", RecordingProvider)

    result = simulate_pass(_fast_config(), link_effects=[IdentityEffect()])

    assert "satellite_pass" in captured
    assert captured["satellite_pass"].elevation_deg is result.elevation_deg
    assert captured["satellite_pass"].slant_range_km is result.slant_range_km
    # result.time_s is `simulate_profile`'s copied axis_values list; identity
    # is instead checked by value equality against the wrapped SatellitePass.
    assert captured["satellite_pass"].time_s == result.time_s


# ---------------------------------------------------------------------------
# 21. Jitter quadrature composition
# ---------------------------------------------------------------------------


def test_jitter_quadrature_composition():
    provider = _provider()
    effect_a = ConstantObservableEffect("j1", channel=ChannelObservables(timing_jitter_s=3.0))
    effect_b = ConstantObservableEffect("j2", channel=ChannelObservables(timing_jitter_s=4.0))
    stack = ChannelStack([effect_a, effect_b], provider)
    t = _small_pass().time_s[0]

    state = stack.evaluate(t, sample_index=0)

    assert state.channel.timing_jitter_s == pytest.approx(5.0, rel=0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 22. Control audit record byte-stable
# ---------------------------------------------------------------------------


def test_control_audit_record_byte_stable():
    provider = _provider()
    effect = ControlledMockEffect("ctl", control_name="mock_control")
    stack = ChannelStack([effect], provider, seed=42)

    controls = {"mock_control": 0.3}
    record_1 = stack.audit_record(controls)
    record_2 = stack.audit_record(controls)

    assert record_1 == record_2

    decoded = json.loads(record_1)
    assert decoded["link_seed"] == 42
    assert decoded["controls"] == controls
    assert decoded["effect_ids"] == ["ctl"]


def test_control_audit_record_differs_for_different_effect_ids():
    provider = _provider()
    stack_a = ChannelStack([IdentityEffect("a")], provider, seed=1)
    stack_b = ChannelStack([IdentityEffect("b")], provider, seed=1)

    assert stack_a.audit_record() != stack_b.audit_record()


# ---------------------------------------------------------------------------
# 23. seed=None rejected for a stochastic stack
# ---------------------------------------------------------------------------


def test_seed_none_rejected_for_stochastic_stack():
    provider = _provider()
    stack = ChannelStack([StochasticMockEffect("s1")], provider, seed=None)
    t = _small_pass().time_s[0]

    with pytest.raises(SeedRequiredError):
        stack.evaluate(t, sample_index=0)


def test_seed_none_allowed_for_wholly_deterministic_stack():
    provider = _provider()
    stack = ChannelStack(
        [MultiplicativeMockEffect("m1", transmittance_factor=0.9)], provider, seed=None
    )
    t = _small_pass().time_s[0]

    state = stack.evaluate(t, sample_index=0)
    assert state.channel.transmittance_factor == pytest.approx(0.9, rel=0.0, abs=1e-15)
