"""
macOS LibreSSL 2.8.3 Double-Free Workaround
In macOS Apple Python 3.9 linked against LibreSSL 2.8.3 (/usr/lib/libssl.46.dylib),
handling TLS 1.3 NewSessionTicket messages in libssl (ssl3_get_new_session_ticket -> CBS_stow)
crashes with a fatal double-free abort:
  malloc: Double free of object 0x...
  zsh: abort python3 run.py
Disabling session tickets (OP_NO_TICKET) and capping TLS at TLSv1_2 prevents calling
ssl3_get_new_session_ticket entirely.
"""
import ssl
import logging

logger = logging.getLogger("creator_forge.ssl")

openssl_ver = getattr(ssl, "OPENSSL_VERSION", "")
if "libressl" in openssl_ver.lower():
    try:
        _orig_ssl_context_init = ssl.SSLContext.__init__

        def _safe_ssl_context_init(self, *args, **kwargs):
            try:
                _orig_ssl_context_init(self)
            except Exception:
                pass
            if hasattr(ssl, "OP_NO_TICKET"):
                self.options |= ssl.OP_NO_TICKET
            if hasattr(ssl, "TLSVersion") and hasattr(ssl.TLSVersion, "TLSv1_2"):
                try:
                    self.maximum_version = ssl.TLSVersion.TLSv1_2
                except Exception:
                    pass

        ssl.SSLContext.__init__ = _safe_ssl_context_init

        _orig_create_default_context = ssl.create_default_context

        def _safe_create_default_context(*args, **kwargs):
            ctx = _orig_create_default_context(*args, **kwargs)
            if hasattr(ssl, "OP_NO_TICKET"):
                ctx.options |= ssl.OP_NO_TICKET
            if hasattr(ssl, "TLSVersion") and hasattr(ssl.TLSVersion, "TLSv1_2"):
                try:
                    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
                except Exception:
                    pass
            return ctx

        ssl.create_default_context = _safe_create_default_context
        if hasattr(ssl, "_create_default_https_context"):
            ssl._create_default_https_context = _safe_create_default_context
    except Exception as e:
        logger.warning(f"[SSL Patch] Could not apply LibreSSL workaround: {e}")
