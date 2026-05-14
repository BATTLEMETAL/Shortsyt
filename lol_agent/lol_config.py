"""
LOL Agent — Centralna konfiguracja
Kanał: Dwannellenga (League of Legends Gaming)
"""
import os

# ==========================================
# ŚCIEŻKI
# ==========================================

# Folder gdzie wrzucasz surowe klipy (np. z Outplayed / OBS / Shadowplay)
LOL_INPUT_DIR = r"C:\Users\mz100\OneDrive\Pulpit\yt\filmy"

# Folder archiwum — klipy po przetworzeniu
LOL_ARCHIVE_DIR = os.path.join(os.path.dirname(__file__), "lol_archive")

# Folder z muzyką (mp3/wav royalty-free)
LOL_MUSIC_DIR = os.path.join(os.path.dirname(__file__), "lol_music")

# Folder tymczasowy do montażu
LOL_TEMP_DIR = os.path.join(os.path.dirname(__file__), "lol_temp")

# ==========================================
# AUTORYZACJA YOUTUBE
# ==========================================

# Nazwa profilu — token będzie zapisany jako accounts/lol_token.pickle
CHANNEL_PROFILE = "lol"

# Plik secrets (wspólny dla całego projektu)
CLIENT_SECRET_PATH = os.path.join(os.path.dirname(__file__), "..", "client_secret.json")
ACCOUNTS_DIR = os.path.join(os.path.dirname(__file__), "..", "accounts")
TOKEN_PATH = os.path.join(ACCOUNTS_DIR, f"{CHANNEL_PROFILE}_token.pickle")

# ==========================================
# USTAWIENIA MONTAŻU
# ==========================================

# Docelowy format wideo
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 60

# Czas trwania Shorta (sekundy)
SHORT_MAX_DURATION = 58  # <60s dla YouTube Shorts

# Głośność muzyki vs game audio (game audio WYCISZONY)
MUSIC_VOLUME = 0.85  # 85% głośności muzyki
GAME_AUDIO_VOLUME = 0.0  # Całkowite wyciszenie

# Slow motion na peak action (None = wyłączone, 0.5 = połowa prędkości)
SLOWMO_FACTOR = 0.5
SLOWMO_DURATION = 1.5  # sekundy slow-mo na końcu akcji

# ==========================================
# OVERLAYE TEKSTOWE
# ==========================================

# Style tekstu
OVERLAY_FONT = "Impact"
OVERLAY_FONT_FALLBACK = "Arial-Bold"

# Dostępne etykiety akcji (AI dobiera na podstawie klipu)
ACTION_LABELS = {
    "pentakill": "PENTAKILL 🔥",
    "quadrakill": "QUADRA KILL ⚡",
    "triple": "TRIPLE KILL 💥",
    "double": "DOUBLE KILL",
    "outplay": "OUTPLAY 🎯",
    "clutch": "CLUTCH PLAY 👑",
    "escape": "IMPOSSIBLE ESCAPE 🚀",
    "oneshot": "ONE SHOT 💀",
    "baron": "BARON STEAL 🐉",
    "dragon": "DRAGON STEAL",
}

# ==========================================
# METADANE YOUTUBE
# ==========================================

# Kategoria: 20 = Gaming
YT_CATEGORY_ID = "20"

# Privacy: "public" / "private" / "unlisted"
YT_PRIVACY = "public"

# Bazowe hashtagi (AI doda specyficzne dla championa)
YT_BASE_TAGS = [
    "league of legends",
    "lol",
    "lol shorts",
    "league shorts",
    "lol gameplay",
    "lol highlights",
    "league of legends highlights",
    "lol 2025",
    "lol montage",
    "lol moments",
    "best plays lol",
    "gaming shorts",
    "#shorts",
]

# ==========================================
# API KEYS
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    raise EnvironmentError("GEMINI_API_KEY is not set. Add it to your .env file.")


# ==========================================
# WSPIERANE FORMATY WIDEO
# ==========================================
SUPPORTED_FORMATS = ("*.mp4", "*.mov", "*.mkv", "*.avi", "*.webm")
