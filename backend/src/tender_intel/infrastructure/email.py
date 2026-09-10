"""SMTP delivery (implements the EmailSender port).

Credentials come from settings, which come from the environment. Nothing is
hardcoded here, and no recipient address appears anywhere in this module — the
recipient set is resolved from the user table by role at send time.

``smtplib`` is synchronous, so the send runs on a worker thread rather than
blocking the event loop, the same way file IO does in ``storage.py``.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from tender_intel.core.config import Settings
from tender_intel.infrastructure.observability.logging import get_logger

_log = get_logger(__name__)


class EmailNotConfiguredError(RuntimeError):
    """Raised when a send is attempted with no SMTP host configured.

    Deliberately loud. A notification feature that silently does nothing because
    a variable is unset is worse than one that fails, because nobody finds out
    until the tender they were meant to see has closed.
    """


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(
        self, *, to: list[str], subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        s = self._settings
        if not s.smtp_host or not s.notification_from_email:
            raise EmailNotConfiguredError(
                "SMTP_HOST and NOTIFICATION_FROM_EMAIL must be set to send notifications"
            )
        if not to:
            # The caller is responsible for treating an empty recipient set as a
            # failure; refusing here as well keeps a bug from becoming a no-op.
            raise ValueError("refusing to send with no recipients")

        message = EmailMessage()
        message["From"] = s.notification_from_email
        # Recipients go in Bcc, not To. A digest is sent to everyone holding a
        # role, and disclosing that roster to each recipient is not this
        # feature's business.
        message["To"] = s.notification_from_email
        message["Bcc"] = ", ".join(to)
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        await asyncio.to_thread(self._deliver, message, to)
        _log.info("notification.sent", recipients=len(to), subject=subject)

    def _deliver(self, message: EmailMessage, to: list[str]) -> None:
        s = self._settings
        assert s.smtp_host is not None  # guarded by the caller
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as client:
            if s.smtp_use_tls:
                client.starttls()
            if s.smtp_user and s.smtp_password:
                client.login(s.smtp_user, s.smtp_password)
            client.send_message(message, to_addrs=to)
