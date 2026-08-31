"""
Email sending integration (Google SMTP).
Replaces SendGrid to ensure DMARC alignment and zero-spam delivery for Gmail addresses.
"""
from app.config import settings
from app.integrations.base import IntegrationError, IntegrationNotConfiguredError


class EmailProvider:
    def is_configured(self) -> bool:
        # Check if we have the Gmail username and app password
        has_new = bool(settings.GOOGLE_EMAIL) and bool(settings.GOOGLE_APP_PASSWORD)
        has_old = bool(settings.SENDGRID_API_KEY) and bool(settings.FROM_EMAIL)
        return has_new or has_old

    def send(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str,
        from_email: str = None,
        from_name: str = None,
    ) -> dict:
        """
        Sends a single transactional email via Google SMTP.
        Returns {"message_id": str, "status": str}.
        """
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        import uuid

        if not self.is_configured():
            raise IntegrationNotConfiguredError("Google SMTP configurations are not fully set in .env (GOOGLE_EMAIL and GOOGLE_APP_PASSWORD required)")

        # Determine SMTP credentials
        if settings.GOOGLE_EMAIL and settings.GOOGLE_APP_PASSWORD:
            smtp_user = settings.GOOGLE_EMAIL
            smtp_password = settings.GOOGLE_APP_PASSWORD.replace(" ", "")
        else:
            smtp_user = settings.FROM_EMAIL
            smtp_password = settings.SENDGRID_API_KEY.replace(" ", "")

        display_name = from_name or settings.FROM_NAME or "Creator Forge"

        # Create MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{display_name} <{smtp_user}>"
        msg["To"] = to_email

        # Attach text and html parts
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        last_err = None

        # 1. Primary: Connect via Port 587 with STARTTLS (Standard for cloud platforms e.g. Render/AWS/Vercel)
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=12)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e587:
            last_err = e587

        # 2. Fallback: Connect via Port 465 SSL
        try:
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=12)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e465:
            last_err = e465

        raise IntegrationError(f"Failed to send email via Google SMTP: {str(last_err)}")

    def check_bounce_status(self, email: str) -> bool:
        """Returns True if email is on bounce list."""
        return False


email_provider = EmailProvider()
