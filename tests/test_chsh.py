import math

import pytest

from qkd.chsh import CHSHResult, chsh_value


@pytest.mark.parametrize("method", ["analytic", "numeric"])
def test_chsh_returns_result_object(method):
    result = chsh_value(0.9, method=method)

    assert isinstance(result, CHSHResult)
    assert result.method == method


@pytest.mark.parametrize("method", ["analytic", "numeric"])
def test_chsh_constants(method):
    result = chsh_value(1.0, method=method)

    assert result.S == pytest.approx(2 * math.sqrt(2), abs=1e-12)
    assert result.classical_bound == 2.0
    assert result.tsirelson_bound == pytest.approx(2 * math.sqrt(2), abs=1e-12)
    assert result.violates is True
    assert result.margin == pytest.approx((2 * math.sqrt(2)) - 2.0, abs=1e-12)


@pytest.mark.parametrize("method", ["analytic", "numeric"])
def test_chsh_threshold(method):
    result = chsh_value(1 / math.sqrt(2), method=method)

    assert result.S == pytest.approx(2.0, abs=1e-12)
    assert result.violates is False
    assert result.margin == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("method", ["analytic", "numeric"])
def test_chsh_zero_state(method):
    result = chsh_value(0.0, method=method)

    assert result.S == pytest.approx(0.0, abs=1e-12)
    assert result.violates is False
    assert result.margin == pytest.approx(-2.0, abs=1e-12)


def test_chsh_numeric_matches_analytic():
    for werner_p in [0.0, 0.25, 1 / math.sqrt(2), 0.9, 1.0]:
        analytic = chsh_value(werner_p, method="analytic")
        numeric = chsh_value(werner_p, method="numeric")

        assert numeric.S == pytest.approx(analytic.S, abs=1e-12)
        assert numeric.violates is analytic.violates
        assert numeric.margin == pytest.approx(analytic.margin, abs=1e-12)


def test_chsh_rejects_out_of_range_p():
    with pytest.raises(ValueError, match="werner_p"):
        chsh_value(-0.1)

    with pytest.raises(ValueError, match="werner_p"):
        chsh_value(1.1)


def test_chsh_rejects_unknown_method():
    with pytest.raises(ValueError, match="Unknown CHSH method"):
        chsh_value(0.5, method="not-a-method")
