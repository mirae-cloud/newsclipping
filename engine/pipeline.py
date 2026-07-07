"""전체 파이프라인 오케스트레이터 — 수집 → 분류 → 요약/인사이트 생성 → JSON 저장.

실행: python -m engine.pipeline
산출물: docs/data/economy.json, docs/data/domestic.json, docs/data/global.json (DATA_SCHEMA.md 참고)
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

from engine import categories, email_sender, gemini_client
from engine.sources import currents_news, ecos, fred, google_news, naver_news

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"

# 실행 중 Gemini 요약이 실패한(503 등 일시적 오류) 카테고리 목록을 기록해두는 파일.
# docs/ 는 GitHub Pages로 공개 서빙되므로, 내부 상태 파일은 그 바깥(저장소 루트)에 둔다.
FAILED_CATEGORIES_PATH = ROOT / ".failed_categories.json"

CATEGORY_WORKERS = 10  # 카테고리별 요약(Gemini 호출)을 동시에 처리할 스레드 수
# 구글 링크 해제는 반복 호출 시 구글 쪽에서 느려지는 경향이 관찰되어 낮은 동시 실행 수 유지
LINK_RESOLVE_WORKERS = 5

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


def _classify_and_group(candidates: list[dict], allowed_categories: list[str]) -> tuple[dict[str, list[dict]], bool]:
    """반환: (카테고리별 후보 목록, 분류가 일부라도 실패했는지 여부).

    분류가 실패한 카테고리는 후보가 0개로 남는데, 이는 '분류 실패로 못 채움'과 '원래 관련 기사가 없음'을
    구분할 수 없으므로, 호출부에서 classify_failed=True일 때 빈 카테고리를 재시도 대상에 포함시켜야 한다.
    """
    grouped: dict[str, list[dict]] = {c: [] for c in allowed_categories}
    if not candidates:
        return grouped, False

    indexed = [{"index": i, "title": c["title"], "description": c["description"]} for i, c in enumerate(candidates)]
    try:
        assignments, classify_failed = gemini_client.classify_articles(indexed, allowed_categories)
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] 분류 실패: {exc}")
        return grouped, True

    for i, candidate in enumerate(candidates):
        category = assignments.get(i)
        if category and category in grouped:
            grouped[category].append(candidate)

    return grouped, classify_failed


def _empty_block() -> dict:
    return {"sub_summary_bullets": [], "articles": [], "extra_topics": []}


def _build_category_block(category_name: str, cat_candidates: list[dict]) -> tuple[dict, bool]:
    """Gemini 요약만 수행하고 링크 해제는 하지 않는다 — 구글 리다이렉트 해제는 느려서(기사당 수초~수십초)
    전체를 모은 뒤 _finalize_articles()에서 한꺼번에 병렬로 처리한다. articles의 url/id는 그때 확정된다.

    반환: (block, success). candidates가 애초에 없어서 빈 것과, Gemini 호출 자체가 실패해서 빈 것을 구분한다
    (후자만 '실패'로 기록해 나중에 --retry-failed로 재시도할 수 있게 한다).
    """
    if not cat_candidates:
        return _empty_block(), True

    indexed = [{"index": i, "title": c["title"], "description": c["description"]} for i, c in enumerate(cat_candidates)]
    try:
        summary = gemini_client.summarize_category(category_name, indexed)
    except Exception as exc:  # noqa: BLE001
        print(f"[gemini] '{category_name}' 요약 실패: {exc}")
        return _empty_block(), False

    articles = []
    for sel in summary.selected:
        if sel.index >= len(cat_candidates):
            continue
        candidate = cat_candidates[sel.index]
        articles.append(
            {
                "_raw_source": candidate.get("raw_source"),
                "url": candidate["url"],
                "title": sel.title,
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
    }, True


def _build_category_blocks_parallel(names: list[str], grouped: dict[str, list[dict]]) -> tuple[dict[str, dict], list[str]]:
    """카테고리별 Gemini 요약은 서로 독립적이므로 동시에 호출해 실행 시간을 줄인다.

    반환: (블록 딕셔너리, 실패한 카테고리명 목록).
    """
    blocks: dict[str, dict] = {}
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=CATEGORY_WORKERS) as executor:
        future_map = {executor.submit(_build_category_block, name, grouped[name]): name for name in names}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                blocks[name], success = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"[gemini] '{name}' 요약 스레드 실패: {exc}")
                blocks[name], success = _empty_block(), False
            if not success:
                failed.append(name)
    return blocks, failed


def _finalize_articles(category_blocks: dict[str, dict]) -> None:
    """모든 카테고리의 기사 중 구글 소스인 것만 병렬로 링크를 해제하고, 전체 기사의 id를 확정한다 (in-place)."""
    to_resolve = [a for block in category_blocks.values() for a in block["articles"] if a["_raw_source"] == "google"]

    if to_resolve:
        with ThreadPoolExecutor(max_workers=LINK_RESOLVE_WORKERS) as executor:
            future_map = {executor.submit(google_news.resolve_link, a["url"]): a for a in to_resolve}
            for future in as_completed(future_map):
                article = future_map[future]
                try:
                    article["url"] = future.result()
                except Exception:  # noqa: BLE001 — 실패 시 구글 리다이렉트 링크를 그대로 둔다
                    pass

    for block in category_blocks.values():
        for article in block["articles"]:
            article["id"] = _make_id(article["url"])
            del article["_raw_source"]


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


def _mark_classify_failures(classify_failed: bool, allowed: list[str], blocks: dict[str, dict], failed: list[str]) -> list[str]:
    """분류 단계 자체가 실패하면 그 여파로 후보 0개가 된 카테고리도 재시도 대상에 포함시킨다
    ('분류 실패로 못 채움'과 '원래 관련 기사가 없음'을 구분할 수 없어 안전하게 재시도 대상에 넣는다)."""
    if classify_failed:
        for name in allowed:
            if not blocks[name]["articles"] and name not in failed:
                failed.append(name)
    return failed


def _build_source_json(source: str) -> tuple[dict, list[str]]:
    if source == "domestic":
        raw = _collect_domestic_raw({**categories.INDUSTRY_KEYWORDS, **categories.BUSINESS_KEYWORDS})
    else:
        raw = _collect_global_raw({**categories.INDUSTRY_KEYWORDS_EN, **categories.BUSINESS_KEYWORDS_EN})

    allowed = categories.INDUSTRY_CATEGORIES + categories.BUSINESS_CATEGORIES
    grouped, classify_failed = _classify_and_group(raw, allowed)

    category_blocks, failed = _build_category_blocks_parallel(allowed, grouped)
    failed = _mark_classify_failures(classify_failed, allowed, category_blocks, failed)
    _finalize_articles(category_blocks)

    industry_json = {name: category_blocks[name] for name in categories.INDUSTRY_CATEGORIES}
    business_json = {name: category_blocks[name] for name in categories.BUSINESS_CATEGORIES}

    summary_json = _build_overall_summary({**industry_json, **business_json})

    result = {
        "date": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary_json,
        "categories": {"industry": industry_json, "business": business_json},
    }
    return result, failed


def _build_economy_news_json() -> tuple[dict, list[str]]:
    raw = _collect_domestic_raw(categories.ECONOMY_KEYWORDS) + _collect_global_raw(categories.ECONOMY_KEYWORDS_EN)
    raw = _dedup(raw)

    allowed = categories.ECONOMY_KEYWORD_GROUPS
    grouped, classify_failed = _classify_and_group(raw, allowed)

    keyword_groups_json, failed = _build_category_blocks_parallel(allowed, grouped)
    failed = _mark_classify_failures(classify_failed, allowed, keyword_groups_json, failed)
    _finalize_articles(keyword_groups_json)
    summary_json = _build_overall_summary(keyword_groups_json)

    return {"summary": summary_json, "keyword_groups": keyword_groups_json}, failed


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


def _build_economy_json() -> tuple[dict, list[str]]:
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

    news_json, failed = _build_economy_news_json()
    result = {
        "date": date.today().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "indicators": indicators,
        "news": news_json,
    }
    return result, failed


# ---------- 실패 카테고리 재시도 ----------


def _category_kind(name: str) -> str:
    return "industry" if name in categories.INDUSTRY_CATEGORIES else "business"


def _save_failed_categories(failures: dict[str, list[str]]) -> None:
    non_empty = {k: v for k, v in failures.items() if v}
    if non_empty:
        FAILED_CATEGORIES_PATH.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(len(v) for v in failures.values())
        print(f"[retry] 실패한 카테고리 {total}개를 {FAILED_CATEGORIES_PATH.name}에 기록함 — "
              f"나중에 'python -m engine.pipeline --retry-failed'로 재시도 가능.")
    elif FAILED_CATEGORIES_PATH.exists():
        FAILED_CATEGORIES_PATH.unlink()


def _retry_source_categories(source: str, names: list[str]) -> list[str]:
    """source(economy/domestic/global)에서 실패했던 카테고리 names만 재수집·재분류·재요약해서
    기존 docs/data/{source}.json에 해당 카테고리만 병합한다. 여전히 실패한 카테고리명을 반환한다.
    """
    json_path = DATA_DIR / f"{source}.json"
    if not json_path.exists():
        print(f"[retry] {json_path.name}가 없어 재시도할 수 없습니다. 전체 파이프라인을 먼저 실행하세요.")
        return names

    existing = json.loads(json_path.read_text(encoding="utf-8"))

    if source == "economy":
        kr_map = {n: categories.ECONOMY_KEYWORDS[n] for n in names}
        en_map = {n: categories.ECONOMY_KEYWORDS_EN[n] for n in names}
        raw = _dedup(_collect_domestic_raw(kr_map) + _collect_global_raw(en_map))
        grouped, classify_failed = _classify_and_group(raw, names)
        blocks, failed = _build_category_blocks_parallel(names, grouped)
        failed = _mark_classify_failures(classify_failed, names, blocks, failed)
        _finalize_articles(blocks)
        for name in names:
            existing["news"]["keyword_groups"][name] = blocks[name]
    else:
        industry_kw = categories.INDUSTRY_KEYWORDS if source == "domestic" else categories.INDUSTRY_KEYWORDS_EN
        business_kw = categories.BUSINESS_KEYWORDS if source == "domestic" else categories.BUSINESS_KEYWORDS_EN
        keyword_map = {n: (industry_kw.get(n) or business_kw.get(n)) for n in names}
        collect_fn = _collect_domestic_raw if source == "domestic" else _collect_global_raw
        raw = collect_fn(keyword_map)
        grouped, classify_failed = _classify_and_group(raw, names)
        blocks, failed = _build_category_blocks_parallel(names, grouped)
        failed = _mark_classify_failures(classify_failed, names, blocks, failed)
        _finalize_articles(blocks)
        for name in names:
            existing["categories"][_category_kind(name)][name] = blocks[name]

    json_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[retry] {source}: {len(names) - len(failed)}/{len(names)}개 성공 — {json_path.name}에 반영함.")
    return failed


def retry_failed():
    """직전 실행에서 실패한 카테고리만 다시 수집·분류·요약해 기존 JSON에 채워 넣는다.

    실행: python -m engine.pipeline --retry-failed
    전체 요약(overall summary)은 다시 계산하지 않는다 — 실패했던 개별 카테고리만 채우는 용도.
    """
    sys.stdout.reconfigure(line_buffering=True)

    if not FAILED_CATEGORIES_PATH.exists():
        print("재시도할 실패 카테고리 기록이 없습니다.")
        return

    failures = json.loads(FAILED_CATEGORIES_PATH.read_text(encoding="utf-8"))
    still_failed: dict[str, list[str]] = {}
    for source in ["economy", "domestic", "global"]:
        names = failures.get(source, [])
        if not names:
            continue
        print(f"[retry] {source}: {names}")
        still_failed[source] = _retry_source_categories(source, names)

    _save_failed_categories(still_failed)
    print("재시도 완료.")


def main():
    sys.stdout.reconfigure(line_buffering=True)  # 파일로 리다이렉트해도 진행 로그가 즉시 보이도록
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_start = time.monotonic()

    print("[1/3] 경제지표·경제 뉴스 수집 중...")
    t0 = time.monotonic()
    economy_json, economy_failed = _build_economy_json()
    print(f"  -> {time.monotonic() - t0:.1f}초")

    print("[2/3] 국내 뉴스 수집 중...")
    t0 = time.monotonic()
    domestic_json, domestic_failed = _build_source_json("domestic")
    print(f"  -> {time.monotonic() - t0:.1f}초")

    print("[3/3] 글로벌 뉴스 수집 중...")
    t0 = time.monotonic()
    global_json, global_failed = _build_source_json("global")
    print(f"  -> {time.monotonic() - t0:.1f}초")

    (DATA_DIR / "economy.json").write_text(json.dumps(economy_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "domestic.json").write_text(json.dumps(domestic_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "global.json").write_text(json.dumps(global_json, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"완료 — {DATA_DIR} 에 저장됨.")

    _save_failed_categories({"economy": economy_failed, "domestic": domestic_failed, "global": global_failed})

    print("이메일 발송 중...")
    try:
        html_body = email_sender.build_email_html(economy_json, domestic_json, global_json)
        email_sender.send_email(html_body, subject=f"뉴스클리핑 {economy_json['date']}")
        print("이메일 발송 완료.")
    except Exception as exc:  # noqa: BLE001
        print(f"[email] 발송 실패: {exc}")

    _print_usage_summary()
    print(f"\n총 실행 시간: {time.monotonic() - run_start:.1f}초")


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
    if "--retry-failed" in sys.argv:
        retry_failed()
    else:
        main()
