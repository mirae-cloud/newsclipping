"""FRED API 클라이언트 — 미국 경제지표(기준금리 FEDFUNDS, CPI CPIAUCSL).

문서: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
무료, 120 req/분 한도.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import requests

from engine import config

OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
REQUEST_TIMEOUT = 10

FEDFUNDS_SERIES = "FEDFUNDS"
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
    response = requests.get(OBSERVATIONS_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    points = []
    for obs in payload.get("observations", []):
        if obs["value"] == ".":  # FRED는 결측치를 "." 문자로 표기
            continue
        points.append(FredPoint(date_str=obs["date"], value=float(obs["value"])))
    return points


def fetch_fedfunds(years: int = 5) -> list[FredPoint]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_series(FEDFUNDS_SERIES, start.isoformat(), end.isoformat())


def fetch_cpi_us(years: int = 5) -> list[FredPoint]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_series(CPI_SERIES, start.isoformat(), end.isoformat())


if __name__ == "__main__":
    print("최근 미국 기준금리:", fetch_fedfunds()[-3:])
    print("최근 미국 CPI:", fetch_cpi_us()[-3:])
