import smtplib
import logging
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import settings

logger = logging.getLogger(__name__)

def send_html_email(subject: str, html: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.MAIL_USERNAME
        msg["To"] = settings.REPORT_EMAIL
        msg.attach(MIMEText(html, "html"))

        # Use port 465 with SSL (Railway blocks 587)
        with smtplib.SMTP_SSL(settings.MAIL_HOST, 465) as server:
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            server.sendmail(settings.MAIL_USERNAME, settings.REPORT_EMAIL, msg.as_string())

        logger.info(f"Email sent to {settings.REPORT_EMAIL}")

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        logger.error(traceback.format_exc())
