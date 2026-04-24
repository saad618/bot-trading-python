import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "T50H37RBFKT509FY")
    BACKTEST_API_KEY = os.getenv("BACKTEST_API_KEY", "") or os.getenv("ALPHA_VANTAGE_API_KEY", "T50H37RBFKT509FY")
    API_BASE_URL = "https://www.alphavantage.co/query"

    # Set DATA_SOURCE=crypto in .env to switch to Binance / crypto mode
    DATA_SOURCE = os.getenv("DATA_SOURCE", "stocks").strip().lstrip("=").strip().lower()
    _crypto = DATA_SOURCE == "crypto"

    _default_symbols = (
        "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT,ADA/USDT"
        if _crypto else
        "RELIANCE.BSE,TCS.BSE,INFY.BSE,MARUTI.BSE,SUNPHARMA.BSE"
    )
    SYMBOLS = os.getenv("SYMBOLS", _default_symbols).split(",")

    SHORT_MA_PERIOD = 9
    LONG_MA_PERIOD = 21
    RSI_PERIOD = 14
    BREAKOUT_PERIOD = 20

    BUY_SCORE_THRESHOLD = int(os.getenv("BUY_SCORE_THRESHOLD", "5").strip().lstrip("=").strip())
    SELL_SCORE_THRESHOLD = int(os.getenv("SELL_SCORE_THRESHOLD", "-5").strip().lstrip("=").strip())

    POSITION_SIZE_PERCENT = float(os.getenv("POSITION_SIZE_PERCENT", "2.0"))
    # Crypto needs wider stops/targets and a higher daily-loss tolerance
    STOP_LOSS_PERCENT     = float(os.getenv("STOP_LOSS_PERCENT",     "3.0" if _crypto else "1.5"))
    TARGET_PERCENT        = float(os.getenv("TARGET_PERCENT",        "6.0" if _crypto else "3.0"))
    MAX_DAILY_LOSS_PERCENT= float(os.getenv("MAX_DAILY_LOSS_PERCENT","8.0" if _crypto else "3.0"))
    MAX_ATR_PERCENT       = float(os.getenv("MAX_ATR_PERCENT",       "8.0" if _crypto else "4.0"))
    INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "100000.0"))
    PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

    MAIL_HOST = os.getenv("MAIL_HOST", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "saadsiddiqqui14798@gmail.com")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "ofzdserhlgskqkdi")
    REPORT_EMAIL = os.getenv("REPORT_EMAIL", "saadsiddiqqui14798@gmail.com")

    PORT = int(os.getenv("PORT", "8080"))

settings = Settings()
