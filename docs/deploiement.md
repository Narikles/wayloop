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
```

Retirez le service `mailpit` de `docker-compose.yml`, puis :

```bash
docker compose up -d --build
```

Les migrations de base s'appliquent au démarrage du conteneur `app`.

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
   Sans elle, les CV et données candidats sont illisibles ; avec elle et une sauvegarde, ils sont
   lisibles : ne la stockez pas avec les sauvegardes.

Les purges RGPD s'appliquent à la base vivante ; prévoyez une rotation des sauvegardes cohérente
avec les durées de conservation.

## 5. Mises à jour

```bash
git pull && docker compose up -d --build
```

## 6. Diffusion automatique des offres

À la publication, chaque offre part sans action du dirigeant vers :

1. **Google pour l'emploi.** La page publique de l'offre (`/offres/<jeton>`) est servie avec ses
   balises et ses données structurées `JobPosting` (schema.org) ; le plan du site `/sitemap.xml`
   liste les offres ouvertes ; `robots.txt` l'indique et ferme les pages privées. À faire une fois :
   - déclarer le domaine dans **Google Search Console** et y soumettre
     `https://recrutement.votre-domaine.fr/sitemap.xml` ;
   - facultatif mais recommandé par Google pour les offres d'emploi : créer un **compte de
     service** Google Cloud, activer l'API « Web Search Indexing API », ajouter l'adresse du compte
     de service comme **propriétaire** de la propriété dans Search Console, puis renseigner
     `GOOGLE_INDEXING_CREDENTIALS` (chemin du fichier JSON, ou son contenu). Chaque publication,
     modification et clôture est alors signalée à Google (`URL_UPDATED` / `URL_DELETED`), via le
     worker. En cas d'échec, l'offre reste visible par le plan du site ; rien ne bloque.
   - Google ne garantit pas l'affichage d'une offre balisée ; il décide seul de l'indexation.
2. **Lien à partager**, avec suivi de provenance (`?src=<id>` ; les visites venant de google.fr sont
   reconnues) : réseaux, e-mail, affichage.
3. **Plateformes partenaires** (flux XML `/feeds/<id>.xml`, format usuel des agrégateurs) : une
   plateforme n'est servie qu'une fois listée dans `PUBLICATION_FEEDS`, c'est-à-dire **après
   l'accord passé avec elle** (Jooble, Talent.com, Adzuna, Jobijoba, Optioncarrière, Jobrapido…).
   France Travail, Indeed, LinkedIn et l'Apec demandent une intégration ou une convention propre,
   à négocier par l'éditeur ; les identifiants `france_travail`, `indeed`, `linkedin`, `apec` sont
   prévus dans `services/publication.py` pour le jour où l'accord existe.

À la clôture (embauche ou abandon), l'offre disparaît du plan du site et des flux, ses données
structurées sont retirées de la page (qui passe en `noindex`), et Google est prévenu si l'API
d'indexation est configurée.

```
GOOGLE_INDEXING_CREDENTIALS=/run/secrets/google-indexing.json
PUBLICATION_FEEDS=jooble,talent
JOB_VALIDITY_DAYS=60
```

Si votre serveur filtre les sorties, autorisez `oauth2.googleapis.com` et `indexing.googleapis.com`.

## 7. E-mails

Tout passe par e-mail : notifications du dirigeant (avec un lien qui ouvre directement la bonne
page), messages aux candidats (accusé, invitation, confirmation avec invitation d'agenda `.ics`,
rappel la veille, réponses). Utilisez un service d'envoi qui signe vos e-mails (SPF, DKIM, DMARC
configurés sur votre domaine) : sans cela, une partie finira en indésirables. Les candidats
répondent directement au dirigeant (en-tête `Reply-To`).

## 8. Qualité des règles

Après toute modification des règles de lecture des CV ou du masquage :

```bash
docker compose exec app python scripts/regression.py
docker compose exec app python scripts/regression.py --cv-seul
docker compose exec app python scripts/bias_check.py
```

## 9. Données publiques

Aucune clé n'est nécessaire :

- **Référentiel ROME 4.0** (France Travail, Licence Ouverte) : embarqué dans
  `backend/app/data/rome.json.gz`. Pour le mettre à jour, téléchargez les fichiers sur
  francetravail.org (rubrique open data du ROME) puis
  `python scripts/build_referentiels.py <dossier> "<version>" "<date>"` (voir l'en-tête du script).
- **Géoplateforme** (IGN, `GEOCODING_URL`) pour les communes et adresses, et **API Recherche
  d'entreprises** (`COMPANY_SEARCH_URL`) pour le SIREN : appels sortants HTTPS, réponses mises en
  cache une heure, délai maximal `PUBLIC_API_TIMEOUT_SECONDS`. En cas d'indisponibilité, la saisie
  libre reste possible. Si votre serveur filtre les sorties, autorisez `data.geopf.fr` et
  `recherche-entreprises.api.gouv.fr`.

## 10. Paiement (Stripe)

1. Dans Stripe (mode test d'abord) : créez un produit « WayLoop Premium » avec deux prix récurrents
   en euros, HT : 49 €/mois et 468 €/an. Notez leurs identifiants `price_…`.
2. Point de terminaison webhook : `https://recrutement.votre-domaine.fr/webhooks/stripe`, événements
   `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.payment_failed`. Notez le secret de signature `whsec_…`.
3. Portail client Stripe : activez-le (factures, moyen de paiement, résiliation).
4. Dans `.env` :

```
BILLING_MODE=stripe
STRIPE_SECRET_KEY=sk_live_…
STRIPE_WEBHOOK_SECRET=whsec_…
STRIPE_PRICE_MONTHLY=price_…
STRIPE_PRICE_YEARLY=price_…
STRIPE_TRIAL_DAYS=14
PRICE_MONTHLY_EUR=49
PRICE_YEARLY_EUR=468
# STRIPE_AUTOMATIC_TAX=true si Stripe Tax est configuré (TVA)
```

Le webhook vérifie la signature et ignore les événements déjà traités (table `stripe_events`).
L'accès Premium suit l'état de l'abonnement (`active`, `trialing`, `past_due`), avec 3 jours de
grâce après la fin de période. `BILLING_MODE=demo` active Premium sans paiement (développement,
démonstrations) ; `BILLING_MODE=disabled` cache le paiement.

## 11. Exploitation

- Journaux : `docker compose logs -f app worker`.
- Santé : `GET /api/health`.
- Intégrité du journal d'audit : `GET /api/audit/verify`.
- E-mails envoyés à un candidat : sa fiche (« E-mails envoyés »).
- Diffusion : `GET /sitemap.xml`, `GET /feeds/<id>.xml` ; le statut Google de chaque offre
  (« Signalée à Google ») s'affiche dans la page Offre du recrutement.
