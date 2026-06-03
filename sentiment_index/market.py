from __future__ import annotations

from datetime import date, datetime, time, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

from .http import request_json, request_text
from .models import MarketPrice


class MarketDataClient:
    binance_klines_url = "https://api.binance.com/api/v3/klines"
    yahoo_chart_url = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    naver_index_url = "https://finance.naver.com/sise/sise_index_day.naver"

    def fetch_default_prices(self, *, start: date, end: date) -> list[MarketPrice]:
        prices: list[MarketPrice] = []
        prices.extend(self.fetch_binance_daily("bitcoin", "BTCUSDT", start=start, end=end))
        prices.extend(self.fetch_yahoo_daily("nasdaq", "^IXIC", start=start, end=end))
        prices.extend(self.fetch_naver_index_daily("kospi", "KOSPI", start=start, end=end))
        return prices

    def fetch_binance_daily(
        self,
        market: str,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketPrice]:
        payload = request_json(
            self.binance_klines_url,
            query={
                "symbol": symbol,
                "interval": "1d",
                "startTime": _epoch_ms(start),
                "endTime": _epoch_ms(end, end_of_day=True),
                "limit": 1000,
            },
        )
        prices: list[MarketPrice] = []
        for row in payload if isinstance(payload, list) else []:
            row_date = datetime.fromtimestamp(int(row[0]) / 1000, timezone.utc).date().isoformat()
            prices.append(
                MarketPrice(
                    market=market,
                    symbol=symbol,
                    date=row_date,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    source="binance",
                ).normalized()
            )
        return prices

    def fetch_yahoo_daily(
        self,
        market: str,
        symbol: str,
        *,
        start: date,
        end: date,
    ) -> list[MarketPrice]:
        payload = request_json(
            self.yahoo_chart_url.format(symbol=quote(symbol, safe="")),
            headers={"User-Agent": "Mozilla/5.0"},
            query={
                "period1": _epoch_seconds(start),
                "period2": _epoch_seconds(end, end_of_day=True),
                "interval": "1d",
                "events": "history",
                "includeAdjustedClose": "true",
            },
        )
        results = payload.get("chart", {}).get("result", [])
        if not results:
            return []
        result = results[0]
        timestamps = result.get("timestamp", [])
        quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote_data.get("close", [])
        opens = quote_data.get("open", [])
        highs = quote_data.get("high", [])
        lows = quote_data.get("low", [])
        volumes = quote_data.get("volume", [])
        prices: list[MarketPrice] = []
        for index, timestamp in enumerate(timestamps):
            close = _list_value(closes, index)
            if close is None:
                continue
            row_date = datetime.fromtimestamp(int(timestamp), timezone.utc).date().isoformat()
            prices.append(
                MarketPrice(
                    market=market,
                    symbol=symbol,
                    date=row_date,
                    open=_list_value(opens, index),
                    high=_list_value(highs, index),
                    low=_list_value(lows, index),
                    close=close,
                    volume=_list_value(volumes, index),
                    source="yahoo_chart",
                ).normalized()
            )
        return prices

    def fetch_naver_index_daily(
        self,
        market: str,
        code: str,
        *,
        start: date,
        end: date,
        max_pages: int = 90,
    ) -> list[MarketPrice]:
        prices: list[MarketPrice] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            html = request_text(
                self.naver_index_url,
                query={"code": code, "page": page},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            parser = NaverIndexDayParser(market=market, symbol=code)
            parser.feed(html)
            if not parser.prices:
                break
            oldest: date | None = None
            for price in parser.prices:
                row_date = date.fromisoformat(price.date)
                oldest = row_date if oldest is None else min(oldest, row_date)
                if row_date < start or row_date > end or price.date in seen:
                    continue
                seen.add(price.date)
                prices.append(price)
            if oldest is not None and oldest < start:
                break
        return sorted(prices, key=lambda price: price.date)


class NaverIndexDayParser(HTMLParser):
    def __init__(self, *, market: str, symbol: str) -> None:
        super().__init__()
        self.market = market
        self.symbol = symbol
        self.prices: list[MarketPrice] = []
        self._field: str | None = None
        self._current_date: str | None = None
        self._waiting_for_close = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "td":
            return
        attr = {key: value or "" for key, value in attrs}
        class_name = attr.get("class", "")
        if "date" in class_name:
            self._field = "date"
        elif "number_1" in class_name:
            self._field = "number"

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._field is None:
            return
        if self._field == "date":
            try:
                self._current_date = date.fromisoformat(text.replace(".", "-")).isoformat()
                self._waiting_for_close = True
            except ValueError:
                self._current_date = None
                self._waiting_for_close = False
            return
        if self._field == "number" and self._current_date and self._waiting_for_close:
            close = _float_text(text)
            if close is not None:
                self.prices.append(
                    MarketPrice(
                        market=self.market,
                        symbol=self.symbol,
                        date=self._current_date,
                        close=close,
                        source="naver_finance",
                    ).normalized()
                )
                self._waiting_for_close = False

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self._field = None


def _epoch_seconds(value: date, *, end_of_day: bool = False) -> int:
    row_time = time.max if end_of_day else time.min
    return int(datetime.combine(value, row_time, tzinfo=timezone.utc).timestamp())


def _epoch_ms(value: date, *, end_of_day: bool = False) -> int:
    return _epoch_seconds(value, end_of_day=end_of_day) * 1000


def _list_value(values: list[Any], index: int) -> float | None:
    if index >= len(values):
        return None
    value = values[index]
    return float(value) if value is not None else None


def _float_text(value: str) -> float | None:
    cleaned = value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
