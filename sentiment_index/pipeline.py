from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from pathlib import Path
from statistics import median
from time import sleep
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .bobaedream import BobaedreamClient
from .config import DEFAULT_CONFIG, PipelineConfig
from .dcinside import DcinsideClient
from .http import HttpError
from .models import CommunityPost, TrendPoint, kst_today, kst_today_iso, utc_now_iso
from .naver import MissingNaverCredentials, NaverClient
from .scoring import DailyIndex, build_daily_index, clamp, score_post
from .settings import load_runtime_config, load_runtime_lexicon
from .storage import SentimentStore


@dataclass
class PipelineResult:
    posts_collected: int = 0
    trends_collected: int = 0
    posts_scored: int = 0
    snapshots_backfilled: int = 0
    daily_index: DailyIndex | None = None
    warnings: list[str] = field(default_factory=list)


def load_env_file(path: Path | str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def initialize_store(config: PipelineConfig = DEFAULT_CONFIG) -> SentimentStore:
    store = SentimentStore(config.db_path)
    store.initialize()
    return store


def collect_sources(
    config: PipelineConfig = DEFAULT_CONFIG,
    *,
    include_naver: bool = True,
    include_bobaedream: bool = True,
    include_dcinside: bool = True,
    include_trends: bool = True,
    strict: bool = False,
    verbose: bool = False,
    use_runtime_settings: bool = True,
) -> PipelineResult:
    load_env_file()
    if use_runtime_settings:
        config = load_runtime_config(config)
    store = initialize_store(config)
    result = PipelineResult()
    posts: list[CommunityPost] = []
    trends: list[TrendPoint] = []

    if include_naver:
        naver = NaverClient()
        if naver.configured:
            try:
                _log("collecting naver cafe articles...", verbose)
                posts.extend(
                    naver.collect_target_cafe_articles(
                        config.keywords,
                        target_cafes=config.target_cafes,
                        pages_per_keyword=config.cafe_pages_per_keyword,
                        verbose=verbose,
                    )
                )
                if include_trends:
                    _log("collecting naver datalab trends...", verbose)
                    trends.extend(naver.collect_default_trends())
            except (HttpError, MissingNaverCredentials) as exc:
                if strict:
                    raise
                result.warnings.append(f"naver skipped: {exc}")
        else:
            result.warnings.append("naver skipped: NAVER_CLIENT_ID/NAVER_CLIENT_SECRET not set")

    if include_bobaedream:
        bobaedream = BobaedreamClient()
        try:
            _log("collecting bobaedream board posts...", verbose)
            posts.extend(
                bobaedream.collect_board_posts(
                    config.bobaedream_boards,
                    pages_per_board=config.bobaedream_pages_per_board,
                    keywords=config.keywords,
                )
            )
        except HttpError as exc:
            if strict:
                raise
            result.warnings.append(f"bobaedream skipped: {exc}")

    if include_dcinside:
        dc = DcinsideClient()
        try:
            _log("collecting dcinside gallery posts...", verbose)
            posts.extend(
                dc.collect_gallery_posts(
                    config.dc_galleries,
                    pages_per_gallery=config.dc_pages_per_gallery,
                    keywords=config.keywords,
                )
            )
        except HttpError as exc:
            if strict:
                raise
            result.warnings.append(f"dcinside skipped: {exc}")

    result.posts_collected = store.upsert_posts(posts)
    result.trends_collected = store.upsert_trends(trends)
    _log(
        f"stored posts={result.posts_collected}, trends={result.trends_collected}",
        verbose,
    )
    return result


def score_posts(config: PipelineConfig = DEFAULT_CONFIG, *, rescore: bool = True) -> PipelineResult:
    store = initialize_store(config)
    posts = store.fetch_posts_for_scoring() if rescore else store.fetch_unscored_posts()
    lexicon = load_runtime_lexicon()
    scores = [score_post(post, lexicon=lexicon) for post in posts]
    return PipelineResult(posts_scored=store.upsert_scores(scores))


def calculate_index(
    store: SentimentStore,
    *,
    day: str | None = None,
    persist: bool = False,
) -> DailyIndex:
    if day:
        rows = store.fetch_daily_score_rows(day=day)
        index_day = str(rows[0]["day"]) if rows else day
    else:
        rows = store.fetch_rolling_score_rows(hours=24, day=kst_today_iso())
        index_day = kst_today_iso()
    baseline = store.fetch_baseline_snapshots(day=index_day) if index_day else []
    index = build_daily_index(
        rows,
        baseline_snapshots=baseline,
        trend_momentum=store.fetch_trend_momentum(),
    )
    if persist:
        store.upsert_daily_snapshot(index)
    return index


def backfill_datalab_baseline(
    config: PipelineConfig = DEFAULT_CONFIG,
    *,
    days: int = 30,
    refresh_trends: bool = True,
    strict: bool = False,
) -> PipelineResult:
    load_env_file()
    store = initialize_store(config)
    result = PipelineResult()

    if refresh_trends:
        naver = NaverClient()
        if naver.configured:
            try:
                end = kst_today()
                start = end - timedelta(days=days)
                trends = naver.collect_default_trends(
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                )
                result.trends_collected = store.upsert_trends(trends)
            except (HttpError, MissingNaverCredentials) as exc:
                if strict:
                    raise
                result.warnings.append(f"naver trends skipped: {exc}")
        else:
            result.warnings.append("naver trends skipped: NAVER_CLIENT_ID/NAVER_CLIENT_SECRET not set")

    current_rows = store.fetch_daily_score_rows()
    if not current_rows:
        result.warnings.append("baseline backfill skipped: no scored current rows")
        return result

    current_index = build_daily_index(current_rows, min_baseline_days=9999)
    current_day = current_index.day
    trend_rows = store.fetch_trend_period_rows()
    snapshots = _build_datalab_estimated_snapshots(
        trend_rows,
        current_index=current_index,
        current_day=current_day,
        days=days,
    )
    for snapshot in snapshots:
        store.upsert_daily_snapshot(snapshot)
    result.snapshots_backfilled = len(snapshots)
    result.daily_index = calculate_index(store, day=current_day, persist=True)
    return result


def build_index(config: PipelineConfig = DEFAULT_CONFIG, *, day: str | None = None) -> PipelineResult:
    store = initialize_store(config)
    return PipelineResult(daily_index=calculate_index(store, day=day, persist=False))


def build_index_with_hourly_snapshot(
    config: PipelineConfig = DEFAULT_CONFIG,
    *,
    day: str | None = None,
) -> PipelineResult:
    store = initialize_store(config)
    index = calculate_index(store, day=day, persist=False)
    store.upsert_hourly_snapshot(index)
    if day:
        store.upsert_daily_snapshot(index)
    elif _is_daily_snapshot_time():
        store.upsert_daily_snapshot(replace(index, day=_daily_checkpoint_day()))
    return PipelineResult(daily_index=index)


def run_daily(
    config: PipelineConfig = DEFAULT_CONFIG,
    *,
    include_dcinside: bool = True,
    include_bobaedream: bool = True,
    strict: bool = False,
    verbose: bool = False,
    use_runtime_settings: bool = True,
) -> PipelineResult:
    result = collect_sources(
        config,
        include_bobaedream=include_bobaedream,
        include_dcinside=include_dcinside,
        strict=strict,
        verbose=verbose,
        use_runtime_settings=use_runtime_settings,
    )
    scored = score_posts(config, rescore=True)
    indexed = build_index_with_hourly_snapshot(config)
    result.posts_scored = scored.posts_scored
    result.daily_index = indexed.daily_index
    return result


def run_scheduler(
    config: PipelineConfig = DEFAULT_CONFIG,
    *,
    times: tuple[str, ...] = ("09:00", "21:00"),
    timezone_name: str = "Asia/Seoul",
    include_dcinside: bool = False,
    include_bobaedream: bool = True,
    strict: bool = False,
    verbose: bool = False,
    run_on_start: bool = False,
) -> None:
    scheduler_timezone = _load_timezone(timezone_name)
    schedule_times = tuple(sorted(_parse_time(value) for value in times))
    _log(
        f"scheduler timezone={timezone_name}, times={','.join(value.strftime('%H:%M') for value in schedule_times)}",
        True,
    )
    if run_on_start:
        _log("running initial scheduled update...", True)
        run_daily(
            config,
            include_dcinside=include_dcinside,
            include_bobaedream=include_bobaedream,
            strict=strict,
            verbose=verbose,
        )

    while True:
        now = datetime.now(scheduler_timezone)
        next_run = _next_run_at(now, schedule_times)
        seconds = max(1.0, (next_run - now).total_seconds())
        _log(f"next update at {_format_schedule_time(next_run)}", True)
        sleep(seconds)
        try:
            collect_result = collect_sources(
                config,
                include_bobaedream=include_bobaedream,
                include_dcinside=include_dcinside,
                strict=strict,
                verbose=verbose,
            )
            score_result = score_posts(config, rescore=True)
            index_result = build_index_with_hourly_snapshot(config)
            _log(
                "scheduled update complete: "
                f"posts={collect_result.posts_collected}, "
                f"trends={collect_result.trends_collected}, "
                f"scored={score_result.posts_scored}, "
                f"index={index_result.daily_index.index_score if index_result.daily_index else 'n/a'} "
                "(hourly snapshot saved)",
                True,
            )
        except Exception as exc:
            if strict:
                raise
            _log(f"scheduled update failed: {exc}", True, error=True)


def _log(message: str, verbose: bool, *, error: bool = False) -> None:
    if verbose:
        stream = sys.stderr if error else sys.stdout
        print(f"[sentiment-index] {message}", file=stream, flush=True)


def _is_daily_snapshot_time() -> bool:
    return datetime.now(ZoneInfo("Asia/Seoul")).hour == 0


def _daily_checkpoint_day() -> str:
    return (datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=1)).isoformat()


