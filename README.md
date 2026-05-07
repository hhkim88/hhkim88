# Company Search + Bull vs Bear Debate

자체 호스팅 기업 정보 검색 백엔드와 강세론(Bull) vs 약세론(Bear) 애널리스트 토론 시스템.
유료 검색 API 의존 없이 공시·재무·뉴스·SNS·애널리스트 우회 자료를 무료 공개 소스에서 수집·캐싱합니다.

## 두 가지 사용 방식

1. **Standalone 토론 실행**: `uv run debate 삼성전자 --rounds 3 -o samsung.md`
2. **Claude Code MCP 통합**: `.mcp.json`에 등록하여 Claude Code에서 자연어로 단일 검색

## 데이터 소스

| 영역 | 소스 | 라이브러리 |
|---|---|---|
| 시세 | KRX, NASDAQ, NYSE, AMEX | `finance-datareader` |
| 재무 (KR) | OpenDART | `requests` |
| 재무 (US) | Yahoo Finance | `yfinance` |
| 뉴스 (KR) | 네이버 뉴스 검색 | `newspaper4k` |
| 뉴스 (US) | Google News RSS | `newspaper4k`, `feedparser` |
| 애널리스트 PDF (KR) | 한경 컨센서스 | `pypdf` |
| 컨센서스 메타 | 네이버금융 / yfinance | `bs4` |
| 2차 인용 뉴스 | 네이버/Google + 브로커 키워드 | (위 뉴스 모듈 재사용) |
| 유튜브 트랜스크립트 | 슈카·삼프로TV·Damodaran 등 | `yt-dlp`, `youtube-transcript-api` |
| SNS | Reddit, 네이버 종목토론방 | `praw`, `bs4` |
| IR 자료 | DART, SEC EDGAR 8-K | `requests` |
| Earnings call (US) | Motley Fool 무료 트랜스크립트 | `feedparser`, `newspaper4k` |
| Seeking Alpha (US) | SA 컨트리뷰터 헤드라인 (Google News 경유) | `feedparser` |
| 매크로 | 한국은행 ECOS, FRED, BLS | `requests` |

## 셋업

```bash
# 1. 의존성 설치
uv sync

# 2. .env 파일 작성 (.env.example 참고)
cp .env.example .env
# 편집 후:
#   DART_API_KEY=...             (필수, KR 재무용 - opendart.fss.or.kr 무료)
#   REDDIT_CLIENT_ID/SECRET=...  (선택, US 소셜용 - reddit.com/prefs/apps)
#   FRED_API_KEY=...             (선택, US 매크로용 - fred.stlouisfed.org)
#   ECOS_API_KEY=...             (선택, KR 매크로용 - ecos.bok.or.kr)
#
# 토론 LLM은 claude-agent-sdk가 로컬 `claude` CLI를 통해 호출하므로
# Claude Code Max 구독이면 별도 API 키 불필요.
```

## 사용

### CLI 단위 검증

```bash
uv run python -m company_search resolve "삼성전자"
uv run python -m company_search financials "삼성전자" --year 2024
uv run python -m company_search news "삼성전자" --stance bear --limit 5
uv run python -m company_search news-us "Apple" --stance bull --limit 5
uv run python -m company_search price 005930 --days 365
uv run python -m company_search consensus 005930 --market KR
uv run python -m company_search consensus AAPL --market US
uv run python -m company_search youtube "삼성전자" --limit 3
uv run python -m company_search social AAPL --market US
uv run python -m company_search ir "삼성전자" --limit 5
```

두 번째 호출부터는 SQLite 캐시(`~/.company_search.db`, 24h TTL)가 적용됩니다.

### 토론 실행

```bash
# 빠르고 저렴한 검증 (Haiku)
uv run debate 삼성전자 --market KR --rounds 2 --model claude-haiku-4-5 -o samsung.md

# 기본 (Sonnet 4.6)
uv run debate 삼성전자 --market KR --rounds 3 -o samsung.md

# 깊이 있는 분석 (Opus, 비용 큼)
uv run debate AAPL --market US --rounds 3 --model claude-opus-4-7 -o aapl.md
```

라운드 수에 따른 흐름:
- `rounds=2`: 개진 → 마무리
- `rounds=3`: 개진 → 반박 → 마무리 (기본값, 권장)
- `rounds≥4`: 개진 → 반박 × N → 마무리

각 라운드마다 Bull과 Bear가 발언하고 마지막에 Moderator가 합의 사실/대립
해석/중장기 투자 질문을 구조화 요약으로 정리합니다. 출력 마크다운은 상단에
Moderator 요약, 하단에 토론 전문 순서로 배치됩니다.

### Claude Code MCP 등록

`~/.config/claude/.mcp.json` 또는 프로젝트 루트의 `.mcp.json`에 추가:

