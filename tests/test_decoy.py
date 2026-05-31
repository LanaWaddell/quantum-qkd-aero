import pytest


pytestmark = pytest.mark.skip(
    reason="Phase 2B future test: decoy-state estimation is not implemented in Phase 2A."
)


def test_decoy_anomaly_future_contract():
    pass
