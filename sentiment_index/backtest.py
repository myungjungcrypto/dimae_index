from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from .config import DEFAULT_CONFIG, PipelineConfig
from .market import MarketDataClient
from .models import MarketPrice, kst_today
from .naver import MissingNaverCredentials, NaverClient
from .pipeline import initialize_store, load_env_file
from .storage import SentimentStore


SIGNAL_GROUPS = ("crypto", "stocks", "fomo", "risk")
HORIZONS = (0, 1, 3, 7)


@dataclass(frozen=True)
class BacktestCorrelation:
    market: str
    signal: str
    horizon_days: int
    samples: int
    correlation: float
    avg_return_when_high: float
    avg_return_all: float


@dataclass(frozen=True)
class DatalabBacktestResult:
    start: str
    end: str
    trend_rows: int
    price_rows: int
    correlations: list[BacktestCorrelation]
    warnings: list[str]


def run_datalab_price_backtest(
    config: PipelineConfig = DEFAULT_CONFIG,
    *,
    days: int = 365,
    end_date: str | None = None,
    refresh: bool = True,
) -> DatalabBacktestResult:
    load_env_file()
    end = date.fromisoformat(end_date) if end_date else kst_today()
    start = end - timedelta(days=days)
    store = initialize_store(config)
    warnings: list[str] = []

    if refresh:
        naver = NaverClient()
        if naver.configured:
            try:
                trends = naver.collect_default_trends(
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                )
                store.upsert_trends(trends)
            except MissingNaverCredentials as exc:
                warnings.append(f"datalab skipped: {exc}")
        else:
            warnings.append("datalab skipped: NAVER_CLIENT_ID/NAVER_CLIENT_SECRET not set")

        prices = _fetch_market_prices(start=start, end=end, warnings=warnings)
        store.upsert_market_prices(prices)

    result = build_datalab_price_backtest(store, start=start, end=end, warnings=warnings)
    return result


def _fetch_market_prices(
    *,
    start: date,
    end: date,
    warnings: list[str],
) -> list[MarketPrice]:
    client = MarketDataClient()
    prices: list[MarketPrice] = []
    fetchers = (
        ("bitcoin", lambda: client.fetch_binance_daily("bitcoin", "BTCUSDT", start=start, end=end)),
        ("nasdaq", lambda: client.fetch_yahoo_daily("nasdaq", "^IXIC", start=start, end=end)),
        ("kospi", lambda: client.fetch_naver_index_daily("kospi", "KOSPI", start=start, end=end)),
    )
    for market, fetcher in fetchers:
        try:
            prices.extend(fetcher())
        except Exception as exc:
            warnings.append(f"{market} prices skipped: {exc}")
    return prices


def build_datalab_price_backtest(
    store: SentimentStore,
    *,
    start: date,
    end: date,
    warnings: list[str] | None = None,
) -> DatalabBacktestResult:
    trend_rows = store.fetch_trend_period_rows_between(
        start=start.isoformat(),
        end=end.isoformat(),
    )
    price_rows = store.fetch_market_prices_between(
        start=start.isoformat(),
        end=end.isoformat(),
    )
    signals_by_date = _build_signal_rows(trend_rows)
    prices_by_market = _prices_by_market(price_rows)
    correlations: list[BacktestCorrelation] = []

    for market, rows in prices_by_market.items():
        returns_by_horizon = _returns_by_horizon(rows)
        for signal in _signal_names(signals_by_date):
            signal_series = {
                day: values[signal]
                for day, values in signals_by_date.items()
                if signal in values
            }
            for horizon in HORIZONS:
                returns = returns_by_horizon.get(horizon, {})
                paired = [
                    (signal_value, returns[day])
                    for day, signal_value in signal_series.items()
                    if day in returns
                ]
                if len(paired) < 20:
                    continue
                correlation = _pearson([item[0] for item in paired], [item[1] for item in paired])
                if correlation is None:
                    continue
                threshold = _percentile([item[0] for item in paired], 0.8)
                high_returns = [ret for value, ret in paired if value >= threshold]
                correlations.append(
                    BacktestCorrelation(
                        market=market,
                        signal=signal,
                        horizon_days=horizon,
                        samples=len(paired),
                        correlation=round(correlation, 4),
                        avg_return_when_high=round(_average(high_returns), 4),
                        avg_return_all=round(_average([item[1] for item in paired]), 4),
                    )
                )

    return DatalabBacktestResult(
        start=start.isoformat(),
        end=end.isoformat(),
        trend_rows=len(trend_rows),
        price_rows=len(price_rows),
        correlations=sorted(
            correlations,
            key=lambda row: abs(row.correlation),
            reverse=True,
        ),
        warnings=warnings or [],
    )


