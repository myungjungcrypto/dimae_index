from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import PipelineConfig
from .models import utc_hours_ago_iso
from .pipeline import calculate_index, score_posts
from .settings import add_term, load_settings, remove_term
from .storage import SentimentStore


def serve_dashboard(db_path: Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    store = SentimentStore(db_path)
    store.initialize()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/summary":
                self._send_json(build_summary(store))
                return
            if path in {"/", "/index.html"}:
                self._send_html(render_dashboard(store))
                return
            self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in {"/settings/add", "/settings/remove"}:
                self.send_error(404)
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = parse_qs(self.rfile.read(length).decode("utf-8"))
            list_name = _first_form_value(payload, "list")
            value = _first_form_value(payload, "value")

            try:
                if path == "/settings/add":
                    add_term(list_name, value)
                else:
                    remove_term(list_name, value)
                if list_name == "fomo":
                    config = PipelineConfig(db_path=store.path)
                    score_posts(config, rescore=True)
            except ValueError as exc:
                self.send_error(400, str(exc))
                return

            self.send_response(303)
            self.send_header("Location", "/#settings")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_html(self, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, object]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"dashboard: http://{host}:{port}", flush=True)
    server.serve_forever()


def build_summary(store: SentimentStore) -> dict[str, object]:
    index = calculate_index(store, persist=False)
    since = utc_hours_ago_iso(24)
    return {
        "day": index.day,
        "window": "rolling_24h",
        "index_score": index.index_score,
        "regime": index.regime,
        "post_count": index.post_count,
        "new_post_count": index.new_post_count,
        "baseline_days": index.baseline_days,
        "baseline_estimated_days": index.baseline_estimated_days,
        "mention_change_pct": index.mention_change_pct,
        "attention_score": index.attention_score,
        "sentiment": index.sentiment,
        "fomo_score": index.fomo_score,
        "fomo_change_pct": index.fomo_change_pct,
        "risk_score": index.risk_score,
        "risk_change_pct": index.risk_change_pct,
        "trend_momentum": index.trend_momentum,
        "spam_rate": index.spam_rate,
        "snapshot_source": index.snapshot_source,
        "source_breakdown": store.fetch_source_breakdown(since=since),
    }


