from __future__ import annotations

from .models import utc_hours_ago_iso
from .scoring import DailyIndex
from .storage import SentimentStore


def format_index(index: DailyIndex) -> str:
    return "\n".join(
        [
            f"day: {index.day}",
            f"index_score: {index.index_score}",
            f"regime: {index.regime}",
            f"post_count: {index.post_count}",
            f"new_post_count: {index.new_post_count}",
            f"weighted_post_count: {index.weighted_post_count}",
            f"new_weighted_post_count: {index.new_weighted_post_count}",
            f"baseline_days: {index.baseline_days}",
            f"baseline_estimated_days: {index.baseline_estimated_days}",
            f"baseline_weighted_post_count: {index.baseline_weighted_post_count}",
            f"mention_change_pct: {index.mention_change_pct}",
            f"attention_score: {index.attention_score}",
            f"sentiment: {index.sentiment}",
            f"fomo_score: {index.fomo_score}",
            f"fomo_change_pct: {index.fomo_change_pct}",
            f"risk_score: {index.risk_score}",
            f"risk_change_pct: {index.risk_change_pct}",
            f"trend_momentum: {index.trend_momentum}",
            f"spam_rate: {index.spam_rate}",
            f"snapshot_source: {index.snapshot_source}",
        ]
    )


def build_markdown_report(store: SentimentStore, index: DailyIndex, *, top_limit: int = 12) -> str:
    rows = store.fetch_top_rows(limit=top_limit, since=utc_hours_ago_iso(24))
    lines = [
        "# Community Sentiment Index",
        "",
        "- Window: Rolling 24H",
        f"- KST date label: {index.day}",
        f"- Score: **{index.index_score}** / 100",
        f"- Regime: **{index.regime}**",
        f"- Posts: {index.post_count} ({index.weighted_post_count} weighted)",
        f"- New posts: {index.new_post_count} ({index.new_weighted_post_count} weighted)",
        f"- Baseline days: {index.baseline_days}",
        f"- Estimated baseline days: {index.baseline_estimated_days}",
        f"- Baseline weighted posts: {index.baseline_weighted_post_count}",
        f"- Mention change: {index.mention_change_pct:.2%}",
        f"- Attention: {index.attention_score}",
        f"- Sentiment: {index.sentiment}",
        f"- FOMO: {index.fomo_score}",
        f"- FOMO change: {index.fomo_change_pct:.2%}",
        f"- Risk: {index.risk_score}",
        f"- Risk change: {index.risk_change_pct:.2%}",
        f"- Search trend momentum: {index.trend_momentum:.2%}",
        f"- Spam rate: {index.spam_rate}",
        "",
        "## Top Signals",
        "",
    ]
    if not rows:
        lines.append("No scored posts yet.")
    else:
        for row in rows:
            lines.append(
                "- "
                f"[{row['source_name']}] {row['title']} "
                f"(sentiment={row['sentiment']:.2f}, fomo={row['fomo_score']:.2f}, risk={row['risk_score']:.2f})"
            )
            lines.append(f"  {row['url']}")
    return "\n".join(lines) + "\n"
