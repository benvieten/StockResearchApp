"""
Phase 4 — LangGraph graph: core/graph.py

Tests validate:
  1. ResearchState uses Annotated reducers (critical — without this, parallel agents
     silently overwrite each other with no error)
  2. run_research() returns a complete FinalReport for AAPL
  3. All 5 agent signals are present in the final state
  4. The graph does not propagate individual agent failures to the caller

These tests make real Anthropic API calls and consume tokens.
Only run after Phase 3 is fully validated: `pytest -m phase4`
"""

import pytest

pytestmark = pytest.mark.phase4


class TestResearchStateSchema:
    """
    Validate the state schema before running the graph.
    These are unit tests — no API calls.
    """

    @pytest.mark.unit
    def test_agent_signals_has_reducer(self):
        """
        The most critical structural test in the suite.
        Without Annotated[list, operator.add], parallel agents silently overwrite each other.
        """
        import typing
        from backend.core.graph import ResearchState

        hints = typing.get_type_hints(ResearchState, include_extras=True)
        agent_signals_hint = hints.get("agent_signals")

        assert agent_signals_hint is not None, (
            "ResearchState must have an 'agent_signals' field"
        )

        # Check it's Annotated — get_type_hints with include_extras=True preserves Annotated
        origin = getattr(agent_signals_hint, "__class__", None)
        metadata = getattr(agent_signals_hint, "__metadata__", ())

        assert len(metadata) > 0, (
            "agent_signals must use Annotated[list, operator.add] — "
            "without a reducer, parallel agents silently overwrite each other"
        )

        import operator
        assert operator.add in metadata, (
            "agent_signals reducer must be operator.add — "
            f"found: {metadata}"
        )

    @pytest.mark.unit
    def test_state_has_ticker_field(self):
        from backend.core.graph import ResearchState
        import typing
        hints = typing.get_type_hints(ResearchState)
        assert "ticker" in hints

    @pytest.mark.unit
    def test_state_has_final_report_field(self):
        from backend.core.graph import ResearchState
        import typing
        hints = typing.get_type_hints(ResearchState)
        assert "final_report" in hints


class TestRunResearch:
    """Integration tests — make real API calls. Require ANTHROPIC_API_KEY."""

    async def test_returns_final_report(self):
        from backend.core.graph import run_research
        from backend.core.data_models import FinalReport

        report = await run_research("AAPL")
        assert isinstance(report, FinalReport), (
            f"Expected FinalReport, got {type(report)}"
        )

    async def test_report_has_valid_verdict(self):
        from backend.core.graph import run_research

        report = await run_research("AAPL")
        valid_verdicts = {"strong_buy", "buy", "hold", "sell", "strong_sell"}
        assert report.verdict in valid_verdicts, (
            f"Verdict '{report.verdict}' not in {valid_verdicts}"
        )

    async def test_report_has_all_signal_scores(self):
        from backend.core.graph import run_research

        report = await run_research("AAPL")
        expected_agents = {"fundamental", "technical", "quant", "sector", "sentiment"}
        found = expected_agents & report.signal_scores.keys()
        assert len(found) == 5, (
            f"Expected all 5 signal scores, found: {found}"
        )

    async def test_report_has_conflicts_field(self):
        from backend.core.graph import run_research

        report = await run_research("AAPL")
        assert isinstance(report.conflicts, list), (
            "conflicts must be a list — may be empty if agents agree, but must exist"
        )

    async def test_report_ticker_is_aapl(self):
        from backend.core.graph import run_research

        report = await run_research("AAPL")
        assert report.ticker == "AAPL"

    async def test_report_has_narrative(self):
        from backend.core.graph import run_research

        report = await run_research("AAPL")
        assert len(report.narrative) > 50, "Narrative is unexpectedly short"

    async def test_report_has_generated_at(self):
        from backend.core.graph import run_research

        report = await run_research("AAPL")
        assert report.generated_at is not None
        assert len(report.generated_at) > 0


class TestParallelAgentExecution:
    """Validate that all 5 agents actually ran (not just synthesis)."""

    async def test_all_five_agents_produced_signals(self):
        """
        If the reducer is missing, some agents will be silently overwritten.
        This test catches that — all 5 must be present.
        """
        from backend.core.graph import run_research

        report = await run_research("AAPL")
        expected = {"fundamental", "technical", "quant", "sector", "sentiment"}
        present = set(report.signal_scores.keys()) & expected
        assert present == expected, (
            f"Not all agents produced signals. Present: {present}. "
            f"Missing: {expected - present}. "
            "This is often caused by a missing Annotated reducer on ResearchState.agent_signals."
        )


class TestAgentFailureIsolation:
    """Synthesis must handle partial agent failures gracefully."""

    async def test_invalid_ticker_returns_degraded_report(self):
        """
        A ticker with no Reddit data / StockTwits data should still
        produce a FinalReport — not raise an exception.
        """
        from backend.core.graph import run_research
        from backend.core.data_models import FinalReport

        # BRK.B is a valid ticker but has limited Reddit/StockTwits coverage
        try:
            report = await run_research("BRK.B")
            assert isinstance(report, FinalReport)
            # Some signals may be partial — that's acceptable
        except Exception as e:
            pytest.fail(
                f"run_research raised an exception instead of returning a degraded report: {e}"
            )
