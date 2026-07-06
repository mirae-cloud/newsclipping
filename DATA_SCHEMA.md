# 데이터 파일 스키마 (엔진 → 웹사이트 계약)

엔진이 매일 아래 3개 JSON을 생성하고, 웹사이트는 이 파일만 읽어 렌더링한다 (지시서 0/1번 원칙).
경로: `docs/data/economy.json`, `docs/data/domestic.json`, `docs/data/global.json`.

## 공통 타입 — Article

```json
{
  "id": "string (url의 안정적 해시 등 고유값 — 저장/북마크 키로 사용)",
  "title": "string — 뉴스 핵심 한 줄 요약",
  "url": "string — 원문 링크 (구글 리다이렉트 해제된 것)",
  "bullets": ["string", "string"],
  "insight": "string — 파급효과 분석 문단. '추정'/'가능성' 문구 포함 필수(5-2 규칙)이나 프론트에서 별도로 강조 표시하지는 않음",
  "published_at": "ISO 8601 datetime",
  "category": "string — 6/7번 산업군 또는 Business 카테고리명, 또는 8번 경제 키워드 그룹명"
}
```

## domestic.json / global.json

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO 8601",
  "summary": {
    "overall_bullets": ["string — 아래 '요약 bullet 분량' 참고", ...],
    "headlines": [{"category": "string", "headline": "string"}, ...]
  },
  "categories": {
    "industry": {
      "<16개 산업군 카테고리명>": {
        "sub_summary_bullets": ["string", ...],
        "articles": [Article, ...]   // 최대 3개, 중요도순
        "extra_topics": ["string(15~20자)", ...]  // 3개 초과 시 하위 주제명만
      }
    },
    "business": {
      "<11개 Business 카테고리명>": { "sub_summary_bullets": [...], "articles": [...], "extra_topics": [...] }
    }
  }
}
```

## economy.json

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO 8601",
  "indicators": {
    "policy_rate": {
      "kr": {"latest": number, "avg_1m": number, "avg_1y": number, "history_5y": [{"date": "YYYY-MM-DD", "value": number}, ...]},
      "us": { "...동일 구조..." }
    },
    "cpi": { "kr": {...}, "us": {...} },
    "fx_usd_krw": {"latest": number, "avg_1m": number, "avg_1y": number, "history_5y": [...]}
  },
  "news": {
    "summary": {"overall_bullets": [...], "headlines": [...]},
    "keyword_groups": {
      "<8번 경제 키워드 그룹명 6개>": {"sub_summary_bullets": [...], "articles": [Article, ...]}
    }
  }
}
```

## 요약 bullet 분량 (`overall_bullets` / `sub_summary_bullets`)

- 이 두 bullet은 "오늘의 핵심 요약"에 해당하며, 카테고리명이나 제목만 나열하는 짧은 구가 아니라
  **해당 기사들의 실제 내용(수치·주체·배경)을 반영한 완결된 문장**이어야 한다.
- 분량은 초기 시안 대비 약 **2.5배** 수준(문장당 40~80자 내외)을 기준으로 한다.
- `article.bullets`(기사별 2~3개 요약)는 5-1 스펙의 별도 규칙(짧은 bullet)을 그대로 따르며, 이 분량 기준의 대상이 아니다.

## 소스 구분

- `domestic.json`의 기사는 전량 국내 소스(구글 뉴스 RSS + 네이버), `global.json`은 전량 Currents(글로벌).
- 웹사이트의 "국내/글로벌 토글"은 같은 카테고리명으로 `domestic.json`과 `global.json`을 각각 조회해 전환 표시하는 것으로 구현(스키마 자체에 source 필드 불필요).
- `economy.json`의 뉴스는 국내·글로벌을 이미 통합해 하나로 담는다(토글 없음, 9-1 참고).

## 카테고리명 고정값

- 산업군 16개(6번), Business 11개(7번), 경제 키워드 그룹 6개(8번) — 지시서에 명시된 표기를 **키 이름 그대로** 사용해야 프론트 라우팅과 어긋나지 않는다.

## keywords.json — 카테고리별 검색 키워드 (엔진 ↔ 웹사이트 '키워드 설정' 탭 공용)

경로: `docs/data/keywords.json`. `engine/categories.py`가 이 파일을 유일한 소스로 읽어들이고,
웹사이트 '키워드 설정' 탭도 같은 파일을 읽어 편집 UI를 그린다.

```json
{
  "industry": { "<16개 산업군 카테고리명>": {"ko": ["string", ...], "en": ["string", ...]} },
  "business": { "<11개 Business 카테고리명>": {"ko": [...], "en": [...]} },
  "economy":  { "<6개 경제 키워드 그룹명>":   {"ko": [...], "en": [...]} }
}
```

- `ko`: 네이버(메인)·구글 뉴스 RSS(보충) 검색에 쓰는 한국어 키워드.
- `en`: Currents(글로벌) 검색에 쓰는 영어 키워드.
- 웹사이트에서 편집한 내용은 **로컬 브라우저에만** 임시 저장(localStorage)되며, 실제 파이프라인에 반영하려면
  '키워드 설정' 탭에서 내려받은 파일로 이 경로를 덮어쓰고 커밋·푸시해야 한다(자동 반영 아님 — 2026-07 확인).
