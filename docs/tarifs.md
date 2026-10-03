# Offres et prix

Marqueurs : **[FAIT]** vérifié sur une source primaire (page de l'éditeur) à la date indiquée ·
**[SECONDAIRE]** chiffre tiré d'un site comparateur, non confirmé sur la page de l'éditeur ·
**[À VÉRIFIER]** non revérifié, ou sources qui divergent · **[HYPOTHÈSE]** choix de notre part.

## 1. Les offres WayLoop

| | Gratuit | Pro | Agence |
|---|---|---|---|
| Prix | 0 € | **25 € HT / mois** sans engagement, ou **240 € HT / an** (20 € / mois) | **79 € HT / mois**, ou **756 € HT / an** (63 € / mois) |
| Essai | — | 14 jours (Stripe) | 14 jours (Stripe) |
| Recrutements en même temps | 1 | Illimités | Illimités |
| Assistant de rédaction (une phrase → offre, critères, 3 questions) | ✓ | ✓ | ✓ |
| Diffusion : Google pour l'emploi automatique, textes prêts pour LinkedIn, Indeed, France Travail, relais locaux | ✓ | ✓ | ✓ |
| Candidatures centralisées (formulaire, e-mail dédié, ajout manuel), provenance affichée | ✓ | ✓ | ✓ |
| Pipeline, fiche candidat, notes, alerte à chaque candidature | ✓ | ✓ | ✓ |
| Entretiens (grille, notes, comparatif), décision, réponse à tous | ✓ | ✓ | ✓ |
| Remerciement automatique des refusés, relance des non-répondants, récapitulatif du lundi | — | ✓ | ✓ |
| Historique | 30 derniers jours | Complet | Complet |
| Créneaux d'entretien choisis en ligne par les candidats, export CSV | — | ✓ | ✓ |
| Plusieurs utilisateurs, support prioritaire | — | — | ✓ |

Ce découpage suit la feuille de route (Gratuit : offre et pipeline de base ; 15 à 30 € : accès
complet, automatisations, historique illimité ; 50 à 100 € : plusieurs utilisateurs, support
prioritaire). Les prix retenus, 25 € et 79 € HT, sont **[HYPOTHÈSE]** dans ces fourchettes ;
l'annuel revient 20 % moins cher.

La conformité (offre conforme d'office, information des candidats, absence de rejet automatique,
journal, suppression des données) est identique dans les trois offres.

Les limites sont appliquées côté serveur (`backend/app/services/plans.py`, réponse HTTP 402) et
non seulement masquées dans l'interface. Les prix affichés se règlent dans `.env`
(`PRICE_MONTHLY_EUR`, `PRICE_YEARLY_EUR`, `PRICE_AGENCY_MONTHLY_EUR`, `PRICE_AGENCY_YEARLY_EUR`)
et doivent correspondre aux prix créés dans Stripe. L'identifiant interne de l'offre Pro reste
`premium` (compatibilité des comptes existants).

## 2. Le marché

Relevé du 2 octobre 2026, inchangé depuis.

| Éditeur | Offre d'entrée | Ce qu'elle inclut | Fiabilité |
|---|---|---|---|
| Breezy HR | Gratuit (« Bootstrap ») ; payant dès 157 $/mois en annuel, 189 $ en mensuel (« Startup ») | Gratuit : 1 poste ou vivier actif ; payant : postes illimités | [FAIT] breezy.hr/pricing |
| Zoho Recruit | Gratuit ; « Standard » facturé par recruteur | Gratuit : 1 offre active par licence ; Standard : 10 offres actives par licence | [FAIT] pour les limites (zoho.com) ; environ 25 à 30 $ par recruteur et par mois selon des comparateurs [SECONDAIRE] |
| Flatchr (France) | « Starter » 49 €/mois | 1 emplacement (une campagne active), utilisateurs illimités | [SECONDAIRE] |
| Jobaffinity | Environ 79 € par utilisateur et par mois | — | [À VÉRIFIER] |
| Taleez, Teamtailor, Recruitee, Welcome to the Jungle | Sur devis | — | [À VÉRIFIER] |

Ce que le tableau établit :

- **Le gratuit limité à un poste actif est la norme du freemium ATS** (Breezy, Zoho, vérifiés sur
  leurs pages). WayLoop s'y aligne.
- **Pro à 25 € HT se place sous le prix d'entrée français relevé** (Flatchr Starter, 49 €/mois
  pour une seule campagne active), avec des recrutements illimités. Agence à 79 € HT reste sous
  les offres d'équipe des ATS généralistes relevés.
