# Déploiement

## 1. Serveur

Un petit serveur virtuel hébergé dans l'UE suffit pour commencer (2 vCPU, 4 Go de RAM), par exemple
chez OVHcloud ou Scaleway, avec Docker installé. Base PostgreSQL et fichiers restent sur ce serveur
(volumes Docker `pgdata` et `files`). Pour un stockage objet, voir `STORAGE_BACKEND=s3` dans
`backend/app/config.py` (installer `boto3`).

## 2. Installation

```bash
git clone <votre dépôt> wayloop && cd wayloop
python3 scripts/init_env.py
```

Dans `.env`, pour la production :

```
ENVIRONMENT=prod
DEMO_MODE=false
PUBLIC_BASE_URL=https://recrutement.votre-domaine.fr
EMAIL_BACKEND=smtp
SMTP_HOST=…  SMTP_PORT=587  SMTP_USER=…  SMTP_PASSWORD=…  SMTP_STARTTLS=true
EMAIL_FROM=Recrutement <recrutement@votre-domaine.fr>
# Assistant de rédaction (§ 9) et e-mails entrants (§ 8), facultatifs
ANTHROPIC_API_KEY=…
INBOUND_ADDRESS=offres@recrutement.votre-domaine.fr
IMAP_HOST=…  IMAP_USER=…  IMAP_PASSWORD=…
```

Retirez le service `mailpit` de `docker-compose.yml`, puis :

```bash
docker compose up -d --build
```

Les migrations de base s'appliquent au démarrage du conteneur `app` (`alembic upgrade head`,
jusqu'à `0004`).

## 3. HTTPS (Caddy)

```
# /etc/caddy/Caddyfile
recrutement.votre-domaine.fr {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 15MB
    }
}
```

En production, exposez le port 8000 uniquement en local (`"127.0.0.1:8000:8000"` dans
`docker-compose.yml`).

## 4. Sauvegardes

Trois éléments, à sauvegarder séparément :

1. la base : `docker compose exec -T db pg_dump -U wayloop wayloop | gzip > wayloop-$(date +%F).sql.gz` ;
2. les CV chiffrés : volume `files` ;
3. **la clé `STORAGE_ENCRYPTION_KEY`**, conservée hors du serveur (gestionnaire de mots de passe).
   Sans elle, les CV, notes et données candidats sont illisibles ; ne la stockez pas avec les
   sauvegardes.

Les purges RGPD s'appliquent à la base vivante ; prévoyez une rotation des sauvegardes cohérente
avec les durées de conservation.

## 5. Mises à jour

```bash
git pull && docker compose up -d --build
```

## 6. Diffusion des offres

À la publication, sans action du dirigeant :

1. **Google pour l'emploi.** La page publique de l'offre (`/offres/<jeton>`) est servie avec ses
   balises et ses données structurées `JobPosting` ; `/sitemap.xml` liste les offres ouvertes. À
   faire une fois : déclarer le domaine dans **Google Search Console** et y soumettre le plan du
   site ; facultatif, l'**API d'indexation** (compte de service Google Cloud déclaré propriétaire
   dans Search Console, puis `GOOGLE_INDEXING_CREDENTIALS`). Google ne garantit pas l'affichage.
2. **Plateformes partenaires** (flux XML `/feeds/<id>.xml`) : servies seulement une fois listées
   dans `PUBLICATION_FEEDS`, c'est-à-dire après l'accord passé avec elles.

Ensuite, en un copier-coller par le dirigeant (page Offre) : **LinkedIn, Indeed, France Travail,
relais locaux**. Chaque texte est adapté au site et contient un lien `?src=<site>` qui rattache
les candidats à leur provenance. Ces sites n'acceptent pas de publication automatique sans
convention ou intégration négociée par l'éditeur.

À la clôture, l'offre sort du plan du site et des flux, la page passe en `noindex`, Google est
prévenu si l'API d'indexation est configurée, et le dirigeant reçoit la liste des sites où il doit
retirer l'annonce lui-même.

```
GOOGLE_INDEXING_CREDENTIALS=/run/secrets/google-indexing.json
PUBLICATION_FEEDS=jooble,talent
JOB_VALIDITY_DAYS=60
```

