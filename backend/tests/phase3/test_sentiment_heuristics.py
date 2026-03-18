"""
Phase 3 — Sentiment agent: bot detection heuristic unit tests.

The bot detection logic is pure Python — deterministic, no LLM, no network.
These tests fully cover every heuristic rule before any LLM call is made.

Will fail until agents/sentiment.py exposes apply_bot_heuristics().
"""

from datetime import datetime
import pytest

pytestmark = [pytest.mark.phase3, pytest.mark.unit]


@pytest.fixture
def apply_heuristics():
    from backend.agents.sentiment import apply_bot_heuristics
    return apply_bot_heuristics


class TestNewAccountFlag:
    """Account age < 30 days at time of post → bot_flag: True"""

    def test_new_account_flagged(self, apply_heuristics, sample_reddit_posts):
        results = apply_heuristics(sample_reddit_posts)
        new_account_posts = [
            r for r in results if r["author"] == "user_new_account"
        ]
        assert len(new_account_posts) == 1
        assert new_account_posts[0]["bot_flag"] is True, (
            "Account < 30 days old at post time must be flagged as bot"
        )

    def test_old_account_not_flagged_for_age(self, apply_heuristics, sample_reddit_posts):
        results = apply_heuristics(sample_reddit_posts)
        clean_posts = [r for r in results if r["author"] == "user_clean"]
        assert len(clean_posts) == 1
        assert clean_posts[0]["bot_flag"] is False, (
            "Account > 30 days old should not be flagged for account age"
        )

    def test_boundary_exactly_30_days_not_flagged(self, apply_heuristics):
        """Boundary condition: exactly 30 days old = not flagged."""
        base_time = datetime(2026, 3, 18, 12, 0, 0).timestamp()
        posts = [
            {
                "title": "AAPL analysis",
                "selftext": "",
                "score": 50,
                "upvote_ratio": 0.85,
                "num_comments": 10,
                "author": "boundary_user",
                "author_created_utc": base_time - (30 * 86400),  # exactly 30 days
                "post_created_utc": base_time,
                "subreddit": "stocks",
            }
        ]
        results = apply_heuristics(posts)
        assert results[0]["bot_flag"] is False, (
            "Exactly 30 days old should NOT be flagged (threshold is < 30)"
        )


class TestSuspiciousVoteFlag:
    """upvote_ratio < 0.55 AND score > 100 → suspicious_flag: True"""

    def test_low_ratio_high_score_flagged(self, apply_heuristics, sample_reddit_posts):
        results = apply_heuristics(sample_reddit_posts)
        suspicious_posts = [
            r for r in results if r["author"] == "user_suspicious"
        ]
        assert len(suspicious_posts) == 1
        assert suspicious_posts[0]["suspicious_flag"] is True

    def test_low_ratio_low_score_not_flagged(self, apply_heuristics):
        base_time = datetime(2026, 3, 18, 12, 0, 0).timestamp()
        posts = [
            {
                "title": "AAPL thoughts",
                "selftext": "",
                "score": 50,            # below 100 — should NOT trigger
                "upvote_ratio": 0.48,   # below 0.55
                "num_comments": 5,
                "author": "normal_user",
                "author_created_utc": base_time - (90 * 86400),
                "post_created_utc": base_time,
                "subreddit": "stocks",
            }
        ]
        results = apply_heuristics(posts)
        assert results[0]["suspicious_flag"] is False

    def test_high_ratio_high_score_not_flagged(self, apply_heuristics):
        base_time = datetime(2026, 3, 18, 12, 0, 0).timestamp()
        posts = [
            {
                "title": "AAPL deep dive",
                "selftext": "Long analysis here...",
                "score": 800,
                "upvote_ratio": 0.94,   # above 0.55 — should NOT trigger
                "num_comments": 120,
                "author": "quality_user",
                "author_created_utc": base_time - (365 * 86400),
                "post_created_utc": base_time,
                "subreddit": "investing",
            }
        ]
        results = apply_heuristics(posts)
        assert results[0]["suspicious_flag"] is False


class TestSpamAuthorFlag:
    """Same author, 3+ posts about same ticker within 24h → bot_flag: True"""

    def test_spammer_all_three_posts_flagged(self, apply_heuristics, sample_reddit_posts):
        results = apply_heuristics(sample_reddit_posts)
        spammer_posts = [r for r in results if r["author"] == "user_spammer"]
        assert len(spammer_posts) == 3
        for post in spammer_posts:
            assert post["bot_flag"] is True, (
                f"All posts from spam author should be flagged: {post['title']}"
            )

    def test_two_posts_same_author_not_flagged(self, apply_heuristics):
        """2 posts in 24h is allowed — threshold is 3."""
        base_time = datetime(2026, 3, 18, 12, 0, 0).timestamp()
        posts = [
            {
                "title": "AAPL post 1",
                "selftext": "",
                "score": 20,
                "upvote_ratio": 0.80,
                "num_comments": 5,
                "author": "two_post_user",
                "author_created_utc": base_time - (180 * 86400),
                "post_created_utc": base_time - 3600,
                "subreddit": "stocks",
            },
            {
                "title": "AAPL post 2",
                "selftext": "",
                "score": 15,
                "upvote_ratio": 0.75,
                "num_comments": 3,
                "author": "two_post_user",
                "author_created_utc": base_time - (180 * 86400),
                "post_created_utc": base_time,
                "subreddit": "stocks",
            },
        ]
        results = apply_heuristics(posts)
        for post in results:
            assert post["bot_flag"] is False, (
                "Two posts from same author should NOT trigger spam flag"
            )

    def test_three_posts_outside_24h_not_flagged(self, apply_heuristics):
        """3 posts but spread over 25h — outside the 24h window."""
        base_time = datetime(2026, 3, 18, 12, 0, 0).timestamp()
        posts = [
            {
                "title": f"AAPL post {i}",
                "selftext": "",
                "score": 10,
                "upvote_ratio": 0.70,
                "num_comments": 2,
                "author": "spread_user",
                "author_created_utc": base_time - (90 * 86400),
                "post_created_utc": base_time - (i * 9 * 3600),  # 9h apart = 27h total
                "subreddit": "stocks",
            }
            for i in range(3)
        ]
        results = apply_heuristics(posts)
        for post in results:
            assert post["bot_flag"] is False, (
                "Posts spread over >24h should not trigger spam flag"
            )


class TestOutputStructure:
    def test_all_posts_have_flag_fields(self, apply_heuristics, sample_reddit_posts):
        results = apply_heuristics(sample_reddit_posts)
        for post in results:
            assert "bot_flag" in post, "Each result must have 'bot_flag'"
            assert "suspicious_flag" in post, "Each result must have 'suspicious_flag'"
            assert isinstance(post["bot_flag"], bool)
            assert isinstance(post["suspicious_flag"], bool)

    def test_original_fields_preserved(self, apply_heuristics, sample_reddit_posts):
        results = apply_heuristics(sample_reddit_posts)
        for result, original in zip(results, sample_reddit_posts):
            assert result["title"] == original["title"]
            assert result["author"] == original["author"]
            assert result["score"] == original["score"]

    def test_output_count_matches_input(self, apply_heuristics, sample_reddit_posts):
        results = apply_heuristics(sample_reddit_posts)
        assert len(results) == len(sample_reddit_posts)
