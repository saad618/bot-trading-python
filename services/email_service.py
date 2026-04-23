import smtplib
import logging
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import settings

logger = logging.getLogger(__name__)

def send_html_email(subject: str, html: str):
    logger.info(f"Connecting to {settings.MAIL_HOST}:587 as {settings.MAIL_USERNAME}")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.MAIL_USERNAME
        msg["To"] = settings.REPORT_EMAIL
        msg.attach(MIMEText(html, "html"))

        server = smtplib.SMTP(settings.MAIL_HOST, 587, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_USERNAME, settings.REPORT_EMAIL, msg.as_string())
        server.quit()

        logger.info(f"Email sent successfully to {settings.REPORT_EMAIL}")

    except Exception as e:
        logger.error(f"Email failed: {e}")
        logger.error(traceback.format_exc())
