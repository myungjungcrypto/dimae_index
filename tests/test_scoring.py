import unittest

from sentiment_index.models import CommunityPost
from sentiment_index.scoring import build_daily_index, score_post


class ScoringTest(unittest.TestCase):
    def test_score_post_counts_fomo_and_positive_terms(self) -> None:
        post = CommunityPost(
            source="sample",
            source_name="디젤매니아",
            title="비트코인 신고가 가즈아 풀매수",
            summary="수익 인증이 계속 올라옵니다",
            url="sample://1",
        ).normalized()

        score = score_post(post)

        self.assertGreaterEqual(score.positive, 3)
        self.assertGreaterEqual(score.fomo, 1)
        self.assertGreater(score.sentiment, 0)

    def test_build_daily_index_handles_empty_rows(self) -> None:
        index = build_daily_index([])

        self.assertEqual(index.index_score, 50.0)
        self.assertEqual(index.regime, "neutral")

    def test_build_daily_index_requires_baseline_before_regime(self) -> None:
        rows = [
            {
                "day": "2026-06-01",
                "weight": 1.0,
                "is_new": 1,
                "positive": 1,
                "negative": 0,
                "fomo": 1,
                "fear": 0,
                "distrust": 0,
                "spam": 0,
                "sentiment": 1.0,
                "fomo_score": 0.5,
                "risk_score": 0.0,
            }
        ]

        index = build_daily_index(rows)

        self.assertEqual(index.regime, "baseline_building")
        self.assertEqual(index.index_score, 50.0)
        self.assertEqual(index.new_post_count, 1)

    def test_build_daily_index_uses_baseline_changes(self) -> None:
        rows = [
            {
                "day": "2026-06-04",
                "weight": 3.0,
                "is_new": 1,
                "positive": 1,
                "negative": 0,
                "fomo": 1,
                "fear": 0,
                "distrust": 0,
                "spam": 0,
                "sentiment": 1.0,
                "fomo_score": 0.1,
                "risk_score": 0.0,
            }
        ]
        baseline = [
            {"new_weighted_post_count": 1.0, "weighted_post_count": 1.0, "fomo_score": 0.01, "risk_score": 0.0},
            {"new_weighted_post_count": 1.0, "weighted_post_count": 1.0, "fomo_score": 0.01, "risk_score": 0.0},
            {"new_weighted_post_count": 1.0, "weighted_post_count": 1.0, "fomo_score": 0.01, "risk_score": 0.0},
        ]

        index = build_daily_index(rows, baseline_snapshots=baseline)

        self.assertGreater(index.index_score, 60.0)
        self.assertGreater(index.mention_change_pct, 0.0)
        self.assertGreater(index.fomo_change_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
