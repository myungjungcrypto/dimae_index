import unittest

from sentiment_index.bobaedream import BobaedreamListParser
from sentiment_index.config import BobaedreamBoard


class BobaedreamParserTest(unittest.TestCase):
    def test_parse_list_row(self) -> None:
        parser = BobaedreamListParser(BobaedreamBoard("보배드림 자유게시판", "freeb", 0.7))
        parser.feed(
            """
            <tr itemscope itemtype="http://schema.org/Article">
              <td class="num01">1940538</td>
              <td class="pl14">
                <a class="bsubject" href="/view?code=freeb&No=3406866&bm=1"
                   title="삼성전자 주식 다시 봐야 하나" itemprop="name">삼성전자 주식 다시 봐야 하나</a>
              </td>
              <td class="author02"><span class="author" title="tester">tester</span></td>
              <td class="date">06/02</td>
              <td class="recomm"><font>8</font></td>
              <td class="count">468</td>
            </tr>
            """
        )

        self.assertEqual(len(parser.posts), 1)
        post = parser.posts[0]
        self.assertEqual(post.source, "bobaedream")
        self.assertEqual(post.source_name, "보배드림 자유게시판")
        self.assertEqual(post.title, "삼성전자 주식 다시 봐야 하나")
        self.assertEqual(post.url, "https://www.bobaedream.co.kr/view?code=freeb&No=3406866&bm=1")
        self.assertEqual(post.author, "tester")
        self.assertEqual(post.recommends, 8)
        self.assertEqual(post.views, 468)
        self.assertEqual(post.article_group, "bobaedream:freeb")
        self.assertEqual(post.article_id, 3406866)


if __name__ == "__main__":
    unittest.main()