Si votre serveur filtre les sorties, autorisez `oauth2.googleapis.com` et `indexing.googleapis.com`.

## 7. E-mails sortants

Notifications du dirigeant (alerte de candidature, récapitulatif du lundi, invitations d'équipe),
messages aux candidats (accusé, lien pour répondre aux questions, invitation, confirmation avec
`.ics`, rappel, remerciement, relance). Utilisez un service d'envoi qui signe vos e-mails (SPF,
DKIM, DMARC configurés sur votre domaine) : sans cela, une partie finira en indésirables. Les
candidats répondent directement au dirigeant (en-tête `Reply-To`).

## 8. E-mails entrants (candidatures reçues par e-mail)

Chaque offre affiche une adresse de réception : `offres+<jeton>@votre-domaine` (sous-adressage).
Un e-mail envoyé à cette adresse, avec ou sans CV joint, devient une candidature de provenance
« E-mail » ; un e-mail transféré par le dirigeant depuis sa propre boîte est rattaché à
l'expéditeur d'origine. Un e-mail envoyé à l'adresse sans code (`offres@…`) est ignoré : rien ne
permet de savoir à quel recrutement le rattacher.

1. Créez une boîte dédiée (`offres@…`) chez un fournisseur qui accepte le sous-adressage
   (`offres+abc@…` livré dans `offres@…`) et l'IMAP. Pour Gmail ou Google Workspace, activez la
   validation en deux étapes et créez un **mot de passe d'application**.
2. Dans `.env` :

```
INBOUND_ADDRESS=offres@recrutement.votre-domaine.fr
IMAP_HOST=imap.votre-fournisseur.fr
IMAP_PORT=993
IMAP_USER=offres@recrutement.votre-domaine.fr
IMAP_PASSWORD=…
IMAP_FOLDER=INBOX
```

La boîte est relevée à chaque passage du planificateur (§ 10) : seuls les messages non lus sont
traités, puis marqués lus. Les réponses automatiques et les rejets de messagerie sont ignorés,
un même message n'est jamais traité deux fois (empreinte du Message-ID). Sans ces variables, la
fonction est simplement masquée.

## 9. Assistant de rédaction (IA)

```
ANTHROPIC_API_KEY=sk-ant-…        # à créer dans la console Anthropic ; ne la partagez jamais
AI_MODEL=claude-haiku-4-5         # par défaut
AI_DAILY_LIMIT=30                 # brouillons par entreprise et par jour
AI_TIMEOUT_SECONDS=30
```

Sans clé, ou si l'API ne répond pas, l'assistant passe en mode « règles » (même formulaire, rempli
à partir des mots reconnus). Seule la phrase du dirigeant est envoyée, jamais une donnée de
candidat. Coût : moins d'un centime d'euro par brouillon (`tarifs.md` § 3), suivi dans
`usage_records`. Si votre serveur filtre les sorties, autorisez `api.anthropic.com`.

## 10. Tâches programmées et automatisations

Refus programmés, relances, récapitulatif du lundi, relève des e-mails entrants, rappels
d'entretien et purge passent par `worker.tick()` :

| Hébergement | Réglage | Qui exécute |
|---|---|---|
| Un seul processus (Render, petit serveur) | `JOBS_MODE=inline` (défaut), `EMBEDDED_SCHEDULER=true` (défaut) | fil d'exécution intégré à l'application, toutes les `SCHEDULER_INTERVAL_SECONDS` (60 s par défaut, 15 s au minimum) |
| Docker Compose | `JOBS_MODE=worker` | conteneur `worker` (`python -m app.worker`) |

