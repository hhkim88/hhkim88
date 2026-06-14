"""크롤링 대상 URL과 컬럼 매핑 설정.

38.co.kr 페이지는 EUC-KR(cp949)로 인코딩되어 있고, 데이터가 들어있는
<table> 의 정확한 클래스/구조가 시기에 따라 바뀔 수 있다. 그래서 이 모듈은
'헤더 텍스트(한글)'를 보고 컬럼을 식별하는 방식으로 파서를 유연하게 구성한다.
"""

BASE_URL = "https://www.38.co.kr/html/fund/"

# 사용자 에이전트 (일반 브라우저처럼 보이도록)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 38.co.kr 페이지 파라미터 (o=)
#   o=k : 공모주 청약일정 (일반 청약경쟁률 포함)
#   o=r : 신규상장 종목 (공모가/시초가/현재가 등, 첫날 수익률 계산용)
#   o=nw: 수요예측결과 (기관경쟁률/의무보유확약 등, 선택적)
# NOTE: 사이트 개편 시 파라미터가 바뀔 수 있으므로 실제 HTML로 검증 필요.
PAGE_SUBSCRIPTION = "k"   # 청약일정 (청약경쟁률)
PAGE_NEW_LISTING = "r"    # 신규상장 (수익률)
PAGE_DEMAND = "nw"        # 수요예측 결과 (선택)

# 인코딩 후보 (앞에서부터 시도)
ENCODINGS = ("euc-kr", "cp949", "utf-8")

# 요청 간 최소 대기(초) - 서버 부하 최소화 (매너)
REQUEST_DELAY = 1.0
REQUEST_TIMEOUT = 20
MAX_RETRIES = 4

# ---------------------------------------------------------------------------
# 헤더(한글) -> 표준 필드명 매핑.
# 각 필드의 키워드 중 하나라도 헤더 텍스트에 '포함'되면 해당 필드로 본다.
# dict 의 '정의 순서'가 곧 우선순위다. 더 구체적인 필드를 먼저 둔다.
# 예) '희망공모가' 는 '공모가' 를 포함하므로 desired_price_band 를 offer_price 보다 먼저 둔다.
# ---------------------------------------------------------------------------
FIELD_KEYWORDS = {
    "name": ["종목명", "기업명", "회사명"],
    "subscription_date": ["공모청약일", "청약일", "청약기간", "공모주일정", "공모일정"],
    "listing_date": ["상장일"],
    "desired_price_band": ["희망공모", "희망가"],
    "offer_price": ["확정공모가", "공모가", "공모가격"],
    "subscription_competition": ["청약경쟁률", "경쟁률"],
    "institutional_competition": ["기관경쟁률", "수요예측경쟁률", "수요예측"],
    "lockup_ratio": ["의무보유", "확약"],
    "open_price": ["시초가"],
    "current_price": ["현재가"],
    "close_price": ["종가", "당일종가"],
    "high_price": ["고가"],
    "return_pct": ["수익률", "등락률"],
    "underwriter": ["주간사", "주관사"],
}

# 각 페이지의 데이터 테이블을 식별하기 위한 '필수 헤더 키워드' 집합.
# 한 테이블의 헤더에 아래 키워드가 (부분문자열로) 모두 존재하면 데이터 테이블로 간주.
TABLE_SIGNATURES = {
    PAGE_SUBSCRIPTION: ["종목명", "경쟁률"],
    PAGE_NEW_LISTING: ["종목명", "공모가"],
    PAGE_DEMAND: ["종목명"],
}
