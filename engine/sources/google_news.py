"""구글 뉴스 RSS 수집기 — 국내 뉴스 메인 소스 (API 키 불필요, 비공식 엔드포인트).

문서화되지 않은 엔드포인트라 대량·고빈도 호출 시 일시 차단될 수 있음(추정) — 키워드별 호출
사이 딜레이를 두고, 실패 시 상위 파이프라인에서 네이버로 폴백한다.
"""

import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
from googlenewsdecoder import gnewsdecoder

RSS_BASE = "https://news.google.com/rss/search"


@dataclass
class GoogleNewsArticle:
    title: str
    link: str  # 리다이렉트 해제를 시도한 최선의 링크 (실패 시 구글 경유 링크)
    description: str
    pub_date: datetime
    source: str = "google"


def _build_url(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"{RSS_BASE}?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"


def resolve_link(google_link: str) -> str:
    """구글 리다이렉트 링크에서 원문 URL을 최선을 다해(best-effort) 풀어낸다.

    단순 HTTP 리다이렉트가 아니라 구글 내부 batchexecute RPC를 거쳐야 하는 방식이라
    googlenewsdecoder 라이브러리를 사용한다. 구글이 공식 지원하지 않는 방식이라
    100% 보장되지 않음 — 실패 시 구글 링크를 그대로 반환.
    """
    try:
        result = gnewsdecoder(google_link, interval=1)
        if result.get("status"):
            return result["decoded_url"]
    except Exception:
        pass

    return google_link


def search_news(query: str, resolve_links: bool = False) -> list[GoogleNewsArticle]:
    """resolve_links는 gnewsdecoder 왕복(기사당 수십~100초)이 걸려 기본은 False.

    분류·요약 단계에는 title/description만 필요하므로, 최종 선택된 기사에 한해서만
    resolve_link()를 호출하는 것을 권장 (파이프라인 전체 실행 시간 절약).
    """
    url = _build_url(query)
    feed = feedparser.parse(url)

    articles: list[GoogleNewsArticle] = []
    for entry in feed.entries:
        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        link = resolve_link(entry.link) if resolve_links else entry.link

        articles.append(
            GoogleNewsArticle(
                title=entry.title,
                link=link,
                description=getattr(entry, "summary", ""),
                pub_date=pub_date,
            )
        )

    return articles


def filter_last_24h(articles: list[GoogleNewsArticle]) -> list[GoogleNewsArticle]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return [a for a in articles if a.pub_date >= cutoff]


if __name__ == "__main__":
    results = filter_last_24h(search_news("반도체", resolve_links=True))
    for a in results:
        print(f"[{a.pub_date.isoformat()}] {a.title} -> {a.link}")
