import math
import random
from dataclasses import dataclass

from qkd.channel import transmit_bit
from qkd.signals import ChannelState, DetectorParams


@dataclass
class BB84Result:
    sifted_key_length: int
    qber: float
    gains: dict[str, float]
    qber_per_intensity: dict[str, float]
    y1_lower_bound: float
    e1_upper_bound: float
    q1: float
    secure_key_rate: float
    decoy_anomaly_score: float


def compute_qber(alice_key, bob_key):
    if not alice_key:
        return 0.0

    errors = sum(1 for alice_bit, bob_bit in zip(alice_key, bob_key) if alice_bit != bob_bit)
    return errors / len(alice_key)


def poisson_prob(n, mean_photon_number):
    if n < 0:
        raise ValueError("n must be non-negative.")
    if mean_photon_number < 0.0:
        raise ValueError("mean_photon_number must be non-negative.")

    return math.exp(-mean_photon_number) * (mean_photon_number**n) / math.factorial(n)


def poisson_distribution(mean_photon_number, *, tail_tolerance=1e-12, max_photons=100):
    if mean_photon_number < 0.0:
        raise ValueError("mean_photon_number must be non-negative.")
    if tail_tolerance <= 0.0:
        raise ValueError("tail_tolerance must be positive.")
    if max_photons < 0:
        raise ValueError("max_photons must be non-negative.")

    distribution = {}
    probability = math.exp(-mean_photon_number)
    cumulative = probability
    distribution[0] = probability

    n = 0
    while (1.0 - cumulative) > tail_tolerance and n < max_photons:
        n += 1
        probability *= mean_photon_number / n
        distribution[n] = probability
        cumulative += probability

    return distribution


def estimate_decoy_bounds(gains, qber_per_intensity, intensities):
    mu = intensities["signal"]
    nu = intensities["decoy"]
    y0 = gains["vacuum"]

    if not 0.0 <= intensities["vacuum"] < nu < mu:
        raise ValueError("intensities must satisfy 0 <= vacuum < decoy < signal.")

    q_mu = gains["signal"]
    q_nu = gains["decoy"]
    e_nu = qber_per_intensity["decoy"]
    e0 = 0.5

    denominator = (mu * nu) - (nu**2)
    y1_lower_bound = (mu / denominator) * (
        (q_nu * math.exp(nu))
        - (q_mu * math.exp(mu) * (nu**2 / mu**2))
        - (((mu**2 - nu**2) / mu**2) * y0)
    )
    y1_lower_bound = _clamp(y1_lower_bound, 0.0, 1.0)

    if y1_lower_bound == 0.0:
        e1_upper_bound = 0.5
    else:
        e1_upper_bound = ((e_nu * q_nu * math.exp(nu)) - (e0 * y0)) / (
            y1_lower_bound * nu
        )
        e1_upper_bound = _clamp(e1_upper_bound, 0.0, 0.5)

    return y1_lower_bound, e1_upper_bound


def binary_entropy(probability):
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1].")
    if probability in (0.0, 1.0):
        return 0.0

    return -(
        probability * math.log2(probability)
        + (1.0 - probability) * math.log2(1.0 - probability)
    )


def secure_key_rate(
    signal_gain,
    signal_qber,
    q1,
    e1_upper_bound,
    *,
    q=0.5,
    error_correction_efficiency=1.16,
):
    raw_rate = q * (
        -(signal_gain * error_correction_efficiency * binary_entropy(signal_qber))
        + (q1 * (1.0 - binary_entropy(e1_upper_bound)))
    )
    return max(0.0, raw_rate)


def run_decoy_bb84(channel, intensities, n_pulses, detector, eve=None, *, q=0.5):
    """Run deterministic expected-value decoy BB84 for the honest/null channel.

    This 2B-4a foundation computes expected gains, QBERs, decoy bounds, and
    the asymptotic key rate. It does not Monte Carlo sample finite pulses; if
    Monte Carlo is added later, estimator tests need statistical tolerances.

    DetectorParams.dark_count_prob is authoritative for BB84 detection windows.
    ChannelState.dark_count_prob is treated as channel-model provenance here.
    Finite-key corrections are out of scope for 2B-4a.
    """

    if eve is not None:
        raise NotImplementedError("Only honest/null decoy BB84 is implemented in 2B-4a.")
    if n_pulses < 0:
        raise ValueError("n_pulses must be non-negative.")

    _validate_channel_and_detector(channel, detector)
    _validate_intensities(intensities)

    eta = channel.transmittance * detector.detection_efficiency
    y0 = detector.dark_count_prob
    ed = channel.intrinsic_qber

    gains = {
        name: _honest_gain(mean_photon_number, eta, y0)
        for name, mean_photon_number in intensities.items()
    }
    qber_per_intensity = {
        name: _honest_qber(mean_photon_number, eta, y0, ed)
        for name, mean_photon_number in intensities.items()
    }

    y1_lower_bound, e1_upper_bound = estimate_decoy_bounds(
        gains,
        qber_per_intensity,
        intensities,
    )
    q1 = y1_lower_bound * intensities["signal"] * math.exp(-intensities["signal"])
    key_rate = secure_key_rate(
        gains["signal"],
        qber_per_intensity["signal"],
        q1,
        e1_upper_bound,
        q=q,
        error_correction_efficiency=detector.error_correction_efficiency,
    )

    honest_y1_lower_bound, _ = estimate_decoy_bounds(
        gains,
        qber_per_intensity,
        intensities,
    )
    decoy_anomaly_score = _relative_y1_shortfall(
        honest_y1_lower_bound,
        y1_lower_bound,
    )

    return BB84Result(
        sifted_key_length=round(n_pulses * q * gains["signal"]),
        qber=qber_per_intensity["signal"],
        gains=gains,
        qber_per_intensity=qber_per_intensity,
        y1_lower_bound=y1_lower_bound,
        e1_upper_bound=e1_upper_bound,
        q1=q1,
        secure_key_rate=key_rate,
        decoy_anomaly_score=decoy_anomaly_score,
    )


