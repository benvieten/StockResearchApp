"""
Phase 1 — Data layer: reddit.py

Tests validate that Reddit posts are fetched and structured correctly
across all 4 subreddits.
"""

import pytest

pytestmark = pytest.mark.phase1

EXPECTED_SUBREDDITS = {"wallstreetbets", "stocks", "investing", "SecurityAnalysis"}
REQUIRED_POST_FIELDS = {
    "title", "selftext", "score", "upvote_ratio", "num_comments",
    "author", "author_created_utc", "post_created_utc", "subreddit"
}


class TestRedditOutput:
    def test_returns_list(self, aapl_reddit):
        assert isinstance(aapl_reddit, list)

    def test_not_empty(self, aapl_reddit):
        assert len(aapl_reddit) > 0, (
            "Reddit returned no posts — check User-Agent header and network access"
        )

    def test_posts_have_required_fields(self, aapl_reddit):
        for i, post in enumerate(aapl_reddit[:5]):
            missing = REQUIRED_POST_FIELDS - post.keys()
            assert not missing, f"Post {i} missing fields: {missing}"

    def test_subreddits_represented(self, aapl_reddit):
        found = {post["subreddit"] for post in aapl_reddit}
        # At least 2 of 4 subreddits should have results
        overlap = found & EXPECTED_SUBREDDITS
        assert len(overlap) >= 2, (
            f"Expected results from ≥2 subreddits, found: {overlap}"
        )

    def test_scores_are_integers(self, aapl_reddit):
        for post in aapl_reddit[:10]:
            assert isinstance(post["score"], int), (
                f"score should be int, got {type(post['score'])}"
            )

    def test_upvote_ratio_in_range(self, aapl_reddit):
        for post in aapl_reddit[:10]:
            ratio = post.get("upvote_ratio")
            if ratio is not None:
                assert 0.0 <= ratio <= 1.0, f"upvote_ratio out of range: {ratio}"

    def test_author_created_utc_is_numeric(self, aapl_reddit):
        for post in aapl_reddit[:10]:
            utc = post.get("author_created_utc")
            if utc is not None:
                assert isinstance(utc, (int, float)), (
                    f"author_created_utc should be numeric, got {type(utc)}"
                )

    def test_titles_are_non_empty(self, aapl_reddit):
        for post in aapl_reddit[:10]:
            assert isinstance(post["title"], str)
            assert len(post["title"].strip()) > 0
