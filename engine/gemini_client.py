"""Gemini 클라이언트 — 뉴스 분류·요약·인사이트 생성.

SDK: google-genai (신형). 모델명은 상수로 분리해 손쉽게 교체 가능하게 함.
문서: https://ai.google.dev/gemini-api/docs/quickstart
"""

import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from engine import config

# 확인 필요: 무료 티어 최신 모델명은 자주 바뀜 — 구현 직전 가격/한도 페이지에서 재확인.
# 2026-07: 결제 계정 연결 후 Tier 1(유료)로 전환되어 하루 20건 제한은 해소됨.
# gemini-2.5-flash 사용 — gemini-3.5-flash 대비 토큰 단가가 약 1/5(입력 $0.30 vs $1.50, 출력 $2.50 vs $9).
MODEL_NAME = "gemini-2.5-flash"

# 유료 티어는 한도가 훨씬 넉넉하지만, 그래도 안전하게 분당 60건으로 자체 제한(스레드 세이프).
MAX_REQUESTS_PER_MINUTE = 60
_recent_call_times: deque = deque()
_throttle_lock = threading.Lock()

# 분류/요약을 여러 카테고리·배치에 걸쳐 동시에 호출하기 위한 동시 실행 수.
PARALLEL_WORKERS = 10

# 토큰 사용량 누적 집계 (하루 실행당 비용 확인용, 스레드 세이프)
_usage_totals = {"prompt": 0, "candidates": 0, "thoughts": 0, "total": 0, "calls": 0}
_usage_lock = threading.Lock()

# Gemini 호출이 재시도를 모두 소진하고 실패한 경우의 실제 예외 메시지를 몇 개만 표본으로 남긴다.
# Actions 로그는 저장소 admin 권한이 없으면 못 보므로, 이 표본을 diagnostics.json에 실어 보내
# git pull만으로 '왜' 실패했는지(인증/과금/버전 등) 확인할 수 있게 한다.
_MAX_ERROR_SAMPLES = 5
_error_samples: list[str] = []
_error_lock = threading.Lock()


def _record_error(exc: Exception) -> None:
    with _error_lock:
        if len(_error_samples) < _MAX_ERROR_SAMPLES:
            _error_samples.append(str(exc))


def get_error_samples() -> list[str]:
    with _error_lock:
        return list(_error_samples)

MAX_RETRIES = 7
BASE_BACKOFF_SEC = 2.0

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다 (.env 확인).")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _throttle() -> None:
    """분당 요청 수를 자체 제한해 429(rate limit)를 애초에 피한다 (여러 스레드에서 동시 호출 가능)."""
    with _throttle_lock:
        now = time.monotonic()
        while _recent_call_times and now - _recent_call_times[0] > 60:
            _recent_call_times.popleft()

        wait = 0.0
        if len(_recent_call_times) >= MAX_REQUESTS_PER_MINUTE:
            wait = 60 - (now - _recent_call_times[0]) + 0.5

        _recent_call_times.append(time.monotonic())

    if wait > 0:
        time.sleep(wait)


def _parse_retry_delay(exc: Exception) -> Optional[float]:
    """429 오류 메시지에 포함된 'retryDelay': '9s' 같은 힌트를 최선을 다해 추출한다."""
    match = re.search(r"retryDelay['\"]?:\s*['\"](\d+(?:\.\d+)?)s", str(exc))
    return float(match.group(1)) if match else None


def _generate_json(prompt: str, schema: type[BaseModel]) -> BaseModel:
    """자체 분당 요청 제한 + 429(rate limit) 대비 재시도(서버가 알려주는 대기시간 우선)를 포함한 구조화 JSON 생성.

    thinking_budget=0으로 추론 토큰을 꺼서 지연시간·비용을 줄인다(분류/요약은 복잡한 추론이 필요 없는 구조화 추출 작업).
    """
    last_error = None

    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            client = _get_client()
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            _record_usage(response)
            if response.parsed is not None:
                return response.parsed
            return schema.model_validate_json(response.text)
        except Exception as exc:  # noqa: BLE001 — SDK 예외 타입이 rate-limit별로 세분화되어 있지 않음
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                wait = _parse_retry_delay(exc)
                if wait is None:
                    wait = BASE_BACKOFF_SEC * (2**attempt)
                time.sleep(wait + 1)

    _record_error(last_error)
    raise RuntimeError(f"Gemini 호출이 {MAX_RETRIES}회 재시도 후에도 실패했습니다: {last_error}")


