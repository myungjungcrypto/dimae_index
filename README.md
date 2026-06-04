# Dimaejipyo Community Sentiment Index

디젤매니아와 30~40대 남성 이용자가 많다고 가정한 공개 커뮤니티에서 코인/주식 관련 언급을 모아 대중 심리 지표를 만드는 MVP입니다.

## 프로젝트 목표

이 프로젝트의 최종 목표는 커뮤니티 심리 지표가 실제 시장 움직임을 설명하거나 선행하는지 검증하는 것입니다.

수집한 `index_score`, `new_post_count`, `mention_change_pct`, Greed 지표(`fomo_score`, `fomo_change_pct`), Fear 지표(`risk_score`, `risk_change_pct`), `trend_momentum`을 나스닥 지수, 코인 지수, 코스피 지수와 함께 백테스트해서 의미 있는 파라미터를 도출합니다.

검증 대상 예시는 다음과 같습니다.

- 나스닥 지수: 미국 성장주/위험자산 심리와 커뮤니티 위험 선호의 관계
- 코인 지수: 비트코인 또는 전체 코인 시장과 Greed/Fear 신호의 관계
- 코스피 지수: 국내 주식 관심도와 국장/반도체/2차전지 키워드 반응

백테스트의 목표는 매매 신호를 바로 확정하는 것이 아니라, 어떤 심리 지표가 어떤 시장에서 유의미한지 확인하고 임계값, 관찰 기간, 지연 효과를 찾는 것입니다.

## 현재 구현 범위

- 네이버 카페글 검색 API: 디젤매니아/나이키매니아 공개 카페글 후보 수집
- 네이버 데이터랩 API: 남성 30~49세 검색 트렌드 수집
- 디시인사이드 공개 게시판: 비트코인/주식 갤러리 목록 수집
- 보배드림 공개 게시판: 자유게시판/베스트글 목록 수집
- SQLite 저장
- 사전 기반 감성 점수화
- 처음 발견/마지막 발견 날짜 추적
- 네이버 카페 글번호 파싱 후 카페별 이전 최고 글번호보다 큰 URL을 신규 포착으로 판정
- 최근 24시간 롤링 지수와 과거 기준선 분위수 기반 0~100 커뮤니티 심리 지수 산출
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

대시보드의 `Settings`에서 검색 키워드와 Greed 사전을 추가/삭제할 수 있습니다. 변경값은 `data/settings.json`에 저장됩니다.

- 검색 키워드 변경: 다음 수집부터 적용
- Greed 사전 변경: 저장 즉시 기존 글을 재점수화

하루 2회 자동 갱신 프로세스를 켜려면:

```bash
python3 -m sentiment_index.cli schedule --times 09:00,21:00 --timezone Asia/Seoul --verbose
```

이 명령은 계속 실행되는 프로세스입니다. AWS에서는 `systemd`, `supervisor`, `tmux` 같은 프로세스 매니저로 켜두는 방식이 좋습니다.

매시간 갱신하려면:

```bash
python3 -m sentiment_index.cli schedule --hourly --timezone Asia/Seoul --include-dcinside --verbose
```

EC2/PM2 배포는 [docs/EC2_DEPLOY.md](docs/EC2_DEPLOY.md)를 참고합니다.

데이터랩으로 30일 추정 기준선을 먼저 만들려면:

```bash
python3 -m sentiment_index.cli backfill-datalab --days 30
```

데이터랩 1년치와 가격 일봉으로 큰 상관관계를 먼저 보려면:

```bash
python3 -m sentiment_index.cli backtest-datalab --days 365 --top 30 --output data/backtests/datalab_price_1y.md
```

이 명령은 네이버 데이터랩 남성 30~49세 일별 검색 트렌드와 코스피/나스닥/비트코인 일봉을 저장한 뒤, 데이터랩 신호와 당일/다음 1일/3일/7일 수익률의 단순 상관관계를 Markdown으로 출력합니다.

## 지표 해석

화면 구조는 CoinMarketCap의 Fear & Greed Index처럼 현재 점수, Historical Values, Yearly High/Low를 먼저 보여주는 형태를 따릅니다. 다만 입력 데이터는 가격/거래량/변동성이 아니라 커뮤니티 글, Greed/Fear 사전, 검색 모멘텀, 소스별 가중치입니다.

