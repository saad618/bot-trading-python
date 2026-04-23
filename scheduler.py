import logging
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from database import SessionLocal
from services.portfolio import portfolio_service
from services.email_service import send_html_email
import services.trading as trading_svc

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

def _run_trading_cycle():
    db = SessionLocal()
    try:
        trading_svc.execute_trading_cycle(db)
    finally:
        db.close()

def send_daily_report():
    import traceback
    db = SessionLocal()
    try:
        today_trades = trading_svc.get_today_trades(db)
        open_positions = trading_svc.get_open_positions(db)
        today_pnl = trading_svc.get_today_pnl(db)
        total_pnl = trading_svc.get_total_pnl(db)
        cash = portfolio_service.get_cash_balance()

        subject = ("[Trading Bot] Daily Report " + date.today().strftime('%d-%b-%Y') +
                   " | P&L: " + ('+' if today_pnl >= 0 else '') + "Rs" + f"{today_pnl:.2f}")
        html = _build_html_report(today_trades, open_positions, today_pnl, total_pnl, cash)
        send_html_email(subject, html)
    except Exception as e:
        logger.error(f"send_daily_report failed: {e}")
        logger.error(traceback.format_exc())
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(_run_trading_cycle, CronTrigger(
        day_of_week="mon-fri", hour="9-15", minute="*/5", timezone="Asia/Kolkata"
    ), id="trading_cycle")
    scheduler.add_job(send_daily_report, CronTrigger(
        day_of_week="mon-fri", hour=15, minute=35, timezone="Asia/Kolkata"
    ), id="daily_report")
    scheduler.start()
    logger.info("Scheduler started — trading every 5 min, report at 15:35 IST")

def _build_html_report(trades, open_positions, today_pnl, total_pnl, cash):
    date_str = date.today().strftime("%A, %d %B %Y")
    pnl_color = "#27ae60" if today_pnl >= 0 else "#e74c3c"
    total_color = "#27ae60" if total_pnl >= 0 else "#e74c3c"

    trades_html = ""
    if not trades:
        trades_html = "<tr><td colspan='6' style='text-align:center;padding:15px;color:#888;'>No trades today</td></tr>"
    else:
        for t in trades:
            type_color = "#2980b9" if t.type.value == "BUY" else "#8e44ad"
            if t.type.value == "SELL":
                pnl_color = "#27ae60" if t.realized_pnl >= 0 else "#e74c3c"
                pnl_sign = "+" if t.realized_pnl >= 0 else ""
                pnl_cell = f"<td style='color:{pnl_color};font-weight:bold;'>{pnl_sign}Rs{t.realized_pnl:.2f}</td>"
            else:
                pnl_cell = "<td style='color:#888;'>-</td>"
            trades_html += f"""
            <tr style='border-bottom:1px solid #eee;'>
                <td style='padding:10px;font-weight:bold;'>{t.symbol.replace('.BSE','')}</td>
                <td style='padding:10px;'><span style='background:{type_color};color:white;padding:3px 8px;border-radius:4px;font-size:12px;'>{t.type.value}</span></td>
                <td style='padding:10px;'>{t.quantity}</td>
                <td style='padding:10px;'>₹{t.price:.2f}</td>
                {pnl_cell}
                <td style='padding:10px;color:#888;font-size:12px;'>{t.executed_at.strftime('%H:%M:%S')}</td>
            </tr>"""

    if not open_positions:
        pos_html = "<p style='color:#888;text-align:center;'>No open positions</p>"
    else:
        pos_html = "<table style='width:100%;border-collapse:collapse;'><tr style='background:#f8f9fa;'><th style='padding:8px;text-align:left;'>Symbol</th><th>Qty</th><th>Entry</th><th>Stop-Loss</th><th>Target</th></tr>"
        for p in open_positions:
            pos_html += f"""<tr style='border-bottom:1px solid #eee;'>
                <td style='padding:8px;font-weight:bold;'>{p.symbol.replace('.BSE','')}</td>
                <td style='padding:8px;text-align:center;'>{p.quantity}</td>
                <td style='padding:8px;text-align:center;'>₹{p.entry_price:.2f}</td>
                <td style='padding:8px;text-align:center;color:#e74c3c;'>₹{p.stop_loss_price:.2f}</td>
                <td style='padding:8px;text-align:center;color:#27ae60;'>₹{p.target_price:.2f}</td>
            </tr>"""
        pos_html += "</table>"

    return f"""<html><body style="font-family:Arial,sans-serif;max-width:650px;margin:0 auto;background:#f0f2f5;">
      <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);color:white;padding:30px;text-align:center;border-radius:8px 8px 0 0;">
        <h1 style="margin:0;font-size:24px;">📈 Trading Bot Daily Report</h1>
        <p style="margin:8px 0 0;color:#aaa;">{date_str}</p>
      </div>
      <div style="display:flex;gap:12px;padding:20px;background:white;">
        <div style="flex:1;background:#f8f9fa;padding:15px;border-radius:8px;text-align:center;border-left:4px solid {pnl_color};">
          <div style="font-size:22px;font-weight:bold;color:{pnl_color};">{'+' if today_pnl >= 0 else ''}₹{today_pnl:.2f}</div>
          <div style="color:#888;font-size:13px;margin-top:4px;">Today's P&L</div>
        </div>
        <div style="flex:1;background:#f8f9fa;padding:15px;border-radius:8px;text-align:center;border-left:4px solid {total_color};">
          <div style="font-size:22px;font-weight:bold;color:{total_color};">{'+' if total_pnl >= 0 else ''}₹{total_pnl:.2f}</div>
          <div style="color:#888;font-size:13px;margin-top:4px;">Total P&L</div>
        </div>
        <div style="flex:1;background:#f8f9fa;padding:15px;border-radius:8px;text-align:center;border-left:4px solid #3498db;">
          <div style="font-size:22px;font-weight:bold;color:#2c3e50;">₹{cash:.2f}</div>
          <div style="color:#888;font-size:13px;margin-top:4px;">Cash Balance</div>
        </div>
        <div style="flex:1;background:#f8f9fa;padding:15px;border-radius:8px;text-align:center;border-left:4px solid #9b59b6;">
          <div style="font-size:22px;font-weight:bold;color:#2c3e50;">{len(trades)}</div>
          <div style="color:#888;font-size:13px;margin-top:4px;">Trades Today</div>
        </div>
      </div>
      <div style="background:white;margin-top:2px;padding:20px;">
        <h3 style="margin:0 0 15px;color:#2c3e50;">Today's Trades</h3>
        <table style="width:100%;border-collapse:collapse;">
          <tr style="background:#f8f9fa;font-size:13px;color:#888;">
            <th style="padding:10px;text-align:left;">SYMBOL</th><th style="padding:10px;">TYPE</th>
            <th style="padding:10px;">QTY</th><th style="padding:10px;">PRICE</th>
            <th style="padding:10px;">P&L</th><th style="padding:10px;">TIME</th>
          </tr>{trades_html}
        </table>
      </div>
      <div style="background:white;margin-top:2px;padding:20px;">
        <h3 style="margin:0 0 15px;color:#2c3e50;">Open Positions ({len(open_positions)})</h3>
        {pos_html}
      </div>
      <div style="background:#2c3e50;color:#aaa;padding:15px;text-align:center;font-size:12px;border-radius:0 0 8px 8px;">
        Trading Bot | Paper Trading Mode | Auto-generated at market close
      </div>
    </body></html>"""
