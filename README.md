# WayLoop — le recrutement simple pour les TPE et PME

WayLoop mène un recrutement de bout en bout pour le dirigeant d'une petite entreprise. Il décrit
son besoin dans un formulaire en quatre étapes (appuyé sur le référentiel des métiers de France
Travail) ; l'offre est rédigée, conforme d'office, et publiée en un geste ; chaque candidat répond
aux questions issues des critères ; une synthèse montre, critère par critère, ce qu'il déclare et
ce que son CV confirme. Le dirigeant sélectionne, invite, note les entretiens, choisit et répond à
tous. L'outil prépare ; le dirigeant décide.

Aucune IA, dans aucune offre : formulaire, référentiels publics et règles explicites. Tout passe
par e-mail. Interface en thème clair (sombre au choix dans Paramètres).

Le logiciel suit le *Dossier de construction* (octobre 2026) : les numéros de section cités
renvoient à ce dossier.

## Offres

| | Gratuit | Premium |
|---|---|---|
| Prix | 0 € | 49 € HT/mois sans engagement, ou 468 € HT/an (39 € HT/mois), 14 jours d'essai |
| Recrutements en même temps | 1 | Illimités |
| Rendez-vous | Invitation par e-mail, le dirigeant fixe la date | En plus : le candidat choisit son créneau en ligne, relance automatique |
| Export CSV des candidatures | — | ✓ |
| Tout le reste (offre, publication, synthèse, sélection, e-mails groupés, entretiens, décision, conformité) | ✓ | ✓ |

Détail, comparaison de marché sourcée et raisons du découpage : [docs/tarifs.md](docs/tarifs.md).

## Le parcours : une page par étape

| Page | Ce que le dirigeant y fait |
|---|---|
| **Offre** | Relit l'offre, la publie, voit où elle est diffusée, retouche le texte |
| **Candidatures** | Consulte les candidatures, valide la sélection préparée, écrit ou répond en masse |
| **Entretiens** | Envoie les invitations, fixe les dates (ou laisse les candidats réserver, Premium) |
| **Débrief** | Note chaque entretien sur la grille de questions |
| **Décision** | Compare, choisit, envoie les réponses à tous |

Chaque e-mail de notification ouvre directement la bonne page. L'historique du recrutement est
dans le menu ⋯ ; l'agenda de tous les entretiens a sa propre entrée dans le menu principal.

## Diffusion des offres

À la publication, sans autre action du dirigeant :

- **Google pour l'emploi** : page publique balisée (données structurées `JobPosting`), plan du
  site, signalement par l'API d'indexation si elle est configurée. C'est le seul canal à la fois
  gratuit et automatique sans accord préalable ; Google reste seul juge de l'affichage.
- **Lien à partager** (réseaux, e-mail, affichage), avec suivi de provenance.
- **Plateformes partenaires** par flux XML, une fois l'accord passé avec chacune
  (`PUBLICATION_FEEDS`). France Travail, l'Apec, Indeed et LinkedIn demandent une convention ou
  une intégration à obtenir par l'éditeur ; voir [docs/deploiement.md](docs/deploiement.md) § 6.

À l'embauche ou à l'abandon, l'offre est retirée partout.

## Ce qui est livré

