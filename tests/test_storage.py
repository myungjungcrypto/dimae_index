import tempfile
import unittest
from pathlib import Path

from sentiment_index.models import CommunityPost, parse_article_identity
from sentiment_index.scoring import build_daily_index, score_post
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

    def test_parse_bobaedream_article_identity(self) -> None:
        article_group, article_id = parse_article_identity(
            source="bobaedream",
            source_name="보배드림 자유게시판",
            url="https://www.bobaedream.co.kr/view?code=freeb&No=3406866&bm=1",
        )

        self.assertEqual(article_group, "bobaedream:freeb")
        self.assertEqual(article_id, 3406866)

    def test_parse_dcinside_article_identity(self) -> None:
        article_group, article_id = parse_article_identity(
            source="dcinside",
            source_name="디시 비트코인 갤러리",
            url="https://gall.dcinside.com/board/view/?id=bitcoins_new1&no=12345",
        )

        self.assertEqual(article_group, "dcinside:bitcoins_new1")
        self.assertEqual(article_id, 12345)

    def test_daily_rows_use_kst_day_and_article_sequence_newness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SentimentStore(Path(tmp) / "sentiment.sqlite3")
            store.initialize()

            previous = self._post(
                "http://cafe.naver.com/dieselmania/100",
                "전날 최고 번호 주식 글",
                "2026-06-01T18:00:00+00:00",
            )
            lower_late = self._post(
                "http://cafe.naver.com/dieselmania/99",
                "뒤늦게 잡힌 낮은 번호 주식 글",
                "2026-06-02T18:00:00+00:00",
            )
            same_day_lower_than_highest = self._post(
                "http://cafe.naver.com/dieselmania/101",
                "오늘 신규지만 최고 번호보다 낮게 늦게 발견된 글",
                "2026-06-02T18:10:00+00:00",
            )
            higher_late = self._post(
                "http://cafe.naver.com/dieselmania/102",
                "새로 올라온 높은 번호 주식 글",
                "2026-06-02T18:20:00+00:00",
            )

            for post in (previous, higher_late, lower_late, same_day_lower_than_highest):
                store.upsert_posts([post])
                store.upsert_scores([score_post(post)])

            rows = store.fetch_daily_score_rows(day="2026-06-03")

            self.assertEqual(len(rows), 3)
            self.assertEqual({row["day"] for row in rows}, {"2026-06-03"})
            by_url = {row["url"]: row for row in rows}
            self.assertEqual(by_url[lower_late.url]["is_new"], 0)
            self.assertEqual(by_url[same_day_lower_than_highest.url]["is_new"], 1)
            self.assertEqual(by_url[higher_late.url]["is_new"], 1)
            self.assertEqual(len(store.fetch_daily_score_rows(day="2026-06-02")), 1)

    def test_hourly_snapshot_is_upserted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SentimentStore(Path(tmp) / "sentiment.sqlite3")
            store.initialize()
            index = build_daily_index(
                [
                    {
                        "day": "2026-06-03",
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
                ],
                baseline_snapshots=[
                    {"new_weighted_post_count": 1.0, "weighted_post_count": 1.0},
                    {"new_weighted_post_count": 1.0, "weighted_post_count": 1.0},
                    {"new_weighted_post_count": 1.0, "weighted_post_count": 1.0},
                ],
            )

            store.upsert_hourly_snapshot(index, snapshot_at="2026-06-03T10:00:00+09:00")
            store.upsert_hourly_snapshot(index, snapshot_at="2026-06-03T10:00:00+09:00")

            rows = store.fetch_hourly_snapshots(limit=5)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["snapshot_at"], "2026-06-03T10:00:00+09:00")
            self.assertEqual(rows[0]["day"], "2026-06-03")

    def test_source_breakdown_groups_daily_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SentimentStore(Path(tmp) / "sentiment.sqlite3")
            store.initialize()
            bobaedream = CommunityPost(
                source="bobaedream",
                source_name="보배드림 자유게시판",
                title="삼성전자 주식 반등",
                summary="",
                url="https://www.bobaedream.co.kr/view?code=freeb&No=3406866",
                weight=0.7,
                collected_at="2026-06-02T18:00:00+00:00",
            ).normalized()
            dcinside = CommunityPost(
                source="dcinside",
                source_name="디시 비트코인 갤러리",
                title="비트코인 풀매수",
                summary="",
                url="https://gall.dcinside.com/board/view/?id=bitcoins_new1&no=12345",
                weight=0.6,
                collected_at="2026-06-02T18:10:00+00:00",
            ).normalized()
            for post in (bobaedream, dcinside):
                store.upsert_posts([post])
                store.upsert_scores([score_post(post)])

            rows = store.fetch_source_breakdown(day="2026-06-03")

            self.assertEqual(len(rows), 2)
            by_source = {row["source_name"]: row for row in rows}
            self.assertEqual(by_source["보배드림 자유게시판"]["post_count"], 1)
            self.assertEqual(by_source["보배드림 자유게시판"]["new_post_count"], 1)
            self.assertEqual(by_source["디시 비트코인 갤러리"]["post_count"], 1)
            self.assertEqual(by_source["디시 비트코인 갤러리"]["new_post_count"], 1)

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