def _record_usage(response) -> None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    with _usage_lock:
        _usage_totals["prompt"] += usage.prompt_token_count or 0
        _usage_totals["candidates"] += usage.candidates_token_count or 0
        _usage_totals["thoughts"] += usage.thoughts_token_count or 0
        _usage_totals["total"] += usage.total_token_count or 0
        _usage_totals["calls"] += 1


def get_usage_summary() -> dict:
    """이번 프로세스 실행 동안 누적된 Gemini 토큰 사용량 (하루 실행당 비용 확인용)."""
    with _usage_lock:
        return dict(_usage_totals)


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
- "석탄 & 석유 & 가스"는 연료·자원 자체(원유·LNG 수입·유가), "에너지 & 전력"은 그 연료로 전기를 만드는 발전·전력망(원자력·태양광·한전 등).
- 농업·농산물 관련 기사는 별도 카테고리 없이 전량 "소비재 & 리테일 (B2C)"로 분류.
- 기업의 치명적·혁신적 인사/노조 이슈(예: 노조 갈등)는 "Artificial Intelligence"가 아니라 "PMI / Operations"로 분류.
  단, 일반적인 조직 혁신·HR 이슈는 두 카테고리 모두에서 제외.
- 'DX를 위한 AI 도입' 류 기사는 "Artificial Intelligence"로 분류.
- "M&A / Strategic Investment" vs "Corporate Finance / Turnaround" vs "New Business / Business Building"
  vs "New Market Entry / Go-To-Market" (넷 다 해당 가능해 보이는 기사가 많으므로 아래 순서로 판단할 것):
  1. 계열사·자회사·보유 지분 등을 파는(매각) 기사는 인수 주체가 아니라 "매도자" 관점이므로
     "M&A / Strategic Investment"가 아니라 "Corporate Finance / Turnaround"(재무구조 조정)로 분류
     (예: "SK, 실트론 매각 이달 중 결정"은 SK의 재무구조 조정 결정이므로 Corporate Finance / Turnaround).
  2. 특정 기업의 지분을 사들이거나 인수·합병하는(매수) 기사만 "M&A / Strategic Investment".
     신규 시장·사업 진출이 "목적"이어도 지분 인수 형태가 아니면 이 카테고리가 아님
     (예: "한화그룹, 미국 AI 및 방산 시장 본격 진출"처럼 특정 대상 기업의 지분 인수가 아닌 진출
     발표는 M&A가 아니라 New Business).
  3. 기존 사업과 구별되는 신규 사업 영역·아이템·모델 자체를 새로 발굴·착수하는 기사(지역을 막론하고,
     기존에 하지 않던 사업/산업으로 진출하는 경우 포함)는 "New Business / Business Building".
  4. 기존에 하던 동일 사업을 해외/신규 지역·신규 채널·신규 고객층으로 넓히는 기사(예: 기존 제품을
     해외 유통사와 업무협약으로 해외에 파는 것)만 "New Market Entry / Go-To-Market".
"""

SUMMARY_LENGTH_RULE = """
요약 bullet 작성 규칙:
- 카테고리명이나 제목만 나열하는 짧은 구가 아니라, 실제 기사 내용(수치·주체·배경)을 반영한 완결된 문장으로 작성할 것.
- 문장당 40~80자 내외의 분량으로 작성할 것 (지나치게 짧은 요약 금지).
"""

RELEVANCE_RULES = """
기사 관련성 판단 기준 (전략 컨설턴트가 기업 활동을 분석하는 목적):
- 포함 대상: 기업의 신규 움직임(신규 전략 방향성·신제품·신시장 진출·사업 확장·신규 프로젝트·실적 발표 및 분석 등)을 다루는 기사.
- 포함 대상: 산업 전반의 구조·경쟁 구도·수요 변화를 다루는 동향 분석 기사.
- 포함 대상: 금리 변동, 정책·규제 변화, 전쟁·지정학적 리스크로 인한 유가·환율 변동 등 거시적 사건이라도,
  기업의 경영 판단·활동에 실질적 영향을 미치는 경우.
