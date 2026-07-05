"""카테고리 상수 — 지시서 6/7/8번, DATA_SCHEMA.md와 정확히 일치해야 함.

이름 문자열이 곧 프론트(docs/js/app.js)가 JSON에서 찾는 키이므로 임의로 바꾸지 말 것.
"""

INDUSTRY_CATEGORIES = [
    "Finance (금융)",
    "TMT (기술·미디어·통신)",
    "Robotics & Semiconductors",
    "헬스케어 & 라이프사이언스",
    "소비재 & 리테일 (B2C)",
    "여행 (Travel)",
    "자동차 & 모빌리티",
    "산업재 (Industrial Goods)",
    "항공 & 방산",
    "운송 & 물류",
    "건설 & 인프라",
    "부동산",
    "소재 & 화학",
    "Oil & Gas",
    "에너지 & 전력",
    "공공·사회·교육",
]

BUSINESS_CATEGORIES = [
    "M&A / Strategic Investment",
    "Financial Investment (VC/PE)",
    "Corporate Finance / Turnaround",
    "Strategy",
    "PMI / Operations",
    "New Business / Business Building",
    "Go-To-Market",
    "Geopolitics & Regulation",
    "ESG & Sustainability",
    "Risk & Resilience",
    "Artificial Intelligence",
]

ECONOMY_KEYWORD_GROUPS = ["통화·금리", "물가·환율", "성장·경기", "주식·투자", "무역·정책", "금융·가계"]

# 6번 산업군 키워드 (RSS/네이버/Currents 검색어로 사용)
INDUSTRY_KEYWORDS = {
    "Finance (금융)": ["은행", "금융지주", "대출", "카드", "보험", "증권", "금융규제"],
    "TMT (기술·미디어·통신)": ["통신", "미디어", "플랫폼", "콘텐츠", "클라우드", "소프트웨어", "빅테크"],
    "Robotics & Semiconductors": ["반도체", "파운드리", "HBM", "메모리", "로봇", "로보틱스", "자동화"],
    "헬스케어 & 라이프사이언스": ["제약", "바이오", "신약", "의료기기", "병원", "임상", "헬스케어"],
    "소비재 & 리테일 (B2C)": ["소비재", "유통", "리테일", "이커머스", "식품", "화장품", "농업", "농산물"],
    "여행 (Travel)": ["여행", "관광", "여객 항공", "호텔", "항공권"],
    "자동차 & 모빌리티": ["자동차", "전기차", "완성차", "모빌리티", "자율주행"],
    "산업재 (Industrial Goods)": ["철강", "비철금속", "기계", "장비", "부품", "조선", "중공업"],
    "항공 & 방산": ["방산", "국방", "무기", "항공우주", "방위산업"],
    "운송 & 물류": ["물류", "화물", "해운", "택배", "공급망 운송"],
    "건설 & 인프라": ["건설", "건설사", "수주", "인프라", "플랜트", "SOC"],
    "부동산": ["부동산", "아파트", "분양", "리츠", "상업용부동산", "주택시장"],
    "소재 & 화학": ["석유화학", "나프타", "기초화학", "배터리소재", "양극재", "리튬", "희토류", "신소재"],
    "Oil & Gas": ["석유", "원유", "천연가스", "LNG", "정유", "유가"],
    "에너지 & 전력": ["발전", "전력", "원자력", "태양광", "풍력", "신재생", "송전", "한전"],
    "공공·사회·교육": ["정부정책", "공공", "규제", "교육", "사회복지", "비영리"],
}

# 7번 Business 키워드
BUSINESS_KEYWORDS = {
    "M&A / Strategic Investment": ["인수합병", "M&A", "지분인수", "전략적투자", "합병"],
    "Financial Investment (VC/PE)": ["사모펀드", "PE", "바이아웃", "엑시트", "벤처투자", "VC", "투자유치"],
    "Corporate Finance / Turnaround": ["실적", "어닝", "적자", "흑자", "영업이익", "구조조정", "주가", "재무"],
    "Strategy": ["사업전략", "사업재편", "신규전략", "마케팅 전략", "세일즈 전략"],
    "PMI / Operations": ["통합", "운영효율", "생산", "오퍼레이션", "PMI"],
    "New Business / Business Building": ["신사업", "사업확장", "신규진출", "벤처빌딩"],
    "Go-To-Market": ["해외진출", "시장진출", "지역확장", "글로벌진출"],
    "Geopolitics & Regulation": ["지정학", "관세", "수출통제", "규제", "제재", "무역분쟁"],
    "ESG & Sustainability": ["ESG", "탄소중립", "지속가능", "친환경", "공시규제"],
    "Risk & Resilience": ["공급망", "리스크", "사이버보안", "위기관리", "회복탄력성"],
    "Artificial Intelligence": ["AI", "인공지능", "LLM", "생성형AI", "데이터센터", "AI인프라", "GPU"],
}

