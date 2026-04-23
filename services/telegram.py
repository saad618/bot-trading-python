import os
import requests
import logging

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

def send_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        logger.error(f"Telegram notification failed: {e}")

def notify_buy(symbol: str, price: float, stop_loss: float, target: float, qty: int):
    send_message(
        f"🟢 <b>BUY {symbol.replace('.BSE', '')}</b>\n"
        f"📈 Price:     ₹{price:.2f}\n"
        f"🔢 Quantity:  {qty} shares\n"
        f"🛡 Stop-Loss: ₹{stop_loss:.2f}\n"
        f"🎯 Target:    ₹{target:.2f}\n"
        f"💰 Risk/share: ₹{price - stop_loss:.2f}"
    )

def notify_sell(symbol: str, price: float, pnl: float, reason: str):
    emoji = "✅" if pnl >= 0 else "❌"
    sign  = "+" if pnl >= 0 else ""
    send_message(
        f"{emoji} <b>SELL {symbol.replace('.BSE', '')}</b>\n"
        f"📉 Price:  ₹{price:.2f}\n"
        f"💵 P&amp;L:   {sign}₹{pnl:.2f}\n"
        f"📌 Reason: {reason}"
    )

def notify_stop_loss(symbol: str, price: float, loss: float):
    send_message(
        f"🔴 <b>STOP-LOSS HIT — {symbol.replace('.BSE', '')}</b>\n"
        f"📉 Price: ₹{price:.2f}\n"
        f"💸 Loss:  ₹{loss:.2f}"
    )

def notify_target(symbol: str, price: float, profit: float):
    send_message(
        f"🎯 <b>TARGET HIT — {symbol.replace('.BSE', '')}</b>\n"
        f"📈 Price:  ₹{price:.2f}\n"
        f"💰 Profit: +₹{profit:.2f}"
    )

def notify_circuit_breaker(today_pnl: float):
    send_message(
        f"⚠️ <b>CIRCUIT BREAKER TRIGGERED</b>\n"
        f"📛 Daily loss limit reached\n"
        f"💸 Today P&amp;L: ₹{today_pnl:.2f}\n"
        f"🛑 No more trades today"
    )
