from __future__ import annotations

from collections.abc import Iterable
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

from .config import CommunityBoard, NaverFinanceStock
from .dcinside import parse_int
from .http import request_text
from .models import CommunityPost


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
}


class CommunityLinkParser(HTMLParser):
    def __init__(self, board: CommunityBoard) -> None:
        super().__init__(convert_charrefs=True)
        self.board = board
        self.posts: list[CommunityPost] = []
        self._anchor: dict[str, str] | None = None
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {key: value or "" for key, value in attrs}
        href = attr.get("href")
        if not href:
            return
        url = _absolute_url(href, base_url=self.board.url_template)
        if not _matches_board_url(self.board.source, url):
            return
        self._anchor = {
            "url": _canonical_url(url),
            "title": _clean_text(attr.get("title", "")),
        }
        self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._anchor is None:
            return
        text = _clean_text(data)
        if text:
            self._title_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._anchor is None:
            return
        title = self._anchor.get("title") or _clean_text(" ".join(self._title_parts))
        url = self._anchor.get("url", "")
        if title and url and not _is_noise_title(title):
            self.posts.append(
                CommunityPost(
                    source=self.board.source,
                    source_name=self.board.name,
                    title=title,
                    summary="",
                    url=url,
                    weight=self.board.weight,
                ).normalized()
            )
        self._anchor = None
        self._title_parts = []


class NaverFinanceBoardParser(HTMLParser):
    def __init__(self, stock: NaverFinanceStock) -> None:
        super().__init__(convert_charrefs=True)
        self.stock = stock
        self.posts: list[CommunityPost] = []
        self._anchor: dict[str, str] | None = None
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {key: value or "" for key, value in attrs}
        href = attr.get("href")
        if not href:
            return
        url = _absolute_url(href, base_url="https://finance.naver.com/item/board.naver")
        if not _is_naver_finance_post_url(url):
            return
        self._anchor = {
            "url": _canonical_url(url),
            "title": _clean_text(attr.get("title", "")),
        }
        self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._anchor is None:
            return
        text = _clean_text(data)
        if text:
            self._title_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._anchor is None:
            return
        title = self._anchor.get("title") or _clean_text(" ".join(self._title_parts))
        url = self._anchor.get("url", "")
        if title and url and not _is_noise_title(title):
            self.posts.append(
                CommunityPost(
                    source="naver_finance",
                    source_name=f"네이버 종토방 {self.stock.name}",
                    title=title,
                    summary=self.stock.name,
                    url=url,
                    keyword=self.stock.name,
                    weight=self.stock.weight,
                ).normalized()
            )
        self._anchor = None
        self._title_parts = []


class CommunitySourceClient:
    def fetch_naver_finance_page(
        self,
        stock: NaverFinanceStock,
        *,
        page: int = 1,
    ) -> list[CommunityPost]:
        html = request_text(
            "https://finance.naver.com/item/board.naver",
            query={"code": stock.code, "page": page},
            headers={
                **BROWSER_HEADERS,
                "Referer": "https://finance.naver.com/",
            },
        )
        parser = NaverFinanceBoardParser(stock)
        parser.feed(html)
        return parser.posts

    def fetch_board_page(
        self,
        board: CommunityBoard,
        *,
        page: int = 1,
    ) -> list[CommunityPost]:
        html = request_text(
            board.url_template.format(page=page),
            headers={
                **BROWSER_HEADERS,
                "Referer": _referer_for(board.url_template),
            },
        )
        parser = CommunityLinkParser(board)
        parser.feed(html)
        return parser.posts

    def collect_naver_finance_posts(
        self,
        stocks: Iterable[NaverFinanceStock],
        *,
        pages_per_stock: int = 1,
    ) -> list[CommunityPost]:
        seen: set[str] = set()
        collected: list[CommunityPost] = []
        for stock in stocks:
            for page in range(1, max(pages_per_stock, 1) + 1):
                for post in self.fetch_naver_finance_page(stock, page=page):
                    if post.url in seen:
                        continue
                    seen.add(post.url)
                    collected.append(post)
        return collected

    def collect_board_posts(
        self,
        boards: Iterable[CommunityBoard],
        *,
        pages_per_board: int = 1,
        keywords: Iterable[str] = (),
    ) -> list[CommunityPost]:
        keyword_tuple = tuple(keywords)
        seen: set[str] = set()
        collected: list[CommunityPost] = []
        for board in boards:
            for page in range(1, max(pages_per_board, 1) + 1):
                for post in self.fetch_board_page(board, page=page):
                    if post.url in seen:
                        continue
                    keyword = _matched_keyword(post, keyword_tuple)
                    if board.keyword_filter and keyword_tuple and keyword is None:
                        continue
                    seen.add(post.url)
                    collected.append(
                        CommunityPost(
                            source=post.source,
                            source_name=post.source_name,
                            title=post.title,
                            summary=post.summary,
                            url=post.url,
                            published_at=post.published_at,
                            keyword=keyword,
                            author=post.author,
                            views=post.views,
                            recommends=post.recommends,
                            comments=post.comments,
                            weight=post.weight,
                            collected_at=post.collected_at,
                            article_group=post.article_group,
                            article_id=post.article_id,
                        )
                    )
        return collected


def _matches_board_url(source: str, url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    query = parse_qs(parsed.query)
    if source == "ppomppu":
        return (
            "ppomppu.co.kr" in host
            and path.endswith("/zboard/view.php")
            and bool(query.get("id"))
            and parse_int(_first_query_value(query, "no")) is not None
        )
    if source == "fmkorea":
        return "fmkorea.com" in host and path.strip("/").isdigit()
    if source == "coinpan":
        parts = [part for part in path.split("/") if part]
        return (
            "coinpan.com" in host
            and len(parts) >= 2
            and parts[0] in {"free", "coin_info", "pnl"}
            and parts[1].isdigit()
        )
    if source == "mlbpark":
        return (
            "mlbpark.donga.com" in host
            and path.endswith("/mp/b.php")
            and _first_query_value(query, "b") == "bullpen"
            and _first_query_value(query, "m") == "view"
            and parse_int(_first_query_value(query, "id")) is not None
        )
    return False


def _is_naver_finance_post_url(url: str) -> bool:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return (
        "finance.naver.com" in parsed.netloc.lower()
        and parsed.path.endswith("/item/board_read.naver")
        and _first_query_value(query, "code") is not None
        and parse_int(_first_query_value(query, "nid")) is not None
    )


def _absolute_url(href: str, *, base_url: str) -> str:
    if href.startswith("//"):
        return f"https:{href}"
    return urljoin(base_url, href)


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _referer_for(url_template: str) -> str:
    parsed = urlparse(url_template.format(page=1))
    return f"{parsed.scheme}://{parsed.netloc}/"


def _matched_keyword(post: CommunityPost, keywords: tuple[str, ...]) -> str | None:
    text = f"{post.title} {post.summary}".lower()
    for keyword in keywords:
        if keyword.lower() in text:
            return keyword
    return None


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split())


def _is_noise_title(title: str) -> bool:
    return title.startswith(("공지", "AD", "[공지]")) or title in {
        "전체",
        "이전",
        "다음",
        "로그인",
        "회원가입",
    }
