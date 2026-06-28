from qkd.mission import simulate_pass
from qkd.provenance import Provenance


def test_provenance_declares_in_use_and_reserved_tags():
    assert {tag.value for tag in Provenance} == {
        "ANALYTIC",
        "SIMULATED",
        "DERIVED",
        "ILLUSTRATIVE",
        "MEASURED",
        "ESTIMATED",
        "VALIDATED",
    }


def test_default_pass_does_not_apply_reserved_provenance_tags():
    reserved = {
        Provenance.MEASURED.value,
        Provenance.ESTIMATED.value,
        Provenance.VALIDATED.value,
    }

    result = simulate_pass()

    assert reserved.isdisjoint(set(result.provenance.values()))
