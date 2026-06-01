import math

import pytest

from qkd.bb84 import run_decoy_bb84
from qkd.eve import InterceptResend, NullEve, QND_PNS
from qkd.signals import ChannelState, DetectorParams


INTENSITIES = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}


def test_null_eve_through_pipeline_reproduces_honest_baseline():
    channel, detector = _reference_channel_and_detector()

    honest = run_decoy_bb84(channel, INTENSITIES, 1_000_000, detector)
    null_eve = run_decoy_bb84(channel, INTENSITIES, 1_000_000, detector, eve=NullEve())

    assert math.isclose(null_eve.qber, honest.qber, rel_tol=0.0, abs_tol=1e-12)
    assert math.isclose(
        null_eve.decoy_anomaly_score,
        0.0,
        rel_tol=0.0,
        abs_tol=1e-10,
    )
    for name in INTENSITIES:
        assert math.isclose(
            null_eve.gains[name],
            honest.gains[name],
            rel_tol=0.0,
            abs_tol=1e-12,
        )


def test_qnd_pns_is_qber_invisible_but_decoy_visible():
    channel, detector = _reference_channel_and_detector()

    honest = run_decoy_bb84(channel, INTENSITIES, 1_000_000, detector)
    pns = run_decoy_bb84(channel, INTENSITIES, 1_000_000, detector, eve=QND_PNS())

    assert math.isclose(pns.qber, honest.qber, rel_tol=0.0, abs_tol=1e-12)
    assert pns.decoy_anomaly_score > 0.1
    assert pns.gains["signal"] == pytest.approx(honest.gains["signal"], abs=1e-12)
    assert pns.gains["decoy"] < honest.gains["decoy"]


def test_qnd_pns_reduces_secure_key_rate_through_decoy_bound():
    channel, detector = _reference_channel_and_detector()

    honest = run_decoy_bb84(channel, INTENSITIES, 1_000_000, detector)
    pns = run_decoy_bb84(channel, INTENSITIES, 1_000_000, detector, eve=QND_PNS())

    assert pns.y1_lower_bound < honest.y1_lower_bound
    assert pns.secure_key_rate < honest.secure_key_rate


def test_intercept_resend_is_loud_in_qber():
    channel, detector = _reference_channel_and_detector()

    attacked = run_decoy_bb84(
        channel,
        INTENSITIES,
        1_000_000,
        detector,
        eve=InterceptResend(),
    )

    assert math.isclose(attacked.qber, 0.25, rel_tol=0.0, abs_tol=1e-4)


def _reference_channel_and_detector():
    channel = ChannelState(
        transmittance=0.4,
        werner_p=0.98,
        intrinsic_qber=0.015,
        dark_count_prob=0.0,
    )
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0e-6)

    return channel, detector
