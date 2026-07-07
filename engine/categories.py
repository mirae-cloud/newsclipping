"""카테고리 상수 — 지시서 6/7/8번, DATA_SCHEMA.md와 정확히 일치해야 함.

이름 문자열이 곧 프론트(docs/js/app.js)가 JSON에서 찾는 키이므로 임의로 바꾸지 말 것.
키워드 자체는 docs/data/keywords.json 이 단일 소스 — 웹사이트 '키워드 설정' 탭에서 내려받은
파일로 이 경로를 덮어쓰면 다음 파이프라인 실행부터 그대로 반영된다.
"""

import json
from pathlib import Path

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

# 제목/설명에 이 단어가 포함된 기사는 수집 단계에서 제외한다 (오피니언·칼럼·사설류 배제).
EXCLUDE_KEYWORDS = ["오피니언", "칼럼", "사설"]

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


_KEYWORDS = _load_keyword_sets()

INDUSTRY_KEYWORDS, INDUSTRY_KEYWORDS_EN = _split_ko_en(_KEYWORDS["industry"])
BUSINESS_KEYWORDS, BUSINESS_KEYWORDS_EN = _split_ko_en(_KEYWORDS["business"])
ECONOMY_KEYWORDS, ECONOMY_KEYWORDS_EN = _split_ko_en(_KEYWORDS["economy"])
