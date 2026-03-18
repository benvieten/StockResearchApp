"""
Phase 1 — Data layer: stocktwits.py

Tests validate that StockTwits messages are fetched with correct structure
and that all three sentiment states are handled.
"""

import pytest

pytestmark = pytest.mark.phase1

REQUIRED_MESSAGE_FIELDS = {"body", "sentiment", "created_at"}
VALID_SENTIMENTS = {"Bullish", "Bearish", None}


class TestStockTwitsOutput:
    def test_returns_list(self, aapl_stocktwits):
        assert isinstance(aapl_stocktwits, list)

    def test_not_empty(self, aapl_stocktwits):
        if len(aapl_stocktwits) == 0:
            pytest.skip(
                "StockTwits public API is returning 403 — "
                "unauthenticated access has been restricted upstream"
            )
        assert len(aapl_stocktwits) > 0

    def test_messages_have_required_fields(self, aapl_stocktwits):
        for i, msg in enumerate(aapl_stocktwits[:5]):
            missing = REQUIRED_MESSAGE_FIELDS - msg.keys()
            assert not missing, f"Message {i} missing fields: {missing}"

    def test_sentiment_values_are_valid(self, aapl_stocktwits):
        for msg in aapl_stocktwits:
            sentiment = msg.get("sentiment")
            assert sentiment in VALID_SENTIMENTS, (
                f"Unexpected sentiment value: {sentiment!r}. "
                f"Must be 'Bullish', 'Bearish', or None."
            )

    def test_all_three_sentiment_states_handled(self, aapl_stocktwits):
        """
        Verifies that absent sentiment is serialized as None, not missing key.
        This is the most common implementation bug with StockTwits data.
        """
        for msg in aapl_stocktwits:
            assert "sentiment" in msg, (
                "Message is missing 'sentiment' key entirely — "
                "absent sentiment must be serialized as None, not omitted"
            )

    def test_bodies_are_strings(self, aapl_stocktwits):
        for msg in aapl_stocktwits[:10]:
            assert isinstance(msg["body"], str)
            assert len(msg["body"].strip()) > 0

    def test_created_at_is_string(self, aapl_stocktwits):
        for msg in aapl_stocktwits[:10]:
            assert isinstance(msg["created_at"], str), (
                f"created_at should be string, got {type(msg['created_at'])}"
            )
