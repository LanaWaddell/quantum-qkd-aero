import pytest


pytestmark = pytest.mark.skip(
    reason="Phase 2B future test: CHSH computation is not implemented in Phase 2A."
)


def test_chsh_value_future_contract():
    pass