- 제외 대상: 개인·조직의 범죄·사기·소송 등 기업 경영 전략과 무관한 사건.
- 제외 대상: 기업의 사업화·제품화·투자와 직접 연결되지 않는 순수 학술·과학 연구 결과.
- 제외 대상: 연예 이슈 등 경영 분석과 무관한 뉴스.
- 판단이 애매하면 "전략 컨설턴트가 기업 활동 분석 자료로 쓸 수 있는 기사인가"를 기준으로 판단할 것.
"""


class ArticleClassification(BaseModel):
    index: int
    category: Optional[str]  # 허용된 카테고리명 중 하나, 관련 없으면 null


class ClassificationResult(BaseModel):
    classifications: list[ArticleClassification]


CLASSIFY_BATCH_SIZE = 40  # 한 번에 너무 많은 기사를 보내면 응답 JSON이 잘려 파싱 실패하므로 배치 분할


def _classify_batch(articles: list[dict], allowed_categories: list[str]) -> dict[int, Optional[str]]:
    articles_block = "\n".join(f'{a["index"]}. {a["title"]} — {a["description"][:200]}' for a in articles)
    categories_block = "\n".join(f"- {c}" for c in allowed_categories)

    prompt = f"""
다음은 뉴스 기사 목록이다. 각 기사를 아래 허용된 카테고리 중 하나로 분류하라.
어느 카테고리에도 맞지 않거나 노이즈(광고, 무관한 기사)이거나, 아래 관련성 기준의 제외 대상에 해당하면
category를 null로 하라.

{RELEVANCE_RULES}

{ROUTING_RULES}

허용된 카테고리:
{categories_block}

기사 목록 (번호. 제목 — 설명):
{articles_block}

각 기사 번호에 대해 정확히 하나의 분류 결과를 반환하라.
"""
    result = _generate_json(prompt, ClassificationResult)
    return {c.index: c.category for c in result.classifications}


def classify_articles(articles: list[dict], allowed_categories: list[str]) -> tuple[dict[int, Optional[str]], bool]:
    """articles: [{"index": int, "title": str, "description": str}, ...]

    반환: ({index: 카테고리명 또는 None}, 일부 배치라도 실패했는지 여부). 응답 JSON이 잘리는 것을 막기 위해
    CLASSIFY_BATCH_SIZE 단위로 나누고, 배치끼리는 서로 독립적이므로 동시에 호출한다.
    배치 하나가 실패해도(예: 일시적 503) 나머지 배치의 결과는 버리지 않고 최대한 살린다.
    """
    batches = [articles[i : i + CLASSIFY_BATCH_SIZE] for i in range(0, len(articles), CLASSIFY_BATCH_SIZE)]
    if not batches:
        return {}, False

    merged: dict[int, Optional[str]] = {}
    any_failed = False
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = [executor.submit(_classify_batch, batch, allowed_categories) for batch in batches]
        for future in as_completed(futures):
            try:
                merged.update(future.result())
            except Exception as exc:  # noqa: BLE001
                print(f"[gemini] 분류 배치 실패: {exc}")
                any_failed = True
    return merged, any_failed


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

{RELEVANCE_RULES}

카테고리당 기사 개수 규칙:
- 위 관련성 기준의 제외 대상에 해당하는 기사는 selected와 extra_topics 어디에도 포함하지 말고 완전히 무시할 것.
- 포함 대상 기사 중에서, 규모·변화 정도·산업 내 위치 등을 고려해 가장 핵심적이고 중요한 기사를 최대 3개까지 선택(selected)할 것.
- 선택되지 않은 포함 대상 기사 중 참고할 만한 것이 있으면 주제당 15~20자 이내로 extra_topics에 기재할 것 (없으면 빈 배열).

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
