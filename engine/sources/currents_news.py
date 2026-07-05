"""Currents API 클라이언트 — 글로벌 뉴스 소스.

문서: https://currentsapi.services/en/docs/search
무료 티어 한도는 가입 시점 기준 재확인 필요(변동 가능, 확실하지 않음).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from engine import config

SEARCH_URL = "https://api.currentsapi.services/v1/search"
REQUEST_TIMEOUT = 10


@dataclass
class CurrentsArticle:
    title: str
    url: str
    description: str
    pub_date: datetime
    source: str = "currents"


def _parse_pub_date(raw: str) -> datetime:
    # Currents 응답의 published는 보통 "YYYY-MM-DD HH:MM:SS +0000" 형식
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S %z")


def search_news(query: str, language: str = "en", page_size: int = 50) -> list[CurrentsArticle]:
    if not config.CURRENTS_API_KEY:
        raise RuntimeError("CURRENTS_API_KEY가 설정되지 않았습니다 (.env 확인).")

    params = {
        "apiKey": config.CURRENTS_API_KEY,
        "keywords": query,
        "language": language,
        "page_size": page_size,
    }
    response = requests.get(SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    articles: list[CurrentsArticle] = []
    for item in payload.get("news", []):
        try:
            pub_date = _parse_pub_date(item["published"])
        except (KeyError, ValueError):
            continue
        articles.append(
            CurrentsArticle(
                title=item.get("title", ""),
                url=item.get("url", ""),
                description=item.get("description", ""),
                pub_date=pub_date,
            )
        )
    return articles


def filter_last_24h(articles: list[CurrentsArticle]) -> list[CurrentsArticle]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return [a for a in articles if a.pub_date.astimezone(timezone.utc) >= cutoff]


if __name__ == "__main__":
    results = filter_last_24h(search_news("semiconductor"))
    for a in results:
        print(f"[{a.pub_date.isoformat()}] {a.title} -> {a.url}")
