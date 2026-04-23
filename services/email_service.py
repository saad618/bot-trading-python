import os
import logging
import traceback
import resend
from config import settings

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")

def send_html_email(subject: str, html: str):
    if not resend.api_key:
        logger.error("RESEND_API_KEY not set")
        return
    try:
        logger.info(f"Sending email to {settings.REPORT_EMAIL} via Resend...")
        params = {
            "from": "Trading Bot <onboarding@resend.dev>",
            "to": [settings.REPORT_EMAIL],
            "subject": subject,
            "html": html,
        }
        resend.Emails.send(params)
        logger.info(f"Email sent successfully to {settings.REPORT_EMAIL}")
    except Exception as e:
        logger.error(f"Email failed: {e}")
        logger.error(traceback.format_exc())
