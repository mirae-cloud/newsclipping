"""한국은행 ECOS OpenAPI 클라이언트 — 국내 경제지표(기준금리·CPI·원달러 환율).

문서: https://ecos.bok.or.kr/api/

주의: 아래 STAT_CODE/ITEM_CODE 상수는 공개 자료 기준 best-effort 값이다.
실제 키 발급 후 `list_items()`로 한 번 검증할 것을 권장한다 (확실하지 않음, 확인 필요).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import requests

from engine import config

BASE_URL = "https://ecos.bok.or.kr/api"
REQUEST_TIMEOUT = 10

# 확인 필요: 실제 키로 list_items()를 호출해 아래 항목코드가 맞는지 검증할 것.
POLICY_RATE_STAT_CODE = "722Y001"
POLICY_RATE_ITEM_CODE = "0101000"  # 한국은행 기준금리

CPI_STAT_CODE = "901Y009"
CPI_ITEM_CODE = "0"  # 총지수

FX_USD_KRW_STAT_CODE = "731Y001"
FX_USD_KRW_ITEM_CODE = "0000001"  # 원/달러 매매기준율


@dataclass
class EcosPoint:
    date_str: str  # 원본 TIME 값 (주기에 따라 YYYYMM 또는 YYYYMMDD)
    value: float


def _request(path_segments: list[str]) -> dict:
    if not config.ECOS_API_KEY:
        raise RuntimeError("ECOS_API_KEY가 설정되지 않았습니다 (.env 확인).")

    url = "/".join([BASE_URL, *path_segments])
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    if "RESULT" in payload:
        raise RuntimeError(f"ECOS API 오류: {payload['RESULT']}")

    return payload


def fetch_time_series(
    stat_code: str,
    item_code: str,
    cycle: str,
    start_date: str,
    end_date: str,
    count: int = 5000,
) -> list[EcosPoint]:
    """주기(cycle)에 맞는 날짜 형식으로 시계열을 조회한다.

    cycle: "D"(일), "M"(월), "A"(년) 등. start_date/end_date는 cycle에 맞는 형식
    (D: YYYYMMDD, M: YYYYMM, A: YYYY).
    """
    payload = _request(
        [
            "StatisticSearch",
            config.ECOS_API_KEY,
            "json",
            "kr",
            "1",
            str(count),
            stat_code,
            cycle,
            start_date,
            end_date,
            item_code,
        ]
    )

    rows = payload.get("StatisticSearch", {}).get("row", [])
    return [EcosPoint(date_str=row["TIME"], value=float(row["DATA_VALUE"])) for row in rows]


def list_items(stat_code: str) -> list[dict]:
    """통계표코드 하위의 실제 항목코드 목록을 조회한다 (상수 검증용)."""
    payload = _request(["StatisticItemList", config.ECOS_API_KEY, "json", "kr", "1", "100", stat_code])
    return payload.get("StatisticItemList", {}).get("row", [])


def fetch_policy_rate_kr(years: int = 5) -> list[EcosPoint]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_time_series(
        POLICY_RATE_STAT_CODE, POLICY_RATE_ITEM_CODE, "M", start.strftime("%Y%m"), end.strftime("%Y%m")
    )


def fetch_cpi_kr(years: int = 5) -> list[EcosPoint]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_time_series(CPI_STAT_CODE, CPI_ITEM_CODE, "M", start.strftime("%Y%m"), end.strftime("%Y%m"))


def fetch_fx_usd_krw(years: int = 5) -> list[EcosPoint]:
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_time_series(
        FX_USD_KRW_STAT_CODE, FX_USD_KRW_ITEM_CODE, "D", start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    )


if __name__ == "__main__":
    print("기준금리 항목 목록:", list_items(POLICY_RATE_STAT_CODE)[:5])
    print("최근 기준금리:", fetch_policy_rate_kr()[-3:])
