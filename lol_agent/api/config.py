"""
Shortsyt API — konfiguracja serwera
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Ładuj .env z roota projektu
_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_ROOT / ".env")

# ── Serwer ──────────────────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8765"))

# ── Bezpieczeństwo ───────────────────────────────────────────────────────────
# Hasło do logowania (zmień w .env!)
API_PASSWORD = os.getenv("API_PASSWORD", "shortsyt2026")

# Sekret JWT (zmień w .env!)
JWT_SECRET = os.getenv("JWT_SECRET", "change_me_in_production_jwt_secret_32chars")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "720"))  # 30 dni

# ── Ścieżki projektu ─────────────────────────────────────────────────────────
LOL_AGENT_DIR = Path(__file__).parent.parent
LOL_INPUT_DIR = Path(os.getenv("LOL_INPUT_DIR", r"C:\Medal\Edits"))
LOL_OUTPUT_DIR = Path(os.getenv("LOL_OUTPUT_DIR", r"C:\Users\mz100\Videos\lol_shorts_output"))
LOL_TEMP_DIR = LOL_AGENT_DIR / "lol_temp"

# ── YouTube OAuth ─────────────────────────────────────────────────────────────
ACCOUNTS_DIR = _ROOT / "accounts"
CLIENT_SECRET_PATH = _ROOT / "client_secret.json"
YT_TOKEN_PATH = ACCOUNTS_DIR / "lol_token.pickle"

# ── Expo Push Notifications ──────────────────────────────────────────────────
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# ── CORS ─────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:8081",
    "http://localhost:19006",
    "exp://localhost:8081",
    "*",  # Cloudflare Tunnel — apka mobilna
]