# 8번 경제 키워드
ECONOMY_KEYWORDS = {
    "통화·금리": ["기준금리", "금리", "국채", "채권", "한국은행", "금통위", "Fed", "FOMC", "연준", "금리인하", "금리인상"],
    "물가·환율": ["소비자물가", "인플레이션", "CPI", "원/달러", "환율", "외환"],
    "성장·경기": ["GDP", "경제성장률", "경기 침체", "실업률", "고용지표"],
    "주식·투자": ["코스피", "코스닥", "증권", "증시", "나스닥", "투자"],
    "무역·정책": ["수출", "수입", "무역수지", "관세", "경제 정책", "재정정책", "통화정책"],
    "금융·가계": ["대출", "신용대출", "가계대출", "은행", "저축은행", "인터넷은행", "금융권"],
}

# Currents(글로벌, 영어 위주 소스) 검색용 영어 키워드 — 카테고리당 대표 키워드 1~3개.
# 지시서에는 한국어 키워드만 명시되어 있어, 글로벌 소스 검색을 위해 추가로 정의함(확인·튜닝 필요).
INDUSTRY_KEYWORDS_EN = {
    "Finance (금융)": ["bank", "financial holding", "insurance", "securities"],
    "TMT (기술·미디어·통신)": ["telecom", "media platform", "cloud software", "big tech"],
    "Robotics & Semiconductors": ["semiconductor", "foundry", "HBM memory", "robotics"],
    "헬스케어 & 라이프사이언스": ["pharmaceutical", "biotech", "medical device", "clinical trial"],
    "소비재 & 리테일 (B2C)": ["consumer goods", "retail", "e-commerce", "agriculture"],
    "여행 (Travel)": ["travel", "tourism", "airline passenger", "hotel"],
    "자동차 & 모빌리티": ["automaker", "electric vehicle", "mobility", "autonomous driving"],
    "산업재 (Industrial Goods)": ["steel", "machinery", "shipbuilding", "industrial equipment"],
    "항공 & 방산": ["defense industry", "aerospace", "military weapons"],
    "운송 & 물류": ["logistics", "shipping freight", "supply chain transport"],
    "건설 & 인프라": ["construction", "infrastructure project", "engineering contract"],
    "부동산": ["real estate", "housing market", "REIT"],
    "소재 & 화학": ["petrochemical", "battery materials", "cathode material", "lithium"],
    "Oil & Gas": ["crude oil", "natural gas", "LNG", "refinery"],
    "에너지 & 전력": ["power generation", "electricity grid", "nuclear power", "renewable energy"],
    "공공·사회·교육": ["government policy", "public sector", "education policy"],
}

BUSINESS_KEYWORDS_EN = {
    "M&A / Strategic Investment": ["merger acquisition", "M&A", "strategic investment"],
    "Financial Investment (VC/PE)": ["private equity", "venture capital", "buyout", "exit deal"],
    "Corporate Finance / Turnaround": ["earnings", "operating profit", "restructuring", "turnaround"],
    "Strategy": ["business strategy", "marketing strategy", "growth strategy"],
    "PMI / Operations": ["post-merger integration", "operations efficiency"],
    "New Business / Business Building": ["new business", "business building", "expansion"],
    "Go-To-Market": ["market entry", "global expansion"],
    "Geopolitics & Regulation": ["geopolitics", "export control", "tariff", "sanctions"],
    "ESG & Sustainability": ["ESG", "carbon neutral", "sustainability disclosure"],
    "Risk & Resilience": ["supply chain risk", "cybersecurity", "crisis management"],
    "Artificial Intelligence": ["artificial intelligence", "generative AI", "data center", "AI infrastructure", "GPU"],
}

ECONOMY_KEYWORDS_EN = {
    "통화·금리": ["interest rate", "Fed", "FOMC", "central bank", "rate cut", "rate hike"],
    "물가·환율": ["inflation", "CPI", "exchange rate", "currency"],
    "성장·경기": ["GDP", "economic growth", "recession", "unemployment rate"],
    "주식·투자": ["stock market", "Nasdaq", "equity investment"],
    "무역·정책": ["exports", "trade balance", "tariff", "fiscal policy"],
    "금융·가계": ["household debt", "bank loan", "consumer credit"],
}
