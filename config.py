import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "T50H37RBFKT509FY")
    API_BASE_URL = "https://www.alphavantage.co/query"
    SYMBOLS = os.getenv("SYMBOLS", "RELIANCE.BSE,TCS.BSE,INFY.BSE,MARUTI.BSE,SUNPHARMA.BSE").split(",")

    SHORT_MA_PERIOD = 9
    LONG_MA_PERIOD = 21
    RSI_PERIOD = 14
    BREAKOUT_PERIOD = 20

    BUY_SCORE_THRESHOLD = int(os.getenv("BUY_SCORE_THRESHOLD", "4"))
    SELL_SCORE_THRESHOLD = int(os.getenv("SELL_SCORE_THRESHOLD", "-4"))

    POSITION_SIZE_PERCENT = float(os.getenv("POSITION_SIZE_PERCENT", "2.0"))
    STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "1.5"))
    TARGET_PERCENT = float(os.getenv("TARGET_PERCENT", "3.0"))
    MAX_DAILY_LOSS_PERCENT = float(os.getenv("MAX_DAILY_LOSS_PERCENT", "3.0"))
    INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "100000.0"))
    PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

    MAIL_HOST = os.getenv("MAIL_HOST", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "saadsiddiqqui14798@gmail.com")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "ofzdserhlgskqkdi")
    REPORT_EMAIL = os.getenv("REPORT_EMAIL", "saadsiddiqqui14798@gmail.com")

    PORT = int(os.getenv("PORT", "8080"))

settings = Settings()
