from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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

    def normalized(self) -> "CommunityPost":
        collected_at = self.collected_at or utc_now_iso()
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