def format_datalab_backtest_markdown(
    result: DatalabBacktestResult,
    *,
    top: int = 20,
) -> str:
    lines = [
        "# Datalab Price Backtest",
        "",
        f"- Period: {result.start} to {result.end}",
        f"- Datalab rows: {result.trend_rows}",
        f"- Price rows: {result.price_rows}",
        "",
    ]
    if result.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in result.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.extend(
        [
            "## Top Correlations",
            "",
            "| Market | Signal | Horizon | Samples | Corr | High Signal Avg Return | All Avg Return |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result.correlations[:top]:
        horizon = "same-day" if row.horizon_days == 0 else f"+{row.horizon_days}d"
        lines.append(
            "| "
            f"{row.market} | {row.signal} | {horizon} | {row.samples} | "
            f"{row.correlation:.4f} | {row.avg_return_when_high:.2%} | {row.avg_return_all:.2%} |"
        )
    if not result.correlations:
        lines.append("| n/a | n/a | n/a | 0 | 0.0000 | 0.00% | 0.00% |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `*_level` is the raw Naver DataLab relative ratio.",
            "- `*_momentum_7d` is the latest 7-day average versus the previous 28-day average.",
            "- `High Signal Avg Return` uses the top 20% signal days for that row.",
            "- This is an exploratory proxy backtest, not the observed community index backtest.",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_signal_rows(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        group = str(row["group_name"])
        if group not in SIGNAL_GROUPS:
            continue
        period = str(row["period"])
        grouped.setdefault(period, {})[f"{group}_level"] = float(row["ratio"])

    periods = sorted(grouped)
    for index, period in enumerate(periods):
        values = grouped[period]
        for group in SIGNAL_GROUPS:
            history = [
                grouped[day].get(f"{group}_level")
                for day in periods[max(0, index - 35) : index + 1]
            ]
            history_values = [float(value) for value in history if value is not None]
            latest = history_values[-7:]
            previous = history_values[-35:-7]
            if len(latest) >= 3 and len(previous) >= 7:
                values[f"{group}_momentum_7d"] = _relative_change(
                    _average(latest),
                    _average(previous),
                )
        if "fomo_momentum_7d" in values and "risk_momentum_7d" in values:
            values["fomo_minus_risk_momentum"] = values["fomo_momentum_7d"] - values["risk_momentum_7d"]
    return grouped


def _signal_names(signals_by_date: dict[str, dict[str, float]]) -> list[str]:
    names: set[str] = set()
    for values in signals_by_date.values():
        names.update(values)
    return sorted(names)


def _prices_by_market(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["market"]), []).append(row)
    for values in grouped.values():
        values.sort(key=lambda row: str(row["date"]))
    return grouped


def _returns_by_horizon(rows: list[dict[str, object]]) -> dict[int, dict[str, float]]:
    returns: dict[int, dict[str, float]] = {horizon: {} for horizon in HORIZONS}
    closes = [float(row["close"]) for row in rows]
    dates = [str(row["date"]) for row in rows]
    for index, close in enumerate(closes):
        if index > 0 and closes[index - 1] > 0:
            returns[0][dates[index]] = (close / closes[index - 1]) - 1.0
        for horizon in (1, 3, 7):
            target = index + horizon
            if target < len(closes) and close > 0:
                returns[horizon][dates[index]] = (closes[target] / close) - 1.0
    return returns


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x_mean = _average(xs)
    y_mean = _average(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_denominator = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_denominator = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    denominator = x_denominator * y_denominator
    if denominator == 0:
        return None
    return numerator / denominator


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * percentile))))
    return sorted_values[index]


def _relative_change(current: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return max(-1.0, min(5.0, (current - baseline) / baseline))


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
