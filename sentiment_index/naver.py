from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from datetime import date, timedelta
from html.parser import HTMLParser

from .config import CafeTarget, NaverConfig
from .http import request_json
from .models import CommunityPost, TrendPoint


class MissingNaverCredentials(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def strip_markup(value: str | None) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return parser.text()


class NaverClient:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        config: NaverConfig | None = None,
    ) -> None:
        self.config = config or NaverConfig()
        self.client_id = client_id or os.getenv(self.config.client_id_env)
        self.client_secret = client_secret or os.getenv(self.config.client_secret_env)

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise MissingNaverCredentials(
                "NAVER_CLIENT_ID and NAVER_CLIENT_SECRET are required for Naver APIs."
            )
        return {
            "X-Naver-Client-Id": self.client_id or "",
            "X-Naver-Client-Secret": self.client_secret or "",
        }

    def fetch_cafe_articles(
        self,
        query: str,
        *,
        display: int = 100,
        start: int = 1,
        sort: str = "date",
        keyword: str | None = None,
    ) -> list[CommunityPost]:
        payload = request_json(
            self.config.cafe_search_url,
            headers=self._headers(),
            query={
                "query": query,
                "display": min(max(display, 1), 100),
                "start": min(max(start, 1), 1000),
                "sort": sort,
            },
        )
        posts: list[CommunityPost] = []
        for item in payload.get("items", []):
            posts.append(
                CommunityPost(
                    source="naver_cafe",
                    source_name=strip_markup(item.get("cafename")),
                    title=strip_markup(item.get("title")),
                    summary=strip_markup(item.get("description")),
                    url=item.get("link", ""),
                    keyword=keyword or query,
                    weight=1.0,
                ).normalized()
            )
        return posts

    def collect_target_cafe_articles(
        self,
        keywords: Iterable[str],
        *,
        target_cafes: Iterable[CafeTarget],
        pages_per_keyword: int = 2,
        verbose: bool = False,
    ) -> list[CommunityPost]:
        targets = tuple(target_cafes)
        starts = [1 + (page * 100) for page in range(max(pages_per_keyword, 1))]
        seen: set[str] = set()
        collected: list[CommunityPost] = []

        for keyword in keywords:
            queries = [keyword, *(f"{target.name} {keyword}" for target in targets)]
            for query in dict.fromkeys(queries):
                for start in starts:
                    if verbose:
                        print(
                            f"[sentiment-index] naver cafe query='{query}' start={start}",
                            file=sys.stderr,
                            flush=True,
                        )
                    posts = self.fetch_cafe_articles(query, start=start, keyword=keyword)
                    for post in posts:
                        matched_target = self._match_target(post, targets)
                        if not matched_target:
                            continue
                        if post.url in seen:
                            continue
                        seen.add(post.url)
                        collected.append(
                            CommunityPost(
                                **{
                                    **post.__dict__,
                                    "source_name": matched_target.name,
                                    "weight": matched_target.weight,
                                }
                            ).normalized()
                        )
        return collected

    def fetch_datalab(
        self,
        keyword_groups: list[dict[str, list[str] | str]],
        *,
        start_date: str,
        end_date: str,
        time_unit: str = "date",
        ages: tuple[str, ...] | None = None,
        gender: str | None = None,
    ) -> list[TrendPoint]:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups,
            "ages": list(ages or self.config.ages_30_40_male),
            "gender": gender or self.config.gender_male,
        }
        payload = request_json(
            self.config.datalab_url,
            method="POST",
            headers=self._headers(),
            body=body,
        )

        points: list[TrendPoint] = []
        for group in payload.get("results", []):
            group_name = str(group.get("title", "unknown"))
            keywords = ",".join(group.get("keywords", []))
            for row in group.get("data", []):
                points.append(
                    TrendPoint(
                        source="naver_datalab",
                        group_name=group_name,
                        keyword_group=keywords,
                        period=row.get("period", ""),
                        ratio=float(row.get("ratio", 0.0)),
                    ).normalized()
                )
        return points

    def collect_default_trends(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[TrendPoint]:
        end = date.fromisoformat(end_date) if end_date else date.today()
        start = date.fromisoformat(start_date) if start_date else end - timedelta(days=30)
        groups: list[dict[str, list[str] | str]] = [
            {
                "groupName": "crypto",
                "keywords": ["비트코인", "코인", "이더리움", "업비트", "빗썸"],
            },
            {
                "groupName": "stocks",
                "keywords": ["주식", "국장", "미장", "코스피", "나스닥"],
            },
            {
                "groupName": "risk",
                "keywords": ["손절", "청산", "폭락", "상폐", "물렸다"],
            },
            {
                "groupName": "fomo",
                "keywords": ["가즈아", "불장", "신고가", "몰빵", "영끌"],
            },
        ]
        return self.fetch_datalab(
            groups,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            time_unit="date",
        )

    @staticmethod
    def _match_target(post: CommunityPost, targets: tuple[CafeTarget, ...]) -> CafeTarget | None:
        text = f"{post.source_name} {post.url}".lower()
        for target in targets:
            if target.name.lower() in text or target.url_fragment.lower() in text:
                return target
        return None
