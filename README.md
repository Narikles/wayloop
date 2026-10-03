# WayLoop — recruter sans le chaos, pour les TPE et PME

WayLoop donne au dirigeant d'une petite entreprise un processus clair, de l'offre au dernier
candidat :

1. **Il décrit le poste en une phrase.** L'assistant (Claude Haiku) rédige la description, les
   critères clés et trois questions de présélection ; le dirigeant relit et corrige dans le
   formulaire habituel. Sans clé d'API, un repli par règles remplit le même formulaire.
2. **Il publie partout, honnêtement.** Google pour l'emploi automatiquement ; LinkedIn, Indeed,
   France Travail et les relais locaux en un copier-coller, avec un texte adapté à chaque site et
   un lien de candidature suivi.
3. **Toutes les candidatures arrivent au même endroit** : formulaire en ligne, adresse e-mail
   dédiée, candidatures reçues ailleurs (message LinkedIn, appel, CV déposé) ajoutées à la main.
   La provenance de chaque candidat est affichée.
4. **Un pipeline simple** : Reçu → À évaluer → Présélectionné → Entretien → Refusé / Embauché, avec
   CV, réponses aux questions, notes et historique complet sur chaque fiche.
5. **Les relances se font seules** : remerciement automatique des refusés (annulable pendant une
   heure), relance des non-répondants, récapitulatif chaque lundi, alerte à chaque candidature.

L'IA ne sert qu'à **rédiger les textes de l'employeur**. Elle ne lit, ne note et ne trie aucune
candidature, et aucune donnée de candidat ne lui est envoyée (voir
[docs/conformite.md](docs/conformite.md) § 2). Le dirigeant décide de tout.

## Offres

| | Gratuit | Pro | Agence |
|---|---|---|---|
| Prix | 0 € | **25 € HT/mois**, ou 240 € HT/an (20 €/mois) | **79 € HT/mois**, ou 756 € HT/an (63 €/mois) |
| Recrutements en même temps | 1 | Illimités | Illimités |
| Assistant de rédaction, diffusion, pipeline, notes, e-mail dédié, alertes | ✓ | ✓ | ✓ |
| Remerciement automatique, relances, récapitulatif hebdomadaire | — | ✓ | ✓ |
| Historique | 30 derniers jours | Complet | Complet |
| Créneaux d'entretien en ligne, export CSV | — | ✓ | ✓ |
| Plusieurs utilisateurs, support prioritaire | — | — | ✓ |

Les limites sont appliquées côté serveur (HTTP 402). Prix, coûts de l'IA et comparaison de
marché : [docs/tarifs.md](docs/tarifs.md).

## Le parcours : une page par étape

| Page | Ce que le dirigeant y fait |
|---|---|
| **Offre** | Relit l'offre, la publie, coche les sites où il l'a postée, copie le texte adapté à chacun |
| **Candidatures** | Pipeline en colonnes (glisser-déposer) ou liste ; ajoute un candidat reçu ailleurs ; valide la sélection |
| **Entretiens** | Invite, fixe les dates (ou laisse les candidats réserver, Pro) |
| **Débrief** | Note chaque entretien sur la grille de questions |
| **Décision** | Compare, choisit, répond à tous |

Paramètres : entreprise, automatisations, équipe (Agence), apparence, abonnement.

## Ce qui est livré

| Fonction | État | Où |
|---|---|---|
| Assistant de rédaction : une phrase → description, critères, 3 questions ; appel forcé d'outil, limite quotidienne, coût suivi, repli par règles ; le salaire, le lieu et le contrat saisis par le dirigeant priment toujours | Fait | `modules/assistant.py` |
| Offre conforme d'office (« (H/F) », reformulations sûres, mentions interdites bloquées) et garde-fous sur les questions de présélection | Fait | `modules/compliance.py`, `modules/form.py` |
| Diffusion : Google pour l'emploi (JobPosting, plan du site, API d'indexation), flux XML partenaires après accord, liste de contrôle des sites manuels avec texte adapté et lien suivi | Fait | `services/publication.py` |
| Candidatures centralisées : formulaire, e-mail entrant (IMAP, `offres+<jeton>@…`), ajout manuel avec accusé de réception RGPD | Fait | `services/inbound.py`, `orchestrator.add_candidate` |
| Pipeline Kanban à 6 colonnes, notes d'équipe, historique par candidat | Fait | `orchestrator.pipeline_move`, `views.py`, `pages/recruitment/pipeline.tsx` |
| Automatisations : remerciement programmé et annulable, relance unique, récapitulatif du lundi, alerte de candidature | Fait | `services/automations.py`, `scheduler.py`, `worker.py` |
| Offres Gratuit / Pro / Agence, paiement Stripe (Checkout, portail, webhook signé) | Fait | `services/plans.py`, `services/billing.py` |
| Équipe : invitation par e-mail, retrait (Agence) | Fait | `routers/api.py` (`/api/team`) |
| Synthèse des réponses par règles (critère par critère, jamais de rejet automatique), entretiens, débrief, décision | Fait | `modules/screening.py`, `modules/interview.py` |
| Journal d'audit chaîné, purge à 24 mois, page « mes données » | Fait | `audit.py`, `services/purge.py` |
| Messages LinkedIn reçus automatiquement | Impossible sans partenariat LinkedIn : ajout manuel + lien suivi | — |
| Synchronisation Google / Microsoft Agenda | Non fait (invitation `.ics` jointe) | — |

