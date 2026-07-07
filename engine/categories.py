"""카테고리 상수 — 지시서 6/7/8번, DATA_SCHEMA.md와 정확히 일치해야 함.

이름 문자열이 곧 프론트(docs/js/app.js)가 JSON에서 찾는 키이므로 임의로 바꾸지 말 것.
키워드 자체는 docs/data/keywords.json 이 단일 소스 — 웹사이트 '키워드 설정' 탭에서 내려받은
파일로 이 경로를 덮어쓰면 다음 파이프라인 실행부터 그대로 반영된다.
"""

import json
from pathlib import Path
from urllib.parse import urlparse

INDUSTRY_CATEGORIES = [
    "금융",
    "TMT (기술 & 미디어 & 통신)",
    "로봇 & 반도체",
    "헬스케어 & 라이프사이언스",
    "소비재 & 리테일 (B2C)",
    "여행 & 항공",
    "자동차 & 모빌리티",
    "산업재 (Industrial Goods)",
    "항공 & 방산",
    "운송 & 물류",
    "건설 & 인프라",
    "부동산",
    "소재 & 화학",
    "석유 & 가스",
    "에너지 & 전력",
    "공공 & 사회 & 교육",
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

# 제목/설명에 이 단어가 포함된 기사는 수집 단계에서 제외한다 (오피니언·칼럼·사설·블로그류 배제).
EXCLUDE_KEYWORDS = ["오피니언", "칼럼", "사설", "블로그", "Opinion", "Column", "Editorial", "Blog"]

# 이 도메인에서 나온 기사는 제목에 특정 단어가 없어도 통째로 제외한다
# (뉴스가 아니라 개인/기업 블로그 플랫폼인 경우 — 시작점(seed)이라 필요시 추가/삭제할 것).
EXCLUDED_DOMAINS = [
    "hackernoon.com",
    "medium.com",
    "dev.to",
    "substack.com",
    "blogspot.com",
    "wordpress.com",
    "tistory.com",
    "brunch.co.kr",
    "velog.io",
]

_KEYWORDS_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "keywords.json"


def _load_keyword_sets() -> dict:
    with open(_KEYWORDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _split_ko_en(section: dict) -> tuple[dict, dict]:
    ko = {name: entry.get("ko", []) for name, entry in section.items()}
    en = {name: entry.get("en", []) for name, entry in section.items()}
    return ko, en


def is_excluded(*texts: str) -> bool:
    """제목/설명 등에 EXCLUDE_KEYWORDS 중 하나라도 포함되어 있으면 True (대소문자 무시)."""
    combined = " ".join(t for t in texts if t).lower()
    return any(kw.lower() in combined for kw in EXCLUDE_KEYWORDS)


def is_excluded_domain(url: str) -> bool:
    """URL의 도메인이 EXCLUDED_DOMAINS(또는 그 서브도메인)에 해당하면 True."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    host = host.split(":")[0]  # 포트 제거
    return any(host == d or host.endswith("." + d) for d in EXCLUDED_DOMAINS)


_KEYWORDS = _load_keyword_sets()

INDUSTRY_KEYWORDS, INDUSTRY_KEYWORDS_EN = _split_ko_en(_KEYWORDS["industry"])
BUSINESS_KEYWORDS, BUSINESS_KEYWORDS_EN = _split_ko_en(_KEYWORDS["business"])
ECONOMY_KEYWORDS, ECONOMY_KEYWORDS_EN = _split_ko_en(_KEYWORDS["economy"])