def run_bb84(num_bits=1000, p_loss=0.0, p_flip=0.0, rng=None):
    rng = rng or random.Random(42)

    alice_bits = [rng.randint(0, 1) for _ in range(num_bits)]
    alice_bases = [rng.choice(("Z", "X")) for _ in range(num_bits)]
    bob_bases = [rng.choice(("Z", "X")) for _ in range(num_bits)]

    received_bits = []
    sifted_alice_bits = []
    sifted_bob_bits = []

    lost_count = 0
    basis_matches = 0

    for alice_bit, alice_basis, bob_basis in zip(alice_bits, alice_bases, bob_bases):
        received_bit = transmit_bit(alice_bit, p_loss=p_loss, p_flip=p_flip, rng=rng)

        if received_bit is None:
            lost_count += 1
            received_bits.append(None)
            continue

        received_bits.append(received_bit)

        if alice_basis == bob_basis:
            basis_matches += 1
            sifted_alice_bits.append(alice_bit)
            sifted_bob_bits.append(received_bit)

    qber = compute_qber(sifted_alice_bits, sifted_bob_bits)

    return {
        "bb84": {
            "input_bits": num_bits,
            "lost_bits": lost_count,
            "received_bits": num_bits - lost_count,
            "basis_matches": basis_matches,
            "sifted_bits": len(sifted_alice_bits),
            "qber": round(qber, 4),
            "channel": {
                "p_loss": p_loss,
                "p_flip": p_flip,
            },
        },
        "raw": {
            "alice_bits": alice_bits,
            "alice_bases": alice_bases,
            "bob_bases": bob_bases,
            "received_bits": received_bits,
            "sifted_alice_bits": sifted_alice_bits,
            "sifted_bob_bits": sifted_bob_bits,
        },
    }


def _validate_channel_and_detector(channel, detector):
    if not isinstance(channel, ChannelState):
        raise TypeError("channel must be a ChannelState.")
    if not isinstance(detector, DetectorParams):
        raise TypeError("detector must be a DetectorParams.")
    if not 0.0 <= channel.transmittance <= 1.0:
        raise ValueError("channel.transmittance must be in [0, 1].")
    if not 0.0 <= detector.detection_efficiency <= 1.0:
        raise ValueError("detector.detection_efficiency must be in [0, 1].")
    if not 0.0 <= channel.intrinsic_qber <= 0.5:
        raise ValueError("channel.intrinsic_qber must be in [0, 0.5].")
    if not 0.0 <= detector.dark_count_prob <= 1.0:
        raise ValueError("detector.dark_count_prob must be in [0, 1].")


def _validate_intensities(intensities):
    required = {"signal", "decoy", "vacuum"}
    missing = required - set(intensities)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Missing intensities: {missing_names}")
    if not 0.0 <= intensities["vacuum"] < intensities["decoy"] < intensities["signal"]:
        raise ValueError("intensities must satisfy 0 <= vacuum < decoy < signal.")


def _honest_gain(mean_photon_number, eta, y0):
    if mean_photon_number == 0.0:
        return y0
    return 1.0 - ((1.0 - y0) * math.exp(-eta * mean_photon_number))


def _honest_qber(mean_photon_number, eta, y0, ed):
    if mean_photon_number == 0.0:
        return 0.5 if y0 > 0.0 else 0.0
    gain = _honest_gain(mean_photon_number, eta, y0)
    if gain == 0.0:
        return 0.0

    error_gain = (0.5 * y0) + (ed * (1.0 - math.exp(-eta * mean_photon_number)))
    return _clamp(error_gain / gain, 0.0, 0.5)


def _relative_y1_shortfall(reference_y1, observed_y1):
    if reference_y1 == 0.0:
        return 0.0
    return max(0.0, (reference_y1 - observed_y1) / reference_y1)


def _clamp(value, lower, upper):
    return max(lower, min(upper, value))