Correspondance détaillée avec la feuille de route : [docs/roadmap.md](docs/roadmap.md).

## Démarrer en 3 commandes (Docker)

```bash
python3 scripts/init_env.py          # crée .env avec des clés aléatoires
docker compose up -d --build         # PostgreSQL, application, tâches de fond, boîte mail de test
open http://localhost:8000           # créez votre compte ; le lien de connexion s'affiche (mode démo)
```

Les e-mails arrivent dans la boîte de test <http://localhost:8025>. En mode démo
(`BILLING_MODE=demo`), « Passer à Pro » active l'offre sans paiement.

Pour activer l'assistant IA, ajoutez dans `.env` (ou dans les variables du service Render) :

```
ANTHROPIC_API_KEY=sk-ant-…
# AI_MODEL=claude-haiku-4-5        (par défaut)
```

Sans clé, l'assistant fonctionne en mode « règles » : il remplit le formulaire à partir des mots
reconnus dans la phrase (métier, années, salaire, ville, logiciels, permis…), sans inventer le
reste. Réception des CV par e-mail : [docs/deploiement.md](docs/deploiement.md) § 8.

## Développer

```bash
# Back-end (Python 3.12+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
DEMO_MODE=true python -m app.seed        # entreprise et recrutement fictifs ; --full, --premium
DEMO_MODE=true uvicorn app.main:app --reload
pytest                                   # 54 tests ; TEST_DATABASE_URL=postgresql+psycopg://… pour PostgreSQL

# Interface (Node 22)
cd frontend
npm install
npm run dev                              # http://localhost:5173, l'API est relayée vers :8000
npm run build                            # servi ensuite par FastAPI depuis frontend/dist
npm run build:demo                       # démo hors ligne en un seul fichier (dist-demo/)
```

En développement, la base SQLite est créée automatiquement. En production (PostgreSQL), le schéma
est géré par Alembic (`alembic upgrade head`, lancé par le conteneur). Le planificateur intégré
(refus programmés, relances, récapitulatif, e-mails entrants) tourne dans le processus web quand
`JOBS_MODE=inline` ; avec `JOBS_MODE=worker`, c'est le worker qui s'en charge.

## Organisation du dépôt

```
backend/
  app/
    orchestrator.py     machine à états, propositions, pipeline, candidatures ajoutées, notes
    views.py            ce que chaque page affiche (colonne, compteurs, historique)
    modules/            assistant de rédaction, formulaire, offre et conformité, lecture des CV,
                        synthèse, masquage, grille d'entretien, e-mails aux candidats
    services/           publication, automatisations, e-mail entrant, offres et paiement,
                        stockage chiffré, purge, indicateurs, référentiels
    scheduler.py        planificateur intégré (un seul processus)
    worker.py           tâches différées et périodiques
    routers/            API, pages publiques, webhook Stripe, authentification
  migrations/           Alembic (0004 : notes, e-mails entrants, automatisations)
  scripts/              régression, biais, export des données de la démo
  tests/                parcours complet, nouvel angle (test_pivot.py), offres, conformité…
frontend/               React + TypeScript ; src/api/demo.ts = démo hors ligne
docs/                   architecture, conformité, déploiement, offres et prix, feuille de route
```

## Avant la mise en production

1. **Revue juridique** : qualification de l'assistant au regard de l'AI Act (art. 6(3), 50(2)),
   contrat de sous-traitance, AIPD — [docs/conformite.md](docs/conformite.md).
2. **Déploiement** : HTTPS, PostgreSQL, sauvegardes, e-mails signés (SPF, DKIM, DMARC), boîte de
   réception dédiée — [docs/deploiement.md](docs/deploiement.md).
3. **Diffusion** : déclarer le domaine dans Google Search Console ; les textes pour LinkedIn,
   Indeed et France Travail sont prêts à coller, une publication automatique demanderait un
   accord avec chaque plateforme.
4. **Tarifs** : créer les quatre prix (Pro et Agence, mensuel et annuel) dans Stripe.

## Limites connues

- La diffusion automatique se limite à Google pour l'emploi tant qu'aucun accord partenaire n'est
  signé ; Google ne garantit pas l'affichage.
- Les messages LinkedIn ne peuvent pas être relevés automatiquement (API de messagerie réservée
  aux partenaires) : on les ajoute à la main, ou le candidat passe par le lien suivi.
- L'e-mail entrant demande une boîte IMAP acceptant les adresses `offres+…@` (sous-adressage).
- La lecture des CV par règles reconnaît les cas simples ; un CV scanné est « à lire vous-même ».
- Sur l'offre gratuite de Render, le service s'endort : les tâches programmées attendent son
  réveil, et la base est effacée à chaque redémarrage.
- La démo hors ligne simule les envois et l'assistant (exemples rejoués, phrase libre analysée par
  règles) ; elle ne publie rien réellement.
