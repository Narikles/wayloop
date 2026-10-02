"""Envoi des e-mails (SMTP). Tout passe par e-mail : dirigeant comme candidats.

En mode « console », rien ne part ; le message est journalisé et conservé en base
(utile en développement et en démonstration).
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid

from ..config import get_settings

log = logging.getLogger("wayloop.channels")


@dataclass
class Attachment:
    filename: str
    content: bytes
    mime: str = "application/octet-stream"


@dataclass
class SendResult:
    ok: bool
    error: str | None = None
    provider_id: str | None = None
    extra: dict = field(default_factory=dict)


def send_email(to: str, subject: str, body: str, attachments: list[Attachment] | None = None,
               reply_to: str | None = None) -> SendResult:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="wayloop.local")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    for a in attachments or []:
        maintype, _, subtype = a.mime.partition("/")
        msg.add_attachment(a.content, maintype=maintype, subtype=subtype or "octet-stream", filename=a.filename)
    if s.email_backend == "console":
        log.info("E-MAIL (console) à %s : %s\n%s", to, subject, body)
        return SendResult(True)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        return SendResult(True)
    except Exception as exc:  # noqa: BLE001
        log.exception("Échec d'envoi e-mail")
        return SendResult(False, str(exc)[:300])
