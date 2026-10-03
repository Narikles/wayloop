"""Communication avec les candidats : accusé, information RGPD, rendez-vous, réponse à tous.

Textes courts et respectueux. L'information RGPD (art. 13 et 14) et l'information sur
la méthode de présélection (art. L1221-8 du Code du travail) sont données au candidat dès
l'accusé de réception ; le dirigeant n'a rien à configurer pour cela.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..models import Company, Recruitment

TZ = ZoneInfo("Europe/Paris")
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def fr_datetime(dt: datetime) -> str:
    d = dt.astimezone(TZ)
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} à {d.hour}h{d.minute:02d}"


def fr_date(dt: datetime) -> str:
    d = dt.astimezone(TZ)
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


def _sign(company: Company) -> str:
    return f"\n\n{company.name}"


def retention_sentence(company: Company) -> str:
    months = company.retention_months or get_settings().retention_months_after_last_contact
    return (f"Vos données sont conservées au plus {months} mois après notre dernier échange, "
            "puis supprimées automatiquement.")


def acknowledgment(company: Company, rec: Recruitment, first_name: str | None, data_link: str,
                   privacy_link: str) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    hello = f"Bonjour {first_name}," if first_name else "Bonjour,"
    body = f"""{hello}

Nous avons bien reçu votre candidature au poste « {title} ». Merci de votre intérêt.

Comment se passe la suite :
- {company.name} examine toutes les candidatures et vous répondra, que la réponse soit positive ou non.
- Si votre profil correspond, nous vous proposerons un entretien.

Ce que nous faisons de vos données :
- Responsable du traitement : {company.name}. Finalité : examiner votre candidature à ce poste.
- Vos réponses et votre CV sont comparés aux critères du poste selon des règles fixes, identiques pour tous ; les informations sans rapport avec le poste (âge, adresse, situation de famille…) sont masquées. Rien n'est décidé automatiquement : toutes les candidatures restent consultables et c'est une personne de l'entreprise qui décide.
- {retention_sentence(company)}
- Vous pouvez consulter vos données, retirer votre candidature ou demander leur suppression à tout moment : {data_link}
- Notice complète et contact : {privacy_link}{_sign(company)}"""
    return f"Candidature reçue : {title}", body


def acknowledgment_received(company: Company, rec: Recruitment, first_name: str | None, data_link: str,
                            privacy_link: str, complete_link: str | None, channel: str) -> tuple[str, str]:
    """Accusé pour une candidature reçue par e-mail ou transmise autrement (message, appel) : même
    information RGPD que l'accusé du formulaire, et lien pour répondre aux questions du poste."""
    title = rec.profile.get("title") or rec.title
    hello = f"Bonjour {first_name}," if first_name else "Bonjour,"
    how = {"email": "par e-mail", "linkedin": "par LinkedIn", "telephone": "par téléphone"}.get(channel, "")
    complete = (f"\n\nPour compléter votre candidature, merci de répondre à quelques questions sur le poste "
                f"(2 minutes, CV facultatif si vous l'avez déjà envoyé) : {complete_link}") if complete_link else ""
    body = f"""{hello}

Nous avons bien reçu votre candidature{(' ' + how) if how else ''} au poste « {title} ». Merci de votre intérêt.{complete}

Comment se passe la suite :
- {company.name} examine toutes les candidatures et vous répondra, que la réponse soit positive ou non.
- Si votre profil correspond, nous vous proposerons un entretien.

Ce que nous faisons de vos données :
- Responsable du traitement : {company.name}. Finalité : examiner votre candidature à ce poste. Vos coordonnées et votre CV ont été enregistrés dans notre outil de recrutement à partir de votre envoi.
- Vos réponses et votre CV sont comparés aux critères du poste selon des règles fixes, identiques pour tous ; les informations sans rapport avec le poste (âge, adresse, situation de famille…) sont masquées. Rien n'est décidé automatiquement : c'est une personne de l'entreprise qui décide.
- {retention_sentence(company)}
- Vous pouvez consulter vos données, retirer votre candidature ou demander leur suppression à tout moment : {data_link}
- Notice complète et contact : {privacy_link}{_sign(company)}"""
    return f"Candidature reçue : {title}", body


