"""
Cấu hình tập trung – học từ cr-bot (settings.py + authsettings.py).

Thay vì dùng 2 file riêng như cr-bot, ta gộp vào 1 file
và đọc tất cả từ biến môi trường (.env).

Để override, tạo file usersettings.py và import ở đây.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # đọc .env

# ── Phiên bản ──────────────────────────────────────────────────────────────────
PROGRAM_VERSION = "2.0.0"

# ── User-Agent chuẩn theo Danbooru API docs ────────────────────────────────────
# Format: "BotName/version (by user #id)"
BOORU_USER_ID = os.getenv("BOORU_USER_ID", "")
_uid = f" (by user #{BOORU_USER_ID})" if BOORU_USER_ID else ""
USERAGENT = os.getenv(
    "BOORU_USER_AGENT",
    f"fumimi-discord-python/{PROGRAM_VERSION}{_uid}"
)

# ── Danbooru Production ────────────────────────────────────────────────────────
BOORU_URL   = os.getenv("BOORU_URL",   "https://danbooru.donmai.us")
LOGIN       = os.getenv("BOORU_USER",  "")
APIKEY      = os.getenv("BOORU_API_KEY", "")

# ── Danbooru Testbooru ────────────────────────────────────────────────────────
# https://testbooru.donmai.us  (dùng để test trước khi deploy production)
TEST_URL    = os.getenv("TEST_BOORU_URL",     "https://testbooru.donmai.us")
TEST_LOGIN  = os.getenv("TEST_BOORU_USER",    "")
TEST_APIKEY = os.getenv("TEST_BOORU_API_KEY", "")

# ── Discord ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN     = os.getenv("DISCORD_TOKEN", "")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
# Channel ID để post report (optional)
DISCORD_REPORT_CHANNEL_ID = os.getenv("DISCORD_REPORT_CHANNEL_ID", "")

# ── Bot behavior ───────────────────────────────────────────────────────────────
# Nếu TEST_MODE=true → dùng testbooru thay vì production
TEST_MODE = os.getenv("TEST_MODE", "false").lower() in ("true", "1", "yes")

# Domains sẽ được auto-embed khi paste link vào chat
_raw_domains  = os.getenv("BOORU_DOMAINS", "")
import re as _re
_default_domain = _re.sub(r"https?://", "", BOORU_URL)
BOORU_DOMAINS = _raw_domains.split() if _raw_domains else [_default_domain]

# ── Chọn config theo mode ──────────────────────────────────────────────────────
def get_active_booru_url() -> str:
    return TEST_URL if TEST_MODE else BOORU_URL

def get_active_login() -> str:
    return TEST_LOGIN if TEST_MODE else LOGIN

def get_active_apikey() -> str:
    return TEST_APIKEY if TEST_MODE else APIKEY

# ── Override từ usersettings.py (nếu có) ──────────────────────────────────────
try:
    from usersettings import *  # type: ignore # noqa: F401, F403
except ImportError:
    pass
