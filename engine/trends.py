"""누적 산업 동향 — 일별 선별 기사 아카이브(AI 호출 없음) + 월별 요약/6개월 종합(trends.json).

구조(가볍게 유지하기 위한 원칙):
- 매일: 그날 선별된 기사 제목·extra_topics만 archive/YYYY-MM.jsonl에 덧붙인다(웹으로 서빙되지 않음).
- 월 단위: 끝난 달마다 카테고리별 월 요약을 한 번 만들고, 월 요약이 바뀐 카테고리만 6개월 종합을 다시 만든다.
- 이 모듈의 실패는 매일 뉴스 발송에 영향을 주지 않도록 호출부(pipeline.main)에서 try/except로 감싼다.

CLI: python -m engine.trends --backfill   (Git 이력에서 아카이브 복원)
     python -m engine.trends --rebuild    (월 요약·종합 생성/갱신)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from engine import categories, gemini_client

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"
TRENDS_PATH = ROOT / "docs" / "data" / "trends.json"

TRENDS_VERSION = 1
KEEP_MONTHS = 6  # trends.json에는 최근 6개월분 월 요약만 둔다(더 오래된 건 아카이브에서 다시 만들 수 있음)
MIN_DAYS_CLOSED_MONTH = 5  # 끝난 달이라도 수집된 날이 이보다 적으면 요약하지 않고 '공백'으로 표시
MIN_DAYS_PARTIAL_MONTH = 3
PARTIAL_REFRESH_DAYS = 7  # 진행 중인 달 요약은 입력이 바뀌어도 이 간격 안에는 다시 만들지 않는다
DAILY_MAX_CALLS = 60
DAILY_TIME_BUDGET_SEC = 900

# 과거 스냅샷에 남아 있는 옛 카테고리명 → 현재 이름 (아카이브는 이름을 그대로 저장하므로 쓰는 시점에 정규화한다)
CATEGORY_RENAMES = {"Go-To-Market": "New Market Entry / Go-To-Market"}

CATEGORY_ORDER = categories.INDUSTRY_CATEGORIES + categories.BUSINESS_CATEGORIES
_VALID = set(CATEGORY_ORDER)
_ORDER_INDEX = {name: i for i, name in enumerate(CATEGORY_ORDER)}


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _day_blocks(source_json: dict, unknown: set[str]) -> dict[str, dict]:
    """domestic/global JSON에서 {현재 카테고리명: block}을 뽑는다(산업군·Business만, 경제 키워드는 제외)."""
    blocks: dict[str, dict] = {}
    for kind in ("industry", "business"):
        for name, block in (source_json.get("categories", {}).get(kind, {}) or {}).items():
            name = CATEGORY_RENAMES.get(name, name)
            if name in _VALID:
                blocks[name] = block
            else:
                unknown.add(name)
    return blocks


def _archive_path(date: str) -> Path:
    return ARCHIVE_DIR / f"{date[:7]}.jsonl"


def _read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def archive_day(date: str, domestic: dict, global_: dict) -> int:
    """그날 선별된 기사(국내·글로벌)의 제목과 extra_topics를 (날짜, 카테고리)당 한 줄로 기록한다.

    같은 날짜를 다시 기록하면 기존 줄을 교체한다(수동 재실행에도 멱등). 기사가 하나도 없는 날(수집 실패)은
    기록하지 않고 기존 기록도 건드리지 않는다. 반환값은 기록한 줄 수.
    """
    unknown: set[str] = set()
    kr = _day_blocks(domestic, unknown)
    gl = _day_blocks(global_, unknown)
    if unknown:
        print(f"[trends] 현재 분류 체계에 없는 카테고리 제외: {sorted(unknown)}")

    new_rows = []
    for name in CATEGORY_ORDER:
        kr_block, gl_block = kr.get(name, {}), gl.get(name, {})
        kr_titles = [a["title"] for a in kr_block.get("articles", [])]
        gl_titles = [a["title"] for a in gl_block.get("articles", [])]
        extras = list(kr_block.get("extra_topics", []))[:10] + list(gl_block.get("extra_topics", []))[:10]
        if kr_titles or gl_titles or extras:
            new_rows.append({"d": date, "c": name, "kr": kr_titles, "gl": gl_titles, "ex": extras})

    if not any(r["kr"] or r["gl"] for r in new_rows):
        return 0

    path = _archive_path(date)
    rows = [r for r in _read_lines(path) if r["d"] != date] + new_rows
    rows.sort(key=lambda r: (r["d"], _ORDER_INDEX.get(r["c"], 999)))
    _atomic_write(path, "\n".join(_compact(r) for r in rows) + "\n")
    return len(new_rows)


def list_months() -> list[str]:
    return sorted(p.stem for p in ARCHIVE_DIR.glob("*.jsonl")) if ARCHIVE_DIR.exists() else []


def load_month(ym: str) -> dict[str, list[dict]]:
    """{카테고리: [그 달의 일별 레코드(날짜순)]}"""
    by_cat: dict[str, list[dict]] = {}
    for row in _read_lines(ARCHIVE_DIR / f"{ym}.jsonl"):
        by_cat.setdefault(row["c"], []).append(row)
    return by_cat


def format_days_text(records: list[dict]) -> str:
    """월 요약 프롬프트 입력: 날짜별 한 줄('MM-DD KR: 제목 / 제목 || GL: 제목 || 기타: 주제, 주제')."""
    lines = []
    for r in records:
        parts = []
        if r["kr"]:
            parts.append("KR: " + " / ".join(r["kr"]))
        if r["gl"]:
            parts.append("GL: " + " / ".join(r["gl"]))
        if r["ex"]:
            parts.append("기타: " + ", ".join(r["ex"]))
        lines.append(f'{r["d"][5:]} ' + " || ".join(parts))
    return "\n".join(lines)


# ---------- 백필 (Git 이력에서 복원) ----------


def _git_show_json(sha: str, relpath: str) -> dict | None:
    result = subprocess.run(["git", "show", f"{sha}:{relpath}"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _has_articles(source_json: dict) -> bool:
    for kind in ("industry", "business"):
        for block in (source_json.get("categories", {}).get(kind, {}) or {}).values():
            if block.get("articles"):
                return True
    return False


def backfill() -> None:
    """자동 데이터 갱신 커밋(github-actions)을 훑어 날짜당 마지막(기사가 있는) 스냅샷을 아카이브에 기록한다."""
    shas = subprocess.run(
        ["git", "log", "--reverse", "--format=%H", "--author=github-actions", "--", "docs/data/domestic.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    by_date: dict[str, tuple[dict, dict]] = {}
    for sha in shas:
        dom = _git_show_json(sha, "docs/data/domestic.json")
        glo = _git_show_json(sha, "docs/data/global.json") or {}
        if not dom or "date" not in dom:
            continue
        date = dom["date"]
        if date in by_date and _has_articles(by_date[date][0]) and not _has_articles(dom):
            continue  # 같은 날 뒤늦은 빈 재실행이 앞선 정상 스냅샷을 덮어쓰지 않게 한다
        by_date[date] = (dom, glo)

    written_days = skipped_days = 0
    for date in sorted(by_date):
        dom, glo = by_date[date]
        if archive_day(date, dom, glo):
            written_days += 1
        else:
            skipped_days += 1
    print(f"[trends] 백필 완료: {written_days}일 기록, 기사 없는 {skipped_days}일 건너뜀 (스냅샷 날짜 {len(by_date)}개)")


# ---------- 월 요약 · 6개월 종합 (trends.json) ----------


def _today_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


_failure_logs = 0


def _log_failure(msg: str) -> None:
    """전부 실패하는 상황에서 로그가 수백 줄 쏟아지지 않도록 처음 3건만 출력한다(건수는 마지막 요약에 나옴)."""
    global _failure_logs
    _failure_logs += 1
    if _failure_logs <= 3:
        print(msg)


def _kind(category: str) -> str:
    return "industry" if category in categories.INDUSTRY_CATEGORIES else "business"


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _load_trends() -> dict:
    if TRENDS_PATH.exists():
        try:
            data = json.loads(TRENDS_PATH.read_text(encoding="utf-8"))
            if data.get("version") == TRENDS_VERSION:
                return data
        except json.JSONDecodeError:
            pass
    return {"version": TRENDS_VERSION, "generated_at": None, "categories": {"industry": {}, "business": {}}}


def _entry(data: dict, category: str) -> dict:
    return data["categories"][_kind(category)].setdefault(category, {"trend": None, "months": {}})


def _digests_text(months: dict[str, dict]) -> tuple[str, list[str]]:
    """종합 입력으로 쓸 월 요약(요약이 있는 달만, 오래된 달부터)과 사용한 달 목록."""
    used = [ym for ym in sorted(months) if months[ym].get("bullets")][-KEEP_MONTHS:]
    lines = [
        f'{ym} ({months[ym]["n_days"]}일): '
        + " / ".join(months[ym]["bullets"])
        + " || 주제: "
        + ", ".join(months[ym]["themes"])
        for ym in used
    ]
    return "\n".join(lines), used


def update(
    today: str | None = None,
    force: bool = False,
    max_calls: int | None = DAILY_MAX_CALLS,
    time_budget_sec: float = DAILY_TIME_BUDGET_SEC,
) -> dict:
    """아카이브를 읽어 월 요약과 6개월 종합을 만들고 trends.json에 저장한다.

    - 끝난 달: 수집 일수가 충분하면 월 요약을 한 번 만든다(입력 해시가 같으면 다시 만들지 않음).
    - 진행 중인 달: '현재까지' 요약을 입력이 바뀌고 마지막 갱신 후 7일이 지났을 때만 갱신한다.
    - 월 요약이 바뀐 카테고리(또는 종합이 없는 카테고리)만 6개월 종합을 다시 만든다.
    - 카테고리별 실패는 기존 값을 유지한 채 다음 실행에서 다시 시도한다. 변경이 없으면 파일을 쓰지 않는다.
    """
    global _failure_logs
    _failure_logs = 0
    today = today or _today_kst()
    cur_ym = today[:7]
    data = _load_trends()
    deadline = time.monotonic() + time_budget_sec
    stats = {"digests": 0, "syntheses": 0, "failed": 0, "gap_months": 0}
    changed = False

    # --- 1) 월 요약 ---
    tasks = []  # (category, ym, text, n_days, hash, partial)
    for ym in list_months():
        month_recs = load_month(ym)
        closed = ym < cur_ym
        for cat in CATEGORY_ORDER:
            recs = month_recs.get(cat, [])
            n_days = len(recs)
            text = format_days_text(recs)
            h = _sha1(text)
            entry = _entry(data, cat)["months"].get(ym)
            if closed:
                if n_days < MIN_DAYS_CLOSED_MONTH:
                    gap = {"gap": True, "n_days": n_days, "bullets": [], "themes": [], "input_hash": h}
                    if entry != gap and n_days > 0:
                        _entry(data, cat)["months"][ym] = gap
                        stats["gap_months"] += 1
                        changed = True
                    continue
                if not force and entry and entry.get("input_hash") == h and not entry.get("partial") and entry.get("bullets"):
                    continue
            else:
                if n_days < MIN_DAYS_PARTIAL_MONTH:
                    continue
                if not force and entry and entry.get("input_hash") == h:
                    continue
                if not force and entry and entry.get("updated") and _days_between(entry["updated"], today) < PARTIAL_REFRESH_DAYS:
                    continue
            tasks.append((cat, ym, text, n_days, h, not closed))

    if max_calls is not None:
        tasks = tasks[:max_calls]

    def run_digest(task):
        cat, ym, text, n_days, h, partial = task
        if time.monotonic() > deadline:
            return task, None
        try:
            d = gemini_client.summarize_month(cat, ym, text, n_days, partial)
            return task, d
        except Exception as exc:  # noqa: BLE001
            _log_failure(f"[trends] '{cat}' {ym} 월 요약 실패: {exc}")
            return task, "failed"

    changed_cats: set[str] = set()
    with ThreadPoolExecutor(max_workers=gemini_client.PARALLEL_WORKERS) as executor:
        for task, d in executor.map(run_digest, tasks):
            cat, ym, _text, n_days, h, partial = task
            if d is None:
                continue  # 시간 예산 초과 — 다음 실행에서 이어서 처리
            if d == "failed":
                stats["failed"] += 1
                continue
            _entry(data, cat)["months"][ym] = {
                "bullets": d.bullets,
                "themes": d.themes,
                "n_days": n_days,
                "gap": False,
                "partial": partial,
                "input_hash": h,
                "updated": today,
            }
            changed_cats.add(cat)
            stats["digests"] += 1
            changed = True

    # --- 2) 6개월 종합 ---
    synth_tasks = []  # (category, text, used_months)
    for cat in CATEGORY_ORDER:
        entry = _entry(data, cat)
        text, used = _digests_text(entry["months"])
        if len(used) < 2:
            continue
        h = _sha1(text)
        trend = entry.get("trend")
        if not force and cat not in changed_cats and trend and trend.get("input_hash") == h:
            continue
        synth_tasks.append((cat, text, used, h))

    def run_synth(task):
        cat, text, used, h = task
        if time.monotonic() > deadline:
            return task, None
        try:
            return task, gemini_client.synthesize_trend(cat, text, len(used))
        except Exception as exc:  # noqa: BLE001
            _log_failure(f"[trends] '{cat}' 6개월 종합 실패: {exc}")
            return task, "failed"

    with ThreadPoolExecutor(max_workers=gemini_client.PARALLEL_WORKERS) as executor:
        for task, t in executor.map(run_synth, synth_tasks):
            cat, text, used, h = task
            if t is None:
                continue
            if t == "failed":
                stats["failed"] += 1
                continue
            records = [r for ym in used for r in load_month(ym).get(cat, [])]
            _entry(data, cat)["trend"] = {
                "headline": t.headline,
                "bullets": t.bullets,
                "themes": t.themes,
                "months_covered": len(used),
                "from": records[0]["d"] if records else None,
                "to": records[-1]["d"] if records else None,
                "as_of": today,
                "input_hash": h,
            }
            stats["syntheses"] += 1
            changed = True

    # --- 3) 오래된 월 요약 정리 후 저장 (변경이 있을 때만) ---
    if changed:
        for kind_block in data["categories"].values():
            for entry in kind_block.values():
                for ym in sorted(entry["months"])[:-KEEP_MONTHS]:
                    del entry["months"][ym]
        data["generated_at"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
        _atomic_write(TRENDS_PATH, _compact(data))

    print(
        f"[trends] 월 요약 {stats['digests']}건, 종합 {stats['syntheses']}건, 공백 달 {stats['gap_months']}건, "
        f"실패 {stats['failed']}건 ({'저장' if changed else '변경 없음'})"
    )
    return stats


def _days_between(d1: str, d2: str) -> int:
    return (datetime.fromisoformat(d2) - datetime.fromisoformat(d1)).days


def main() -> None:
    if "--backfill" in sys.argv:
        backfill()
    elif "--rebuild" in sys.argv:
        update(force="--force" in sys.argv, max_calls=None, time_budget_sec=3600)
        u = gemini_client.get_usage_summary()
        print(f"[trends] 호출 {u['calls']}회 · 입력 {u['prompt']:,} · 출력 {u['candidates']:,} 토큰")
    else:
        print("사용법: python -m engine.trends --backfill | --rebuild [--force]")


if __name__ == "__main__":
    main()