def complete_reminder(company: Company, rec: Recruitment, first_name: str | None, complete_link: str,
                      data_link: str) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

Votre candidature au poste « {title} » est bien enregistrée. Il ne manque que vos réponses à quelques questions sur le poste (2 minutes) : {complete_link}

Si vous ne souhaitez plus donner suite, vous pouvez retirer votre candidature ici : {data_link}{_sign(company)}"""
    return f"Votre candidature au poste « {title} » : une étape à finir", body


def invitation_reminder(company: Company, rec: Recruitment, first_name: str | None,
                        booking_link: str | None) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    ask = (f"Choisissez le créneau qui vous convient : {booking_link}" if booking_link else
           "Pourriez-vous nous indiquer vos disponibilités ? Il vous suffit de répondre à ce message.")
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

Nous aimerions toujours vous rencontrer pour le poste « {title} ». {ask}

Si vous nous avez déjà répondu, ne tenez pas compte de ce message.{_sign(company)}"""
    return f"Rappel — entretien pour le poste « {title} »", body


def closing_reminder_to_owner(rec: Recruitment, sites: list[str]) -> str:
    return (f"{rec.title} : le recrutement est clos. L'offre a été retirée de Google et de sa page. Pensez à la "
            f"retirer aussi des sites où vous l'avez publiée vous-même : {', '.join(sites)}.")


def invitation(company: Company, rec: Recruitment, first_name: str | None, booking_link: str) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

Votre candidature au poste « {title} » a retenu notre attention et nous aimerions vous rencontrer.

