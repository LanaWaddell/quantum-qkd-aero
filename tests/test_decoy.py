import math

from qkd.bb84 import (
    binary_entropy,
    poisson_distribution,
    poisson_prob,
    run_decoy_bb84,
)
from qkd.signals import ChannelState, DetectorParams


INTENSITIES = {"signal": 0.5, "decoy": 0.1, "vacuum": 0.0}


def test_poisson_distribution_normalizes_and_has_expected_mean():
    distribution = poisson_distribution(0.5, tail_tolerance=1e-14)

    assert math.isclose(poisson_prob(0, 0.5), math.exp(-0.5), rel_tol=0.0, abs_tol=1e-15)
    assert math.isclose(sum(distribution.values()), 1.0, rel_tol=0.0, abs_tol=1e-14)
    assert math.isclose(
        sum(n * probability for n, probability in distribution.items()),
        0.5,
        rel_tol=0.0,
        abs_tol=1e-13,
    )


def test_honest_decoy_gains_match_closed_form_expectations():
    channel, detector = _reference_channel_and_detector()
    result = run_decoy_bb84(channel, INTENSITIES, n_pulses=1_000_000, detector=detector)
    eta = channel.transmittance * detector.detection_efficiency
    y0 = detector.dark_count_prob

    for name, intensity in INTENSITIES.items():
        expected_gain = 1.0 - ((1.0 - y0) * math.exp(-eta * intensity))
        assert math.isclose(result.gains[name], expected_gain, rel_tol=0.0, abs_tol=1e-15)


def test_decoy_estimator_matches_regression_locked_reference_case():
    channel, detector = _reference_channel_and_detector()
    result = run_decoy_bb84(channel, INTENSITIES, n_pulses=1_000_000, detector=detector)

    # Regression anchors for the current Lo-Ma-Chen transcription; the
    # tightening-limit test below provides the structural behavior check.
    assert math.isclose(
        result.y1_lower_bound,
        0.09725428004793941,
        rel_tol=0.0,
        abs_tol=1e-15,
    )
    assert math.isclose(
        result.e1_upper_bound,
        0.01696605033056249,
        rel_tol=0.0,
        abs_tol=1e-15,
    )


def test_decoy_estimator_is_conservative_against_true_single_photon_values():
    channel, detector = _reference_channel_and_detector()
    result = run_decoy_bb84(channel, INTENSITIES, n_pulses=1_000_000, detector=detector)
    eta = channel.transmittance * detector.detection_efficiency
    y0 = detector.dark_count_prob
    ed = channel.intrinsic_qber
    e0 = 0.5

    y1_true = 1.0 - ((1.0 - y0) * (1.0 - eta))
    e1_true = ((e0 * y0) + (ed * eta)) / y1_true

    assert result.y1_lower_bound <= y1_true
    assert result.e1_upper_bound >= e1_true


def test_decoy_bound_tightens_as_decoy_intensity_approaches_vacuum():
    channel, detector = _reference_channel_and_detector()
    eta = channel.transmittance * detector.detection_efficiency
    y0 = detector.dark_count_prob
    y1_true = 1.0 - ((1.0 - y0) * (1.0 - eta))
    decoy_intensities = [0.2, 0.1, 0.05, 0.02, 0.01]

    estimates = [
        run_decoy_bb84(
            channel,
            {"signal": 0.5, "decoy": decoy_intensity, "vacuum": 0.0},
            n_pulses=1_000_000,
            detector=detector,
        ).y1_lower_bound
        for decoy_intensity in decoy_intensities
    ]

    assert all(estimate <= y1_true for estimate in estimates)
    assert estimates == sorted(estimates)
    assert (y1_true - estimates[-1]) < (y1_true - estimates[0])


def test_honest_channel_has_zero_decoy_anomaly_and_positive_key_rate():
    channel, detector = _reference_channel_and_detector()
    result = run_decoy_bb84(channel, INTENSITIES, n_pulses=1_000_000, detector=detector)

    assert result.decoy_anomaly_score == 0.0
    assert result.secure_key_rate > 0.0
    assert result.sifted_key_length == round(1_000_000 * 0.5 * result.gains["signal"])


def test_honest_key_rate_decreases_with_loss():
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0e-6)
    stronger_channel = ChannelState(
        transmittance=0.4,
        werner_p=0.98,
        intrinsic_qber=0.015,
        dark_count_prob=0.0,
    )
    weaker_channel = ChannelState(
        transmittance=0.04,
        werner_p=0.98,
        intrinsic_qber=0.015,
        dark_count_prob=0.0,
    )

    stronger = run_decoy_bb84(stronger_channel, INTENSITIES, 1_000_000, detector)
    weaker = run_decoy_bb84(weaker_channel, INTENSITIES, 1_000_000, detector)

    assert stronger.secure_key_rate > weaker.secure_key_rate


def test_detector_dark_count_is_authoritative_for_bb84():
    channel = ChannelState(
        transmittance=0.2,
        werner_p=0.98,
        intrinsic_qber=0.015,
        dark_count_prob=0.25,
    )
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0e-6)

    result = run_decoy_bb84(channel, INTENSITIES, n_pulses=1_000_000, detector=detector)

    assert result.gains["vacuum"] == detector.dark_count_prob


def test_binary_entropy_boundaries():
    assert binary_entropy(0.0) == 0.0
    assert binary_entropy(1.0) == 0.0
    assert math.isclose(binary_entropy(0.5), 1.0, rel_tol=0.0, abs_tol=1e-15)


def _reference_channel_and_detector():
    channel = ChannelState(
        transmittance=0.2,
        werner_p=0.98,
        intrinsic_qber=0.015,
        dark_count_prob=0.0,
    )
    detector = DetectorParams(detection_efficiency=0.5, dark_count_prob=1.0e-6)

    return channel, detector
