from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def kst_today() -> date:
    return datetime.now(KST).date()


def kst_today_iso() -> str:
    return kst_today().isoformat()


def parse_article_identity(
    *,
    source: str,
    source_name: str,
    url: str,
) -> tuple[str | None, int | None]:
    if source != "naver_cafe":
        return None, None

    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    if "articles" in parts:
        index = parts.index("articles")
        if index + 1 < len(parts) and parts[index + 1].isdigit():
            group = _naver_group_from_parts(parts, fallback=source_name)
            return f"naver_cafe:{group}", int(parts[index + 1])

    if len(parts) >= 2 and parts[-1].isdigit():
        group = parts[-2] or source_name
        return f"naver_cafe:{group}", int(parts[-1])

    article_id = _first_int(query, "articleid", "articleId")
    if article_id is not None:
        group = _first_text(query, "clubid", "clubId") or source_name
        return f"naver_cafe:{group}", article_id

    return None, None


def _naver_group_from_parts(parts: list[str], *, fallback: str) -> str:
    if "cafes" in parts:
        index = parts.index("cafes")
        if index + 1 < len(parts):
            return parts[index + 1]
    return fallback


def _first_int(query: dict[str, list[str]], *keys: str) -> int | None:
    value = _first_text(query, *keys)
    return int(value) if value and value.isdigit() else None


def _first_text(query: dict[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        values = query.get(key)
        if values:
            return values[0]
    return None


@dataclass(frozen=True)
class CommunityPost:
    source: str
    source_name: str
    title: str
    summary: str
    url: str
    published_at: str | None = None
    keyword: str | None = None
    author: str | None = None
    views: int | None = None
    recommends: int | None = None
    comments: int | None = None
    weight: float = 1.0
    collected_at: str = ""
    article_group: str | None = None
    article_id: int | None = None

    def normalized(self) -> "CommunityPost":
        collected_at = self.collected_at or utc_now_iso()
        article_group = self.article_group
        article_id = self.article_id
        if article_group is None or article_id is None:
            article_group, article_id = parse_article_identity(
                source=self.source,
                source_name=self.source_name,
                url=self.url,
            )
        return CommunityPost(
            source=self.source,
            source_name=self.source_name,
            title=self.title.strip(),
            summary=self.summary.strip(),
            url=self.url.strip(),
            published_at=self.published_at,
            keyword=self.keyword,
            author=self.author,
            views=self.views,
            recommends=self.recommends,
            comments=self.comments,
            weight=self.weight,
            collected_at=collected_at,
            article_group=article_group,
            article_id=article_id,
        )


@dataclass(frozen=True)
class TrendPoint:
    source: str
    group_name: str
    period: str
    ratio: float
    keyword_group: str
    demographic: str = "male_30_49"
    collected_at: str = ""

    def normalized(self) -> "TrendPoint":
        return TrendPoint(
            source=self.source,
            group_name=self.group_name,
            period=self.period,
            ratio=self.ratio,
            keyword_group=self.keyword_group,
            demographic=self.demographic,
            collected_at=self.collected_at or utc_now_iso(),
        )


@dataclass(frozen=True)
class ArticleScore:
    post_url: str
    scored_at: str
    positive: int
    negative: int
    fomo: int
    fear: int
    distrust: int
    spam: int
    sentiment: float
    fomo_score: float
    risk_score: float
    text: str

    def as_row(self) -> dict[str, Any]:
        return {
            "post_url": self.post_url,
            "scored_at": self.scored_at,
            "positive": self.positive,
            "negative": self.negative,
            "fomo": self.fomo,
            "fear": self.fear,
            "distrust": self.distrust,
            "spam": self.spam,
            "sentiment": self.sentiment,
            "fomo_score": self.fomo_score,
            "risk_score": self.risk_score,
            "text": self.text,
        }