def render_dashboard(store: SentimentStore) -> str:
    index = calculate_index(store, persist=False)
    since = utc_hours_ago_iso(24)
    top_rows = store.fetch_top_rows(limit=20, since=since)
    source_rows = store.fetch_source_breakdown(since=since)
    hourly_rows = store.fetch_hourly_snapshots(limit=12)
    settings = load_settings()
    score_color = score_to_color(index.index_score)
    baseline_note = baseline_label(index.baseline_days, index.baseline_estimated_days)
    metric_notes = build_metric_notes()
    explanation_html = render_explanations()
    threshold_html = render_thresholds(index)
    source_html = render_source_breakdown(source_rows)
    hourly_html = render_hourly_snapshots(hourly_rows)
    settings_html = render_settings(settings)
    rows_html = "\n".join(render_post_row(row) for row in top_rows)
    if not rows_html:
        rows_html = '<tr><td colspan="5" class="empty">아직 점수화된 글이 없습니다.</td></tr>'

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>Dimaejipyo Sentiment Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1f2937;
      --muted: #64748b;
      --line: #d8dee8;
      --panel: #ffffff;
      --bg: #f5f7fb;
      --accent: {score_color};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 22px 28px 14px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .sub {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: 1.2fr repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-height: 126px;
    }}
    .metric strong {{
      display: block;
      font-size: 13px;
      color: var(--muted);
      font-weight: 600;
    }}
    .metric span {{
      display: block;
      margin-top: 10px;
      font-size: 28px;
      font-weight: 750;
    }}
    .metric small {{
      display: block;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .score span {{
      color: var(--accent);
      font-size: 42px;
      line-height: 1;
    }}
    .regime {{
      display: inline-flex;
      margin-top: 12px;
      padding: 5px 8px;
      border-radius: 6px;
      background: color-mix(in srgb, var(--accent) 14%, white);
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
    }}
    .table-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .table-head {{
      padding: 16px 16px 0;
    }}
    .table-head h2 {{
      margin: 0;
      font-size: 16px;
      letter-spacing: 0;
    }}
    .table-head p {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .hourly-wrap {{
      margin-bottom: 18px;
    }}
    .explain {{
      margin: 0 0 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .explain h2 {{
      margin: 0 0 12px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    .explain-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 16px;
    }}
    .explain-item {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .explain-item strong {{
      color: var(--ink);
      font-size: 13px;
    }}
    .thresholds {{
      margin: 0 0 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .thresholds h2 {{
      margin: 0 0 12px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    .signals {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .signal {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 6px 9px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 650;
      border: 1px solid var(--line);
      background: #f8fafc;
      color: var(--ink);
    }}
    .signal.watch {{
      color: #92400e;
      background: #fffbeb;
      border-color: #f7d98d;
    }}
    .signal.hot {{
      color: #991b1b;
      background: #fef2f2;
      border-color: #fecaca;
    }}
    .signal.cool {{
      color: #075985;
      background: #f0f9ff;
      border-color: #bae6fd;
    }}
    .signal.info {{
      color: #475569;
      background: #f8fafc;
      border-color: var(--line);
    }}
    .threshold-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 16px;
    }}
    .threshold-item {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .threshold-item strong {{
      color: var(--ink);
      font-size: 13px;
    }}
    .settings {{
      margin: 0 0 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .settings h2 {{
      margin: 0 0 12px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    .settings-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .settings-group h3 {{
      margin: 0 0 10px;
      color: var(--ink);
      font-size: 13px;
    }}
    .term-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
    }}
    .term-list form {{
      margin: 0;
    }}
    .term-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 5px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: var(--ink);
      font-size: 13px;
      cursor: pointer;
    }}
    .term-chip b {{
      margin-left: 6px;
      color: var(--muted);
      font-weight: 700;
    }}
    .settings-add {{
      display: flex;
      gap: 8px;
    }}
    .settings-add input {{
      min-width: 0;
      flex: 1;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
    }}
    .settings-add button {{
      height: 34px;
      border: 1px solid #c7d2fe;
      border-radius: 6px;
      background: #eef2ff;
      color: #3730a3;
      font-weight: 700;
      padding: 0 12px;
      cursor: pointer;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      color: var(--muted);
      background: #f8fafc;
      font-size: 12px;
      text-transform: uppercase;
    }}
    td.title {{
      width: 48%;
      overflow-wrap: anywhere;
    }}
    td.title a {{
      color: var(--ink);
      text-decoration: none;
    }}
    td.source {{
      color: var(--muted);
      width: 18%;
    }}
    .empty {{
      color: var(--muted);
      text-align: center;
      padding: 36px;
    }}
    @media (max-width: 860px) {{
      header {{ padding: 18px; }}
      main {{ padding: 14px; }}
      .metrics {{ grid-template-columns: 1fr 1fr; }}
      .explain-grid {{ grid-template-columns: 1fr; }}
      .threshold-grid {{ grid-template-columns: 1fr; }}
      .settings-grid {{ grid-template-columns: 1fr; }}
      .score {{ grid-column: 1 / -1; }}
      table {{ table-layout: auto; }}
      th:nth-child(3), td:nth-child(3),
      th:nth-child(4), td:nth-child(4),
      th:nth-child(5), td:nth-child(5) {{ display: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Dimaejipyo Sentiment Dashboard</h1>
    <div class="sub">Rolling 24H window · KST 기준일: {html.escape(index.day)} · {html.escape(baseline_note)} · auto-refresh 60s</div>
  </header>
  <main>
    <section class="metrics">
      <div class="metric score">
        <strong>Index Score</strong>
        <span>{index.index_score:.2f}</span>
        <div class="regime">{html.escape(index.regime)}</div>
        <small>{html.escape(metric_notes["index_score"])}</small>
      </div>
      <div class="metric"><strong>Posts</strong><span>{index.post_count}</span><small>{html.escape(metric_notes["posts"])}</small></div>
      <div class="metric"><strong>New Posts</strong><span>{index.new_post_count}</span><small>{html.escape(metric_notes["new_posts"])}</small></div>
      <div class="metric"><strong>Baseline</strong><span>{index.baseline_days}d</span><small>{html.escape(metric_notes["baseline"])}</small></div>
      <div class="metric"><strong>Estimated</strong><span>{index.baseline_estimated_days}d</span><small>{html.escape(metric_notes["estimated"])}</small></div>
      <div class="metric"><strong>Mentions Δ</strong><span>{format_pct(index.mention_change_pct)}</span><small>{html.escape(metric_notes["mentions_delta"])}</small></div>
      <div class="metric"><strong>Greed</strong><span>{format_rate(index.fomo_score)}</span><small>{html.escape(metric_notes["fomo"])}</small></div>
      <div class="metric"><strong>Greed Δ</strong><span>{format_pct(index.fomo_change_pct)}</span><small>{html.escape(metric_notes["fomo_delta"])}</small></div>
      <div class="metric"><strong>Fear</strong><span>{format_rate(index.risk_score)}</span><small>{html.escape(metric_notes["risk"])}</small></div>
      <div class="metric"><strong>Fear Δ</strong><span>{format_pct(index.risk_change_pct)}</span><small>{html.escape(metric_notes["risk_delta"])}</small></div>
      <div class="metric"><strong>Search Δ</strong><span>{format_pct(index.trend_momentum)}</span><small>{html.escape(metric_notes["search_delta"])}</small></div>
    </section>
    {explanation_html}
    {threshold_html}
    {source_html}
    {hourly_html}
    {settings_html}
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Source</th>
            <th>Title</th>
            <th>Sentiment</th>
            <th>Greed</th>
            <th>Fear</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def _first_form_value(payload: dict[str, list[str]], name: str) -> str:
    values = payload.get(name)
    return values[0].strip() if values else ""


def render_post_row(row: dict[str, object]) -> str:
    source = html.escape(str(row["source_name"]))
    title = html.escape(str(row["title"]))
    url = html.escape(str(row["url"]), quote=True)
    sentiment = float(row["sentiment"])
    fomo = float(row["fomo_score"])
    risk = float(row["risk_score"])
    return (
        "<tr>"
        f'<td class="source">{source}</td>'
        f'<td class="title"><a href="{url}" target="_blank" rel="noreferrer">{title}</a></td>'
        f"<td>{sentiment:.2f}</td>"
        f"<td>{fomo:.2f}</td>"
        f"<td>{risk:.2f}</td>"
        "</tr>"
    )


def render_hourly_snapshots(rows: list[dict[str, object]]) -> str:
    row_html = "\n".join(render_hourly_row(row) for row in rows)
    if not row_html:
        row_html = '<tr><td colspan="7" class="empty">아직 시간별 스냅샷이 없습니다.</td></tr>'
    return (
        '<section class="table-wrap hourly-wrap">'
        '<div class="table-head">'
        "<h2>Rolling 24H Snapshots</h2>"
        "<p>매시간 수집 직후 저장된 최근 24시간 기준 지표입니다. 자정 리셋 없이 한 시간씩 밀려갑니다.</p>"
        "</div>"
        "<table>"
        "<thead>"
        "<tr>"
        "<th>KST Hour</th>"
        "<th>Score</th>"
        "<th>Regime</th>"
        "<th>Posts</th>"
        "<th>New</th>"
        "<th>Greed</th>"
        "<th>Fear</th>"
        "</tr>"
        "</thead>"
        f"<tbody>{row_html}</tbody>"
        "</table>"
        "</section>"
    )


def render_source_breakdown(rows: list[dict[str, object]]) -> str:
    row_html = "\n".join(render_source_row(row) for row in rows)
    if not row_html:
        row_html = '<tr><td colspan="8" class="empty">아직 소스별 집계가 없습니다.</td></tr>'
    return (
        '<section class="table-wrap hourly-wrap">'
        '<div class="table-head">'
        "<h2>Source Breakdown</h2>"
        "<p>최근 24시간 기준 소스별 기여도입니다. 표본이 한 커뮤니티에 쏠리는지 확인할 때 사용합니다.</p>"
        "</div>"
        "<table>"
        "<thead>"
        "<tr>"
        "<th>Source</th>"
        "<th>Posts</th>"
        "<th>New</th>"
        "<th>Weighted</th>"
        "<th>New W.</th>"
        "<th>Greed</th>"
        "<th>Fear</th>"
        "<th>Spam</th>"
        "</tr>"
        "</thead>"
        f"<tbody>{row_html}</tbody>"
        "</table>"
        "</section>"
    )


def render_source_row(row: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(str(row['source_name']))}</td>"
        f"<td>{int(row['post_count'])}</td>"
        f"<td>{int(row['new_post_count'])}</td>"
        f"<td>{float(row['weighted_post_count']):.1f}</td>"
        f"<td>{float(row['new_weighted_post_count']):.1f}</td>"
        f"<td>{format_rate(float(row['fomo_score'] or 0.0))}</td>"
        f"<td>{format_rate(float(row['risk_score'] or 0.0))}</td>"
        f"<td>{format_rate(float(row['spam_rate'] or 0.0))}</td>"
        "</tr>"
    )


def render_hourly_row(row: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(str(row['snapshot_at'])[:16])}</td>"
        f"<td>{float(row['index_score']):.2f}</td>"
        f"<td>{html.escape(str(row['regime']))}</td>"
        f"<td>{int(row['post_count'])}</td>"
        f"<td>{int(row['new_post_count'])}</td>"
        f"<td>{format_rate(float(row['fomo_score']))}</td>"
        f"<td>{format_rate(float(row['risk_score']))}</td>"
        "</tr>"
    )


def render_settings(settings: dict[str, object]) -> str:
    lexicon = settings.get("lexicon", {})
    fomo_terms = lexicon.get("fomo", []) if isinstance(lexicon, dict) else []
    return (
        '<section id="settings" class="settings">'
        "<h2>Settings</h2>"
        '<div class="settings-grid">'
        + render_term_editor(
            "Search Keywords",
            "keywords",
            settings.get("keywords", []),
            "검색어 추가",
        )
        + render_term_editor(
            "Greed Dictionary",
            "fomo",
            fomo_terms,
            "Greed 단어 추가",
        )
        + "</div>"
        "</section>"
    )


def render_term_editor(
    title: str,
    list_name: str,
    terms: object,
    placeholder: str,
) -> str:
    term_list = [str(term) for term in terms] if isinstance(terms, list) else []
    chips = "\n".join(render_term_chip(list_name, term) for term in term_list)
    if not chips:
        chips = '<span class="signal info">비어 있음</span>'
    return (
        '<div class="settings-group">'
        f"<h3>{html.escape(title)} ({len(term_list)})</h3>"
        f'<div class="term-list">{chips}</div>'
        '<form class="settings-add" method="post" action="/settings/add">'
        f'<input type="hidden" name="list" value="{html.escape(list_name, quote=True)}">'
        f'<input name="value" placeholder="{html.escape(placeholder, quote=True)}" autocomplete="off">'
        "<button type=\"submit\">추가</button>"
        "</form>"
        "</div>"
    )


def render_term_chip(list_name: str, term: str) -> str:
    escaped_list = html.escape(list_name, quote=True)
    escaped_term = html.escape(term, quote=True)
    visible_term = html.escape(term)
    return (
        '<form method="post" action="/settings/remove">'
        f'<input type="hidden" name="list" value="{escaped_list}">'
        f'<input type="hidden" name="value" value="{escaped_term}">'
        f'<button class="term-chip" type="submit">{visible_term}<b>삭제</b></button>'
        "</form>"
    )


def build_metric_notes() -> dict[str, str]:
    return {
        "index_score": "최근 24시간 값을 과거 기준선 분포의 분위수로 환산한 0~100 점수입니다.",
        "posts": "최근 24시간 안에 마지막으로 포착된 전체 글 수입니다. 검색 결과 재발견 글도 포함됩니다.",
        "new_posts": "최근 24시간 안에 처음 포착됐고, 글번호가 이전 최고값보다 큰 URL 수입니다.",
        "baseline": "비교에 쓰는 과거 스냅샷 일수입니다. 14일 미만이면 보정 중으로 봅니다.",
        "estimated": "데이터랩으로 추정한 과거 기준선 일수입니다. 실제 관측값이 쌓이면 비중이 낮아집니다.",
        "mentions_delta": "신규 포착 언급량이 기준선보다 얼마나 늘거나 줄었는지입니다.",
        "fomo": "놓칠까 봐 따라붙는 탐욕/추격매수 단어 비중입니다.",
        "fomo_delta": "Greed 비중이 과거 기준선 대비 얼마나 변했는지입니다.",
        "risk": "폭락, 청산, 상폐, 조작, 해킹 같은 공포/불신 단어 비중입니다.",
        "risk_delta": "Fear 비중이 과거 기준선 대비 얼마나 변했는지입니다.",
        "search_delta": "남성 30~49세 네이버 검색량의 최근 모멘텀입니다.",
    }


def render_explanations() -> str:
    items = [
        ("Index Score", "최근 24시간 관측값이 과거 기준선에서 어느 분위수인지 봅니다. 80 이상은 과열 후보, 20 이하는 패닉 후보입니다."),
        ("Regime", "calibrating은 기준선 부족, risk_on은 상위권 위험 선호, euphoria는 극단적 과열 후보입니다."),
        ("Mentions Δ", "최근 24시간 신규 포착 언급량의 평균 대비 변화입니다. 점수 산식은 평균 변화율보다 분위수를 우선합니다."),
        ("Greed Δ", "탐욕/추격매수 언어가 평소보다 늘었는지 봅니다. 최종 점수에는 Greed 원점수의 과거 분위수가 반영됩니다."),
        ("Fear Δ", "공포/불신 언어가 평소보다 늘었는지 봅니다. 최종 점수에서는 Fear 분위수가 높을수록 점수를 낮춥니다."),
        ("Daily Score", "하루 대표값은 KST 00시대에 전날 날짜로 저장되는 Rolling 24H Score입니다. 지표는 하나이고 보는 간격만 다릅니다."),
    ]
    rendered = "\n".join(
        f'<div class="explain-item"><strong>{html.escape(title)}</strong><br>{html.escape(body)}</div>'
        for title, body in items
    )
    return (
        '<section class="explain">'
        "<h2>How To Read</h2>"
        f'<div class="explain-grid">{rendered}</div>'
        "</section>"
    )


def render_thresholds(index: object) -> str:
    signals = current_signals(index)
    signal_html = "\n".join(
        f'<span class="signal {html.escape(level)}">{html.escape(text)}</span>'
        for level, text in signals
    )
    items = [
        ("Index Score", "≤20 panic · 20~35 risk_off · 65~80 risk_on · ≥80 euphoria"),
        ("Mentions Δ", "+50% 관심 증가 · +100% 급증 · -40% 관심 둔화"),
        ("Greed", "원점수 2% 이상 주의 · 5% 이상 과열 후보"),
        ("Greed Δ", "+100% 주의 · +250% 급증. 단, 원점수가 1% 미만이면 약한 신호로 봅니다."),
        ("Fear", "원점수 5% 이상 스트레스 · 10% 이상 고위험 후보"),
        ("Fear Δ", "+100% 주의 · +250% 급증. 가격 하락/뉴스와 함께 확인합니다."),
        ("Search Δ", "±25% 이상이면 검색 모멘텀 변화로 봅니다."),
        ("Spam Rate", "10% 이상 노이즈 주의 · 20% 이상이면 지표 신뢰도 낮음"),
    ]
    threshold_items = "\n".join(
        f'<div class="threshold-item"><strong>{html.escape(title)}</strong><br>{html.escape(body)}</div>'
        for title, body in items
    )
    return (
        '<section class="thresholds">'
        "<h2>Thresholds</h2>"
        f'<div class="signals">{signal_html}</div>'
        f'<div class="threshold-grid">{threshold_items}</div>'
        "</section>"
    )


def current_signals(index: object) -> list[tuple[str, str]]:
    signals: list[tuple[str, str]] = []
    if index.baseline_days < 14:
        signals.append(("info", "기준선 보정 중: 14일 미만"))
    elif index.index_score >= 80:
        signals.append(("hot", "Index 과열 후보"))
    elif index.index_score >= 65:
        signals.append(("watch", "Index 위험 선호"))
    elif index.index_score <= 20:
        signals.append(("hot", "Index 패닉 후보"))
    elif index.index_score <= 35:
        signals.append(("watch", "Index 위험 회피"))

    if index.mention_change_pct >= 1.0:
        signals.append(("hot", "언급량 급증"))
    elif index.mention_change_pct >= 0.5:
        signals.append(("watch", "언급량 증가"))
    elif index.mention_change_pct <= -0.4:
        signals.append(("cool", "언급량 둔화"))

    if index.fomo_score >= 0.05:
        signals.append(("hot", "Greed 원점수 과열"))
    elif index.fomo_score >= 0.02:
        signals.append(("watch", "Greed 원점수 주의"))
    elif index.fomo_change_pct >= 1.0:
        signals.append(("info", "Greed 변화율 상승, 원점수는 낮음"))

    if index.risk_score >= 0.10:
        signals.append(("hot", "Fear 원점수 고위험"))
    elif index.risk_score >= 0.05:
        signals.append(("watch", "Fear 원점수 주의"))
    elif index.risk_change_pct >= 1.0:
        signals.append(("info", "Fear 변화율 상승, 원점수는 낮음"))

    if index.trend_momentum >= 0.25:
        signals.append(("watch", "검색 관심 증가"))
    elif index.trend_momentum <= -0.25:
        signals.append(("cool", "검색 관심 둔화"))

    if index.spam_rate >= 0.20:
        signals.append(("hot", "스팸 노이즈 높음"))
    elif index.spam_rate >= 0.10:
        signals.append(("watch", "스팸 노이즈 주의"))

    if index.baseline_estimated_days:
        signals.append(("info", f"추정 기준선 {index.baseline_estimated_days}일 포함"))
    if not signals:
        signals.append(("info", "임계값 초과 신호 없음"))
    return signals


def format_pct(value: float) -> str:
    return f"{value * 100:+.0f}%"


def format_rate(value: float) -> str:
    return f"{value * 100:.1f}%"


def baseline_label(days: int, estimated_days: int) -> str:
    if days == 0:
        return "no baseline yet"
    if estimated_days == days:
        return f"{days}d estimated baseline"
    if estimated_days:
        return f"{days}d baseline, {estimated_days}d estimated"
    return f"{days}d observed baseline"


def score_to_color(score: float) -> str:
    if score >= 75:
        return "#0f9f6e"
    if score >= 60:
        return "#2563eb"
    if score <= 30:
        return "#dc2626"
    if score <= 42:
        return "#c2410c"
    return "#4f46e5"
