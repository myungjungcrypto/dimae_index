import unittest

from sentiment_index.market import NaverIndexDayParser


class MarketParserTest(unittest.TestCase):
    def test_parse_naver_index_rows(self) -> None:
        parser = NaverIndexDayParser(market="kospi", symbol="KOSPI")
        parser.feed(
            """
            <td class="date">2026.06.02</td>
            <td class="number_1">2,801.49</td>
            <td class="number_1">ignore</td>
            <td class="date">2026.06.01</td>
            <td class="number_1">2,788.38</td>
            """
        )

        self.assertEqual(len(parser.prices), 2)
        self.assertEqual(parser.prices[0].date, "2026-06-02")
        self.assertEqual(parser.prices[0].close, 2801.49)
        self.assertEqual(parser.prices[1].date, "2026-06-01")
        self.assertEqual(parser.prices[1].close, 2788.38)


if __name__ == "__main__":
    unittest.main()
