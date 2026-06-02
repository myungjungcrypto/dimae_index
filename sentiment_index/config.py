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
    cafe_pages_per_keyword: int = 2
    dc_pages_per_gallery: int = 2


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