| Module | État | Où |
|---|---|---|
| Offres Gratuit / Premium, limites appliquées côté serveur (HTTP 402), paiement Stripe (Checkout, portail, webhook signé et idempotent) | Fait | `services/plans.py`, `services/billing.py`, `routers/webhooks.py` |
| Formulaire guidé : référentiel ROME 4.0 embarqué, communes (Géoplateforme), SIREN (API Recherche d'entreprises), offre rédigée par modèle de texte | Fait | `modules/form.py`, `modules/templates.py`, `services/referentiels.py` |
| Offre conforme d'office : « (H/F) », reformulations sûres ; seule une mention impossible à corriger est signalée, sous son champ, avec « Retirer » | Fait | `modules/compliance.py` |
| Publication automatique : Google pour l'emploi, plan du site, API d'indexation, flux partenaires, retrait à la clôture | Fait ; partenaires à activer après accord | `services/publication.py` |
| Questions aux candidats, synthèse par règles (déclaré / confirmé par le CV / écart à vérifier), masquage, aucun rejet automatique | Fait | `modules/screening.py`, `modules/cv_rules.py`, `modules/masking.py` |
| Sélection en masse : e-mail groupé avec modèles, refus courtois, ajout aux entretiens, export CSV (Premium) | Fait | `modules/mailing.py` |
| Parcours en 5 pages, machine à états, propositions validées d'un geste (§3, §4, §6.1) | Fait | `orchestrator.py`, `views.py` |
| Rendez-vous : date fixée par le dirigeant ou créneaux en ligne (Premium), invitation d'agenda `.ics`, relance, rappel la veille, annulation | Fait | `orchestrator.py`, `worker.py` |
| Synchronisation Google / Microsoft Agenda | Non fait (fichier `.ics` joint à la place) | — |
| Grille d'entretien par banque de questions, garde-fous, version imprimable, notes, comparatif | Fait | `modules/question_bank.py`, `modules/interview.py` |
| E-mails aux candidats : accusé avec information RGPD, invitation, rappel, réponse à tous | Fait | `modules/communication.py` |
| Journal d'audit en ajout seul, chaîné, sans donnée personnelle | Fait (+ déclencheur PostgreSQL) | `audit.py`, `migrations/` |
| Échéancier de purge (24 mois après le dernier contact), retrait par le candidat, page « mes données » | Fait | `services/purge.py` |
| Indicateurs de pilotage (§9), suivi à 3 et 6 mois | Fait | `services/metrics.py` |
| Tests de régression et de biais par CV jumeaux | Fait | `scripts/regression.py`, `scripts/bias_check.py`, `tests/` |
| Espace prescripteur, multisite (phase 3) | Non fait | — |

## Démarrer en 3 commandes (Docker)

Prérequis : Docker et Docker Compose.

```bash
python3 scripts/init_env.py          # crée .env avec des clés aléatoires
docker compose up -d --build         # base PostgreSQL, application, tâches de fond, boîte mail de test
open http://localhost:8000           # créez votre compte ; le lien de connexion s'affiche à l'écran (mode démo)
```

Les e-mails envoyés (au dirigeant comme aux candidats) arrivent dans la boîte de test
<http://localhost:8025>. En mode démo (`BILLING_MODE=demo`), « Passer à Premium » active l'offre
sans paiement ; pour encaisser, voir [docs/deploiement.md](docs/deploiement.md) § 10.

## Développer

```bash
# Back-end (Python 3.12+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
DEMO_MODE=true python -m app.seed        # entreprise (offre Gratuit) et recrutement fictifs ; --full : jusqu'à la sélection ; --premium
DEMO_MODE=true uvicorn app.main:app --reload
pytest                                   # 40 tests ; TEST_DATABASE_URL=postgresql+psycopg://… pour PostgreSQL

# Interface (Node 22)
cd frontend
npm install
npm run dev                              # http://localhost:5173, l'API est relayée vers :8000
npm run build                            # servi ensuite par FastAPI depuis frontend/dist
npm run build:demo                       # démo hors ligne en un seul fichier (dist-demo/)
```

En développement, la base SQLite est créée automatiquement. En production (PostgreSQL), le schéma
est géré par Alembic (`alembic upgrade head`, lancé automatiquement par le conteneur).

## Organisation du dépôt

```
backend/
  app/
    orchestrator.py     machine à états, propositions, enchaînement des étapes (le cœur)
    views.py            ce que chaque page affiche (étape, compteurs, libellés)
    modules/            formulaire, offre et conformité, lecture des CV et synthèse, masquage,
                        grille d'entretien, e-mails aux candidats, e-mails groupés
    services/           publication, stockage chiffré, purge, indicateurs, abonnement, référentiels
    channels/           envoi des e-mails (SMTP)
    routers/            API dirigeant, pages publiques, webhook Stripe, authentification
    audit.py            journal en ajout seul
    worker.py           synthèse en tâche de fond, rappels, signalements Google, suivi, purge
  migrations/           Alembic (dont le déclencheur qui rend le journal non modifiable)
  scripts/              régression, biais, export des données de la démo
  tests/                parcours complet, offre Gratuit, entretiens, conformité, publication,
                        masquage, purge, biais, journal
frontend/               React + TypeScript ; src/api/demo.ts = démo hors ligne (rejoue les sorties
                        du back-end, exportées par scripts/export_demo_fixtures.py)
docs/                   architecture, conformité, déploiement, offres et prix
```

## Avant la mise en production

1. **Phase 0 d'abord.** Le dossier prévoit d'accompagner 5 à 10 recrutements réels avant d'investir
   dans le produit. L'écran « Indicateurs » mesure ce que cette phase doit établir (temps du
   dirigeant, candidatures par offre et par provenance, sélection validée telle quelle, présence
   aux entretiens, issue).
2. **Revue juridique** (RGPD, Code du travail, qualification au regard de l'AI Act) :
   [docs/conformite.md](docs/conformite.md).
3. **Déploiement** : HTTPS, sauvegardes, clés, e-mails signés (SPF, DKIM, DMARC) :
   [docs/deploiement.md](docs/deploiement.md).
4. **Diffusion** : déclarer le domaine dans Google Search Console, soumettre le plan du site,
   configurer l'API d'indexation ; négocier les accords avec les plateformes visées.
5. **Qualité des règles** : `python scripts/regression.py`, `python scripts/regression.py --cv-seul`
   et `python scripts/bias_check.py` doivent passer sans écart (aussi lancés par l'intégration
   continue).
6. **Tarifs** : confirmer les prix concurrents cités dans [docs/tarifs.md](docs/tarifs.md) avant
   toute communication comparative ; créer les prix dans Stripe.

## Limites connues

- La lecture des CV par règles reconnaît les cas simples (durées d'expérience, permis, langues,
  diplômes, logiciels). Une réponse du candidat non retrouvée dans son CV est marquée « à vérifier
  en entretien », jamais écartée.
- Pas d'OCR : un CV scanné est classé « à lire vous-même ».
- Le masquage ne neutralise pas le genre grammatical (« assistante ») ; les CV jumeaux mesurent
  l'effet résiduel.
- La diffusion automatique gratuite se limite à Google pour l'emploi tant qu'aucun accord
  partenaire n'est signé, et Google ne garantit pas l'affichage.
- La limitation de débit des pages publiques est en mémoire (une seule instance) ; derrière un
  proxy, ajoutez une limite en amont.
- Un seul rôle utilisateur est exposé dans l'interface (le dirigeant).
- La démo hors ligne embarque le ROME mais pas la Géoplateforme ni l'annuaire des entreprises
  (listes réduites) ; elle ne publie rien réellement. Pour des critères différents de l'exemple,
  elle évalue les réponses déclarées sans relire les CV.
