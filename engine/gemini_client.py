"""Gemini 클라이언트 — 뉴스 분류·요약·인사이트 생성.

SDK: google-genai (신형). 모델명은 상수로 분리해 손쉽게 교체 가능하게 함.
문서: https://ai.google.dev/gemini-api/docs/quickstart
"""

import time
from typing import Optional

from google import genai
from pydantic import BaseModel

from engine import config

# 확인 필요: 무료 티어 최신 모델명은 자주 바뀜 — 구현 직전 가격/한도 페이지에서 재확인.
MODEL_NAME = "gemini-3.5-flash"

MAX_RETRIES = 4
BASE_BACKOFF_SEC = 2.0

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다 (.env 확인).")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _generate_json(prompt: str, schema: type[BaseModel]) -> BaseModel:
    """429(rate limit) 대비 지수 백오프 재시도를 포함한 구조화 JSON 생성."""
    client = _get_client()
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            interaction = client.interactions.create(
                model=MODEL_NAME,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema.model_json_schema(),
                },
            )
            return schema.model_validate_json(interaction.output_text)
        except Exception as exc:  # noqa: BLE001 — SDK 예외 타입이 rate-limit별로 세분화되어 있지 않음
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(BASE_BACKOFF_SEC * (2**attempt))

    raise RuntimeError(f"Gemini 호출이 {MAX_RETRIES}회 재시도 후에도 실패했습니다: {last_error}")


# ---------- 프롬프트 공통 규칙 (지시서 5-2/6-1/7번) ----------

INSIGHT_RULES = """
인사이트 작성 규칙:
- 해당 산업 내부 영향뿐 아니라, 후방산업(원재료·소재 공급단)과 전방산업(최종 수요단)으로의 파급을 짚을 것.
- 경기민감 산업(부동산·건설 등)은 거시 흐름과 연결해 해석할 것.
- 타 산업으로의 대체/보완 효과를 최소 1개 제시할 것.
- 일견 무관해 보이는 산업과의 연결이 있다면 제시할 것 (예: 여행·항공 침체 ↔ 홈엔터·게임 수요 증가).
- 확실한 인과가 아니면 반드시 '추정' 또는 '가능성'이라는 단어를 포함해 표시할 것.
"""

ROUTING_RULES = """
카테고리 경계 라우팅 규칙:
- "소재 & 화학" vs "산업재 (Industrial Goods)": 화학적으로 만들어지는 소재(석유화학·나프타·배터리소재 등)는 "소재 & 화학",
  금속 원자재·중간재(철강 등)나 물리적으로 가공·조립되는 부품·기계·장비는 "산업재 (Industrial Goods)".
- 금속 광물(철광석 등)은 "산업재 (Industrial Goods)", 배터리·첨단소재용 광물(리튬·희토류 등)은 "소재 & 화학".
- "Oil & Gas"는 연료·자원 자체(원유·LNG 수입·유가), "에너지 & 전력"은 그 연료로 전기를 만드는 발전·전력망(원자력·태양광·한전 등).
- 농업·농산물 관련 기사는 별도 카테고리 없이 전량 "소비재 & 리테일 (B2C)"로 분류.
- 기업의 치명적·혁신적 인사/노조 이슈(예: 노조 갈등)는 "Artificial Intelligence"가 아니라 "PMI / Operations"로 분류.
  단, 일반적인 조직 혁신·HR 이슈는 두 카테고리 모두에서 제외.
- 'DX를 위한 AI 도입' 류 기사는 "Artificial Intelligence"로 분류.
"""

SUMMARY_LENGTH_RULE = """
요약 bullet 작성 규칙:
- 카테고리명이나 제목만 나열하는 짧은 구가 아니라, 실제 기사 내용(수치·주체·배경)을 반영한 완결된 문장으로 작성할 것.
- 문장당 40~80자 내외의 분량으로 작성할 것 (지나치게 짧은 요약 금지).
"""


class ArticleClassification(BaseModel):
    index: int
    category: Optional[str]  # 허용된 카테고리명 중 하나, 관련 없으면 null