```json
{
  "mcpServers": {
    "company-search": {
      "command": "uv",
      "args": ["run", "--directory", "/home/user/hhkim88",
               "python", "-m", "company_search.server"],
      "env": {
        "DART_API_KEY": "...",
        "REDDIT_CLIENT_ID": "...",
        "REDDIT_CLIENT_SECRET": "..."
      }
    }
  }
}
```

Claude Code 재시작 후 자연어로:
- "삼성전자 최근 약세 논거 찾아줘" → `search_company_news(stance="bear")` 호출
- "AAPL 컨센서스 어때?" → `get_analyst_consensus`
- "TSLA 유튜브 분석" → `get_youtube_analysis`

## Reddit US SNS 데이터

키 없이도 동작합니다 — `get_social_buzz`는 두 가지 경로 중 하나를 자동 선택:

| 경로 | 활성 조건 | 풍부도 | 비고 |
|---|---|---|---|
| **PRAW (Reddit 공식 API)** | `.env`에 `REDDIT_CLIENT_ID/SECRET` 설정됨 | 풍부 — 본문 전체, 업보트 수, 댓글 수 | 키 발급 필요 (아래 단계) |
| **Public JSON fallback** | 키 없거나 PRAW 실패 시 자동 fallback | 풍부 — PRAW와 동일 (본문/업보트/댓글) | `reddit.com/r/<sub>/search.json` 직접 호출, 셋업 불필요 |

### (선택) Reddit API 키 발급으로 풍부도 ↑

1. https://www.reddit.com/prefs/apps 접속 (Reddit 계정 필요, 무료 가입)
2. 페이지 하단 **"create another app..."** 클릭
3. 양식 작성:
   - **name**: `company-search` (자유)
   - **type**: `script` 선택 (개인 사용 목적)
   - **redirect uri**: `http://localhost:8080` (script 타입에선 실제로 사용 안 함)
   - description / about url은 비워둬도 됨
4. **create app** 클릭하면 다음 두 값이 발급됩니다:
   - 앱 이름 바로 아래의 짧은 문자열 (보통 14~22자) → `REDDIT_CLIENT_ID`
   - "secret" 라벨 옆 긴 문자열 → `REDDIT_CLIENT_SECRET`
5. `.env`에 추가:
   ```
   REDDIT_CLIENT_ID=발급받은_client_id
   REDDIT_CLIENT_SECRET=발급받은_secret
   REDDIT_USER_AGENT=company-search/0.1 by yourname
   ```
6. 검증:
   ```bash
   uv run python -m company_search social AAPL --market US
   ```
   `platform: reddit_praw`로 표시되면 PRAW 경로, `reddit_via_google_news`면
   fallback 경로입니다.

**주의**: 4단계에서 *"create app" 버튼이 에러*가 나는 경우가 종종 있습니다.
원인은 보통 ① 이메일 미인증, ② 신규 계정 karma 0, ③ 지역·캡차 차단입니다.
키 발급에 실패해도 자동 fallback이 reddit.com 공식 JSON 엔드포인트로 라우팅되며,
PRAW와 거의 동일한 데이터(본문·업보트 수·댓글 수)를 반환하므로 토론 품질에
실질적 차이가 없습니다.

## 한계 (정직한 평가)

- **80% 대체 가능, 100%는 아님**. Bloomberg/Refinitiv급 실시간 데이터, IBES/FactSet
  컨센서스, 트위터 실시간 여론, 얼터너티브 데이터(신용카드·위성 등)는 커버 안 됨.
- **중장기 투자자에겐 충분**. 단타·HFT·헤지펀드급 정밀 분석엔 부족.
- **트위터(X)** 무료 스크래핑 불가 → Reddit + 네이버 종토방으로 우회.
- **증권사 회원 전용 PDF** 접근 불가 → 한경컨센서스 공개분 + 2차 인용 뉴스 +
  네이버금융·Yahoo Analysts 컨센서스 메타로 우회.
- **미국 정식 애널리스트 리포트 본문** 접근 불가 (Goldman, MS 등 모두 paywall) →
  컨센서스 메타(yfinance) + 2차 인용 뉴스 + Seeking Alpha 컨트리뷰터 헤드라인 +
  Motley Fool 무료 earnings call 트랜스크립트로 우회.
- **한국 earnings call 트랜스크립트**는 무료 공개분이 사실상 없음 → DART 사업·분기
  보고서로 대체. (Motley Fool 같은 한국어 무료 트랜스크립트 사이트 존재 시 추가 예정)

## 비용

- 검색: **0원** (모두 공개 소스 + SQLite 캐시)
- 토론: Claude Code Max 구독 한도 내에서 추가 비용 없음
  (`claude-agent-sdk`가 로컬 `claude` CLI subprocess로 호출)
- API 키로 돌리고 싶다면 `ANTHROPIC_API_KEY`를 환경변수로 설정하면 SDK가
  자동으로 그쪽으로 라우팅. Sonnet 4.6 기준 1회 토론(3라운드) 약 $0.15~$0.40.
