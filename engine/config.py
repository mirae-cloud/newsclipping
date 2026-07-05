"""환경변수 로딩 — 모든 API 키는 여기서만 os.getenv로 참조한다. 실제 값은 절대 하드코딩하지 않는다."""

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

CURRENTS_API_KEY = os.getenv("CURRENTS_API_KEY")

ECOS_API_KEY = os.getenv("ECOS_API_KEY")

FRED_API_KEY = os.getenv("FRED_API_KEY")

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
