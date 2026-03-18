"""
Phase 1 — Data layer: news.py

Tests validate that the news module returns a unified list of headlines
from Google News RSS (and optionally Finviz), with correct structure.
"""

import pytest

pytestmark = pytest.mark.phase1


class TestNewsOutput:
    def test_returns_list(self, aapl_news):
        assert isinstance(aapl_news, list), "Expected a list of news items"

    def test_not_empty(self, aapl_news):
        assert len(aapl_news) > 0, "News list is empty — Google News RSS may have failed"

    def test_items_have_required_fields(self, aapl_news):
        required = {"headline", "source", "timestamp", "url"}
        for i, item in enumerate(aapl_news[:5]):
            missing = required - item.keys()
            assert not missing, f"Item {i} missing fields: {missing}"

    def test_headlines_are_non_empty_strings(self, aapl_news):
        for item in aapl_news[:10]:
            assert isinstance(item["headline"], str), "Headline is not a string"
            assert len(item["headline"].strip()) > 0, "Headline is empty string"

    def test_sources_are_non_empty_strings(self, aapl_news):
        for item in aapl_news[:10]:
            assert isinstance(item["source"], str)
            assert len(item["source"].strip()) > 0

    def test_urls_look_valid(self, aapl_news):
        for item in aapl_news[:10]:
            url = item.get("url", "")
            assert url.startswith("http"), f"URL doesn't look valid: {url}"

    def test_timestamps_are_strings(self, aapl_news):
        for item in aapl_news[:10]:
            ts = item.get("timestamp")
            assert isinstance(ts, str), f"Timestamp should be string, got {type(ts)}"
