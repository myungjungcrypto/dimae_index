# Dimaejipyo Community Sentiment Index

디젤매니아와 30~40대 남성 이용자가 많다고 가정한 공개 커뮤니티에서 코인/주식 관련 언급을 모아 대중 심리 지표를 만드는 MVP입니다.

## 현재 구현 범위

- 네이버 카페글 검색 API: 디젤매니아/나이키매니아 공개 카페글 후보 수집
- 네이버 데이터랩 API: 남성 30~49세 검색 트렌드 수집
- 디시인사이드 공개 게시판: 비트코인/주식 갤러리 목록 수집
- SQLite 저장
- 사전 기반 감성 점수화
- 처음 발견/마지막 발견 날짜 추적
- 일별 스냅샷 저장 후 변화 기반 0~100 커뮤니티 심리 지수 산출
- API 키 없이도 샘플 데이터로 산식 검증 가능

## 빠른 시작

```bash
python3 -m sentiment_index.cli init-db
python3 -m sentiment_index.cli seed-sample
python3 -m sentiment_index.cli report --markdown
```

기본 DB는 `data/sentiment_index.sqlite3`에 생성됩니다.

## 네이버 API 설정

`.env.example`을 참고해서 `.env`를 만듭니다.

```bash
# 네이버 로그인 아이디/비밀번호가 아닙니다.
# 네이버 개발자센터에서 발급하는 Open API 애플리케이션 키입니다.
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret
```

그 다음 전체 파이프라인을 실행합니다.

```bash
python3 -m sentiment_index.cli run
```

네이버 키가 없으면 네이버 수집은 건너뛰고, 디시 공개 게시판 수집만 시도합니다.

처음 키가 잘 되는지만 빠르게 확인하려면:

```bash
python3 -m sentiment_index.cli collect --no-dcinside --quick --verbose --strict
python3 -m sentiment_index.cli score
python3 -m sentiment_index.cli report --markdown
```

네이버를 완전히 빼고 실행하려면:

```bash
python3 -m sentiment_index.cli collect --no-naver
python3 -m sentiment_index.cli score
python3 -m sentiment_index.cli report
```

보안상 네이버 개인 계정에 연결되는 API 앱을 만들기 싫다면, 네이버 없이 공개 커뮤니티 소스만으로 지표를 만들 수 있습니다. 다만 이 경우 남성 30~49세 필터는 네이버 데이터랩만큼 정확하게 잡기 어렵고, 커뮤니티별 가중치로 근사해야 합니다.

## 명령어

```bash
python3 -m sentiment_index.cli init-db
python3 -m sentiment_index.cli collect
python3 -m sentiment_index.cli score
python3 -m sentiment_index.cli report
python3 -m sentiment_index.cli report --markdown
python3 -m sentiment_index.cli run
```

네트워크 수집 없이 구조만 확인하려면:

```bash
python3 -m sentiment_index.cli seed-sample
```

로컬 대시보드를 보려면:

```bash
python3 -m sentiment_index.cli dashboard
```

브라우저에서 `http://127.0.0.1:8765`를 엽니다.

하루 2회 자동 갱신 프로세스를 켜려면:

```bash
python3 -m sentiment_index.cli schedule --times 09:00,21:00 --verbose
```

이 명령은 계속 실행되는 프로세스입니다. AWS에서는 `systemd`, `supervisor`, `tmux` 같은 프로세스 매니저로 켜두는 방식이 좋습니다.

매시간 갱신하려면:

```bash
python3 -m sentiment_index.cli schedule --hourly --verbose
```

EC2/PM2 배포는 [docs/EC2_DEPLOY.md](docs/EC2_DEPLOY.md)를 참고합니다.

데이터랩으로 30일 추정 기준선을 먼저 만들려면:

```bash
python3 -m sentiment_index.cli backfill-datalab --days 30
```

## 지표 해석

- `index_score`: 기준선 대비 언급량, FOMO, 리스크, 검색 모멘텀을 합친 0~100 점수
- `attention_score`: 글 수 기반 관심도
- `new_post_count`: 해당 날짜에 처음 발견된 글 수
- `baseline_days`: 과거 일별 스냅샷 기준선 수
- `mention_change_pct`: 과거 기준선 대비 신규 언급량 변화율
- `sentiment`: 긍정/부정 키워드 균형, -1~1
- `fomo_score`: 몰빵, 영끌, 신고가 추격 같은 과열 언어 비중
- `fomo_change_pct`: 과거 기준선 대비 FOMO 비중 변화율
- `risk_score`: 공포, 불신, 스캠, 출금정지 등 리스크 언어 비중
- `risk_change_pct`: 과거 기준선 대비 리스크 비중 변화율
- `trend_momentum`: 네이버 데이터랩 남성 30~49세 검색량의 최근 모멘텀
- `spam_rate`: 광고/성인/리딩방 신호가 있는 글 비율

최종 `index_score`는 0~100입니다.

- 기준선이 3일 미만이면: `baseline_building`
- 75 이상: `euphoria`
- 60~75: `risk_on`
- 42~60: `neutral`
- 30~42: `risk_off`
- 30 이하: `panic`

보조 임계값:

- `mention_change_pct`: +50% 관심 증가, +100% 급증, -40% 관심 둔화
- `fomo_score`: 2% 이상 주의, 5% 이상 과열 후보
- `fomo_change_pct`: +100% 주의, +250% 급증. 단, 원점수가 1% 미만이면 약한 신호로 봅니다.
- `risk_score`: 5% 이상 스트레스, 10% 이상 고위험 후보
- `risk_change_pct`: +100% 주의, +250% 급증
- `trend_momentum`: ±25% 이상이면 검색 관심 변화
- `spam_rate`: 10% 이상 노이즈 주의, 20% 이상 지표 신뢰도 낮음

## 운영 메모

- 개인 닉네임이나 원문 본문 전체는 저장하지 않고, 제목/요약/공개 URL 중심으로 저장합니다.
- 네이버 카페는 공개 게시글만 API에 노출됩니다.
- 디시인사이드는 광고와 낚시성 글이 많으므로 기본 가중치를 낮게 둡니다.
- 감성 분석은 아직 사전 기반입니다. 실제 매매 지표로 쓰려면 최소 2~4주 데이터를 모아 가격/거래량과 상관 검증을 해야 합니다.
- 첫 며칠은 `baseline_building`으로 보는 것이 정상입니다. 매일 같은 시간에 수집해야 언급량/FOMO 변화율이 의미를 갖습니다.
- 네이버 카페글 검색 API는 카페글의 원 작성일을 안정적으로 제공하지 않으므로, 과거 커뮤니티 글 수를 완벽히 복원하지는 못합니다. `backfill-datalab`은 네이버 데이터랩의 30일 검색 추이로 만든 추정 기준선이며, 관측 기준선이 쌓이면 관측값이 더 중요합니다.
