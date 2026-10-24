import os

# Binance Credentials (Testnet)
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY") or "j2hNz3wJxP6ckSNEcxMM9vqvNfnGCMvhXlMS49sebbItasfa2Xj6UPzegddH3STB"
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET") or "XkbbuU5HN4HeLvvS9JkdXt3WIJGRnAitz1pLVzsUleoU8hJko4NckGjuHL0eJjKR"
BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL") or "https://testnet.binance.vision"

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8810076939:AAHw6JgrPU6OwCvCS353KFKY3p9tzXFaPAI"
BOT_USERNAME = "SRSupportResistance_Bot"

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

AUTH_ADMIN_FILE = os.path.join(DATA_DIR, "admin_user.json")
TRADES_DB_FILE = os.path.join(DATA_DIR, "trades_db.json")

# Money & Risk Management
RISK_PER_TRADE_PCT = 0.08   # 8% of equity per trade
MAX_OPEN_POSITIONS = 11     # Maximum 11 concurrent open positions
TRIAL_DAYS = 15             # 15 days test period
START_DATE = "2026-10-24"

# Selected 72 Coins Watchlist
WATCHLIST_COINS = [
    "FLUX", "MUUB", "IOTX", "AVNT", "CETUS", "ETC", "BLUR", "AAVE", "GPS", "HOME",
    "WLD", "EDEN", "ADA", "POL", "AVAX", "AR", "RENDER", "UNI", "ZRO", "GAS",
    "CATI", "ALGO", "QUICK", "SUI", "VANA", "ZK", "MEME", "MANA", "GMX", "KAVA",
    "PYTH", "MBL", "STRK", "ETH", "KSM", "OGN", "ONT", "PSG", "ONDO", "NEAR",
    "1INCH", "SOL", "DOT", "ICP", "PORTAL", "OSMO", "PEOPLE", "NOT", "COMP", "ENA",
    "PORTO", "NEXO", "HOT", "EPIC", "PENGU", "XAI", "PENDLE", "GALA", "JTO", "WIF",
    "TWT", "IOTA", "LINK", "JASMY", "DOGE", "SHIB", "VET", "SNX"
]

WATCHLIST_PAIRS = [f"{c}USDT" for c in WATCHLIST_COINS]
