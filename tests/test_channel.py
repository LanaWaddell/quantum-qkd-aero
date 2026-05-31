from qkd.channel import apply_bit_flip, apply_loss, fidelity_noise, transmit_bit


def test_apply_loss_extremes():
    assert apply_loss(1, p_loss=0.0) == 1
    assert apply_loss(1, p_loss=1.0) is None


def test_apply_bit_flip_extremes():
    assert apply_bit_flip(0, p_flip=0.0) == 0
    assert apply_bit_flip(0, p_flip=1.0) == 1


def test_transmit_bit_applies_loss_before_flip():
    assert transmit_bit(1, p_loss=1.0, p_flip=1.0) is None
    assert transmit_bit(1, p_loss=0.0, p_flip=1.0) == 0


def test_fidelity_noise_clamps_to_unit_interval():
    assert fidelity_noise(0, base_fidelity=2.0) == 1.0
    assert fidelity_noise(0, base_fidelity=-1.0) == 0.0