- 대시보드 상단의 큰 숫자는 최근 24시간 롤링 점수입니다. 자정에 리셋되지 않고 한 시간씩 밀려가며 계산합니다.
- 점수의 높고 낮음은 최근 24시간 값 자체가 아니라, 과거 `daily_snapshots` 기준선 분포에서 어느 분위수인지로 판단합니다. 기본 비교 범위는 최대 90일입니다.
- `hourly_snapshots`는 매시간 수집 직후의 최근 24시간 지표를 보존합니다. 시간 단위 백테스트에서는 이 테이블을 사용해서 “그 시간에 실제로 보였던 신호”를 기준으로 검증합니다.
- `daily_snapshots`는 매일 KST 00시대에 방금 끝난 전날 24시간 롤링 점수를 하루 대표값으로 저장합니다. 일별 백테스트에서는 이 테이블을 사용합니다.
- `Source Breakdown`은 최근 24시간 기준 소스별 글 수, 신규 글 수, 가중 글 수, Greed/Fear/Spam 비율을 보여줍니다. 특정 커뮤니티 하나가 지표를 과하게 움직이는지 확인할 때 봅니다.
- `index_score`: 최근 24시간의 언급량, Greed, Fear, 검색 모멘텀을 과거 분포 분위수로 정규화한 0~100 점수
- `attention_score`: 글 수 기반 관심도
- `new_post_count`: 최근 24시간 안에 처음 포착됐고, 글번호가 이전 최고값보다 큰 글 수
- `baseline_days`: 과거 일별 스냅샷 기준선 수
- `mention_change_pct`: 과거 기준선 대비 신규 언급량 변화율
- `sentiment`: 긍정/부정 키워드 균형, -1~1
- `fomo_score`: 화면에서는 Greed로 표시합니다. 몰빵, 영끌, 신고가 추격 같은 탐욕/추격매수 언어 비중입니다.
- `fomo_change_pct`: 과거 기준선 대비 Greed 비중 변화율
- `risk_score`: 화면에서는 Fear로 표시합니다. 공포, 불신, 스캠, 출금정지 등 공포 언어 비중입니다.
- `risk_change_pct`: 과거 기준선 대비 Fear 비중 변화율
- `trend_momentum`: 네이버 데이터랩 남성 30~49세 검색량의 최근 모멘텀
- `spam_rate`: 광고/성인/리딩방 신호가 있는 글 비율

최종 `index_score`는 0~100입니다. 100은 절대적인 완전 과열이 아니라, 기준선 기간 안에서 여러 구성요소가 거의 최상위권이라는 뜻입니다. 0도 절대적인 공포가 아니라, 기준선 기간 안에서 거의 최하위권이라는 뜻입니다.

- 기준선이 14일 미만이면: `calibrating`
- 80 이상: `euphoria`
- 65~80: `risk_on`
- 35~65: `neutral`
- 20~35: `risk_off`
- 20 이하: `panic`

현재 합성 점수 가중치는 다음과 같습니다.

- 신규 가중 언급량 분위수: 30%
- Greed 원점수 분위수: 25%
- 긍정/부정 sentiment 분위수: 15%
- 검색 모멘텀 분위수: 10%
- Fear 원점수 역분위수: 15%
- Spam rate 역분위수: 5%

보조 임계값:

- `mention_change_pct`: +50% 관심 증가, +100% 급증, -40% 관심 둔화
- Greed(`fomo_score`): 2% 이상 주의, 5% 이상 과열 후보
- Greed 변화율(`fomo_change_pct`): +100% 주의, +250% 급증. 단, 원점수가 1% 미만이면 약한 신호로 봅니다.
- Fear(`risk_score`): 5% 이상 스트레스, 10% 이상 고위험 후보
- Fear 변화율(`risk_change_pct`): +100% 주의, +250% 급증
- `trend_momentum`: ±25% 이상이면 검색 관심 변화
- `spam_rate`: 10% 이상 노이즈 주의, 20% 이상 지표 신뢰도 낮음

## 백테스트 로드맵

1. 시장 데이터 수집
   - 나스닥 지수 또는 QQQ/NQ proxy
   - 비트코인 또는 코인 시가총액/지수 proxy
   - 코스피 지수 또는 KOSPI ETF proxy

2. 시간축 정렬
   - 큰 흐름 검증은 KST 기준 `daily_snapshots`의 하루 대표 롤링 점수 사용
   - 시간 단위 신호 검증은 KST 기준 `hourly_snapshots`의 매시간 롤링 점수 사용
   - 미국 시장 데이터는 장 마감 기준 날짜를 KST와 매칭
   - 코인은 24시간 시장이므로 UTC/KST 기준을 명시해서 고정
   - 과거 1년 탐색은 `backtest-datalab`으로 데이터랩 proxy와 가격 일봉을 먼저 비교

3. 후보 파라미터
   - `index_score` 절대값: 예 65 이상 risk_on, 80 이상 euphoria
   - `mention_change_pct`: 관심 급증/둔화 임계값
   - Greed(`fomo_score`, `fomo_change_pct`): 과열 후보
   - Fear(`risk_score`, `risk_change_pct`): 위험 회피/패닉 후보
   - 관찰 기간: 1일, 3일, 7일 이동 평균
   - 지연 효과: 신호 발생 당일, 다음날, 3일 뒤 수익률

