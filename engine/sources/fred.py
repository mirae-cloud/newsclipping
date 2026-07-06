"""FRED API 클라이언트 — 미국 경제지표(기준금리 목표상단 DFEDTARU, CPI CPIAUCSL).

문서: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
무료, 120 req/분 한도.

주의: 기준금리는 FEDFUNDS(실효 연방기금금리)가 아니라 DFEDTARU(FOMC 목표범위 상단)를 쓴다.
FEDFUNDS는 목표범위 내에서 매일 변하는 시장 실효금리라 0.25%p 단위로 안 떨어지고,
한국 기준금리(BOK 발표값)처럼 깔끔한 정책 발표값과 비교하려면 목표범위 값이 맞다(2026-07 확인).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import requests

from engine import config

OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
REQUEST_TIMEOUT = 10

POLICY_RATE_SERIES = "DFEDTARU"  # FOMC 목표범위 상단(Upper Limit)
CPI_SERIES = "CPIAUCSL"


@dataclass
class FredPoint:
    date_str: str  # YYYY-MM-DD
    value: float


def fetch_series(series_id: str, start_date: str, end_date: str) -> list[FredPoint]:
    if not config.FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY가 설정되지 않았습니다 (.env 확인).")

    params = {
        "series_id": series_id,
        "api_key": config.FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
    }
    try:
        response = requests.get(OBSERVATIONS_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        # 쿼리 파라미터(api_key)가 요청 URL에 포함되므로 원본 예외(URL 포함)는 노출하지 않되,
        # 응답 본문은 키를 담지 않으므로 진단을 위해 함께 표시한다.
        status = getattr(exc.response, "status_code", "unknown")
        body = getattr(exc.response, "text", "")[:300]
        raise RuntimeError(f"FRED API 요청 실패 (status={status}): {body}") from None

    payload = response.json()

    points = []
    for obs in payload.get("observations", []):
        if obs["value"] == ".":  # FRED는 결측치를 "." 문자로 표기
            continue
        points.append(FredPoint(date_str=obs["date"], value=float(obs["value"])))
    return points


def fetch_policy_rate_us(years: int = 5) -> list[FredPoint]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_series(POLICY_RATE_SERIES, start.isoformat(), end.isoformat())


def fetch_cpi_us(years: int = 5) -> list[FredPoint]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_series(CPI_SERIES, start.isoformat(), end.isoformat())


if __name__ == "__main__":
    print("최근 미국 기준금리(목표 상단):", fetch_policy_rate_us()[-3:])
    print("최근 미국 CPI:", fetch_cpi_us()[-3:])
