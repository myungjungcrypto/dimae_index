from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "sentiment_index.sqlite3"


@dataclass(frozen=True)
class NaverConfig:
    client_id_env: str = "NAVER_CLIENT_ID"
    client_secret_env: str = "NAVER_CLIENT_SECRET"
    cafe_search_url: str = "https://openapi.naver.com/v1/search/cafearticle.json"
    datalab_url: str = "https://openapi.naver.com/v1/datalab/search"
    ages_30_40_male: tuple[str, ...] = ("5", "6", "7", "8")
    gender_male: str = "m"


@dataclass(frozen=True)
class CafeTarget:
    name: str
    url_fragment: str
    weight: float = 1.0


@dataclass(frozen=True)
class DcGallery:
    name: str
    gallery_id: str
    weight: float = 0.7


@dataclass(frozen=True)
class BobaedreamBoard:
    name: str
    code: str
    weight: float = 0.8


@dataclass(frozen=True)
class NaverFinanceStock:
    name: str
    code: str
    weight: float = 0.9


@dataclass(frozen=True)
class CommunityBoard:
    name: str
    source: str
    url_template: str
    weight: float = 0.8
    keyword_filter: bool = False


@dataclass(frozen=True)
class PipelineConfig:
    db_path: Path = DEFAULT_DB_PATH
    keywords: tuple[str, ...] = (
        "코인",
        "비트코인",
        "이더리움",
        "리플",
        "솔라나",
        "알트코인",
        "업비트",
        "빗썸",
        "김프",
        "롱",
        "숏",
        "청산",
        "주식",
        "국장",
        "미장",
        "코스피",
        "코스닥",
        "나스닥",
        "엔비디아",
        "테슬라",
        "삼성전자",
        "하이닉스",
        "SK하이닉스",
        "반도체",
        "2차전지",
    )
    target_cafes: tuple[CafeTarget, ...] = (
        CafeTarget("디젤매니아", "cafe.naver.com/dieselmania", 1.2),
        CafeTarget("나이키매니아", "cafe.naver.com/nikemania", 0.8),
    )
    dc_galleries: tuple[DcGallery, ...] = (
        DcGallery("디시 비트코인 갤러리", "bitcoins_new1", 0.7),
        DcGallery("디시 주식 갤러리", "neostock", 0.6),
    )
    bobaedream_boards: tuple[BobaedreamBoard, ...] = (
        BobaedreamBoard("보배드림 자유게시판", "freeb", 0.7),
        BobaedreamBoard("보배드림 베스트글", "best", 1.0),
    )
    naver_finance_stocks: tuple[NaverFinanceStock, ...] = (
        NaverFinanceStock("삼성전자", "005930", 1.0),
        NaverFinanceStock("SK하이닉스", "000660", 1.0),
        NaverFinanceStock("NAVER", "035420", 0.8),
        NaverFinanceStock("카카오", "035720", 0.8),
        NaverFinanceStock("현대차", "005380", 0.8),
        NaverFinanceStock("두산에너빌리티", "034020", 0.8),
        NaverFinanceStock("한화오션", "042660", 0.8),
        NaverFinanceStock("에코프로", "086520", 0.8),
        NaverFinanceStock("에코프로비엠", "247540", 0.8),
        NaverFinanceStock("HLB", "028300", 0.8),
    )
    community_boards: tuple[CommunityBoard, ...] = (
        CommunityBoard(
            "뽐뿌 증권포럼",
            "ppomppu",
            "https://www.ppomppu.co.kr/zboard/zboard.php?id=stock&page={page}",
            0.8,
            False,
        ),
        CommunityBoard(
            "FM코리아 주식",
            "fmkorea",
            "https://www.fmkorea.com/index.php?mid=stock&sort_index=regdate&order_type=desc&page={page}",
            0.7,
            False,
        ),
        CommunityBoard(
            "FM코리아 코인",
            "fmkorea",
            "https://www.fmkorea.com/index.php?mid=coin&sort_index=regdate&order_type=desc&page={page}",
            0.7,
            False,
        ),
        CommunityBoard(
            "코인판 자유게시판",
            "coinpan",
            "https://coinpan.com/free?page={page}",
            0.9,
            False,
        ),
        CommunityBoard(
            "코인판 코인정보",
            "coinpan",
            "https://coinpan.com/coin_info?page={page}",
            0.9,
            False,
        ),
        CommunityBoard(
            "MLB파크 불펜",
            "mlbpark",
            "https://mlbpark.donga.com/mp/b.php?b=bullpen&m=list&p={page}",
            0.6,
            True,
        ),
    )
    cafe_pages_per_keyword: int = 2
    dc_pages_per_gallery: int = 2
    bobaedream_pages_per_board: int = 2
    naver_finance_pages_per_stock: int = 1
    community_pages_per_board: int = 1


@dataclass(frozen=True)
class Lexicon:
    positive: tuple[str, ...] = (
        "가즈아",
        "불장",
        "떡상",
        "신고가",
        "수익",
        "익절",
        "상승",
        "반등",
        "매수",
        "대박",
        "쏜다",
        "풀롱",
    )
    negative: tuple[str, ...] = (
        "손절",
        "물렸다",
        "물림",
        "폭락",
        "떡락",
        "하락",
        "청산",
        "망했다",
        "상폐",
        "개박살",
        "마이너스",
        "구조대",
    )
    fomo: tuple[str, ...] = (
        "몰빵",
        "영끌",
        "풀매수",
        "풀롱",
        "풀숏",
        "레버리지",
        "배율",
        "인생역전",
        "지금이라도",
        "안사면",
        "놓쳤다",
        "탑승",
        "추격매수",
    )
    fear: tuple[str, ...] = (
        "공포",
        "패닉",
        "도망",
        "위험",
        "불안",
        "무섭다",
        "끝났다",
        "한강",
    )
    distrust: tuple[str, ...] = (
        "조작",
        "설거지",
        "먹튀",
        "출금정지",
        "해킹",
        "사기",
        "스캠",
        "거래소",
        "세력",
        "김프",
    )
    spam: tuple[str, ...] = (
        "무료방",
        "리딩방",
        "텔레그램",
        "카톡방",
        "광고",
        "가입코드",
        "추천인",
        "19",
        "ㅎㅂ",
        "후방",
    )


DEFAULT_CONFIG = PipelineConfig()
DEFAULT_LEXICON = Lexicon()
