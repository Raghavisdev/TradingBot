import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory of the Project
BASE_DIR = Path(__file__).resolve().parent

# Load .env file if present
load_dotenv(BASE_DIR / ".env")

# ----------------------------------------------------
# TELEGRAM CREDENTIALS
# ----------------------------------------------------
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
SESSION_NAME = os.getenv("TELEGRAM_SESSION", "TradingBot")

try:
    API_ID = int(TELEGRAM_API_ID) if TELEGRAM_API_ID else None
except ValueError:
    API_ID = None

API_HASH = TELEGRAM_API_HASH

# ----------------------------------------------------
# DATABASE CONFIGURATION
# ----------------------------------------------------
_db_env = os.getenv("DATABASE_PATH", "database/trading.db")
DATABASE_PATH = Path(_db_env) if Path(_db_env).is_absolute() else BASE_DIR / _db_env
DATABASE = str(DATABASE_PATH)

# Ensure parent directory for DB exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------
# TRACKER & API SETTINGS
# ----------------------------------------------------
SNAPSHOT_INTERVAL = int(os.getenv("SNAPSHOT_INTERVAL", 5))
TRACKING_DURATION = float(os.getenv("TRACKING_DURATION", 86400))
MAX_API_FAILURES = int(os.getenv("MAX_API_FAILURES", 20))
DEXSCREENER_TIMEOUT = int(os.getenv("DEXSCREENER_TIMEOUT", 10))

# ----------------------------------------------------
# TRADING & AI THRESHOLDS
# ----------------------------------------------------
BUY_THRESHOLD = float(os.getenv("BUY_THRESHOLD", 70.0))
INVESTMENT_PER_TRADE = float(os.getenv("INVESTMENT_PER_TRADE", 3.0))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", 10))
PAPER_TRADING = os.getenv("PAPER_TRADING", "True").lower() in ("true", "1", "yes")

# S6 Candidate Settings
S6_CANDIDATE_MODE = os.getenv("S6_CANDIDATE_MODE", "False").lower() in ("true", "1", "yes")
PORTFOLIO_DRAWDOWN_LIMIT = float(os.getenv("PORTFOLIO_DRAWDOWN_LIMIT", 0.15))

# ----------------------------------------------------
# LIVE EXECUTION SAFETY LIMITS
# ----------------------------------------------------
LIVE_PRIORITY_FEE_MAX_SOL = float(os.getenv("LIVE_PRIORITY_FEE_MAX_SOL", 0.005))
LIVE_CALIBRATION_CAP_USD = float(os.getenv("LIVE_CALIBRATION_CAP_USD", 1.00))
LIVE_MIN_SOL_RESERVE = float(os.getenv("LIVE_MIN_SOL_RESERVE", 0.05))
LIVE_MAX_EXECUTION_RETRIES = int(os.getenv("LIVE_MAX_EXECUTION_RETRIES", 2))
LIVE_SLIPPAGE_BPS = int(os.getenv("LIVE_SLIPPAGE_BPS", 100))

# ----------------------------------------------------
# LOGGING & HEALTH MONITORING
# ----------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HEALTH_LOG_INTERVAL = int(os.getenv("HEALTH_LOG_INTERVAL", 600))


def validate_config():
    """
    Validates mandatory production configuration on startup.
    Raises ValueError if required settings are missing or invalid.
    """
    errors = []
    if not API_ID:
        errors.append("TELEGRAM_API_ID is missing or not a valid integer in .env")
    if not API_HASH:
        errors.append("TELEGRAM_API_HASH is missing in .env")

    if errors:
        raise ValueError("Configuration Error:\n  - " + "\n  - ".join(errors))