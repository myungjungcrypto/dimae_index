from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .backtest import format_datalab_backtest_markdown, run_datalab_price_backtest
from .config import DEFAULT_CONFIG, PipelineConfig
from .dashboard import serve_dashboard
from .pipeline import (
    backfill_datalab_baseline,
    build_index,
    collect_sources,
    initialize_store,
    run_daily,
    run_scheduler,
    score_posts,
    seed_sample_data,
)
from .reporting import build_markdown_report, format_index
from .storage import SentimentStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sentiment-index",
        description="Build a Korean community crypto/stock sentiment index.",
    )
    parser.add_argument("--db", default=str(DEFAULT_CONFIG.db_path), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create database tables")

    collect = sub.add_parser("collect", help="Collect from configured sources")
    collect.add_argument("--no-naver", action="store_true", help="Skip Naver APIs")
    collect.add_argument("--no-bobaedream", action="store_true", help="Skip Bobaedream boards")
    collect.add_argument("--no-dcinside", action="store_true", help="Skip DCInside")
    collect.add_argument("--no-trends", action="store_true", help="Skip Naver DataLab trends")
    collect.add_argument("--strict", action="store_true", help="Fail on source errors")
    collect.add_argument("--quick", action="store_true", help="Use a small Naver keyword sample")
    collect.add_argument("--verbose", action="store_true", help="Print progress while collecting")

    score = sub.add_parser("score", help="Score collected posts")
    score.add_argument("--only-new", action="store_true", help="Only score unscored posts")

    report = sub.add_parser("report", help="Print a report")
    report.add_argument("--markdown", action="store_true", help="Print Markdown report")
    report.add_argument("--top", type=int, default=12, help="Top signal count for Markdown")

    run = sub.add_parser("run", help="Collect, score, and print the latest index")
    run.add_argument("--no-bobaedream", action="store_true", help="Skip Bobaedream boards")
    run.add_argument("--no-dcinside", action="store_true", help="Skip DCInside")
    run.add_argument("--strict", action="store_true", help="Fail on source errors")
    run.add_argument("--quick", action="store_true", help="Use a small Naver keyword sample")
    run.add_argument("--verbose", action="store_true", help="Print progress while collecting")

    sub.add_parser("seed-sample", help="Insert sample posts and score them")

    dashboard = sub.add_parser("dashboard", help="Serve a local web dashboard")
    dashboard.add_argument("--host", default="127.0.0.1", help="Dashboard host")
    dashboard.add_argument("--port", type=int, default=8765, help="Dashboard port")

    backfill = sub.add_parser("backfill-datalab", help="Seed estimated 30-day baselines from Naver DataLab")
    backfill.add_argument("--days", type=int, default=30, help="Number of historical days to estimate")
    backfill.add_argument("--no-refresh-trends", action="store_true", help="Use already stored DataLab rows")
    backfill.add_argument("--strict", action="store_true", help="Fail on source errors")

    backtest = sub.add_parser("backtest-datalab", help="Backtest 1y DataLab proxies against market prices")
    backtest.add_argument("--days", type=int, default=365, help="Historical calendar days to test")
    backtest.add_argument("--end-date", help="End date in YYYY-MM-DD; defaults to today")
    backtest.add_argument("--no-refresh", action="store_true", help="Use already stored trends/prices")
    backtest.add_argument("--top", type=int, default=20, help="Rows to show in the Markdown report")
    backtest.add_argument("--output", help="Optional Markdown output path")

    schedule = sub.add_parser("schedule", help="Run automatic scheduled updates")
    schedule.add_argument("--times", default="09:00,21:00", help="Comma-separated local times")
    schedule.add_argument("--hourly", action="store_true", help="Run every hour")
    schedule.add_argument("--timezone", default="Asia/Seoul", help="IANA timezone for schedule times")
    schedule.add_argument("--include-dcinside", action="store_true", help="Also collect DCInside")
    schedule.add_argument("--no-bobaedream", action="store_true", help="Skip Bobaedream boards")
    schedule.add_argument("--run-on-start", action="store_true", help="Run one update immediately")
    schedule.add_argument("--strict", action="store_true", help="Fail on source errors")
    schedule.add_argument("--verbose", action="store_true", help="Print progress")
    return parser.parse_args()


def with_db(path: str) -> PipelineConfig:
    return PipelineConfig(db_path=Path(path))


def maybe_quick_config(config: PipelineConfig, quick: bool) -> PipelineConfig:
    if not quick:
        return config
    return replace(
        config,
        keywords=("비트코인", "코인", "주식", "나스닥", "삼성전자"),
        cafe_pages_per_keyword=1,
        dc_pages_per_gallery=1,
        bobaedream_pages_per_board=1,
    )


def main() -> None:
    args = parse_args()
    config = with_db(args.db)

    if args.command == "init-db":
        initialize_store(config)
        print(f"initialized: {config.db_path}")
        return

    if args.command == "collect":
        config = maybe_quick_config(config, args.quick)
        result = collect_sources(
            config,
            include_naver=not args.no_naver,
            include_bobaedream=not args.no_bobaedream,
            include_dcinside=not args.no_dcinside,
            include_trends=not args.no_trends,
            strict=args.strict,
            verbose=args.verbose,
            use_runtime_settings=not args.quick,
        )
        print(f"posts_collected: {result.posts_collected}")
        print(f"trends_collected: {result.trends_collected}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        return

    if args.command == "score":
        result = score_posts(config, rescore=not args.only_new)
        print(f"posts_scored: {result.posts_scored}")
        return

    if args.command == "report":
        result = build_index(config)
        if result.daily_index is None:
            raise RuntimeError("index was not built")
        if args.markdown:
            store = SentimentStore(config.db_path)
            print(build_markdown_report(store, result.daily_index, top_limit=args.top))
        else:
            print(format_index(result.daily_index))
        return

    if args.command == "run":
        config = maybe_quick_config(config, args.quick)
        result = run_daily(
            config,
            include_bobaedream=not args.no_bobaedream,
            include_dcinside=not args.no_dcinside,
            strict=args.strict,
            verbose=args.verbose,
            use_runtime_settings=not args.quick,
        )
        if result.daily_index is None:
            raise RuntimeError("index was not built")
        print(f"posts_collected: {result.posts_collected}")
        print(f"trends_collected: {result.trends_collected}")
        print(f"posts_scored: {result.posts_scored}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        print(format_index(result.daily_index))
        return

    if args.command == "seed-sample":
        result = seed_sample_data(config)
        print(f"posts_collected: {result.posts_collected}")
        print(f"posts_scored: {result.posts_scored}")
        if result.daily_index:
            print(format_index(result.daily_index))

    if args.command == "dashboard":
        serve_dashboard(config.db_path, host=args.host, port=args.port)

    if args.command == "backfill-datalab":
        result = backfill_datalab_baseline(
            config,
            days=args.days,
            refresh_trends=not args.no_refresh_trends,
            strict=args.strict,
        )
        print(f"trends_collected: {result.trends_collected}")
        print(f"snapshots_backfilled: {result.snapshots_backfilled}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        if result.daily_index:
            print(format_index(result.daily_index))

    if args.command == "backtest-datalab":
        result = run_datalab_price_backtest(
            config,
            days=args.days,
            end_date=args.end_date,
            refresh=not args.no_refresh,
        )
        report_text = format_datalab_backtest_markdown(result, top=args.top)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report_text, encoding="utf-8")
            print(f"wrote: {output_path}")
        print(report_text)
        return

    if args.command == "schedule":
        times = hourly_times() if args.hourly else tuple(part.strip() for part in args.times.split(",") if part.strip())
        run_scheduler(
            config,
            times=times,
            timezone_name=args.timezone,
            include_dcinside=args.include_dcinside,
            include_bobaedream=not args.no_bobaedream,
            strict=args.strict,
            verbose=args.verbose,
            run_on_start=args.run_on_start,
        )


def hourly_times() -> tuple[str, ...]:
    return tuple(f"{hour:02d}:00" for hour in range(24))


if __name__ == "__main__":
    main()
