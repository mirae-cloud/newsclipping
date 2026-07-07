"""전체 파이프라인 오케스트레이터 — 수집 → 분류 → 요약/인사이트 생성 → JSON 저장.

실행: python -m engine.pipeline
산출물: docs/data/economy.json, docs/data/domestic.json, docs/data/global.json (DATA_SCHEMA.md 참고)
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from engine import categories, email_sender, gemini_client
from engine.sources import currents_news, ecos, fred, google_news, naver_news

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"

# 카테고리당 대표 키워드 몇 개만 사용 (호출량/실행시간 절약). 노이즈가 많으면 조정할 것.
KEYWORDS_PER_CATEGORY = 2


def _make_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _dedup(candidates: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for c in candidates:
        key = (c["title"].strip(), c["url"].strip())
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
    return result


# ---------- 수집 ----------


MIN_NAVER_RESULTS = 5  # 네이버(메인) 결과가 이 개수 미만이면 구글(보충)로 보완


def _collect_domestic_raw(keyword_map: dict[str, list[str]]) -> list[dict]:
    """네이버(메인) + 구글 뉴스(보충)로 후보 기사를 모은다.

    네이버는 원문 링크를 바로 주기 때문에 리다이렉트 해제가 필요 없어 훨씬 빠르다.
    구글은 결과가 부족할 때만 보충 호출하며, 링크 리다이렉트 해제는 하지 않는다
    (gnewsdecoder 왕복이 느려 최종 선택된 기사에 한해 나중에 처리).
    """
    candidates = []
    for cat_name, keywords in keyword_map.items():
        for kw in keywords[:KEYWORDS_PER_CATEGORY]:
            try:
                n_articles = naver_news.filter_last_24h(naver_news.search_news(kw, max_results=20))
            except Exception as exc:  # noqa: BLE001
                print(f"[naver_news] '{kw}' 검색 실패: {exc}")
                n_articles = []

            for a in n_articles:
                candidates.append(
                    {
                        "title": a.title,
                        "description": a.description,
                        "url": a.original_link,
                        "published_at": a.pub_date,
                        "hint_category": cat_name,
                        "raw_source": "naver",
                    }
                )

            if len(n_articles) >= MIN_NAVER_RESULTS:
                continue  # 네이버만으로 충분하면 느린 구글 보충 호출은 건너뜀

            try:
                g_articles = google_news.filter_last_24h(google_news.search_news(kw, resolve_links=False))
            except Exception as exc:  # noqa: BLE001
                print(f"[google_news] '{kw}' 검색 실패: {exc}")
                g_articles = []

            for a in g_articles:
                candidates.append(
                    {
                        "title": a.title,
                        "description": a.description,
                        "url": a.link,
                        "published_at": a.pub_date,
                        "hint_category": cat_name,
                        "raw_source": "google",
                    }
                )

    return _dedup(candidates)


def _collect_global_raw(keyword_map: dict[str, list[str]]) -> list[dict]:
    candidates = []
    for cat_name, keywords in keyword_map.items():
        for kw in keywords[:KEYWORDS_PER_CATEGORY]:
            try:
                c_articles = currents_news.filter_last_24h(currents_news.search_news(kw, language="en"))
            except Exception as exc:  # noqa: BLE001
                print(f"[currents] '{kw}' 검색 실패: {exc}")
                c_articles = []

            for a in c_articles:
                candidates.append(
                    {
                        "title": a.title,
                        "description": a.description,
                        "url": a.url,
                        "published_at": a.pub_date,
                        "hint_category": cat_name,
                        "raw_source": "currents",
                    }
                )

    return _dedup(candidates)


# ---------- 분류 + 카테고리별 요약 ----------


def _classify_and_group(candidates: list[dict], allowed_categories: list[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {c: [] for c in allowed_categories}
    if not candidates:
        return grouped

    indexed = [{"index": i, "title": c["title"], "description": c["description"]} for i, c in enumerate(candidates)]
    try:
        assignments = gemini_client.classify_articles(indexed, allowed_categories)
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] 분류 실패: {exc}")
        return grouped

    for i, candidate in enumerate(candidates):
        category = assignments.get(i)
        if category and category in grouped:
            grouped[category].append(candidate)

    return grouped


def _resolve_url_if_google(candidate: dict) -> str:
    if candidate.get("raw_source") == "google":
        return google_news.resolve_link(candidate["url"])
    return candidate["url"]


def _build_category_block(category_name: str, cat_candidates: list[dict]) -> dict:
    if not cat_candidates:
        return {"sub_summary_bullets": [], "articles": [], "extra_topics": []}

    indexed = [{"index": i, "title": c["title"], "description": c["description"]} for i, c in enumerate(cat_candidates)]
    try:
        summary = gemini_client.summarize_category(category_name, indexed)
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] '{category_name}' 요약 실패: {exc}")
        return {"sub_summary_bullets": [], "articles": [], "extra_topics": []}

    articles = []
    for sel in summary.selected:
        if sel.index >= len(cat_candidates):
            continue
        candidate = cat_candidates[sel.index]
        url = _resolve_url_if_google(candidate)
        articles.append(
            {
                "id": _make_id(url),
                "title": sel.title,
                "url": url,
                "bullets": sel.bullets,
                "insight": sel.insight,
                "published_at": candidate["published_at"].isoformat(),
                "category": category_name,
            }
        )

    return {
        "sub_summary_bullets": summary.sub_summary_bullets,
        "articles": articles,
        "extra_topics": summary.extra_topics,
    }


def _build_overall_summary(category_blocks: dict[str, dict]) -> dict:
    top_articles = []
    for name, block in category_blocks.items():
        if block["articles"]:
            top = block["articles"][0]
            top_articles.append({"category": name, "title": top["title"], "description": " ".join(top["bullets"])})

    if not top_articles:
        return {"overall_bullets": [], "headlines": []}

    try:
        overall = gemini_client.generate_overall_summary(top_articles)
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] 전체 요약 실패: {exc}")
        return {"overall_bullets": [], "headlines": []}

    return {
        "overall_bullets": overall.overall_bullets,
        "headlines": [{"category": h.category, "headline": h.headline} for h in overall.headlines],
    }


def _build_source_json(source: str) -> dict:
    if source == "domestic":
        raw = _collect_domestic_raw({**categories.INDUSTRY_KEYWORDS, **categories.BUSINESS_KEYWORDS})
    else:
        raw = _collect_global_raw({**categories.INDUSTRY_KEYWORDS_EN, **categories.BUSINESS_KEYWORDS_EN})

    allowed = categories.INDUSTRY_CATEGORIES + categories.BUSINESS_CATEGORIES
    grouped = _classify_and_group(raw, allowed)

    industry_json = {name: _build_category_block(name, grouped[name]) for name in categories.INDUSTRY_CATEGORIES}
    business_json = {name: _build_category_block(name, grouped[name]) for name in categories.BUSINESS_CATEGORIES}

    summary_json = _build_overall_summary({**industry_json, **business_json})

    return {
        "date": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary_json,
        "categories": {"industry": industry_json, "business": business_json},
    }


def _build_economy_news_json() -> dict:
    raw = _collect_domestic_raw(categories.ECONOMY_KEYWORDS) + _collect_global_raw(categories.ECONOMY_KEYWORDS_EN)
    raw = _dedup(raw)

    allowed = categories.ECONOMY_KEYWORD_GROUPS
    grouped = _classify_and_group(raw, allowed)

    keyword_groups_json = {name: _build_category_block(name, grouped[name]) for name in allowed}
    summary_json = _build_overall_summary(keyword_groups_json)

    return {"summary": summary_json, "keyword_groups": keyword_groups_json}


# ---------- 경제지표 ----------


def _simple_avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _indicator_block_monthly(points: list) -> dict:
    if not points:
        return {"latest": None, "avg_1m": None, "avg_1y": None, "history_5y": []}
    latest = points[-1].value
    avg_1y = _simple_avg([p.value for p in points[-12:]])
    return {
        "latest": latest,
        "avg_1m": latest,  # 월별 발표값이라 '1달 평균'은 최신 발표값과 동일 (지시서 4-1)
        "avg_1y": avg_1y,
        "history_5y": [{"date": p.date_str, "value": p.value} for p in points],
    }


def _indicator_block_daily(points: list) -> dict:
    if not points:
        return {"latest": None, "avg_1m": None, "avg_1y": None, "history_5y": []}
    return {
        "latest": points[-1].value,
        "avg_1m": _simple_avg([p.value for p in points[-30:]]),
        "avg_1y": _simple_avg([p.value for p in points[-365:]]),
        "history_5y": [{"date": p.date_str, "value": p.value} for p in points],
    }


def _normalize_ecos_time(time_str: str, cycle: str) -> str:
    if cycle == "M":
        return f"{time_str[:4]}-{time_str[4:6]}-01"
    if cycle == "D":
        return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}"
    return time_str


def _build_economy_json() -> dict:
    kr_rate = ecos.fetch_policy_rate_kr()
    for p in kr_rate:
        p.date_str = _normalize_ecos_time(p.date_str, "M")

    kr_cpi = ecos.fetch_cpi_kr()
    for p in kr_cpi:
        p.date_str = _normalize_ecos_time(p.date_str, "M")

    fx = ecos.fetch_fx_usd_krw()
    for p in fx:
        p.date_str = _normalize_ecos_time(p.date_str, "D")

    us_rate = fred.fetch_policy_rate_us()
    us_cpi = fred.fetch_cpi_us()

    indicators = {
        "policy_rate": {
            "kr": _indicator_block_monthly(kr_rate),
            "us": _indicator_block_daily(us_rate),  # DFEDTARU는 일단위로 발표되는 시리즈 (값은 FOMC 회의 때만 바뀜)
        },
        "cpi": {
            "kr": _indicator_block_monthly(kr_cpi),
            "us": _indicator_block_monthly(us_cpi),
        },
        "fx_usd_krw": _indicator_block_daily(fx),
    }

    return {
        "date": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "indicators": indicators,
        "news": _build_economy_news_json(),
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/3] 경제지표·경제 뉴스 수집 중...")
    economy_json = _build_economy_json()

    print("[2/3] 국내 뉴스 수집 중...")
    domestic_json = _build_source_json("domestic")

    print("[3/3] 글로벌 뉴스 수집 중...")
    global_json = _build_source_json("global")

    (DATA_DIR / "economy.json").write_text(json.dumps(economy_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "domestic.json").write_text(json.dumps(domestic_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "global.json").write_text(json.dumps(global_json, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료 — {DATA_DIR} 에 저장됨.")

    print("이메일 발송 중...")
    try:
        html_body = email_sender.build_email_html(economy_json, domestic_json, global_json)
        email_sender.send_email(html_body, subject=f"뉴스클리핑 {economy_json['date']}")
        print("이메일 발송 완료.")
    except Exception as exc:  # noqa: BLE001
        print(f"[email] 발송 실패: {exc}")

    _print_usage_summary()


# gemini-3.5-flash 가격(2026-07 기준, 확인 필요 — 가격 페이지에서 재확인할 것): $1.50/1M input, $9/1M output.
# 'thoughts' 토큰(추론)은 출력 토큰과 동일하게 과금되는 것으로 간주.
PRICE_PER_M_INPUT_USD = 1.50
PRICE_PER_M_OUTPUT_USD = 9.00


def _print_usage_summary():
    usage = gemini_client.get_usage_summary()
    output_tokens = usage["candidates"] + usage["thoughts"]
    input_cost = usage["prompt"] / 1_000_000 * PRICE_PER_M_INPUT_USD
    output_cost = output_tokens / 1_000_000 * PRICE_PER_M_OUTPUT_USD
    print("\n--- Gemini 토큰 사용량 (이번 실행) ---")
    print(f"호출 횟수: {usage['calls']}")
    print(f"입력 토큰: {usage['prompt']:,}")
    print(f"출력 토큰(응답 {usage['candidates']:,} + 추론 {usage['thoughts']:,}): {output_tokens:,}")
    print(f"총 토큰: {usage['total']:,}")
    print(f"예상 비용(가격은 확인 필요): 입력 ${input_cost:.4f} + 출력 ${output_cost:.4f} = 약 ${input_cost + output_cost:.4f}")


if __name__ == "__main__":
    main()
