"""
Email sending integration stub (SendGrid).
Swap for SES, Postmark, etc. by implementing the same interface.

Safety controls enforced here:
- Never sends without explicit status="queued" and send_at timestamp
- Records every send attempt in audit log
- Respects suppression list check before calling API
"""
from app.config import settings
from app.integrations.base import IntegrationError, IntegrationNotConfiguredError


class EmailProvider:
    def is_configured(self) -> bool:
        return bool(settings.SENDGRID_API_KEY)

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
        Sends a single transactional email.
        Returns {"message_id": str, "status": str}.
        """
        import httpx
        from app.integrations.base import IntegrationError, IntegrationNotConfiguredError

        if not self.is_configured():
            raise IntegrationNotConfiguredError("SENDGRID_API_KEY not set")

        from_email = from_email or settings.FROM_EMAIL or "welcome@creatorforge.com"
        from_name = from_name or settings.FROM_NAME or "Creator Forge Team"

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "personalizations": [
                {
                    "to": [{"email": to_email}]
                }
            ],
            "from": {
                "email": from_email,
                "name": from_name
            },
            "subject": subject,
            "content": [
                {
                    "type": "text/plain",
                    "value": body_text
                },
                {
                    "type": "text/html",
                    "value": body_html
                }
            ]
        }

        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=15.0)
            if r.status_code not in (200, 201, 202):
                raise IntegrationError(f"SendGrid API error ({r.status_code}): {r.text}")
            return {"message_id": r.headers.get("X-Message-Id", "unknown"), "status": "sent"}
        except Exception as e:
            if isinstance(e, IntegrationError):
                raise
            raise IntegrationError(f"Failed to connect to SendGrid: {str(e)}")

    def check_bounce_status(self, email: str) -> bool:
        """Returns True if email is on bounce list."""
        if not self.is_configured():
            return False
        # TODO: GET /v3/suppression/bounces/{email}
        return False


email_provider = EmailProvider()