class ClassificationResult(BaseModel):
    classifications: list[ArticleClassification]


def classify_articles(articles: list[dict], allowed_categories: list[str]) -> dict[int, Optional[str]]:
    """articles: [{"index": int, "title": str, "description": str}, ...]

    반환: {index: 카테고리명 또는 None}
    """
    articles_block = "\n".join(f'{a["index"]}. {a["title"]} — {a["description"][:200]}' for a in articles)
    categories_block = "\n".join(f"- {c}" for c in allowed_categories)

    prompt = f"""
다음은 뉴스 기사 목록이다. 각 기사를 아래 허용된 카테고리 중 하나로 분류하라.
어느 카테고리에도 맞지 않거나 노이즈(광고, 무관한 기사)라고 판단되면 category를 null로 하라.

{ROUTING_RULES}

허용된 카테고리:
{categories_block}

기사 목록 (번호. 제목 — 설명):
{articles_block}

각 기사 번호에 대해 정확히 하나의 분류 결과를 반환하라.
"""
    result = _generate_json(prompt, ClassificationResult)
    return {c.index: c.category for c in result.classifications}


class ArticleOutput(BaseModel):
    index: int
    title: str
    bullets: list[str]
    insight: str


class CategorySummary(BaseModel):
    sub_summary_bullets: list[str]
    selected: list[ArticleOutput]
    extra_topics: list[str]


def summarize_category(category_name: str, articles: list[dict]) -> CategorySummary:
    """articles: [{"index": int, "title": str, "description": str, "url": str}, ...] (해당 카테고리로 분류된 기사들)"""
    articles_block = "\n".join(f'{a["index"]}. {a["title"]} — {a["description"][:300]}' for a in articles)

    prompt = f"""
아래는 "{category_name}" 카테고리로 분류된 오늘의 기사 목록이다. 다음 규칙에 따라 정리하라.

카테고리당 기사 개수 규칙:
- 규모, 변화 정도, 산업 내 위치 등을 고려해 가장 핵심적이고 중요한 기사를 최대 3개까지 선택(selected)할 것.
- 선택되지 않은 기사 중 참고할 만한 것이 있으면 주제당 15~20자 이내로 extra_topics에 기재할 것 (없으면 빈 배열).
- 관련성이 낮은 기사는 무시할 것.

{SUMMARY_LENGTH_RULE}
(sub_summary_bullets에 적용. 1~2개 문장)

각 selected 기사에는 다음을 작성:
- title: 원문 제목을 다듬은 핵심 한 줄 요약.
- bullets: 주요 내용 요약 bullet 2~3개 (짧고 명확하게).
- insight: 아래 규칙에 따른 파급효과 분석 한 문단.

{INSIGHT_RULES}

기사 목록 (번호. 제목 — 설명):
{articles_block}
"""
    return _generate_json(prompt, CategorySummary)


class Headline(BaseModel):
    category: str
    headline: str


class OverallSummary(BaseModel):
    overall_bullets: list[str]
    headlines: list[Headline]


def generate_overall_summary(top_articles: list[dict]) -> OverallSummary:
    """top_articles: [{"category": str, "title": str, "description": str}, ...] (카테고리별 1위 기사들)"""
    articles_block = "\n".join(f'[{a["category"]}] {a["title"]} — {a["description"][:200]}' for a in top_articles)

    prompt = f"""
아래는 오늘의 카테고리별 대표 기사 목록이다. 이를 바탕으로 전체 요약(overall_bullets)과
카테고리별 헤드라인(headlines)을 작성하라.

{SUMMARY_LENGTH_RULE}
(overall_bullets는 2~3개 문장, 여러 대표 기사의 내용을 종합해 오늘 하루의 핵심 흐름을 반영할 것)

headlines는 각 대표 기사에 대해 카테고리명과 15~30자 내외의 간결한 헤드라인으로 구성.

대표 기사 목록:
{articles_block}
"""
    return _generate_json(prompt, OverallSummary)
