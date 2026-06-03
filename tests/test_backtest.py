import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from sentiment_index.backtest import build_datalab_price_backtest
from sentiment_index.models import MarketPrice, TrendPoint
from sentiment_index.storage import SentimentStore


class BacktestTest(unittest.TestCase):
    def test_build_datalab_price_backtest_correlates_signal_and_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SentimentStore(Path(tmp) / "sentiment.sqlite3")
            store.initialize()
            start = date(2026, 1, 1)
            trends = []
            prices = []
            close = 100.0
            for offset in range(60):
                day = start + timedelta(days=offset)
                ratio = 10.0 + offset
                close += 1.0 + (ratio / 100.0)
                trends.append(
                    TrendPoint(
                        source="naver_datalab",
                        group_name="crypto",
                        period=day.isoformat(),
                        ratio=ratio,
                        keyword_group="비트코인",
                    )
                )
                prices.append(
                    MarketPrice(
                        market="bitcoin",
                        symbol="BTCUSDT",
                        date=day.isoformat(),
                        close=close,
                        source="test",
                    )
                )

            store.upsert_trends(trends)
            store.upsert_market_prices(prices)

            result = build_datalab_price_backtest(
                store,
                start=start,
                end=start + timedelta(days=59),
            )

            self.assertGreater(result.trend_rows, 0)
            self.assertGreater(result.price_rows, 0)
            self.assertTrue(result.correlations)
            self.assertEqual(result.correlations[0].market, "bitcoin")


if __name__ == "__main__":
    unittest.main()
