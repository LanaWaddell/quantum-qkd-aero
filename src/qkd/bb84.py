import random

from qkd.channel import transmit_bit


def compute_qber(alice_key, bob_key):
    if not alice_key:
        return 0.0

    errors = sum(1 for alice_bit, bob_bit in zip(alice_key, bob_key) if alice_bit != bob_bit)
    return errors / len(alice_key)


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
