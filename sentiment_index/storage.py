from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from .models import (
    ArticleScore,
    CommunityPost,
    MarketPrice,
    TrendPoint,
    kst_hour_iso,
    kst_today_iso,
    parse_article_identity,
    utc_hours_ago_iso,
    utc_now_iso,
)


def _kst_day_sql(column: str) -> str:
    return f"substr(datetime({column}, '+9 hours'), 1, 10)"


class SentimentStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    url TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    published_at TEXT,
                    keyword TEXT,
                    author TEXT,
                    views INTEGER,
                    recommends INTEGER,
                    comments INTEGER,
                    weight REAL NOT NULL DEFAULT 1.0,
                    collected_at TEXT NOT NULL,
                    first_seen_at TEXT,
                    last_seen_at TEXT,
                    seen_count INTEGER NOT NULL DEFAULT 1,
                    article_group TEXT,
                    article_id INTEGER,
                    sequence_new INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS article_scores (
                    post_url TEXT PRIMARY KEY,
                    scored_at TEXT NOT NULL,
                    positive INTEGER NOT NULL,
                    negative INTEGER NOT NULL,
                    fomo INTEGER NOT NULL,
                    fear INTEGER NOT NULL,
                    distrust INTEGER NOT NULL,
                    spam INTEGER NOT NULL,
                    sentiment REAL NOT NULL,
                    fomo_score REAL NOT NULL,
                    risk_score REAL NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(post_url) REFERENCES posts(url)
                );

                CREATE TABLE IF NOT EXISTS trends (
                    source TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    period TEXT NOT NULL,
                    ratio REAL NOT NULL,
                    keyword_group TEXT NOT NULL,
                    demographic TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    PRIMARY KEY(source, group_name, period, demographic)
                );

                CREATE TABLE IF NOT EXISTS market_prices (
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL NOT NULL,
                    volume REAL,
                    source TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    PRIMARY KEY(market, date)
                );

                CREATE TABLE IF NOT EXISTS daily_snapshots (
                    day TEXT PRIMARY KEY,
                    post_count INTEGER NOT NULL,
                    new_post_count INTEGER NOT NULL,
                    weighted_post_count REAL NOT NULL,
                    new_weighted_post_count REAL NOT NULL,
                    baseline_days INTEGER NOT NULL,
                    baseline_estimated_days INTEGER NOT NULL DEFAULT 0,
                    baseline_weighted_post_count REAL NOT NULL,
                    mention_change_pct REAL NOT NULL,
                    sentiment REAL NOT NULL,
                    fomo_score REAL NOT NULL,
                    fomo_change_pct REAL NOT NULL,
                    risk_score REAL NOT NULL,
                    risk_change_pct REAL NOT NULL,
                    spam_rate REAL NOT NULL,
                    attention_score REAL NOT NULL,
                    trend_momentum REAL NOT NULL,
                    index_score REAL NOT NULL,
                    regime TEXT NOT NULL,
                    is_estimated INTEGER NOT NULL DEFAULT 0,
                    snapshot_source TEXT NOT NULL DEFAULT 'observed',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS hourly_snapshots (
                    snapshot_at TEXT PRIMARY KEY,
                    day TEXT NOT NULL,
                    post_count INTEGER NOT NULL,
                    new_post_count INTEGER NOT NULL,
                    weighted_post_count REAL NOT NULL,
                    new_weighted_post_count REAL NOT NULL,
                    baseline_days INTEGER NOT NULL,
                    baseline_estimated_days INTEGER NOT NULL DEFAULT 0,
                    baseline_weighted_post_count REAL NOT NULL,
                    mention_change_pct REAL NOT NULL,
                    sentiment REAL NOT NULL,
                    fomo_score REAL NOT NULL,
                    fomo_change_pct REAL NOT NULL,
                    risk_score REAL NOT NULL,
                    risk_change_pct REAL NOT NULL,
                    spam_rate REAL NOT NULL,
                    attention_score REAL NOT NULL,
                    trend_momentum REAL NOT NULL,
                    index_score REAL NOT NULL,
                    regime TEXT NOT NULL,
                    is_estimated INTEGER NOT NULL DEFAULT 0,
                    snapshot_source TEXT NOT NULL DEFAULT 'observed',
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(con, "posts", "first_seen_at", "TEXT")
            self._ensure_column(con, "posts", "last_seen_at", "TEXT")
            self._ensure_column(con, "posts", "seen_count", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(con, "posts", "article_group", "TEXT")
            self._ensure_column(con, "posts", "article_id", "INTEGER")
            self._ensure_column(con, "posts", "sequence_new", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(
                con,
                "daily_snapshots",
                "baseline_estimated_days",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                con,
                "daily_snapshots",
                "is_estimated",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                con,
                "daily_snapshots",
                "snapshot_source",
                "TEXT NOT NULL DEFAULT 'observed'",
            )
            con.execute("UPDATE posts SET first_seen_at = COALESCE(first_seen_at, collected_at)")
            con.execute("UPDATE posts SET last_seen_at = COALESCE(last_seen_at, collected_at)")
            con.execute("UPDATE posts SET seen_count = COALESCE(seen_count, 1)")
            self._backfill_article_identity(con)
            self._rebuild_sequence_new_flags(con)

    def _ensure_column(
        self,
        con: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def upsert_posts(self, posts: Iterable[CommunityPost]) -> int:
        rows = [post.normalized() for post in posts]
        if not rows:
            return 0
        with self.connect() as con:
            max_article_ids = self._fetch_max_article_ids(con, rows)
            before = con.total_changes
            con.executemany(
                """
                INSERT INTO posts (
                    url, source, source_name, title, summary, published_at, keyword,
                    author, views, recommends, comments, weight, collected_at,
                    first_seen_at, last_seen_at, seen_count, article_group, article_id,
                    sequence_new
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    source=excluded.source,
                    source_name=excluded.source_name,
                    title=excluded.title,
                    summary=excluded.summary,
                    published_at=COALESCE(excluded.published_at, posts.published_at),
                    keyword=COALESCE(excluded.keyword, posts.keyword),
                    author=COALESCE(excluded.author, posts.author),
                    views=COALESCE(excluded.views, posts.views),
                    recommends=COALESCE(excluded.recommends, posts.recommends),
                    comments=COALESCE(excluded.comments, posts.comments),
                    weight=excluded.weight,
                    collected_at=excluded.collected_at,
                    first_seen_at=COALESCE(posts.first_seen_at, excluded.first_seen_at),
                    last_seen_at=excluded.last_seen_at,
                    seen_count=COALESCE(posts.seen_count, 0) + 1,
                    article_group=COALESCE(posts.article_group, excluded.article_group),
                    article_id=COALESCE(posts.article_id, excluded.article_id),
                    sequence_new=posts.sequence_new
                """,
                [
                    (
                        post.url,
                        post.source,
                        post.source_name,
                        post.title,
                        post.summary,
                        post.published_at,
                        post.keyword,
                        post.author,
                        post.views,
                        post.recommends,
                        post.comments,
                        post.weight,
                        post.collected_at,
                        post.collected_at,
                        post.collected_at,
                        1,
                        post.article_group,
                        post.article_id,
                        self._is_sequence_new(post, max_article_ids),
                    )
                    for post in rows
                ],
            )
            return con.total_changes - before

    def upsert_scores(self, scores: Iterable[ArticleScore]) -> int:
        rows = list(scores)
        if not rows:
            return 0
        with self.connect() as con:
            before = con.total_changes
            con.executemany(
                """
                INSERT INTO article_scores (
                    post_url, scored_at, positive, negative, fomo, fear, distrust, spam,
                    sentiment, fomo_score, risk_score, text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(post_url) DO UPDATE SET
                    scored_at=excluded.scored_at,
                    positive=excluded.positive,
                    negative=excluded.negative,
                    fomo=excluded.fomo,
                    fear=excluded.fear,
                    distrust=excluded.distrust,
                    spam=excluded.spam,
                    sentiment=excluded.sentiment,
                    fomo_score=excluded.fomo_score,
                    risk_score=excluded.risk_score,
                    text=excluded.text
                """,
                [
                    (
                        score.post_url,
                        score.scored_at,
                        score.positive,
                        score.negative,
                        score.fomo,
                        score.fear,
                        score.distrust,
                        score.spam,
                        score.sentiment,
                        score.fomo_score,
                        score.risk_score,
                        score.text,
                    )
                    for score in rows
                ],
            )
            return con.total_changes - before

    def upsert_trends(self, trends: Iterable[TrendPoint]) -> int:
        rows = [trend.normalized() for trend in trends]
        if not rows:
            return 0
        with self.connect() as con:
            before = con.total_changes
            con.executemany(
                """
                INSERT INTO trends (
                    source, group_name, period, ratio, keyword_group, demographic, collected_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, group_name, period, demographic) DO UPDATE SET
                    ratio=excluded.ratio,
                    keyword_group=excluded.keyword_group,
                    collected_at=excluded.collected_at
                """,
                [
                    (
                        trend.source,
                        trend.group_name,
                        trend.period,
                        trend.ratio,
                        trend.keyword_group,
                        trend.demographic,
                        trend.collected_at,
                    )
                    for trend in rows
                ],
            )
            return con.total_changes - before

    def upsert_market_prices(self, prices: Iterable[MarketPrice]) -> int:
        rows = [price.normalized() for price in prices]
        if not rows:
            return 0
        with self.connect() as con:
            before = con.total_changes
            con.executemany(
                """
                INSERT INTO market_prices (
                    market, symbol, date, open, high, low, close, volume, source, collected_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(market, date) DO UPDATE SET
                    symbol=excluded.symbol,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    source=excluded.source,
                    collected_at=excluded.collected_at
                """,
                [
                    (
                        price.market,
                        price.symbol,
                        price.date,
                        price.open,
                        price.high,
                        price.low,
                        price.close,
                        price.volume,
                        price.source,
                        price.collected_at,
                    )
                    for price in rows
                ],
            )
            return con.total_changes - before

    def fetch_unscored_posts(self, *, limit: int = 1000) -> list[CommunityPost]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT p.*
                FROM posts p
                LEFT JOIN article_scores s ON s.post_url = p.url
                WHERE s.post_url IS NULL
                ORDER BY p.collected_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._post_from_row(row) for row in rows]

    def fetch_posts_for_scoring(self, *, limit: int = 3000) -> list[CommunityPost]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT *
                FROM posts
                ORDER BY collected_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._post_from_row(row) for row in rows]

    def fetch_daily_score_rows(self, *, day: str | None = None) -> list[dict[str, Any]]:
        last_seen_day = _kst_day_sql("p.last_seen_at")
        first_seen_day = _kst_day_sql("p.first_seen_at")
        previous_article_max_sql = f"""
            SELECT MAX(prev.article_id)
            FROM posts prev
            WHERE prev.article_group = p.article_group
              AND prev.article_id IS NOT NULL
              AND {_kst_day_sql("prev.first_seen_at")} < {last_seen_day}
        """
        if day:
            where_sql = f"{last_seen_day} = ?"
            params = (day,)
        else:
            where_sql = f"""
                {last_seen_day} = (
                    SELECT MAX({_kst_day_sql("last_seen_at")}) FROM posts
                )
            """
            params = ()
        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT
                    {last_seen_day} AS day,
                    p.source,
                    p.source_name,
                    p.title,
                    p.url,
                    p.weight,
                    p.first_seen_at,
                    p.last_seen_at,
                    p.seen_count,
                    p.article_group,
                    p.article_id,
                    p.sequence_new,
                    CASE
                        WHEN {first_seen_day} = {last_seen_day}
                         AND (
                            p.article_id IS NULL
                            OR p.article_group IS NULL
                            OR p.article_id > COALESCE(({previous_article_max_sql}), -1)
                         )
                        THEN 1 ELSE 0
                    END AS is_new,
                    s.positive,
                    s.negative,
                    s.fomo,
                    s.fear,
                    s.distrust,
                    s.spam,
                    s.sentiment,
                    s.fomo_score,
                    s.risk_score
                FROM posts p
                JOIN article_scores s ON s.post_url = p.url
                WHERE {where_sql}
                ORDER BY p.collected_at DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_rolling_score_rows(
        self,
        *,
        hours: int = 24,
        since: str | None = None,
        until: str | None = None,
        day: str | None = None,
    ) -> list[dict[str, Any]]:
        since = since or utc_hours_ago_iso(hours)
        until = until or utc_now_iso()
        day = day or kst_today_iso()
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT
                    ? AS day,
                    p.source,
                    p.source_name,
                    p.title,
                    p.url,
                    p.weight,
                    p.first_seen_at,
                    p.last_seen_at,
                    p.seen_count,
                    p.article_group,
                    p.article_id,
                    p.sequence_new,
                    CASE
                        WHEN p.first_seen_at >= ?
                         AND p.first_seen_at <= ?
                         AND p.sequence_new = 1
                        THEN 1 ELSE 0
                    END AS is_new,
                    s.positive,
                    s.negative,
                    s.fomo,
                    s.fear,
                    s.distrust,
                    s.spam,
                    s.sentiment,
                    s.fomo_score,
                    s.risk_score
                FROM posts p
                JOIN article_scores s ON s.post_url = p.url
                WHERE p.last_seen_at >= ?
                  AND p.last_seen_at <= ?
                ORDER BY p.last_seen_at DESC
                """,
                (day, since, until, since, until),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_baseline_snapshots(self, *, day: str, limit: int = 90) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT
                    *
                FROM daily_snapshots
                WHERE day < ?
                ORDER BY day DESC
                LIMIT ?
                """,
                (day, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_daily_snapshot(self, index: Any) -> None:
        payload = self._snapshot_payload(index)
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO daily_snapshots (
                    day, post_count, new_post_count, weighted_post_count,
                    new_weighted_post_count, baseline_days, baseline_estimated_days,
                    baseline_weighted_post_count, mention_change_pct, sentiment,
                    fomo_score, fomo_change_pct, risk_score, risk_change_pct,
                    spam_rate, attention_score, trend_momentum, index_score,
                    regime, is_estimated, snapshot_source, created_at
                )
                VALUES (
                    :day, :post_count, :new_post_count, :weighted_post_count,
                    :new_weighted_post_count, :baseline_days, :baseline_estimated_days,
                    :baseline_weighted_post_count, :mention_change_pct, :sentiment,
                    :fomo_score, :fomo_change_pct, :risk_score, :risk_change_pct,
                    :spam_rate, :attention_score, :trend_momentum, :index_score,
                    :regime, :is_estimated, :snapshot_source, :created_at
                )
                ON CONFLICT(day) DO UPDATE SET
                    post_count=excluded.post_count,
                    new_post_count=excluded.new_post_count,
                    weighted_post_count=excluded.weighted_post_count,
                    new_weighted_post_count=excluded.new_weighted_post_count,
                    baseline_days=excluded.baseline_days,
                    baseline_estimated_days=excluded.baseline_estimated_days,
                    baseline_weighted_post_count=excluded.baseline_weighted_post_count,
                    mention_change_pct=excluded.mention_change_pct,
                    sentiment=excluded.sentiment,
                    fomo_score=excluded.fomo_score,
                    fomo_change_pct=excluded.fomo_change_pct,
                    risk_score=excluded.risk_score,
                    risk_change_pct=excluded.risk_change_pct,
                    spam_rate=excluded.spam_rate,
                    attention_score=excluded.attention_score,
                    trend_momentum=excluded.trend_momentum,
                    index_score=excluded.index_score,
                    regime=excluded.regime,
                    is_estimated=excluded.is_estimated,
                    snapshot_source=excluded.snapshot_source,
                    created_at=excluded.created_at
                """,
                payload,
            )

    def upsert_hourly_snapshot(self, index: Any, *, snapshot_at: str | None = None) -> None:
        payload = self._snapshot_payload(index)
        payload["snapshot_at"] = snapshot_at or kst_hour_iso()
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO hourly_snapshots (
                    snapshot_at, day, post_count, new_post_count, weighted_post_count,
                    new_weighted_post_count, baseline_days, baseline_estimated_days,
                    baseline_weighted_post_count, mention_change_pct, sentiment,
                    fomo_score, fomo_change_pct, risk_score, risk_change_pct,
                    spam_rate, attention_score, trend_momentum, index_score,
                    regime, is_estimated, snapshot_source, created_at
                )
                VALUES (
                    :snapshot_at, :day, :post_count, :new_post_count, :weighted_post_count,
                    :new_weighted_post_count, :baseline_days, :baseline_estimated_days,
                    :baseline_weighted_post_count, :mention_change_pct, :sentiment,
                    :fomo_score, :fomo_change_pct, :risk_score, :risk_change_pct,
                    :spam_rate, :attention_score, :trend_momentum, :index_score,
                    :regime, :is_estimated, :snapshot_source, :created_at
                )
                ON CONFLICT(snapshot_at) DO UPDATE SET
                    day=excluded.day,
                    post_count=excluded.post_count,
                    new_post_count=excluded.new_post_count,
                    weighted_post_count=excluded.weighted_post_count,
                    new_weighted_post_count=excluded.new_weighted_post_count,
                    baseline_days=excluded.baseline_days,
                    baseline_estimated_days=excluded.baseline_estimated_days,
                    baseline_weighted_post_count=excluded.baseline_weighted_post_count,
                    mention_change_pct=excluded.mention_change_pct,
                    sentiment=excluded.sentiment,
                    fomo_score=excluded.fomo_score,
                    fomo_change_pct=excluded.fomo_change_pct,
                    risk_score=excluded.risk_score,
                    risk_change_pct=excluded.risk_change_pct,
                    spam_rate=excluded.spam_rate,
                    attention_score=excluded.attention_score,
                    trend_momentum=excluded.trend_momentum,
                    index_score=excluded.index_score,
                    regime=excluded.regime,
                    is_estimated=excluded.is_estimated,
                    snapshot_source=excluded.snapshot_source,
                    created_at=excluded.created_at
                """,
                payload,
            )

    def fetch_hourly_snapshots(self, *, limit: int = 24) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT *
                FROM hourly_snapshots
                ORDER BY snapshot_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_daily_snapshots(self, *, limit: int = 365) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT *
                FROM daily_snapshots
                ORDER BY day DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_trend_period_rows(self) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT group_name, period, ratio
                FROM trends
                ORDER BY period ASC, group_name ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_trend_period_rows_between(self, *, start: str, end: str) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT group_name, period, ratio
                FROM trends
                WHERE period BETWEEN ? AND ?
                ORDER BY period ASC, group_name ASC
                """,
                (start, end),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_market_prices_between(
        self,
        *,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT market, symbol, date, open, high, low, close, volume, source
                FROM market_prices
                WHERE date BETWEEN ? AND ?
                ORDER BY market ASC, date ASC
                """,
                (start, end),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_trend_momentum(self) -> float:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT group_name, period, ratio
                FROM trends
                WHERE group_name IN ('crypto', 'stocks', 'fomo')
                ORDER BY period DESC
                """
            ).fetchall()
        if not rows:
            return 0.0

        today = kst_today_iso()
        periods = sorted({str(row["period"]) for row in rows if str(row["period"]) < today})
        if len(periods) < 5:
            return 0.0

        latest_periods = set(periods[-3:])
        previous_periods = set(periods[-17:-3])
        latest = [float(row["ratio"]) for row in rows if str(row["period"]) in latest_periods]
        previous = [float(row["ratio"]) for row in rows if str(row["period"]) in previous_periods]
        if not latest or not previous:
            return 0.0

        latest_avg = sum(latest) / len(latest)
        previous_avg = sum(previous) / len(previous)
        return max(-1.0, min(1.0, (latest_avg - previous_avg) / max(previous_avg, 1.0)))

    def fetch_top_rows(
        self,
        *,
        limit: int = 20,
        day: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        last_seen_day = _kst_day_sql("p.last_seen_at")
        if since:
            until = until or utc_now_iso()
            where_sql = "p.last_seen_at >= ? AND p.last_seen_at <= ?"
            params: tuple[Any, ...] = (since, until, limit)
        elif day:
            where_sql = f"{last_seen_day} = ?"
            params = (day, limit)
        else:
            where_sql = f"""
                {last_seen_day} = (
                    SELECT MAX({_kst_day_sql("last_seen_at")}) FROM posts
                )
            """
            params = (limit,)
        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT
                    p.source_name,
                    p.title,
                    p.url,
                    p.weight,
                    p.first_seen_at,
                    p.last_seen_at,
                    p.article_group,
                    p.article_id,
                    p.sequence_new,
                    s.positive,
                    s.negative,
                    s.fomo,
                    s.fear,
                    s.distrust,
                    s.spam,
                    s.sentiment,
                    s.fomo_score,
                    s.risk_score
                FROM posts p
                JOIN article_scores s ON s.post_url = p.url
                WHERE {where_sql}
                ORDER BY (s.positive + s.negative + s.fomo + s.fear + s.distrust) DESC,
                         p.last_seen_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_source_breakdown(
        self,
        *,
        day: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        if since:
            until = until or utc_now_iso()
            with self.connect() as con:
                rows = con.execute(
                    """
                    WITH scored_rows AS (
                        SELECT
                            p.source,
                            p.source_name,
                            p.weight,
                            CASE
                                WHEN p.first_seen_at >= ?
                                 AND p.first_seen_at <= ?
                                 AND p.sequence_new = 1
                                THEN 1 ELSE 0
                            END AS is_new,
                            s.fomo_score,
                            s.risk_score,
                            s.spam
                        FROM posts p
                        JOIN article_scores s ON s.post_url = p.url
                        WHERE p.last_seen_at >= ?
                          AND p.last_seen_at <= ?
                    )
                    SELECT
                        source,
                        source_name,
                        COUNT(*) AS post_count,
                        SUM(is_new) AS new_post_count,
                        SUM(weight) AS weighted_post_count,
                        SUM(CASE WHEN is_new = 1 THEN weight ELSE 0 END) AS new_weighted_post_count,
                        SUM(fomo_score * weight) / NULLIF(SUM(weight), 0) AS fomo_score,
                        SUM(risk_score * weight) / NULLIF(SUM(weight), 0) AS risk_score,
                        AVG(CASE WHEN spam > 0 THEN 1.0 ELSE 0.0 END) AS spam_rate
                    FROM scored_rows
                    GROUP BY source, source_name
                    ORDER BY weighted_post_count DESC, post_count DESC
                    """,
                    (since, until, since, until),
                ).fetchall()
            return [dict(row) for row in rows]

        last_seen_day = _kst_day_sql("p.last_seen_at")
        first_seen_day = _kst_day_sql("p.first_seen_at")
        previous_article_max_sql = f"""
            SELECT MAX(prev.article_id)
            FROM posts prev
            WHERE prev.article_group = p.article_group
              AND prev.article_id IS NOT NULL
              AND {_kst_day_sql("prev.first_seen_at")} < {last_seen_day}
        """
        is_new_sql = f"""
            CASE
                WHEN {first_seen_day} = {last_seen_day}
                 AND (
                    p.article_id IS NULL
                    OR p.article_group IS NULL
                    OR p.article_id > COALESCE(({previous_article_max_sql}), -1)
                 )
                THEN 1 ELSE 0
            END
        """
        if day:
            where_sql = f"{last_seen_day} = ?"
            params: tuple[Any, ...] = (day,)
        else:
            where_sql = f"""
                {last_seen_day} = (
                    SELECT MAX({_kst_day_sql("last_seen_at")}) FROM posts
                )
            """
            params = ()

        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT
                    p.source,
                    p.source_name,
                    COUNT(*) AS post_count,
                    SUM({is_new_sql}) AS new_post_count,
                    SUM(p.weight) AS weighted_post_count,
                    SUM(CASE WHEN {is_new_sql} = 1 THEN p.weight ELSE 0 END) AS new_weighted_post_count,
                    SUM(s.fomo_score * p.weight) / NULLIF(SUM(p.weight), 0) AS fomo_score,
                    SUM(s.risk_score * p.weight) / NULLIF(SUM(p.weight), 0) AS risk_score,
                    AVG(CASE WHEN s.spam > 0 THEN 1.0 ELSE 0.0 END) AS spam_rate
                FROM posts p
                JOIN article_scores s ON s.post_url = p.url
                WHERE {where_sql}
                GROUP BY p.source, p.source_name
                ORDER BY weighted_post_count DESC, post_count DESC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _snapshot_payload(index: Any) -> dict[str, Any]:
        if is_dataclass(index):
            payload = {field.name: getattr(index, field.name) for field in fields(index)}
        else:
            payload = dict(index)
        payload["created_at"] = utc_now_iso()
        return payload

    @staticmethod
    def _post_from_row(row: sqlite3.Row) -> CommunityPost:
        return CommunityPost(
            source=row["source"],
            source_name=row["source_name"],
            title=row["title"],
            summary=row["summary"],
            url=row["url"],
            published_at=row["published_at"],
            keyword=row["keyword"],
            author=row["author"],
            views=row["views"],
            recommends=row["recommends"],
            comments=row["comments"],
            weight=row["weight"],
            collected_at=row["collected_at"],
            article_group=row["article_group"] if "article_group" in row.keys() else None,
            article_id=row["article_id"] if "article_id" in row.keys() else None,
        )

    def _backfill_article_identity(self, con: sqlite3.Connection) -> None:
        rows = con.execute(
            """
            SELECT url, source, source_name
            FROM posts
            WHERE article_group IS NULL OR article_id IS NULL
            """
        ).fetchall()
        for row in rows:
            article_group, article_id = parse_article_identity(
                source=row["source"],
                source_name=row["source_name"],
                url=row["url"],
            )
            if article_group is None or article_id is None:
                continue
            con.execute(
                """
                UPDATE posts
                SET article_group = ?, article_id = ?
                WHERE url = ?
                """,
                (article_group, article_id, row["url"]),
            )

    def _rebuild_sequence_new_flags(self, con: sqlite3.Connection) -> None:
        rows = con.execute(
            """
            SELECT url, article_group, article_id
            FROM posts
            WHERE article_group IS NOT NULL
              AND article_id IS NOT NULL
            ORDER BY article_group ASC, first_seen_at ASC, article_id ASC
            """
        ).fetchall()
        current_group: str | None = None
        max_seen: int | None = None
        updates: list[tuple[int, str]] = []
        for row in rows:
            group = str(row["article_group"])
            article_id = int(row["article_id"])
            if group != current_group:
                current_group = group
                max_seen = None
            sequence_new = 1 if max_seen is None or article_id > max_seen else 0
            max_seen = article_id if max_seen is None else max(max_seen, article_id)
            updates.append((sequence_new, row["url"]))
        con.executemany("UPDATE posts SET sequence_new = ? WHERE url = ?", updates)

    @staticmethod
    def _fetch_max_article_ids(
        con: sqlite3.Connection,
        posts: list[CommunityPost],
    ) -> dict[str, int]:
        groups = sorted({post.article_group for post in posts if post.article_group})
        if not groups:
            return {}
        placeholders = ",".join("?" for _ in groups)
        rows = con.execute(
            f"""
            SELECT article_group, MAX(article_id) AS max_article_id
            FROM posts
            WHERE article_group IN ({placeholders})
              AND article_id IS NOT NULL
            GROUP BY article_group
            """,
            groups,
        ).fetchall()
        return {
            str(row["article_group"]): int(row["max_article_id"])
            for row in rows
            if row["max_article_id"] is not None
        }

    @staticmethod
    def _is_sequence_new(post: CommunityPost, max_article_ids: dict[str, int]) -> int:
        if post.article_group is None or post.article_id is None:
            return 1
        previous_max = max_article_ids.get(post.article_group)
        if previous_max is None:
            return 1
        return 1 if post.article_id > previous_max else 0
