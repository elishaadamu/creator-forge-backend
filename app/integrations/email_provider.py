"""
Email sending integration (Google SMTP).
Replaces SendGrid to ensure DMARC alignment and zero-spam delivery for Gmail addresses.
Includes IPv4 forced socket routing to prevent Linux container [Errno 101] Network unreachable errors on cloud platforms (e.g. Render/Docker).
"""
import socket
import smtplib
import ssl
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.integrations.base import IntegrationError, IntegrationNotConfiguredError


def _connect_smtp_ipv4(host: str = "smtp.gmail.com", port: int = 587, timeout: int = 15, use_ssl: bool = False):
    """
    Connects to SMTP explicitly forcing IPv4 (AF_INET) resolution.
    Bypasses broken/unreachable IPv6 routes in cloud containers (Render, AWS ECS, Docker).
    """
    # 1. Resolve host explicitly to IPv4
    addr_info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    if not addr_info:
        raise OSError(f"Could not resolve IPv4 address for {host}")

    ip, resolved_port = addr_info[0][4]

    # 2. Establish IPv4 socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((ip, resolved_port))

    if use_ssl:
        ctx = ssl.create_default_context()
        sslsock = ctx.wrap_socket(sock, server_hostname=host)
        server = smtplib.SMTP_SSL()
        server._host = host
        server.sock = sslsock
        server.file = sslsock.makefile("rb")
        server.getreply()
        return server
    else:
        server = smtplib.SMTP()
        server._host = host
        server.sock = sock
        server.file = sock.makefile("rb")
        server.getreply()
        server.ehlo("creatorforge.com")
        ctx = ssl.create_default_context()
        server.starttls(context=ctx)
        server.ehlo("creatorforge.com")
        return server


class EmailProvider:
    def is_configured(self) -> bool:
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
        Sends a single transactional email via Google SMTP with IPv4 enforcement.
        Returns {"message_id": str, "status": str}.
        """
        if not self.is_configured():
            raise IntegrationNotConfiguredError(
                "Google SMTP configurations are not fully set in .env (GOOGLE_EMAIL and GOOGLE_APP_PASSWORD required)"
            )

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

        # 1. Primary: Port 587 STARTTLS with forced IPv4
        try:
            server = _connect_smtp_ipv4("smtp.gmail.com", port=587, timeout=15, use_ssl=False)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e587:
            last_err = e587

        # 2. Fallback: Port 465 SSL with forced IPv4
        try:
            server = _connect_smtp_ipv4("smtp.gmail.com", port=465, timeout=15, use_ssl=True)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e465:
            last_err = e465

        raise IntegrationError(f"Failed to send email via Google SMTP: {str(last_err)}")

    def check_bounce_status(self, email: str) -> bool:
        return False


email_provider = EmailProvider()
