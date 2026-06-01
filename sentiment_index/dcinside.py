from __future__ import annotations

from collections.abc import Iterable
from html.parser import HTMLParser

from .config import DcGallery
from .http import request_text
from .models import CommunityPost


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


class DcListParser(HTMLParser):
    def __init__(self, gallery: DcGallery) -> None:
        super().__init__()
        self.gallery = gallery
        self.posts: list[CommunityPost] = []
        self._row: dict[str, str] | None = None
        self._field: str | None = None
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        class_name = attr.get("class", "")
        if tag == "tr" and "ub-content" in class_name and attr.get("data-no"):
            self._row = {"no": attr.get("data-no", "")}
            self._title_parts = []
            return
        if self._row is None:
            return

        if tag == "td":
            if "gall_num" in class_name:
                self._field = "num"
            elif "gall_tit" in class_name:
                self._field = "title"
            elif "gall_writer" in class_name:
                self._field = "author"
            elif "gall_date" in class_name:
                self._field = "published_at"
                if attr.get("title"):
                    self._row["published_at"] = attr["title"]
            elif "gall_count" in class_name:
                self._field = "views"
            elif "gall_recommend" in class_name:
                self._field = "recommends"

        if tag == "a" and self._field == "title" and attr.get("href"):
            href = attr["href"]
            if href.startswith("/"):
                href = "https://gall.dcinside.com" + href
            self._row["url"] = href

    def handle_data(self, data: str) -> None:
        if self._row is None or self._field is None:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._field == "title":
            self._title_parts.append(text)
        else:
            existing = self._row.get(self._field, "")
            self._row[self._field] = f"{existing} {text}".strip()

    def handle_endtag(self, tag: str) -> None:
        if self._row is None:
            return
        if tag == "td":
            self._field = None
        if tag == "tr":
            title = " ".join(self._title_parts).strip()
            url = self._row.get("url", "")
            row_number = self._row.get("num", "")
            is_normal_post = row_number.isdigit()
            if title and url and is_normal_post and not title.startswith(("공지", "AD")):
                self.posts.append(
                    CommunityPost(
                        source="dcinside",
                        source_name=self.gallery.name,
                        title=title,
                        summary="",
                        url=url,
                        published_at=self._row.get("published_at"),
                        author=self._row.get("author"),
                        views=parse_int(self._row.get("views")),
                        recommends=parse_int(self._row.get("recommends")),
                        weight=self.gallery.weight,
                    ).normalized()
                )
            self._row = None
            self._field = None
            self._title_parts = []


class DcinsideClient:
    list_url = "https://gall.dcinside.com/board/lists/"

    def fetch_gallery_page(self, gallery: DcGallery, *, page: int = 1) -> list[CommunityPost]:
        html = request_text(
            self.list_url,
            query={"id": gallery.gallery_id, "page": page},
            headers={"Referer": "https://gall.dcinside.com/"},
        )
        parser = DcListParser(gallery)
        parser.feed(html)
        return parser.posts

    def collect_gallery_posts(
        self,
        galleries: Iterable[DcGallery],
        *,
        pages_per_gallery: int = 2,
        keywords: Iterable[str] = (),
    ) -> list[CommunityPost]:
        keyword_tuple = tuple(keywords)
        seen: set[str] = set()
        collected: list[CommunityPost] = []
        for gallery in galleries:
            for page in range(1, max(pages_per_gallery, 1) + 1):
                for post in self.fetch_gallery_page(gallery, page=page):
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
