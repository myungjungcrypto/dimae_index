import tempfile
import unittest
from pathlib import Path

from sentiment_index.models import CommunityPost, parse_article_identity
from sentiment_index.scoring import score_post
from sentiment_index.storage import SentimentStore


class StorageTest(unittest.TestCase):
    def test_parse_naver_cafe_article_identity(self) -> None:
        article_group, article_id = parse_article_identity(
            source="naver_cafe",
            source_name="디젤매니아",
            url="http://cafe.naver.com/dieselmania/47122184",
        )

        self.assertEqual(article_group, "naver_cafe:dieselmania")
        self.assertEqual(article_id, 47122184)

    def test_daily_rows_use_kst_day_and_article_sequence_newness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SentimentStore(Path(tmp) / "sentiment.sqlite3")
            store.initialize()

            first = self._post(
                "http://cafe.naver.com/dieselmania/100",
                "처음 본 최신 주식 글",
                "2026-06-02T18:00:00+00:00",
            )
            lower_late = self._post(
                "http://cafe.naver.com/dieselmania/99",
                "뒤늦게 잡힌 낮은 번호 주식 글",
                "2026-06-02T18:10:00+00:00",
            )
            higher_late = self._post(
                "http://cafe.naver.com/dieselmania/101",
                "새로 올라온 높은 번호 주식 글",
                "2026-06-02T18:20:00+00:00",
            )

            for post in (first, lower_late, higher_late):
                store.upsert_posts([post])
                store.upsert_scores([score_post(post)])

            rows = store.fetch_daily_score_rows(day="2026-06-03")

            self.assertEqual(len(rows), 3)
            self.assertEqual({row["day"] for row in rows}, {"2026-06-03"})
            by_url = {row["url"]: row for row in rows}
            self.assertEqual(by_url[first.url]["is_new"], 1)
            self.assertEqual(by_url[lower_late.url]["is_new"], 0)
            self.assertEqual(by_url[higher_late.url]["is_new"], 1)
            self.assertEqual(store.fetch_daily_score_rows(day="2026-06-02"), [])

    def _post(self, url: str, title: str, collected_at: str) -> CommunityPost:
        return CommunityPost(
            source="naver_cafe",
            source_name="디젤매니아",
            title=title,
            summary="",
            url=url,
            keyword="주식",
            collected_at=collected_at,
        ).normalized()


if __name__ == "__main__":
    unittest.main()
