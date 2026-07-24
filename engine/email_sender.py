"""Gmail SMTP 이메일 발송 — 경제 → 국내 → 글로벌 순 통합 HTML 메일 1통 (지시서 10번).

인라인 스타일만 사용(이메일 클라이언트 호환성). Gmail 앱 비밀번호로 인증.
"""

import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from engine import config

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

STYLE_H1 = "font-family:Georgia,serif;font-size:22px;margin:24px 0 8px;color:#1f3c63;"
STYLE_H2 = "font-family:Georgia,serif;font-size:18px;margin:20px 0 6px;color:#1f3c63;"
STYLE_H3 = "font-family:Arial,sans-serif;font-size:15px;margin:16px 0 4px;color:#1a1a1a;"
STYLE_P = "font-family:Arial,sans-serif;font-size:13px;color:#6b6b6b;margin:0 0 8px;"
STYLE_TITLE_LINK = "font-family:Arial,sans-serif;font-size:15px;font-weight:bold;color:#1a1a1a;text-decoration:underline;"
STYLE_BULLET = "font-family:Arial,sans-serif;font-size:13.5px;color:#1a1a1a;margin:2px 0;"
STYLE_INSIGHT = (
    "font-family:Arial,sans-serif;font-size:13px;color:#4a3420;"
    "background:#fbf1e5;border-left:3px solid #a85a1d;padding:8px 12px;margin:6px 0 14px;"
)


def _render_article(article: dict) -> str:
    bullets = "".join(f'<li style="{STYLE_BULLET}">{html.escape(b)}</li>' for b in article["bullets"])
    return f"""
    <div style="margin-bottom:16px;">
      <a href="{html.escape(article['url'])}" style="{STYLE_TITLE_LINK}">{html.escape(article['title'])}</a>
      <ul style="margin:4px 0 6px;padding-left:18px;">{bullets}</ul>
      <div style="{STYLE_INSIGHT}">{html.escape(article['insight'])}</div>
    </div>
    """


def _render_category_block(name: str, block: dict) -> str:
    if not block["articles"]:
        return ""
    articles_html = "".join(_render_article(a) for a in block["articles"])
    extra = ""
    if block.get("extra_topics"):
        extra = f'<p style="{STYLE_P}">그 외: {html.escape(" · ".join(block["extra_topics"]))}</p>'
    return f"""
    <h3 style="{STYLE_H3}">{html.escape(name)}</h3>
    {articles_html}
    {extra}
    """


def _render_summary(summary: dict) -> str:
    bullets = "".join(f'<li style="{STYLE_BULLET}">{html.escape(b)}</li>' for b in summary.get("overall_bullets", []))
    return f'<ul style="margin:4px 0 12px;padding-left:18px;">{bullets}</ul>'


def _render_indicator(label: str, block: dict, unit: str, is_cpi: bool = False) -> str:
    if block.get("latest") is None:
        return ""
    # CPI는 월별로만 발표돼 '오늘'이 항상 '1달 평균'과 같은 값이라, 웹사이트와 동일하게
    # 1달/6개월/1년 평균을 보여준다 (다른 지표는 '오늘'이 실제로 다른 값이라 그대로 유지).
    if is_cpi:
        summary = f"1달 평균 {block['avg_1m']}{unit} / 6개월 평균 {block['avg_6m']}{unit} / 1년 평균 {block['avg_1y']}{unit}"
    else:
        summary = f"오늘 {block['latest']}{unit} / 1달 평균 {block['avg_1m']}{unit} / 1년 평균 {block['avg_1y']}{unit}"
    return f'<p style="{STYLE_P}"><b style="color:#1a1a1a;">{html.escape(label)}</b> — {summary}</p>'


def build_email_html(economy: dict, domestic: dict, global_: dict) -> str:
    parts = [f'<div style="max-width:640px;margin:0 auto;padding:16px;">']
    parts.append(f'<h1 style="{STYLE_H1}">뉴스클리핑 — {economy["date"]}</h1>')

    # 1. 경제
    parts.append(f'<h2 style="{STYLE_H2}">경제</h2>')
    ind = economy["indicators"]
    parts.append(_render_indicator("기준금리 (한국)", ind["policy_rate"]["kr"], "%"))
    parts.append(_render_indicator("기준금리 (미국)", ind["policy_rate"]["us"], "%"))
    parts.append(_render_indicator("소비자물가 CPI (한국)", ind["cpi"]["kr"], "", is_cpi=True))
    parts.append(_render_indicator("소비자물가 CPI (미국)", ind["cpi"]["us"], "", is_cpi=True))
    parts.append(_render_indicator("원/달러 환율", ind["fx_usd_krw"], "원"))
    parts.append(_render_summary(economy["news"]["summary"]))
    for name, block in economy["news"]["keyword_groups"].items():
        parts.append(_render_category_block(name, block))

    # 2. 국내 뉴스
    parts.append(f'<h2 style="{STYLE_H2}">국내 뉴스</h2>')
    parts.append('<h3 style="' + STYLE_H3 + '">산업군</h3>')
    parts.append(_render_summary(domestic["summary"]["industry"]))
    for name, block in domestic["categories"]["industry"].items():
        parts.append(_render_category_block(name, block))
    parts.append('<h3 style="' + STYLE_H3 + '">Business</h3>')
    parts.append(_render_summary(domestic["summary"]["business"]))
    for name, block in domestic["categories"]["business"].items():
        parts.append(_render_category_block(name, block))

    # 3. 글로벌 뉴스
    parts.append(f'<h2 style="{STYLE_H2}">글로벌 뉴스</h2>')
    parts.append('<h3 style="' + STYLE_H3 + '">산업군</h3>')
    parts.append(_render_summary(global_["summary"]["industry"]))
    for name, block in global_["categories"]["industry"].items():
        parts.append(_render_category_block(name, block))
    parts.append('<h3 style="' + STYLE_H3 + '">Business</h3>')
    parts.append(_render_summary(global_["summary"]["business"]))
    for name, block in global_["categories"]["business"].items():
        parts.append(_render_category_block(name, block))

    parts.append("</div>")
    return "".join(parts)


def send_email(html_body: str, subject: str) -> None:
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD가 설정되지 않았습니다 (.env 확인).")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config.GMAIL_ADDRESS
    message["To"] = config.GMAIL_ADDRESS
    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        server.sendmail(config.GMAIL_ADDRESS, [config.GMAIL_ADDRESS], message.as_string())
