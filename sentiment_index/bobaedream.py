from __future__ import annotations

from collections.abc import Iterable
from html import unescape
from html.parser import HTMLParser

from .config import BobaedreamBoard
from .dcinside import parse_int
from .http import request_text
from .models import CommunityPost


class BobaedreamListParser(HTMLParser):
    def __init__(self, board: BobaedreamBoard) -> None:
        super().__init__()
        self.board = board
        self.posts: list[CommunityPost] = []
        self._row: dict[str, str] | None = None
        self._field: str | None = None
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "tr" and attr.get("itemscope") is not None:
            self._row = {}
            self._title_parts = []
            return
        if self._row is None:
            return

        class_name = attr.get("class", "")
        if tag == "td":
            if "num01" in class_name:
                self._field = "num"
            elif "pl14" in class_name:
                self._field = "title"
            elif "author02" in class_name:
                self._field = "author"
            elif "date" in class_name:
                self._field = "published_at"
            elif "recomm" in class_name:
                self._field = "recommends"
            elif "count" in class_name:
                self._field = "views"
            return

        if tag == "a" and self._field == "title" and "bsubject" in class_name:
            href = attr.get("href")
            if href:
                self._row["url"] = _absolute_url(href)
            if attr.get("title"):
                self._row["title"] = unescape(attr["title"]).strip()

        if tag == "span" and self._field == "author" and "author" in class_name and attr.get("title"):
            self._row["author"] = unescape(attr["title"]).strip()

    def handle_data(self, data: str) -> None:
        if self._row is None or self._field is None:
            return
        text = " ".join(unescape(data).split())
        if not text:
            return
        if self._field == "title":
            self._title_parts.append(text)
            return
        if self._field == "author" and self._row.get("author"):
            return
        existing = self._row.get(self._field, "")
        self._row[self._field] = f"{existing} {text}".strip()

    def handle_endtag(self, tag: str) -> None:
        if self._row is None:
            return
        if tag == "td":
            self._field = None
            return
        if tag != "tr":
            return

        title = self._row.get("title") or " ".join(self._title_parts).strip()
        url = self._row.get("url", "")
        if title and url:
            self.posts.append(
                CommunityPost(
                    source="bobaedream",
                    source_name=self.board.name,
                    title=title,
                    summary="",
                    url=url,
                    published_at=self._row.get("published_at"),
                    author=self._row.get("author"),
                    views=parse_int(self._row.get("views")),
                    recommends=parse_int(self._row.get("recommends")),
                    weight=self.board.weight,
                ).normalized()
            )
        self._row = None
        self._field = None
        self._title_parts = []


class BobaedreamClient:
    list_url = "https://www.bobaedream.co.kr/list"

    def fetch_board_page(self, board: BobaedreamBoard, *, page: int = 1) -> list[CommunityPost]:
        html = request_text(
            self.list_url,
            query={"code": board.code, "page": page},
            headers={"Referer": "https://www.bobaedream.co.kr/"},
        )
        parser = BobaedreamListParser(board)
        parser.feed(html)
        return parser.posts

    def collect_board_posts(
        self,
        boards: Iterable[BobaedreamBoard],
        *,
        pages_per_board: int = 2,
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
                    if keyword_tuple and not self._matches_keyword(post, keyword_tuple):
                        continue
                    seen.add(post.url)
                    collected.append(post)
        return collected

    @staticmethod
    def _matches_keyword(post: CommunityPost, keywords: tuple[str, ...]) -> bool:
        text = f"{post.title} {post.summary}"
        return any(keyword.lower() in text.lower() for keyword in keywords)


def _absolute_url(href: str) -> str:
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"https://www.bobaedream.co.kr{href}"
    return href
