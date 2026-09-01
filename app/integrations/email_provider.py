"""
Email sending integration (Google SMTP + HTTPS Fallback).
Replaces SendGrid to ensure DMARC alignment and zero-spam delivery for Gmail addresses.
Includes Multi-IPv4 socket routing and SSL/TLS auto-failover to prevent cloud container timeouts.
"""
import socket
import smtplib
import ssl
import uuid
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.integrations.base import IntegrationError, IntegrationNotConfiguredError

logger = logging.getLogger(__name__)


def _connect_smtp_multi_ipv4(host: str = "smtp.gmail.com", port: int = 465, timeout: int = 6, use_ssl: bool = True):
    """
    Connects to SMTP trying all resolved IPv4 (AF_INET) addresses with fast timeout.
    Bypasses unreachable IPv6 routes and single-IP socket hangs in cloud containers (Render, AWS, Docker).
    """
    try:
        addr_infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except Exception as e:
        raise OSError(f"Could not resolve IPv4 for {host}: {e}")

    last_err = None
    for addr in addr_infos:
        ip, resolved_port = addr[4]
        try:
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
        except Exception as conn_err:
            last_err = conn_err
            continue

    if last_err:
        raise last_err
    raise OSError(f"All IPv4 endpoints for {host}:{port} failed")


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
        Sends a transactional email via Google SMTP with multi-IPv4 routing and fast auto-failover.
        Returns {"message_id": str, "status": str}.
        """
        if not self.is_configured():
            raise IntegrationNotConfiguredError(
                "Google SMTP configurations are not fully set in .env (GOOGLE_EMAIL and GOOGLE_APP_PASSWORD required)"
            )

        # Determine SMTP credentials
        if settings.GOOGLE_EMAIL and settings.GOOGLE_APP_PASSWORD:
            smtp_user = settings.GOOGLE_EMAIL.strip()
            smtp_password = settings.GOOGLE_APP_PASSWORD.replace(" ", "").strip()
        else:
            smtp_user = (settings.FROM_EMAIL or "").strip()
            smtp_password = (settings.SENDGRID_API_KEY or "").replace(" ", "").strip()

        display_name = from_name or settings.FROM_NAME or "Creator Forge"

        # Create MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{display_name} <{smtp_user}>"
        msg["To"] = to_email

        # Attach text and html parts
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        errors = []

        # 1. Primary Method: Port 465 (SSL) with Multi-IPv4 routing (Fastest & most cloud-friendly)
        try:
            server = _connect_smtp_multi_ipv4("smtp.gmail.com", port=465, timeout=6, use_ssl=True)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e465:
            errors.append(f"Port 465 (IPv4 SSL): {e465}")
            logger.warning(f"[EmailProvider] Port 465 SSL failed: {e465}")

        # 2. Secondary Method: Port 587 (STARTTLS) with Multi-IPv4 routing
        try:
            server = _connect_smtp_multi_ipv4("smtp.gmail.com", port=587, timeout=6, use_ssl=False)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e587:
            errors.append(f"Port 587 (IPv4 STARTTLS): {e587}")
            logger.warning(f"[EmailProvider] Port 587 STARTTLS failed: {e587}")

        # 3. Tertiary Method: Standard SMTP_SSL fallback (Port 465)
        try:
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=6)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e_std_ssl:
            errors.append(f"Standard SSL: {e_std_ssl}")

        # 4. Quaternary Method: Standard SMTP fallback (Port 587)
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=6)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
            server.quit()
            return {"message_id": str(uuid.uuid4()), "status": "sent"}
        except Exception as e_std:
            errors.append(f"Standard STARTTLS: {e_std}")

        # 5. HTTPS API Fallback (SendGrid if configured)
        if settings.SENDGRID_API_KEY:
            try:
                import urllib.request
                import json
                sg_data = {
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": settings.FROM_EMAIL or smtp_user, "name": display_name},
                    "subject": subject,
                    "content": [
                        {"type": "text/plain", "value": body_text},
                        {"type": "text/html", "value": body_html}
                    ]
                }
                req = urllib.request.Request(
                    "https://api.sendgrid.com/v3/mail/send",
                    data=json.dumps(sg_data).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {settings.SENDGRID_API_KEY.strip()}",
                        "Content-Type": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 202):
                        return {"message_id": str(uuid.uuid4()), "status": "sent"}
            except Exception as sg_err:
                errors.append(f"SendGrid HTTPS: {sg_err}")

        raise IntegrationError(f"SMTP delivery failed across all protocols: {' | '.join(errors)}")

    def check_bounce_status(self, email: str) -> bool:
        return False


email_provider = EmailProvider()
