import unittest
from types import SimpleNamespace

from sentiment_index.dashboard import build_daily_chart_points, render_daily_score_chart


class DashboardChartTest(unittest.TestCase):
    def test_daily_chart_points_are_sorted_and_include_current(self) -> None:
        index = SimpleNamespace(
            day="2026-06-05",
            index_score=67.35,
            regime="risk_on",
            post_count=2537,
            new_post_count=748,
            fomo_score=0.0143,
            risk_score=0.0487,
            is_estimated=0,
            snapshot_source="observed",
        )
        rows = [
            {
                "day": "2026-06-04",
                "index_score": 59.47,
                "regime": "neutral",
                "post_count": 2145,
                "new_post_count": 759,
                "fomo_score": 0.008,
                "risk_score": 0.057,
                "is_estimated": 0,
                "snapshot_source": "observed",
            },
            {
                "day": "2026-06-03",
                "index_score": 50.0,
                "regime": "calibrating",
                "post_count": 1000,
                "new_post_count": 1000,
                "fomo_score": 0.004,
                "risk_score": 0.02,
                "is_estimated": 1,
                "snapshot_source": "datalab_estimate",
            },
        ]

        points = build_daily_chart_points(index, rows)

        self.assertEqual([point["day"] for point in points], ["2026-06-03", "2026-06-04", "2026-06-05"])
        self.assertEqual(points[-1]["score"], 67.35)
        self.assertEqual(points[-1]["snapshotSource"], "observed")

    def test_daily_chart_renders_range_controls(self) -> None:
        index = SimpleNamespace(
            day="2026-06-05",
            index_score=67.35,
            regime="risk_on",
            post_count=2537,
            new_post_count=748,
            fomo_score=0.0143,
            risk_score=0.0487,
            is_estimated=0,
            snapshot_source="observed",
        )

        html = render_daily_score_chart(index, [])

        self.assertIn('data-chart-range="7"', html)
        self.assertIn('data-chart-range="30"', html)
        self.assertIn('data-chart-range="all"', html)
        self.assertIn("daily-score-chart", html)


if __name__ == "__main__":
    unittest.main()