def seed_sample_data(config: PipelineConfig = DEFAULT_CONFIG) -> PipelineResult:
    store = initialize_store(config)
    collected_at = utc_now_iso()
    posts = [
        CommunityPost(
            source="sample",
            source_name="디젤매니아",
            title="비트코인 또 신고가라는데 지금이라도 탑승해야 하나요",
            summary="주변에서 다 수익 인증하니 안 사면 놓치는 느낌입니다.",
            url="sample://dieselmania/bitcoin-fomo",
            keyword="비트코인",
            weight=1.2,
            collected_at=collected_at,
        ),
        CommunityPost(
            source="sample",
            source_name="디시 비트코인 갤러리",
            title="알트코인 물렸다 손절해야 되나",
            summary="청산 공포 때문에 잠을 못 자겠습니다.",
            url="sample://dcinside/altcoin-fear",
            keyword="알트코인",
            weight=0.7,
            collected_at=collected_at,
        ),
        CommunityPost(
            source="sample",
            source_name="팍스넷",
            title="삼성전자 반도체 반등 기대감",
            summary="나스닥 상승에 미장 분위기도 괜찮고 국장도 매수세가 붙는 중입니다.",
            url="sample://paxnet/semiconductor-risk-on",
            keyword="삼성전자",
            weight=0.8,
            collected_at=collected_at,
        ),
        CommunityPost(
            source="sample",
            source_name="코인 커뮤니티",
            title="거래소 출금정지 루머 조작 아니냐",
            summary="먹튀나 스캠이면 상폐까지 갈 수 있어서 위험합니다.",
            url="sample://coin/risk-distrust",
            keyword="거래소",
            weight=0.9,
            collected_at=collected_at,
        ),
    ]
    inserted = store.upsert_posts(posts)
    scored = store.upsert_scores(score_post(post) for post in posts)
    index = calculate_index(store, persist=True)
    return PipelineResult(posts_collected=inserted, posts_scored=scored, daily_index=index)


