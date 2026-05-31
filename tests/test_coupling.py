import math

from qkd.chsh import chsh_value
from qkd.teleportation import teleportation_fidelity


def test_teleportation_beats_classical_only_above_one_third():
    assert teleportation_fidelity(1 / 3).beats_classical is False
    assert teleportation_fidelity((1 / 3) + 1e-6).beats_classical is True


def test_chsh_violates_only_above_one_over_sqrt_two():
    threshold = 1 / math.sqrt(2)

    assert chsh_value(threshold).violates is False
    assert chsh_value(threshold + 1e-6).violates is True
    assert chsh_value(threshold - 1e-6).violates is False


def test_transfer_useful_without_bell_violation_regime():
    werner_p = 0.5

    teleportation = teleportation_fidelity(werner_p)
    chsh = chsh_value(werner_p)

    assert 1 / 3 < werner_p < 1 / math.sqrt(2)
    assert teleportation.beats_classical is True
    assert teleportation.margin > 0
    assert chsh.violates is False
    assert chsh.margin <= 0