- **Indépendance des sources.** Les chiffres Flatchr viennent de deux comparateurs
  (adopteunlogicielfrancais.fr, appvizer.fr) qui reprennent selon toute vraisemblance la page de
  l'éditeur : ils ne se confirment pas l'un l'autre. À contrôler sur flatchr.io avant toute
  communication comparative. Les tarifs SaaS changent souvent.

## 3. Coût de l'IA

L'IA ne sert qu'à rédiger un brouillon d'offre à partir de la phrase du dirigeant. Rien d'autre
ne l'appelle : ni la lecture des CV, ni la synthèse, ni les e-mails.

| Élément | Valeur | Fiabilité |
|---|---|---|
| Modèle | Claude Haiku 4.5 (`claude-haiku-4-5`) | réglable par `AI_MODEL` |
| Prix public | 1 $ par million de jetons en entrée, 5 $ en sortie | [FAIT] platform.claude.com, page des prix, consultée le 3 octobre 2026 |
| Jetons par brouillon | environ 900 en entrée (consigne, schéma de la fiche, phrase) ; 600 à 1 200 en sortie, plafonnés à 1 500 | estimation à partir du code ; le coût réel de chaque appel est enregistré |
| Coût par brouillon | **0,4 à 0,7 centime de dollar**, soit moins d'un centime d'euro | calcul |
| Plafond | 30 brouillons par entreprise et par jour (`AI_DAILY_LIMIT`) : au pire environ 0,25 € par jour et par entreprise | réglage |

Conséquence : même en offre Gratuite, le coût de l'IA reste marginal (quelques centimes par
recrutement, la plupart des dirigeants ne générant qu'un ou deux brouillons). Il est négligeable
devant l'hébergement et l'envoi des e-mails. Les estimations de coût IA de la feuille de route
sont plus prudentes que ce calcul ; elles redeviendraient pertinentes seulement si l'IA servait
aussi à lire les CV, ce que le produit exclut (voir `conformite.md` § 2).

Chaque appel est journalisé avec ses jetons et son coût (`usage_records`, type `ai:draft`, en
dollars et en euros au taux `USD_TO_EUR`, fixé à 0,86 : **[HYPOTHÈSE]** à ajuster). Si l'API ne
répond pas, ou si la clé est absente, le repli par règles remplit le formulaire sans coût.

## 4. Paiement

Stripe Checkout (abonnement mensuel ou annuel, essai de 14 jours), portail client Stripe pour les
factures et la résiliation, webhook signé et idempotent (`/webhooks/stripe`). L'offre choisie
(Pro ou Agence) voyage dans les métadonnées de la session et de l'abonnement ; à défaut, elle est
déduite de l'identifiant de prix. Voir `deploiement.md` § 11. Les données de carte ne transitent
jamais par WayLoop.

## Sources

- Anthropic, prix de l'API : https://platform.claude.com/docs/en/about-claude/pricing (consultée le 3 octobre 2026)
- Breezy HR, page de prix : https://breezy.hr/pricing (consultée le 2 octobre 2026)
- Zoho Recruit, page de prix : https://www.zoho.com/recruit/pricing.html (consultée le 2 octobre 2026)
- Flatchr, comparateurs : https://adopteunlogicielfrancais.fr/flatchr/ et
  https://www.appvizer.fr/ressources-humaines/recrutement/flatchr (consultés le 2 octobre 2026)
- Zoho Recruit, comparateur : https://www.noon.ai/blog/articles/108-zoho-recruit-pricing-2026