def _build_datalab_estimated_snapshots(
    trend_rows: list[dict[str, object]],
    *,
    current_index: DailyIndex,
    current_day: str,
    days: int,
) -> list[DailyIndex]:
    by_period: dict[str, dict[str, float]] = {}
    for row in trend_rows:
        period = str(row["period"])
        if period >= current_day:
            continue
        by_period.setdefault(period, {})[str(row["group_name"])] = float(row["ratio"])

    periods = sorted(by_period)[-days:]
    if not periods:
        return []

    attention_values = [
        _group_average(by_period[period], ("crypto", "stocks")) for period in periods
    ]
    fomo_intensities = [
        _intensity(by_period[period], "fomo", attention_values[index])
        for index, period in enumerate(periods)
    ]
    risk_intensities = [
        _intensity(by_period[period], "risk", attention_values[index])
        for index, period in enumerate(periods)
    ]
    anchor_attention = _positive_median(attention_values, default=1.0)
    anchor_fomo_intensity = _positive_median(fomo_intensities, default=0.01)
    anchor_risk_intensity = _positive_median(risk_intensities, default=0.01)

    snapshots: list[DailyIndex] = []
    current_weight = max(current_index.new_weighted_post_count, current_index.weighted_post_count, 1.0)
    current_fomo = max(current_index.fomo_score, 0.003)
    current_risk = max(current_index.risk_score, 0.005)

    for period in periods:
        groups = by_period[period]
        attention = _group_average(groups, ("crypto", "stocks"))
        fomo_intensity = _intensity(groups, "fomo", attention)
        risk_intensity = _intensity(groups, "risk", attention)

        estimated_weight = current_weight * (attention / max(anchor_attention, 1.0))
        estimated_fomo = clamp(
            current_fomo * (fomo_intensity / max(anchor_fomo_intensity, 0.01)),
            0.0,
            0.35,
        )
        estimated_risk = clamp(
            current_risk * (risk_intensity / max(anchor_risk_intensity, 0.01)),
            0.0,
            0.35,
        )

        snapshots.append(
            DailyIndex(
                day=period,
                post_count=max(1, int(round(estimated_weight))),
                new_post_count=max(1, int(round(estimated_weight))),
                weighted_post_count=round(estimated_weight, 2),
                new_weighted_post_count=round(estimated_weight, 2),
                baseline_days=0,
                baseline_estimated_days=0,
                baseline_weighted_post_count=0.0,
                mention_change_pct=0.0,
                sentiment=current_index.sentiment,
                fomo_score=round(estimated_fomo, 4),
                fomo_change_pct=0.0,
                risk_score=round(estimated_risk, 4),
                risk_change_pct=0.0,
                spam_rate=current_index.spam_rate,
                attention_score=clamp(
                    math.log1p(estimated_weight) / math.log1p(120.0),
                    0.0,
                    1.0,
                ),
                trend_momentum=0.0,
                index_score=50.0,
                regime="datalab_estimate",
                is_estimated=1,
                snapshot_source="datalab_estimate",
            )
        )
    return snapshots


def _group_average(groups: dict[str, float], names: tuple[str, ...]) -> float:
    values = [groups[name] for name in names if name in groups]
    return sum(values) / len(values) if values else 0.0


def _positive_median(values: list[float], *, default: float) -> float:
    positive = [value for value in values if value > 0]
    return float(median(positive)) if positive else default


def _intensity(groups: dict[str, float], name: str, attention: float) -> float:
    return groups.get(name, 0.0) / max(attention, 1.0)


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def _load_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {name}") from exc


def _format_schedule_time(value: datetime) -> str:
    utc_value = value.astimezone(ZoneInfo("UTC"))
    local = value.strftime("%Y-%m-%d %H:%M:%S %Z")
    utc = utc_value.strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"{local} ({utc})"


def _next_run_at(now: datetime, schedule_times: tuple[time, ...]) -> datetime:
    for schedule_time in schedule_times:
        candidate = now.replace(
            hour=schedule_time.hour,
            minute=schedule_time.minute,
            second=0,
            microsecond=0,
        )
        if candidate > now:
            return candidate
    first = schedule_times[0]
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=first.hour, minute=first.minute, second=0, microsecond=0)
