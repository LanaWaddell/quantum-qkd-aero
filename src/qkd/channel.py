import math
import random


def apply_loss(bit, p_loss, rng=None):
    rng = rng or random
    if rng.random() < p_loss:
        return None
    return bit


def apply_bit_flip(bit, p_flip, rng=None):
    rng = rng or random
    if rng.random() < p_flip:
        return 1 - bit
    return bit


def transmit_bit(bit, p_loss=0.0, p_flip=0.0, rng=None):
    transmitted = apply_loss(bit, p_loss, rng=rng)
    if transmitted is None:
        return None
    return apply_bit_flip(transmitted, p_flip, rng=rng)


def fidelity_noise(frame_index, base_fidelity, noise_strength=0.05, p_loss=0.0, p_flip=0.0):
    jitter = math.sin(frame_index / 50) * noise_strength
    # Scale loss and bit-flip probabilities into a simple fidelity degradation term.
    penalty = (p_loss * 0.02) + (p_flip * 0.1)
    fidelity = base_fidelity + jitter - penalty
    return max(0.0, min(1.0, fidelity))
