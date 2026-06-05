import unittest

from sentiment_index.community_sources import CommunityLinkParser, NaverFinanceBoardParser
from sentiment_index.config import CommunityBoard, NaverFinanceStock


class CommunitySourceParserTest(unittest.TestCase):
    def test_parse_naver_finance_board_row(self) -> None:
        parser = NaverFinanceBoardParser(NaverFinanceStock("삼성전자", "005930", 1.0))
        parser.feed(
            """
            <td class="title">
              <a href="/item/board_read.naver?code=005930&nid=123456&page=1">
                삼성전자 풀매수 가나요
              </a>
            </td>
            """
        )

        self.assertEqual(len(parser.posts), 1)
        post = parser.posts[0]
        self.assertEqual(post.source, "naver_finance")
        self.assertEqual(post.source_name, "네이버 종토방 삼성전자")
        self.assertEqual(post.title, "삼성전자 풀매수 가나요")
        self.assertEqual(post.article_group, "naver_finance:005930")
        self.assertEqual(post.article_id, 123456)

    def test_parse_ppomppu_stock_row(self) -> None:
        parser = CommunityLinkParser(
            CommunityBoard(
                "뽐뿌 증권포럼",
                "ppomppu",
                "https://www.ppomppu.co.kr/zboard/zboard.php?id=stock&page={page}",
                0.8,
                False,
            )
        )
        parser.feed(
            """
            <a class="baseList-title" href="view.php?id=stock&page=1&no=370118">
              코스피 반등한다고 보시나요
            </a>
            """
        )

        self.assertEqual(len(parser.posts), 1)
        post = parser.posts[0]
        self.assertEqual(post.source, "ppomppu")
        self.assertEqual(post.article_group, "ppomppu:stock")
        self.assertEqual(post.article_id, 370118)

    def test_parse_fmkorea_stock_row(self) -> None:
        parser = CommunityLinkParser(
            CommunityBoard(
                "FM코리아 주식",
                "fmkorea",
                "https://www.fmkorea.com/index.php?mid=stock&page={page}",
                0.7,
                False,
            )
        )
        parser.feed('<a href="/9917012373">오늘 인버스 외인 기관 다 풀매수네</a>')

        self.assertEqual(len(parser.posts), 1)
        post = parser.posts[0]
        self.assertEqual(post.source, "fmkorea")
        self.assertEqual(post.article_group, "fmkorea:FM코리아 주식")
        self.assertEqual(post.article_id, 9917012373)

    def test_parse_coinpan_row(self) -> None:
        parser = CommunityLinkParser(
            CommunityBoard(
                "코인판 자유게시판",
                "coinpan",
                "https://coinpan.com/free?page={page}",
                0.9,
                False,
            )
        )
        parser.feed('<a href="/free/469856522#comment_1">비트코인 조정 끝난거 같나요</a>')

        self.assertEqual(len(parser.posts), 1)
        post = parser.posts[0]
        self.assertEqual(post.url, "https://coinpan.com/free/469856522")
        self.assertEqual(post.article_group, "coinpan:free")
        self.assertEqual(post.article_id, 469856522)

    def test_parse_mlbpark_bullpen_row(self) -> None:
        parser = CommunityLinkParser(
            CommunityBoard(
                "MLB파크 불펜",
                "mlbpark",
                "https://mlbpark.donga.com/mp/b.php?b=bullpen&m=list&p={page}",
                0.6,
                True,
            )
        )
        parser.feed(
            """
            <div class="title">
              <a href="https://mlbpark.donga.com/mp/b.php?b=bullpen&id=202606050115924310&m=view">
                비트코인 아직 들고 계신가요
              </a>
            </div>
            """
        )

        self.assertEqual(len(parser.posts), 1)
        post = parser.posts[0]
        self.assertEqual(post.source, "mlbpark")
        self.assertEqual(post.article_group, "mlbpark:bullpen")
        self.assertEqual(post.article_id, 202606050115924310)


if __name__ == "__main__":
    unittest.main()
