import random

from qkd.bb84 import compute_qber, run_bb84


def test_compute_qber_counts_mismatches():
    assert compute_qber([0, 1, 1, 0], [0, 0, 1, 1]) == 0.5


def test_compute_qber_handles_empty_key():
    assert compute_qber([], []) == 0.0


def test_run_bb84_current_no_noise_behavior():
    result = run_bb84(num_bits=32, p_loss=0.0, p_flip=0.0, rng=random.Random(42))

    bb84 = result["bb84"]
    assert bb84["input_bits"] == 32
    assert bb84["lost_bits"] == 0
    assert bb84["received_bits"] == 32
    assert bb84["qber"] == 0.0
