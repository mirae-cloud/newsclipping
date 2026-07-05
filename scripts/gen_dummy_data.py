"""로컬 웹사이트 미리보기용 더미 데이터 생성기.

실제 엔진(뉴스 수집·Gemini 요약)이 아직 없는 상태에서 DATA_SCHEMA.md 스키마에 맞는
샘플 JSON을 만들어 docs/data/ 에 저장한다. 프로덕션 파이프라인의 일부가 아니다.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

random.seed(7)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date.today()
NOW_ISO = datetime.now(timezone.utc).isoformat()

INDUSTRY_CATEGORIES = [
    "Finance (금융)",
    "TMT (기술·미디어·통신)",
    "Robotics & Semiconductors",
    "헬스케어 & 라이프사이언스",
    "소비재 & 리테일 (B2C)",
    "여행 (Travel)",
    "자동차 & 모빌리티",
    "산업재 (Industrial Goods)",
    "항공 & 방산",
    "운송 & 물류",
    "건설 & 인프라",
    "부동산",
    "소재 & 화학",
    "Oil & Gas",
    "에너지 & 전력",
    "공공·사회·교육",
]

BUSINESS_CATEGORIES = [
    "M&A / Strategic Investment",
    "Financial Investment (VC/PE)",
    "Corporate Finance / Turnaround",
    "Strategy",
    "PMI / Operations",
    "New Business / Business Building",
    "Go-To-Market",
    "Geopolitics & Regulation",
    "ESG & Sustainability",
    "Risk & Resilience",
    "Artificial Intelligence",
]

ECONOMY_KEYWORD_GROUPS = ["통화·금리", "물가·환율", "성장·경기", "주식·투자", "무역·정책", "금융·가계"]


def make_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def article(title: str, bullets: list[str], insight: str, category: str, hours_ago: int, url: str) -> dict:
    return {
        "id": make_id(url),
        "title": title,
        "url": url,
        "bullets": bullets,
        "insight": insight,
        "published_at": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
        "category": category,
    }


def category_block(sub_bullets: list[str], articles: list[dict], extra_topics: list[str] | None = None) -> dict:
    return {
        "sub_summary_bullets": sub_bullets,
        "articles": articles,
        "extra_topics": extra_topics or [],
    }


def empty_block() -> dict:
    return {"sub_summary_bullets": [], "articles": [], "extra_topics": []}


def build_domestic() -> dict:
    industry = {name: empty_block() for name in INDUSTRY_CATEGORIES}
    business = {name: empty_block() for name in BUSINESS_CATEGORIES}

    industry["Robotics & Semiconductors"] = category_block(
        [
            "국내 메모리 3사가 평택·이천 라인 증설에 나서며 HBM4 양산 경쟁이 본격화되고 있고, OO전자는 내년 매출 비중 30%를 목표로 내걸었다.",
            "파운드리 가동률이 두 분기 연속 상승했는데, 레거시 공정 중심의 수주 회복과 고객사 재고 조정 마무리가 맞물린 결과로 풀이된다.",
        ],
        [
            article(
                "OO전자, 차세대 HBM4 양산 돌입… 내년 매출 비중 30% 목표",
                ["평택 신규 라인 가동률 90% 돌파", "AI 서버향 수요 증가가 주 배경"],
                "메모리 업황 개선은 후방산업인 반도체 장비·소재(증착·식각 장비, 특수가스) 수요 회복으로 이어질 가능성이 있다. "
                "전방산업인 서버·데이터센터 업체 입장에서는 원가 부담이 이어질 수 있어 AI 인프라 투자 속도에 제약 요인이 될 수 있다는 추정도 나온다. "
                "일견 무관해 보이지만, 메모리 가격 상승은 PC·스마트폰 교체 수요를 늦추는 대체효과로 소비재·리테일 업계 단가 정책에도 간접 영향을 줄 가능성이 있다.",
                "Robotics & Semiconductors",
                3,
                "https://example.com/news/hbm4-ramp-up",
            ),
            article(
                "파운드리 가동률 두 분기 연속 상승",
                ["레거시 공정 중심 수주 회복", "고객사 재고 조정 마무리 국면"],
                "가동률 회복은 장비 재투자로 이어져 후방 장비업체 실적 개선에 긍정적일 것으로 추정된다. "
                "다만 레거시 공정 중심 회복이라 첨단 공정 투자로 바로 연결될지는 불확실하다.",
                "Robotics & Semiconductors",
                10,
                "https://example.com/news/foundry-utilization",
            ),
        ],
        ["온디바이스 AI 칩 스타트업 투자 확대"],
    )

    industry["자동차 & 모빌리티"] = category_block(
        [
            "전기차 수요 둔화(캐즘) 국면이 이어지면서 배터리 소재 업체들의 투자 속도 조절 움직임도 함께 감지되고 있다.",
            "완성차 3사가 북미 공장 라인 일부를 하이브리드용으로 전환하는 등 하이브리드 생산 비중 확대에 속도를 내고 있다.",
        ],
        [
            article(
                "완성차 OO그룹, 하이브리드 생산 비중 40%로 확대",
                ["전기차 수요 둔화에 대응한 포트폴리오 조정", "북미 공장 라인 일부 전환"],
                "전기차 캐즘은 배터리 소재(양극재·리튬) 후방산업 투자 속도 조절로 이어질 가능성이 있다(추정). "
                "반대로 하이브리드 부품(엔진·변속기) 공급망에는 단기 수혜가 갈 것으로 보인다. "
                "타 산업 대체효과로는 완성차 대신 대중교통·공유 모빌리티 수요가 일부 흡수할 가능성이 있다.",
                "자동차 & 모빌리티",
                6,
                "https://example.com/news/hybrid-shift",
            ),
        ],
        [],
    )

    business["Artificial Intelligence"] = category_block(
        ["OO그룹이 사내 문서작업 자동화 파일럿을 확대하고 AI 데이터센터 증설까지 검토하면서, 대기업의 DX 전환을 위한 생성형 AI 도입 사례가 빠르게 확산되고 있다."],
        [
            article(
                "OO그룹, 전사 업무에 생성형 AI 도입… DX 가속",
                ["사내 문서작업 자동화 파일럿 확대", "AI 데이터센터 증설 검토"],
                "AI 인프라 투자 확대는 전력·에너지 산업으로의 전방 수요 증가로 이어질 가능성이 있다(추정). "
                "데이터센터 냉각 관련 소재·부품 산업에도 간접 수혜가 예상된다.",
                "Artificial Intelligence",
                5,
                "https://example.com/news/genai-dx",
            ),
        ],
        [],
    )

    business["M&A / Strategic Investment"] = category_block(
        ["OO케미칼이 배터리 소재 스타트업 지분을 약 2천억원 규모로 인수하는 등, 양극재·리튬 원천기술 확보를 위한 중견 화학사들의 M&A가 활발하다."],
        [
            article(
                "OO케미칼, 배터리 소재 스타트업 지분 인수",
                ["양극재 원천기술 확보 목적", "인수가 약 2천억원 규모로 추정"],
                "이번 인수는 후방 원재료(리튬·전구체) 조달 안정화 목적으로 해석된다. "
                "전방산업인 배터리셀 제조사 입장에서는 공급 안정성이 개선될 가능성이 있다.",
                "M&A / Strategic Investment",
                8,
                "https://example.com/news/chemical-ma",
            ),
        ],
        [],
    )

    return {
        "date": TODAY.isoformat(),
        "generated_at": NOW_ISO,
        "summary": {
            "overall_bullets": [
                "OO전자가 평택 신규 라인 가동률 90%를 넘기며 차세대 HBM4 양산에 돌입했고, 국내 파운드리 가동률도 두 분기 연속 상승해 반도체 업황 개선 조짐이 뚜렷해지는 하루였다.",
                "완성차 OO그룹이 전기차 수요 둔화에 대응해 하이브리드 생산 비중을 40%까지 확대하기로 하면서, 업계 전반의 포트폴리오 재편이 가속화되는 모습이다.",
                "OO그룹이 전사 업무에 생성형 AI를 도입하고 AI 데이터센터 증설까지 검토하는 등, 대기업의 DX 전환을 위한 AI 도입 사례가 계속 확산되고 있다.",
            ],
            "headlines": [
                {"category": "Robotics & Semiconductors", "headline": "OO전자, 차세대 HBM4 양산 돌입"},
                {"category": "자동차 & 모빌리티", "headline": "완성차 OO그룹, 하이브리드 생산 비중 확대"},
                {"category": "Artificial Intelligence", "headline": "OO그룹, 전사 생성형 AI 도입"},
            ],
        },
        "categories": {"industry": industry, "business": business},
    }


def build_global() -> dict:
    industry = {name: empty_block() for name in INDUSTRY_CATEGORIES}
    business = {name: empty_block() for name in BUSINESS_CATEGORIES}

    industry["Robotics & Semiconductors"] = category_block(
        ["Global Foundry Co.가 차세대 공정 노드에 100억 달러 규모 투자를 발표했으며, 다음 분기 착공을 목표로 AI 가속기용 생산능력 확충에 나선다."],
        [
            article(
                "Global Foundry Co. to invest $10B in next-gen process node",
                ["Capacity expansion targeted for AI accelerator demand", "Construction to begin next quarter"],
                "This investment is likely to lift demand for upstream equipment and specialty gas suppliers (estimated). "
                "Downstream AI chip designers may benefit from improved capacity access, though pricing pressure could persist.",
                "Robotics & Semiconductors",
                4,
                "https://example.com/global/foundry-investment",
            ),
        ],
        [],
    )

    industry["에너지 & 전력"] = category_block(
        ["데이터센터발 전력 수요 급증에 대응해 유틸리티 업체들의 전력망 투자가 전년 대비 20% 늘었고, 재생에너지 통합이 핵심 투자 동인으로 꼽힌다."],
        [
            article(
                "Utility firms announce grid upgrades amid AI data center boom",
                ["Grid capacity investment up 20% year-over-year", "Renewable integration cited as key driver"],
                "Rising data center power demand is estimated to accelerate renewable and grid infrastructure investment. "
                "This may possibly create knock-on effects for industrial materials suppliers (transformers, cabling).",
                "에너지 & 전력",
                12,
                "https://example.com/global/grid-upgrade",
            ),
        ],
        [],
    )

    business["Geopolitics & Regulation"] = category_block(
        ["주요국이 첨단 반도체 장비에 대한 신규 수출통제 조치를 발표하며 일부 시장으로의 장비 수출이 영향권에 들었고, 업계는 공급망 차질을 우려하고 있다."],
        [
            article(
                "New export control measures target advanced chip equipment",
                ["Affects tooling exports to select markets", "Industry groups warn of supply chain disruption"],
                "Tighter export controls could possibly redirect trade flows toward allied markets (estimated). "
                "Downstream device makers in affected regions may face near-term sourcing constraints.",
                "Geopolitics & Regulation",
                7,
                "https://example.com/global/export-controls",
            ),
        ],
        [],
    )

    business["ESG & Sustainability"] = category_block(
        ["규제당국이 내년 회계연도부터 대형 다국적기업에 적용되는 한층 엄격한 탄소 공시 규정을 확정하면서, 관련 컴플라이언스 비용 상승이 예상된다."],
        [
            article(
                "Regulators finalize stricter carbon disclosure rules",
                ["Applies to large-cap multinationals from next fiscal year", "Compliance costs expected to rise"],
                "Stricter disclosure rules are estimated to increase near-term compliance costs across heavy industry. "
                "This could possibly accelerate demand for carbon accounting software vendors as a complementary effect.",
                "ESG & Sustainability",
                15,
                "https://example.com/global/carbon-disclosure",
            ),
        ],
        [],
    )

    return {
        "date": TODAY.isoformat(),
        "generated_at": NOW_ISO,
        "summary": {
            "overall_bullets": [
                "Global Foundry Co.가 차세대 공정 노드에 100억 달러를 투자하겠다고 발표하는 등, AI 가속기 수요에 대응한 글로벌 파운드리 투자 확대 발표가 잇따르고 있다.",
                "AI 데이터센터 붐에 맞춰 주요 유틸리티 업체들의 전력망 투자가 전년 대비 20% 늘었으며, 재생에너지 통합이 핵심 동인으로 지목되고 있다.",
                "주요국이 첨단 반도체 장비에 대한 수출통제를 강화하면서 업계 단체들은 공급망 차질 가능성을 경고하고 나섰다.",
            ],
            "headlines": [
                {"category": "Robotics & Semiconductors", "headline": "Global Foundry Co., $10B 신규 투자 발표"},
                {"category": "에너지 & 전력", "headline": "전력망 업그레이드 발표 잇따라"},
                {"category": "Geopolitics & Regulation", "headline": "첨단 반도체 장비 수출통제 강화"},
            ],
        },
        "categories": {"industry": industry, "business": business},
    }


def history_5y(base: float, monthly_step: float, noise: float) -> list[dict]:
    points = []
    d = TODAY.replace(day=1) - timedelta(days=1)  # 이번 달 이전 말일부터 역산
    value = base
    for i in range(60):
        value = value + monthly_step + random.uniform(-noise, noise)
        point_date = (d.replace(day=1) - timedelta(days=30 * i))
        points.append({"date": point_date.strftime("%Y-%m-01"), "value": round(value, 3)})
    points.reverse()
    return points


def indicator_block(latest: float, avg_1m: float, avg_1y: float, hist: list[dict]) -> dict:
    return {"latest": latest, "avg_1m": avg_1m, "avg_1y": avg_1y, "history_5y": hist}


def build_economy() -> dict:
    kr_rate_hist = history_5y(base=1.0, monthly_step=0.02, noise=0.05)
    us_rate_hist = history_5y(base=0.5, monthly_step=0.03, noise=0.06)
    kr_cpi_hist = history_5y(base=100.0, monthly_step=0.25, noise=0.15)
    us_cpi_hist = history_5y(base=100.0, monthly_step=0.28, noise=0.15)
    fx_hist = history_5y(base=1150.0, monthly_step=0.8, noise=8.0)

    news_groups = {}
    templates = {
        "통화·금리": (
            "한국은행, 기준금리 3.25% 동결",
            ["금통위 만장일치 동결 결정", "물가 안정세 확인 후 인하 시기 저울질"],
            "금리 동결 기조가 이어지면 가계대출 이자 부담이 지속될 가능성이 있어 소비 여력 위축으로 이어질 것으로 추정된다. "
            "부동산 시장은 거래 관망세가 이어질 가능성이 있다.",
        ),
        "물가·환율": (
            "원/달러 환율 1,380원대 등락",
            ["미 연준 발언에 환율 변동성 확대", "수입물가 부담 우려 지속"],
            "환율 상승은 수입 원자재 비중이 큰 산업재·소재 업종의 원가 부담으로 이어질 가능성이 있다(추정). "
            "반대로 수출 중심 기업에는 가격 경쟁력 개선 효과가 있을 수 있다.",
        ),
        "성장·경기": (
            "2분기 GDP 성장률 시장 예상치 소폭 상회",
            ["수출 회복이 성장 견인", "내수는 여전히 부진"],
            "수출 주도 회복은 제조업 고용 개선으로 이어질 가능성이 있으나, 내수 부진이 지속되면 소비재·리테일 업종에는 부담 요인으로 작용할 것으로 추정된다.",
        ),
        "주식·투자": (
            "코스피, 반도체 강세에 2,850선 회복",
            ["외국인 순매수 전환", "반도체·2차전지 대형주 강세"],
            "외국인 자금 유입은 원화 강세 요인으로 작용해 수출기업 채산성에는 부담이 될 가능성이 있다(추정).",
        ),
        "무역·정책": (
            "정부, 반도체 설비투자 세액공제 연장 검토",
            ["국회 세법 개정안 논의 착수", "업계는 추가 확대 요구"],
            "세액공제 연장은 반도체 후방 장비업체 투자 심리 개선에 긍정적일 것으로 추정된다.",
        ),
        "금융·가계": (
            "가계대출 증가세 3개월 연속 둔화",
            ["금융당국 대출 규제 효과 반영", "주택 거래량 감소와 맞물려"],
            "가계대출 둔화는 부동산 거래 위축과 맞물려 건설·인프라 업종 수주에 부정적 영향을 줄 가능성이 있다(추정).",
        ),
    }
    sub_summaries = {
        "통화·금리": "한국은행 금통위가 만장일치로 기준금리 3.25% 동결을 결정했으며, 물가 안정세를 확인한 뒤 인하 시기를 저울질하는 분위기다.",
        "물가·환율": "미 연준 발언에 원/달러 환율 변동성이 확대되며 1,380원대 등락이 이어졌고, 수입물가 부담에 대한 우려도 계속되고 있다.",
        "성장·경기": "2분기 GDP 성장률이 시장 예상치를 소폭 상회했는데, 수출 회복이 성장을 견인한 반면 내수는 여전히 부진한 흐름이다.",
        "주식·투자": "외국인 순매수 전환에 힘입어 코스피가 반도체·2차전지 대형주 강세 속에 2,850선을 회복했다.",
        "무역·정책": "정부가 반도체 설비투자 세액공제 연장을 검토하며 국회 세법 개정안 논의에 착수했고, 업계는 추가 확대를 요구하고 있다.",
        "금융·가계": "금융당국의 대출 규제 효과가 반영되며 가계대출 증가세가 3개월 연속 둔화됐고, 주택 거래량 감소와도 맞물리는 모습이다.",
    }
    for i, (group, (title, bullets, insight)) in enumerate(templates.items()):
        news_groups[group] = category_block(
            [sub_summaries[group]],
            [article(title, bullets, insight, group, 2 + i, f"https://example.com/economy/{i}")],
        )

    return {
        "date": TODAY.isoformat(),
        "generated_at": NOW_ISO,
        "indicators": {
            "policy_rate": {
                "kr": indicator_block(3.25, 3.25, 3.31, kr_rate_hist),
                "us": indicator_block(4.50, 4.50, 4.68, us_rate_hist),
            },
            "cpi": {
                "kr": indicator_block(114.2, 114.0, 112.6, kr_cpi_hist),
                "us": indicator_block(317.5, 316.8, 312.4, us_cpi_hist),
            },
            "fx_usd_krw": indicator_block(1382.4, 1375.9, 1361.2, fx_hist),
        },
        "news": {
            "summary": {
                "overall_bullets": [
                    "한국은행 금융통화위원회가 만장일치로 기준금리를 3.25%로 동결했고, 원/달러 환율은 미 연준 발언에 따른 변동성 속에 1,380원대에서 등락했다.",
                    "외국인 자금이 순매수로 전환하며 코스피가 반도체·2차전지 대형주 강세에 힘입어 2,850선을 회복하는 모습을 보였다.",
                ],
                "headlines": [{"category": g, "headline": v[0]} for g, v in templates.items()],
            },
            "keyword_groups": news_groups,
        },
    }


def main():
    (DATA_DIR / "domestic.json").write_text(json.dumps(build_domestic(), ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "global.json").write_text(json.dumps(build_global(), ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "economy.json").write_text(json.dumps(build_economy(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote dummy data to {DATA_DIR}")


if __name__ == "__main__":
    main()