4. 검증 항목
   - 신호 이후 1일/3일/7일 수익률
   - 신호 이후 최대 낙폭
   - hit rate, average return, Sharpe-like score
   - 단순 buy-and-hold 대비 초과 성과
   - 신호 빈도가 너무 낮은 파라미터 제외

5. 운영 원칙
   - 검색어 변경은 변경 시점 이후 데이터부터 반영합니다.
   - Greed/Fear 사전 변경은 기존 저장 글의 점수를 재계산할 수 있으므로 변경 이력을 기록하는 것이 좋습니다.
   - 최소 2~4주 이상 관측 데이터가 쌓인 뒤 백테스트 결과를 신뢰합니다.
   - 과최적화를 피하기 위해 in-sample/out-of-sample 구간을 나눕니다.
   - 데이터랩 백테스트는 과거 proxy 탐색용이고, 실제 커뮤니티 지표의 검증은 앞으로 쌓이는 `daily_snapshots`/`hourly_snapshots`로 별도 수행합니다.
   - 앞으로 쌓이는 실제 커뮤니티 지표는 매주 1회 백테스트를 진행하고, 주차별 결과를 `data/backtests/` 아래에 기록합니다.
   - 주간 백테스트에서는 직전 주에 새로 쌓인 `daily_snapshots`/`hourly_snapshots`와 코스피/나스닥/비트코인 수익률을 비교합니다.

## 데이터랩 가격 백테스트

`backtest-datalab`은 과거 커뮤니티 원문을 완벽히 복원할 수 없는 문제를 우회하기 위한 탐색 도구입니다.

- 데이터랩 신호: `crypto`, `stocks`, `fomo`(Greed), `risk`(Fear)
- 신호 형태: 원점수 `*_level`, 7일 평균 모멘텀 `*_momentum_7d`
- 가격 데이터:
  - 비트코인: Binance `BTCUSDT` 일봉
  - 나스닥: Yahoo chart `^IXIC` 일봉
  - 코스피: 네이버 금융 `KOSPI` 일별 시세
- 비교 수익률: 당일, 다음 1일, 3일, 7일
- `High Signal Avg Return`: 해당 신호가 상위 20%였던 날의 평균 수익률

이 결과는 “어떤 검색 심리 proxy가 어떤 시장과 관계가 있는지”를 보는 1차 필터입니다. 유의미해 보이는 신호만 이후 실제 커뮤니티 관측 지표와 비교합니다.

## 수집 소스

현재 기본 소스는 역할을 나눠서 봅니다.

- 디젤매니아: 30~40대 남성 소비/투자 관심 커뮤니티. 기본 가중치 `1.2`
- 나이키매니아: 소비재/리셀 성향이 섞인 남성 커뮤니티. 기본 가중치 `0.8`
- 보배드림 자유게시판: 30~50대 남성 일반 대중 심리 보완 표본. 기본 가중치 `0.7`
- 보배드림 베스트글: 보배드림 내 확산 글 표본. 기본 가중치 `1.0`
- 디시 비트코인 갤러리: 코인 과열/Greed 고속 감지용. 기본 가중치 `0.7`
- 디시 주식 갤러리: 주식 과열/패닉 고속 감지용. 기본 가중치 `0.6`

보배드림과 디시인사이드는 공개 목록 HTML에서 제목/URL/추천/조회수 중심으로 수집합니다. 일반 커뮤니티 특성상 노이즈가 많으므로, 대시보드의 `Source Breakdown`과 `spam_rate`를 같이 보면서 가중치를 조정합니다.

## 운영 메모

- 개인 닉네임이나 원문 본문 전체는 저장하지 않고, 제목/요약/공개 URL 중심으로 저장합니다.
- 네이버 카페는 공개 게시글만 API에 노출됩니다.
- 디시인사이드는 광고와 낚시성 글이 많으므로 기본 가중치를 낮게 둡니다.
- 감성 분석은 아직 사전 기반입니다. 실제 매매 지표로 쓰려면 최소 2~4주 데이터를 모아 가격/거래량과 상관 검증을 해야 합니다.
- 첫 2주 정도는 `calibrating`으로 보는 것이 정상입니다. 매시간 수집하되, 일별 비교는 같은 기준 시각의 `daily_snapshots`를 사용합니다.
- 대시보드 상단 지표는 최근 24시간 롤링 기준이고, 일별 스냅샷의 날짜 라벨은 KST 기준입니다.
- 네이버 카페글 검색 API는 카페글의 원 작성일을 안정적으로 제공하지 않으므로, 과거 커뮤니티 글 수를 완벽히 복원하지는 못합니다. `backfill-datalab`은 네이버 데이터랩의 30일 검색 추이로 만든 추정 기준선이며, 관측 기준선이 쌓이면 관측값이 더 중요합니다.
