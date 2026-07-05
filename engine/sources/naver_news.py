"""네이버 검색 API(뉴스) 클라이언트 — 국내 뉴스 보충 소스.

문서: https://developers.naver.com/docs/serviceapi/search/news/news.md
"""

import html
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from engine import config

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

MAX_DISPLAY_PER_REQUEST = 100  # 네이버 API 상한
MAX_START = 1000  # 네이버 API 상한 (start + display - 1 <= 1000)

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NaverArticle:
    title: str
    original_link: str
    description: str
    pub_date: datetime
    source: str = "naver"


def _clean_text(raw: str) -> str:
    """네이버 응답의 title/description은 검색어를 <b> 태그로 감싸고 HTML 엔티티로 이스케이프되어 온다."""
    return html.unescape(_TAG_RE.sub("", raw)).strip()


def _parse_pub_date(raw: str) -> datetime:
    # 예: "Mon, 26 Sep 2016 07:50:00 +0900"
    return parsedate_to_datetime(raw)


def search_news(
    query: str,
    max_results: int = 100,
    sort: str = "date",
    request_delay_sec: float = 0.2,
) -> list[NaverArticle]:
    """키워드로 네이버 뉴스를 검색해 정규화된 기사 목록을 반환한다.

    max_results가 100을 넘으면 start 파라미터를 늘려가며 여러 번 호출한다(최대 1000건).
    """
    if not config.NAVER_CLIENT_ID or not config.NAVER_CLIENT_SECRET:
        raise RuntimeError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되지 않았습니다 (.env 확인)."
        )

    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }

    articles: list[NaverArticle] = []
    start = 1
    remaining = min(max_results, MAX_START)

    while remaining > 0 and start <= MAX_START:
        display = min(remaining, MAX_DISPLAY_PER_REQUEST)
        params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": sort,
        }

        response = requests.get(NAVER_NEWS_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        items = response.json().get("items", [])

        if not items:
            break

        for item in items:
            articles.append(
                NaverArticle(
                    title=_clean_text(item["title"]),
                    original_link=item["originallink"] or item["link"],
                    description=_clean_text(item["description"]),
                    pub_date=_parse_pub_date(item["pubDate"]),
                )
            )

        start += display
        remaining -= display

        if remaining > 0:
            time.sleep(request_delay_sec)  # 연속 호출 사이 짧은 딜레이

    return articles


def filter_last_24h(articles: list[NaverArticle]) -> list[NaverArticle]:
    """발행일시(pubDate) 기준 지난 24시간 이내 기사만 통과시킨다."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return [a for a in articles if a.pub_date.astimezone(timezone.utc) >= cutoff]


if __name__ == "__main__":
    # 로컬 수동 실행용 간단 확인 (13번 제작순서 1단계): .env에 실제 키를 채운 뒤 실행
    results = filter_last_24h(search_news("반도체"))
    for a in results:
        print(f"[{a.pub_date.isoformat()}] {a.title} -> {a.original_link}")
