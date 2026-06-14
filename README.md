# 공모주 청약 효율 분석 (38.co.kr 크롤러)

[38커뮤니케이션](https://www.38.co.kr/html/fund/?o=k)에서 **공모주 청약 정보**와
**신규상장 종목의 첫날 수익률**을 수집하여,

> **일반 개인투자자 청약경쟁률은 낮고(= 당첨/배정 확률은 높고), 첫날 수익률은 높은**

조건의 종목을 찾는 연구용 도구입니다.

---

## 핵심 아이디어

- **청약경쟁률(`subscription_competition`)이 낮을수록** 비례배정에서 같은 청약증거금으로
  더 많은 주식을 배정받아 **당첨/배정 확률이 높아진다.**
- **첫날 수익률(`first_day_return`)이 높을수록** 상장 직후 차익이 크다.
- 두 조건을 함께 만족하는 종목이 "효율 좋은" 공모주다.

배정 효율 점수:

```
efficiency = 첫날수익률(%) / sqrt(청약경쟁률)
```

경쟁률이 낮을수록·수익률이 높을수록 점수가 커집니다.

첫날 수익률은 공모가 대비로 계산합니다.

```
first_day_return_open  = (시초가  - 공모가) / 공모가 × 100
first_day_return_close = (당일종가 - 공모가) / 공모가 × 100
first_day_return       = close 우선, 없으면 open, 없으면 사이트 제공 등락률
```

---

## 설치

```bash
pip install -r requirements.txt
```

## 사용법

```bash
# 1) 크롤링만 (CSV 저장: data/subscriptions.csv, data/new_listings.csv)
python main.py crawl --max-pages 20 --out-dir data

# 2) 저장된 CSV 로 분석
python main.py analyze --data-dir data --max-competition 200 --min-return 30

# 3) 크롤링 + 분석을 한 번에
python main.py run --max-pages 20 --out-dir data --max-competition 200 --min-return 30
```

### 주요 옵션

| 옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `--max-pages` | 페이지네이션 최대 페이지 수 | 20 |
| `--max-competition` | 이 청약경쟁률(:1) **이하**만 후보 | 미지정 시 하위 50% 분위 |
| `--min-return` | 최소 첫날 수익률(%) | 0 |
| `--top` | 출력할 상위 종목 수 | 30 |

### 출력

- `data/merged.csv` — 청약 + 수익률 병합 전체 데이터
- `data/opportunities.csv` — 조건(낮은 경쟁률 + 높은 수익률)을 만족하는 종목, 효율순
- 콘솔: 경쟁률 ↔ 수익률 **상관관계(Spearman)** 요약과 상위 종목 표

예시 출력:

```
===== 상관관계 분석 =====
경쟁률 vs 수익률 상관계수 (Spearman): -0.800
해석: 경쟁률이 낮을수록 수익률이 높은 경향(역상관) → 가설을 지지합니다.

===== 청약경쟁률 낮고 + 수익률 높은 종목 (효율순) =====
 name   subscription_competition  first_day_return  efficiency
델타에너지                    55.10             160.0   21.55
 베타소재                    120.45             130.0   11.85
```

---

## 구조

```
ipo38/
  config.py    # URL, 인코딩, 헤더(한글)->필드 매핑, 테이블 시그니처
  fetch.py     # HTTP 요청 + EUC-KR 디코딩 + 재시도(지수 백오프)
  parse.py     # 테이블 자동 탐지/파싱 + 숫자 정규화
  crawler.py   # 페이지네이션 순회 + 레코드 정규화 -> DataFrame
  analyze.py   # 병합 + 첫날수익률 + 효율점수 + 기회 탐색 + 상관분석
main.py        # CLI (crawl / analyze / run)
tests/         # 오프라인 fixture 기반 파서·분석 테스트 (pytest)
```

테스트:

```bash
pip install pytest
python -m pytest tests/ -q
```

---

## ⚠️ 네트워크 / 사이트 구조 관련 주의

1. **실행 환경의 네트워크 접근.** 이 도구는 `www.38.co.kr` 로 직접 접속합니다.
   Claude Code 웹/원격 환경 중 일부 네트워크 정책은 외부 사이트 접속을 차단하므로,
   **외부 접속이 허용된 환경(로컬 PC 또는 적절한 네트워크 정책의 세션)에서 실행**하세요.
   (참고: https://code.claude.com/docs/en/claude-code-on-the-web)

2. **사이트 개편 대비.** 38.co.kr 은 옛 방식의 중첩 테이블 HTML 이라
   페이지 파라미터(`o=k`, `o=r` 등)나 컬럼 명칭이 바뀔 수 있습니다.
   파서는 **헤더의 한글 텍스트로 컬럼을 식별**하도록 만들어 변화에 비교적 강하지만,
   결과가 비면 `ipo38/config.py` 의 `PAGE_*`, `FIELD_KEYWORDS`,
   `TABLE_SIGNATURES` 를 실제 HTML 에 맞게 조정하세요.

3. **매너.** 요청 간 기본 1초 지연(`config.REQUEST_DELAY`)을 둡니다. 과도한 요청을 피하세요.

4. **면책.** 본 도구는 연구/학습 목적이며 투자 권유가 아닙니다.
   과거 수익률이 미래 수익을 보장하지 않습니다.
