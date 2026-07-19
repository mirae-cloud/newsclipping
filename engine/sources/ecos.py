"""한국은행 ECOS OpenAPI 클라이언트 — 국내 경제지표(기준금리·CPI·원달러 환율).

문서: https://ecos.bok.or.kr/api/

주의: 아래 STAT_CODE/ITEM_CODE 상수는 2026-07 실제 키로 값을 조회해 합리적인 범위(기준금리·CPI·환율)임을
확인했다(정확한 항목명까지 대조한 것은 아니므로 수치가 이상해 보이면 `list_items()`로 재확인할 것).
"""

from dataclasses import dataclass
from datetime import date, timedelta

import requests

from engine import config

BASE_URL = "https://ecos.bok.or.kr/api"
REQUEST_TIMEOUT = 10

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
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        # URL 경로에 인증키가 그대로 포함되어 있어(.../StatisticSearch/{키}/...) 원본 예외(URL 포함)는
        # 노출하지 않되, 응답 본문은 키를 담지 않으므로 진단을 위해 함께 표시한다.
        status = getattr(exc.response, "status_code", "unknown")
        body = getattr(exc.response, "text", "")[:300]
        raise RuntimeError(f"ECOS API 요청 실패 (status={status}): {body}") from None

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
    """월별(M) 주기는 해당 월이 끝나야 집계되어 금리 인상 직후 며칠간 반영이 안 되는 지연이 있다
    (2026-07-16 인상 후 실측 확인: M 주기는 6월 값에 머물러 있었지만 D 주기는 07-16부터 바로 반영됨).
    미국 기준금리(DFEDTARU)와 동일하게 일별(D) 주기로 조회해 이 지연을 없앤다."""
    end = date.today()
    start = end - timedelta(days=365 * years)
    return fetch_time_series(
        POLICY_RATE_STAT_CODE, POLICY_RATE_ITEM_CODE, "D", start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
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
