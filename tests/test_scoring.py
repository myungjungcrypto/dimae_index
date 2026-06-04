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

    def test_build_daily_index_requires_calibration_baseline_before_regime(self) -> None:
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

        self.assertEqual(index.regime, "calibrating")
        self.assertEqual(index.index_score, 50.0)
        self.assertEqual(index.new_post_count, 1)

    def test_build_daily_index_uses_baseline_percentiles(self) -> None:
        rows = [
            {
                "day": "2026-06-04",
                "weight": 20.0,
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
        baseline = [
            {
                "new_weighted_post_count": float(day),
                "weighted_post_count": float(day),
                "fomo_score": day / 100.0,
                "risk_score": 0.01,
                "sentiment": 0.0,
                "trend_momentum": 0.0,
                "spam_rate": 0.0,
            }
            for day in range(1, 21)
        ]

        index = build_daily_index(rows, baseline_snapshots=baseline)

        self.assertGreater(index.index_score, 80.0)
        self.assertEqual(index.regime, "euphoria")
        self.assertGreater(index.mention_change_pct, 0.0)
        self.assertGreater(index.fomo_change_pct, 0.0)

    def test_build_daily_index_penalizes_high_risk_percentile(self) -> None:
        rows = [
            {
                "day": "2026-06-04",
                "weight": 1.0,
                "is_new": 1,
                "positive": 0,
                "negative": 1,
                "fomo": 0,
                "fear": 1,
                "distrust": 1,
                "spam": 0,
                "sentiment": -1.0,
                "fomo_score": 0.0,
                "risk_score": 0.5,
            }
        ]
        baseline = [
            {
                "new_weighted_post_count": 5.0,
                "weighted_post_count": 5.0,
                "fomo_score": 0.05,
                "risk_score": day / 1000.0,
                "sentiment": 0.0,
                "trend_momentum": 0.0,
                "spam_rate": 0.0,
            }
            for day in range(1, 21)
        ]

        index = build_daily_index(rows, baseline_snapshots=baseline)

        self.assertLess(index.index_score, 35.0)
        self.assertEqual(index.regime, "panic")


if __name__ == "__main__":
    unittest.main()
