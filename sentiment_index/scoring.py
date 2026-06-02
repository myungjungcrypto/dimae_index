from __future__ import annotations

import math
from dataclasses import dataclass

from .config import DEFAULT_LEXICON, Lexicon
from .models import ArticleScore, CommunityPost, kst_today_iso, utc_now_iso


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(lowered.count(term.lower()) for term in terms)


def score_post(post: CommunityPost, lexicon: Lexicon | None = None) -> ArticleScore:
    lex = lexicon or DEFAULT_LEXICON
    text = f"{post.title} {post.summary}".strip()
    positive = count_terms(text, lex.positive)
    negative = count_terms(text, lex.negative)
    fomo = count_terms(text, lex.fomo)
    fear = count_terms(text, lex.fear)
    distrust = count_terms(text, lex.distrust)
    spam = count_terms(text, lex.spam)

    sentiment = (positive - negative) / max(positive + negative, 1)
    hype_denominator = max(positive + negative + fomo + fear + distrust, 1)
    fomo_score = fomo / hype_denominator
    risk_score = (fear + distrust + spam) / max(hype_denominator + spam, 1)

    return ArticleScore(
        post_url=post.url,
        scored_at=utc_now_iso(),
        positive=positive,
        negative=negative,
        fomo=fomo,
        fear=fear,
        distrust=distrust,
        spam=spam,
        sentiment=sentiment,
        fomo_score=fomo_score,
        risk_score=risk_score,
        text=text,
    )


@dataclass(frozen=True)
class DailyIndex:
    day: str
    post_count: int
    new_post_count: int
    weighted_post_count: float
    new_weighted_post_count: float
    baseline_days: int
    baseline_estimated_days: int
    baseline_weighted_post_count: float
    mention_change_pct: float
    sentiment: float
    fomo_score: float
    fomo_change_pct: float
    risk_score: float
    risk_change_pct: float
    spam_rate: float
    attention_score: float
    trend_momentum: float
    index_score: float
    regime: str
    is_estimated: int = 0
    snapshot_source: str = "observed"


def build_daily_index(
    rows: list[dict[str, float | int | str]],
    *,
    baseline_snapshots: list[dict[str, float | int | str]] | None = None,
    trend_momentum: float = 0.0,
    min_baseline_days: int = 3,
) -> DailyIndex:
    today = kst_today_iso()
    baseline = baseline_snapshots or []
    if not rows:
        return DailyIndex(
            day=today,
            post_count=0,
            new_post_count=0,
            weighted_post_count=0.0,
            new_weighted_post_count=0.0,
            baseline_days=len(baseline),
            baseline_estimated_days=sum(int(row.get("is_estimated", 0)) for row in baseline),
            baseline_weighted_post_count=0.0,
            mention_change_pct=0.0,
            sentiment=0.0,
            fomo_score=0.0,
            fomo_change_pct=0.0,
            risk_score=0.0,
            risk_change_pct=0.0,
            spam_rate=0.0,
            attention_score=0.0,
            trend_momentum=round(trend_momentum, 4),
            index_score=50.0,
            regime="neutral",
        )

    total_weight = sum(float(row["weight"]) for row in rows) or 1.0
    new_rows = [row for row in rows if int(row.get("is_new", 0)) == 1]
    new_weighted_count = sum(float(row["weight"]) for row in new_rows)
    weighted_count = total_weight
    sentiment = sum(float(row["sentiment"]) * float(row["weight"]) for row in rows) / total_weight
    fomo = sum(float(row["fomo_score"]) * float(row["weight"]) for row in rows) / total_weight
    risk = sum(float(row["risk_score"]) * float(row["weight"]) for row in rows) / total_weight
    spam_rows = sum(1 for row in rows if int(row["spam"]) > 0)
    spam_rate = spam_rows / len(rows)
    attention = min(1.0, math.log1p(weighted_count) / math.log1p(120.0))

    baseline_days = len(baseline)
    baseline_estimated_days = sum(int(row.get("is_estimated", 0)) for row in baseline)
    baseline_new_weighted = _average(
        baseline,
        "new_weighted_post_count",
        fallback_key="weighted_post_count",
    )
    baseline_fomo = _average(baseline, "fomo_score")
    baseline_risk = _average(baseline, "risk_score")

    mention_change_pct = _relative_change(new_weighted_count, baseline_new_weighted, floor=1.0)
    fomo_change_pct = _relative_change(fomo, baseline_fomo, floor=0.002)
    risk_change_pct = _relative_change(risk, baseline_risk, floor=0.002)

    sentiment_component = (sentiment + 1.0) / 2.0
    if baseline_days < min_baseline_days:
        index_score = 50.0
        regime = "baseline_building"
    else:
        attention_change = clamp(0.5 + (mention_change_pct / 2.0), 0.0, 1.0)
        fomo_change = clamp(0.5 + (fomo_change_pct / 3.0), 0.0, 1.0)
        risk_penalty = clamp(0.5 + (risk_change_pct / 3.0), 0.0, 1.0)
        trend_component = clamp(0.5 + (trend_momentum / 2.0), 0.0, 1.0)
        quality_component = 1.0 - min(1.0, spam_rate)
        index_score = 100.0 * (
            0.32 * attention_change
            + 0.28 * fomo_change
            + 0.16 * sentiment_component
            + 0.12 * trend_component
            + 0.07 * quality_component
            + 0.05 * (1.0 - risk_penalty)
        )
        index_score = clamp(index_score)
        regime = _classify_regime(index_score, risk_penalty, sentiment)

    return DailyIndex(
        day=str(rows[0].get("day") or today),
        post_count=len(rows),
        new_post_count=len(new_rows),
        weighted_post_count=round(weighted_count, 2),
        new_weighted_post_count=round(new_weighted_count, 2),
        baseline_days=baseline_days,
        baseline_estimated_days=baseline_estimated_days,
        baseline_weighted_post_count=round(baseline_new_weighted, 2),
        mention_change_pct=round(mention_change_pct, 4),
        sentiment=round(sentiment, 4),
        fomo_score=round(fomo, 4),
        fomo_change_pct=round(fomo_change_pct, 4),
        risk_score=round(risk, 4),
        risk_change_pct=round(risk_change_pct, 4),
        spam_rate=round(spam_rate, 4),
        attention_score=round(attention, 4),
        trend_momentum=round(trend_momentum, 4),
        index_score=round(index_score, 2),
        regime=regime,
    )


def _average(
    rows: list[dict[str, float | int | str]],
    key: str,
    *,
    fallback_key: str | None = None,
) -> float:
    if not rows:
        return 0.0
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value in (None, "") and fallback_key:
            value = row.get(fallback_key)
        if value not in (None, ""):
            values.append(float(value))
    return sum(values) / len(values) if values else 0.0


def _relative_change(current: float, baseline: float, *, floor: float) -> float:
    if baseline <= 0:
        return 0.0
    return max(-1.0, min(5.0, (current - baseline) / max(baseline, floor)))


def _classify_regime(index_score: float, risk_penalty: float, sentiment: float) -> str:
    if risk_penalty >= 0.82 and sentiment < -0.15:
        return "panic"
    if index_score >= 75:
        return "euphoria"
    if index_score >= 60:
        return "risk_on"
    if index_score <= 30:
        return "panic"
    if index_score <= 42:
        return "risk_off"
    return "neutral"
