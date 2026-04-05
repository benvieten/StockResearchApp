"""
Phase 3 — Sector agent: return computation unit tests.

compute_12m_return() is pure Python with no LLM or network calls.
Tests cover the normal path, edge cases, and the exact boundary condition.
"""

import pytest

pytestmark = [pytest.mark.phase3, pytest.mark.unit]


@pytest.fixture
def compute_return():
    from backend.agents.sector import compute_12m_return

    return compute_12m_return


def _make_ohlcv(n: int, start: float = 100.0, end: float = 120.0) -> dict:
    """Build a minimal OHLCV dict with `n` closes linearly from start to end."""
    import numpy as np

    closes = list(np.linspace(start, end, n))
    return {"close": closes}


class TestCompute12mReturn:
    def test_positive_return_computed_correctly(self, compute_return):
        # 253 closes: past_price = closes[-253] = 100.0, last = closes[-1] = 120.0
        ohlcv = _make_ohlcv(n=253, start=100.0, end=120.0)
        result = compute_return(ohlcv)
        assert result is not None
        assert result == pytest.approx(
            0.20, rel=1e-3
        ), f"Expected ~20% return, got {result}"

    def test_negative_return_computed_correctly(self, compute_return):
        ohlcv = _make_ohlcv(n=253, start=100.0, end=80.0)
        result = compute_return(ohlcv)
        assert result is not None
        assert result == pytest.approx(-0.20, rel=1e-3)

    def test_returns_none_when_fewer_than_253_closes(self, compute_return):
        ohlcv = _make_ohlcv(n=252)
        result = compute_return(ohlcv)
        assert (
            result is None
        ), "Need at least 253 closes (today + 252 trading days back); 252 must return None"

    def test_boundary_exactly_253_closes_returns_value(self, compute_return):
        ohlcv = _make_ohlcv(n=253)
        result = compute_return(ohlcv)
        assert result is not None

    def test_returns_none_for_empty_closes(self, compute_return):
        result = compute_return({"close": []})
        assert result is None

    def test_returns_none_when_past_price_is_zero(self, compute_return):
        import numpy as np

        closes = list(np.linspace(100.0, 110.0, 253))
        closes[-253] = 0.0  # set past price to zero → division by zero guard
        result = compute_return({"close": closes})
        assert (
            result is None
        ), "Zero past price must not produce a return (division by zero)"

    def test_returns_none_when_past_price_is_none(self, compute_return):
        import numpy as np

        closes = list(np.linspace(100.0, 110.0, 253))
        closes[-253] = None  # type: ignore
        result = compute_return({"close": closes})
        assert result is None

    def test_flat_price_gives_zero_return(self, compute_return):
        ohlcv = _make_ohlcv(n=253, start=100.0, end=100.0)
        result = compute_return(ohlcv)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_extra_closes_uses_correct_window(self, compute_return):
        """With 300 closes, only the last 253 matter — index [-253] is the reference."""
        import numpy as np

        # First 47 closes are irrelevant noise
        noise = list(np.ones(47) * 999.0)
        # Closes [-253] onward: past=100, last=110
        window = list(np.linspace(100.0, 110.0, 253))
        ohlcv = {"close": noise + window}
        result = compute_return(ohlcv)
        assert result is not None
        assert result == pytest.approx(0.10, rel=1e-2)