Réglages : `AUTO_REJECT_DELAY_MINUTES` (60, délai pendant lequel un refus s'annule),
`RELANCE_DAYS_DEFAULT` (3), `WEEKLY_RECAP_WEEKDAY` (0 = lundi), `WEEKLY_RECAP_HOUR` (8, heure de
Paris). Si le service s'endort (offre gratuite de Render), les tâches dues partent à son réveil.

## 11. Paiement (Stripe)

1. Dans Stripe (mode test d'abord) : un produit « WayLoop Pro » avec deux prix récurrents en
   euros HT (25 €/mois, 240 €/an), un produit « WayLoop Agence » (79 €/mois, 756 €/an). Notez les
   quatre identifiants `price_…`.
2. Webhook : `https://recrutement.votre-domaine.fr/webhooks/stripe`, événements
   `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.payment_failed`. Notez le secret `whsec_…`.
3. Portail client Stripe : activez-le (factures, moyen de paiement, changement d'offre, résiliation).
4. Dans `.env` :

```
BILLING_MODE=stripe
STRIPE_SECRET_KEY=sk_live_…
STRIPE_WEBHOOK_SECRET=whsec_…
STRIPE_PRICE_MONTHLY=price_…            # Pro mensuel
STRIPE_PRICE_YEARLY=price_…             # Pro annuel
STRIPE_PRICE_AGENCY_MONTHLY=price_…
STRIPE_PRICE_AGENCY_YEARLY=price_…
STRIPE_TRIAL_DAYS=14
PRICE_MONTHLY_EUR=25
PRICE_YEARLY_EUR=240
PRICE_AGENCY_MONTHLY_EUR=79
PRICE_AGENCY_YEARLY_EUR=756
# STRIPE_AUTOMATIC_TAX=true si Stripe Tax est configuré (TVA)
```

L'accès suit l'état de l'abonnement (`active`, `trialing`, `past_due`), avec 3 jours de grâce après
la fin de période. `BILLING_MODE=demo` change d'offre sans paiement (démonstrations) ;
`BILLING_MODE=disabled` cache le paiement.

## 12. Qualité des règles

Après toute modification des règles de lecture des CV ou du masquage :

```bash
docker compose exec app python scripts/regression.py
docker compose exec app python scripts/regression.py --cv-seul
docker compose exec app python scripts/bias_check.py
```

## 13. Données publiques

Aucune clé n'est nécessaire : référentiel ROME 4.0 (France Travail, Licence Ouverte) embarqué ;
Géoplateforme (IGN) pour les communes et API Recherche d'entreprises pour le SIREN, appelées en
HTTPS avec cache d'une heure (autorisez `data.geopf.fr` et `recherche-entreprises.api.gouv.fr` si
les sorties sont filtrées).

## 14. Exploitation

- Journaux : `docker compose logs -f app worker`.
- Santé : `GET /api/health`.
- Intégrité du journal d'audit : `GET /api/audit/verify`.
- E-mails envoyés à un candidat et historique : sa fiche.
- Diffusion : `GET /sitemap.xml`, `GET /feeds/<id>.xml`.

## 15. Essai gratuit sur Render (sans serveur)

Service web Render (offre Free, environnement Docker) relié au dépôt GitHub : Render reconstruit
l'image à chaque modification de la branche `main`.

| Variable | Valeur |
|---|---|
| `DEMO_MODE` | `true` (le lien de connexion s'affiche à l'écran, aucun e-mail n'est nécessaire) |
| `PUBLIC_BASE_URL` | l'adresse donnée par Render, ex. `https://wayloop.onrender.com` |
| `SECRET_KEY` | bouton « Generate » de Render |
| `ANTHROPIC_API_KEY` | facultatif : votre clé, pour l'assistant IA (sinon mode « règles ») |

L'image utilise une base SQLite dans `/app/data`, créée au démarrage, et écoute sur le port `PORT`
fourni par Render. Le planificateur intégré tourne dans le même processus.

Limites de l'offre Free de Render (documentation Render, consultée en octobre 2026) : le service
s'endort après 15 minutes sans visite et met environ une minute à se réveiller ; le disque n'est
pas conservé, donc la base et les CV sont effacés à chaque mise en veille, redémarrage ou
déploiement ; les tâches programmées (remerciements, récapitulatif) n'avancent que service
éveillé. Avec `DEMO_MODE=true`, quiconque connaît une adresse inscrite peut ouvrir le compte : n'y
mettez aucune donnée réelle. Pour un usage réel, suivez les sections 1 à 11.
