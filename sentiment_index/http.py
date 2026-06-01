from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_HEADERS = {
    "User-Agent": "dimaejipyo-sentiment-index/0.1 (+local research)",
}


class HttpError(RuntimeError):
    pass


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 20,
    retries: int = 2,
    pause: float = 0.4,
) -> dict[str, Any]:
    final_url = url
    if query:
        final_url = f"{url}?{urllib.parse.urlencode(query)}"

    payload = None
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json")

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            final_url,
            data=payload,
            headers=merged_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, errors="replace")
                return json.loads(text)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(pause * (attempt + 1))

    raise HttpError(f"JSON request failed: {final_url}: {last_error}") from last_error


def request_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    timeout: int = 20,
    retries: int = 2,
    pause: float = 0.4,
) -> str:
    final_url = url
    if query:
        final_url = f"{url}?{urllib.parse.urlencode(query)}"

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(final_url, headers=merged_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(pause * (attempt + 1))

    raise HttpError(f"Text request failed: {final_url}: {last_error}") from last_error