Choisissez le créneau qui vous convient (entretien d'environ {rec.interview_minutes} minutes) :
{booking_link}

Si aucun créneau ne vous convient, répondez simplement à ce message.{_sign(company)}"""
    return f"Entretien pour le poste « {title} »", body


def booking_confirmation(company: Company, rec: Recruitment, first_name: str | None, start: datetime,
                         location: str | None, manage_link: str) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

Votre entretien pour le poste « {title} » est confirmé : {fr_datetime(start)}.
Lieu : {location or 'précisé par l’entreprise'}

Vous recevrez un rappel la veille. Pour déplacer ou annuler : {manage_link}

L'entretien suit les mêmes questions pour toutes les personnes rencontrées, toutes liées au poste.{_sign(company)}"""
    return f"Entretien confirmé : {fr_datetime(start)}", body


def reminder(company: Company, rec: Recruitment, first_name: str | None, start: datetime, location: str | None,
             manage_link: str) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

Petit rappel : votre entretien pour le poste « {title} » a lieu {fr_datetime(start)}.
Lieu : {location or 'précisé par l’entreprise'}

Un empêchement ? Prévenez-nous ici : {manage_link}{_sign(company)}"""
    return f"Rappel : entretien {fr_datetime(start)}", body


def unscheduled(company: Company, rec: Recruitment, first_name: str | None, start: datetime,
                booking_link: str | None) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    after = (f"Choisissez un nouveau créneau ici : {booking_link}" if booking_link
             else "Nous revenons vers vous très vite pour convenir d'une nouvelle date.")
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

L'entretien prévu {fr_datetime(start)} pour le poste « {title} » doit être déplacé. Toutes nos excuses.

{after}{_sign(company)}"""
    return f"Entretien à déplacer — {title}", body


def closing_hired(company: Company, rec: Recruitment, first_name: str | None) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

Bonne nouvelle : nous souhaitons vous proposer le poste « {title} ». Nous vous appelons très vite pour en parler et convenir de la suite.{_sign(company)}"""
    return f"Votre candidature au poste « {title} »", body


def closing_rejected(company: Company, rec: Recruitment, first_name: str | None, *, interviewed: bool,
                     pool_consent: bool, data_link: str) -> tuple[str, str]:
    title = rec.profile.get("title") or rec.title
    if interviewed:
        core = ("Merci pour le temps que vous nous avez consacré lors de l'entretien. Après avoir rencontré "
                "plusieurs personnes, nous avons retenu une autre candidature, dont le parcours correspondait "
                "davantage aux besoins précis du poste.")
    else:
        core = ("Nous avons reçu de nombreuses candidatures et n'avons pas retenu la vôtre pour la suite du "
                "processus. Cette réponse ne porte pas sur vos qualités : elle tient aux critères précis du poste.")
    pool = ("\n\nVous avez accepté que nous gardions votre candidature pour de futurs postes : nous reviendrons "
            "vers vous si une opportunité correspond.") if pool_consent else ""
    body = f"""Bonjour{(' ' + first_name) if first_name else ''},

{core}{pool}

Nous vous souhaitons une belle réussite dans vos recherches.

{retention_sentence(company)} Vous pouvez demander leur suppression dès maintenant : {data_link}{_sign(company)}"""
    return f"Votre candidature au poste « {title} »", body


def privacy_notice(company: Company, contact: str | None = None) -> str:
    s = get_settings()
    months = company.retention_months or s.retention_months_after_last_contact
    contact = company.privacy_contact or contact or "l'adresse de contact de l'entreprise"
    return f"""Notice d'information — candidatures chez {company.name}

Responsable du traitement : {company.name}{(', ' + company.address) if company.address else ''}.
Contact pour vos données : {contact}.

Finalité : gérer le recrutement au poste auquel vous avez postulé (réception, examen, entretiens, réponse).
Base légale : mesures précontractuelles prises à votre demande (art. 6.1.b du RGPD) et intérêt légitime de l'entreprise à recruter (art. 6.1.f).

Données traitées : celles que vous transmettez, par le formulaire de candidature, par e-mail ou par message (identité, coordonnées, CV, message, réponses aux questions du poste), les échanges liés au recrutement, les notes de l'entreprise et les notes d'entretien.
Aucune donnée n'est collectée sur Internet à votre sujet (réseaux sociaux, moteurs de recherche). Vos données ne sont transmises à aucun service d'intelligence artificielle.

Méthode de présélection (art. L1221-8 du Code du travail) : vos réponses aux questions du poste et votre CV sont comparés, critère par critère, aux exigences fixées par l'entreprise, selon des règles fixes et identiques pour tous. Les informations sans rapport avec le poste (âge, adresse, situation de famille, nationalité, santé…) sont masquées avant cet examen. Aucune note n'est attribuée et personne n'est écarté automatiquement : toutes les candidatures restent consultables et une personne de l'entreprise prend chaque décision. Les entretiens suivent les mêmes questions, liées au poste, pour toutes les personnes rencontrées.

Destinataires : la direction de {company.name} ; l'éditeur du logiciel, en qualité de sous-traitant (art. 28 du RGPD), et son hébergeur dans l'Union européenne.

Durée de conservation : au plus {months} mois après le dernier contact, puis suppression automatique. Si vous êtes recruté(e), votre dossier rejoint votre dossier du personnel.

Vos droits : accès, rectification, effacement, limitation, opposition. Vous pouvez les exercer à tout moment depuis le lien reçu avec l'accusé de réception, ou auprès du contact ci-dessus. Vous pouvez aussi saisir la CNIL (www.cnil.fr)."""


def ics_event(uid: str, start: datetime, end: datetime, summary: str, location: str | None, description: str) -> bytes:
    def fmt(dt: datetime) -> str:
        return dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//WayLoop//FR", "METHOD:PUBLISH", "BEGIN:VEVENT",
        f"UID:{uid}@wayloop", f"DTSTAMP:{fmt(datetime.now(ZoneInfo('UTC')))}", f"DTSTART:{fmt(start)}",
        f"DTEND:{fmt(end)}", f"SUMMARY:{esc(summary)}", f"LOCATION:{esc(location or '')}",
        f"DESCRIPTION:{esc(description)}", "END:VEVENT", "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
