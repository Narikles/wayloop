"""Candidatures reçues par e-mail : une adresse par recrutement, relevée en IMAP.

Chaque recrutement a son adresse « offres+<code>@domaine » (INBOUND_ADDRESS). Elle figure dans
les textes à coller sur les sites d'emploi ; le dirigeant peut aussi y transférer un e-mail de
candidature reçu ailleurs. Le worker (ou le planificateur intégré) relève la boîte : chaque
e-mail avec un CV en pièce jointe (PDF, DOCX, TXT) devient une candidature, provenance
« e-mail », et le candidat reçoit l'accusé avec l'information RGPD et le lien pour répondre
aux questions du poste.

Seule une empreinte de chaque e-mail est conservée (pour ne pas le traiter deux fois).
"""
from __future__ import annotations

import email
import hashlib
import imaplib
import logging
import re
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import getaddresses, parseaddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Application, Candidate, InboundEmail, Recruitment, User
from ..orchestrator_errors import FlowError

log = logging.getLogger("wayloop.inbound")
CV_TYPES = {"application/pdf": ".pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "text/plain": ".txt"}
FORWARD_FROM = re.compile(r"^\s*(?:De|From|Expéditeur)\s*:\s*(.+)$", re.I | re.M)


def configured() -> bool:
    s = get_settings()
    return bool(s.inbound_address and s.imap_host and s.imap_user and s.imap_password)


def _recipients(msg: EmailMessage) -> list[str]:
    values = [str(v) for h in ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To") for v in (msg.get_all(h) or [])]
    return [a.lower() for _, a in getaddresses(values) if a]


def _recruitment_for(db: Session, msg: EmailMessage) -> Recruitment | None:
    addr = (get_settings().inbound_address or "").lower()
    if "@" not in addr:
        return None
    local, domain = addr.split("@", 1)
    pattern = re.compile(rf"^{re.escape(local)}\+([a-z0-9]+)@{re.escape(domain)}$")
    for r in _recipients(msg):
        m = pattern.match(r)
        if m:
            return db.execute(select(Recruitment).where(Recruitment.public_token == m.group(1))).scalar_one_or_none()
    return None


def _body_text(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain",))
    if part is None:
        part = msg.get_body(preferencelist=("html",))
        if part is None:
            return ""
        return re.sub(r"<[^>]+>", " ", part.get_content())
    return part.get_content()


def _sender(db: Session, rec: Recruitment, msg: EmailMessage, body: str) -> tuple[str, str]:
    """(nom affiché, adresse) du candidat ; si le dirigeant a transféré l'e-mail, l'expéditeur d'origine."""
    name, addr = parseaddr(str(msg.get("From", "")))
    addr = addr.lower()
    team = {u.email.lower() for u in db.execute(select(User).where(User.company_id == rec.company_id)).scalars()}
    if addr in team:
        for line in FORWARD_FROM.findall(body):
            n2, a2 = parseaddr(line.strip())
            if a2 and "@" in a2 and a2.lower() not in team:
                return n2.strip().strip('"'), a2.lower()
        return "", ""
    return name.strip().strip('"'), addr


def _cv(msg: EmailMessage) -> tuple[bytes, str, str] | None:
    limit = get_settings().max_upload_mb * 1024 * 1024
    for part in msg.iter_attachments():
        ctype = part.get_content_type()
        fname = part.get_filename() or ""
        suffix = CV_TYPES.get(ctype) or next((x for x in (".pdf", ".docx", ".txt") if fname.lower().endswith(x)), None)
        if not suffix:
            continue
        data = part.get_payload(decode=True) or b""
        if 0 < len(data) <= limit:
            return data, fname or f"cv{suffix}", ctype
    return None


def _split_name(display: str, addr: str) -> tuple[str, str]:
    display = re.sub(r"\s+", " ", display).strip()
    if display and "@" not in display:
        parts = display.split(" ")
        if len(parts) >= 2:
            return parts[0][:80], " ".join(parts[1:])[:80]
        return parts[0][:80], "-"
    local = addr.split("@")[0]
    bits = [b for b in re.split(r"[._-]+", local) if b and not b.isdigit()]
    if len(bits) >= 2:
        return bits[0].capitalize()[:80], " ".join(b.capitalize() for b in bits[1:])[:80]
    return (bits[0].capitalize() if bits else "Candidat")[:80], "-"


def process_message(db: Session, raw: bytes) -> InboundEmail:
    """Traite un e-mail reçu. Renvoie l'enregistrement (created | ignored | error), jamais d'exception."""
    from .. import orchestrator as orch

    msg = email.message_from_bytes(raw, policy=default_policy)
    assert isinstance(msg, EmailMessage)
    mid = str(msg.get("Message-ID") or "") or hashlib.sha256(raw).hexdigest()
    h = hashlib.sha256(mid.encode("utf-8", "replace")).hexdigest()
    seen = db.execute(select(InboundEmail).where(InboundEmail.message_hash == h)).scalar_one_or_none()
    if seen:
        return seen
    rec_row = InboundEmail(message_hash=h, status="ignored")
    db.add(rec_row)

    def done(status: str, detail: str) -> InboundEmail:
        rec_row.status, rec_row.detail = status, detail[:255]
        db.flush()
        return rec_row

    auto = str(msg.get("Auto-Submitted", "no")).lower()
    sender = parseaddr(str(msg.get("From", "")))[1].lower()
    if auto != "no" or sender.startswith(("mailer-daemon", "postmaster", "no-reply", "noreply")):
        return done("ignored", "message automatique")
    rec = _recruitment_for(db, msg)
    if rec is None:
        return done("ignored", "adresse sans code de recrutement")
    rec_row.recruitment_id = rec.id
    body = _body_text(msg)
    name, addr = _sender(db, rec, msg, body)
    if not addr:
        return done("ignored", "expéditeur d'origine introuvable dans le message transféré")
    cv = _cv(msg)
    if not cv and len(body.strip()) < 30:
        return done("ignored", "ni CV ni message")
    first, last = _split_name(name, addr)
    # Déjà candidat avec cette adresse : on complète le CV s'il manquait.
    from ..crypto import hash_token

    email_h = hash_token("email:" + rec.company_id + ":" + addr)
    cand = db.execute(select(Candidate).where(Candidate.company_id == rec.company_id,
                                              Candidate.email_hash == email_h)).scalar_one_or_none()
    if cand:
        app = db.execute(select(Application).where(Application.recruitment_id == rec.id,
                                                   Application.candidate_id == cand.id)).scalar_one_or_none()
        if app and app.status != "withdrawn":
            if cv and not app.cv_file_key:
                orch._store_cv(app, *cv)
                rec_row.application_id = app.id
                return done("created", "CV ajouté à une candidature existante")
            return done("ignored", "déjà candidat")
    try:
        app = orch.add_candidate(db, rec, None, first_name=first, last_name=last, email=addr, phone=None,
                                 source="email", message=re.sub(r"\n{3,}", "\n\n", body.strip())[:3000] or None,
                                 note=None, cv_bytes=cv[0] if cv else None, cv_filename=cv[1] if cv else None,
                                 cv_mime=cv[2] if cv else None, send_ack=True)
    except FlowError as exc:
        return done("error", exc.message)
    rec_row.application_id = app.id
    return done("created", "candidature créée")


def fetch(db: Session, limit: int = 20) -> int:
    """Relève la boîte IMAP (messages non lus). Renvoie le nombre de candidatures créées."""
    if not configured():
        return 0
    s = get_settings()
    created = 0
    try:
        with imaplib.IMAP4_SSL(s.imap_host, s.imap_port, timeout=30) as imap:  # type: ignore[arg-type]
            imap.login(s.imap_user or "", s.imap_password or "")
            imap.select(s.imap_folder)
            typ, data = imap.search(None, "UNSEEN")
            if typ != "OK":
                return 0
            for num in (data[0].split() if data and data[0] else [])[:limit]:
                typ, parts = imap.fetch(num, "(RFC822)")
                if typ != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                row = process_message(db, parts[0][1])
                db.commit()
                created += 1 if row.status == "created" else 0
                imap.store(num, "+FLAGS", "\\Seen")
    except Exception as exc:  # noqa: BLE001 - boîte indisponible : on réessaiera au prochain passage
        db.rollback()
        log.warning("Relève de la boîte de candidatures impossible : %s", str(exc)[:200])
    return created
