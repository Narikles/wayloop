# Offres et prix

Marqueurs : **[FAIT]** vérifié ce 2 octobre 2026 sur une source primaire (page de l'éditeur) ·
**[SECONDAIRE]** chiffre tiré d'un site comparateur, non confirmé sur la page de l'éditeur ·
**[À VÉRIFIER]** non revérifié aujourd'hui, ou sources qui divergent.

## 1. Les offres WayLoop

| | Gratuit | Premium | Réseaux, multisites |
|---|---|---|---|
| Prix | 0 € | **49 € HT / mois** sans engagement, ou **468 € HT / an** (39 € HT / mois) | Sur devis |
| Essai | — | 14 jours (Stripe) | — |
| Recrutements en même temps | 1 | Illimités | Illimités |
| Formulaire en 4 étapes + référentiel ROME, offre rédigée d'office conforme | ✓ | ✓ | ✓ |
| Publication en un geste : Google pour l'emploi, lien à partager, plateformes partenaires activées | ✓ | ✓ | ✓ |
| Questions aux candidats, synthèse critère par critère, vérification dans le CV | ✓ | ✓ | ✓ |
| Sélection, e-mails groupés, réponse à chaque candidat | ✓ | ✓ | ✓ |
| Questions d'entretien, notes, comparatif | ✓ | ✓ | ✓ |
| Dates d'entretien confirmées au candidat (invitation d'agenda), rappel la veille | ✓ | ✓ | ✓ |
| Les candidats choisissent eux-mêmes leur créneau en ligne, relance automatique | — | ✓ | ✓ |
| Export CSV | — | ✓ | ✓ |

**Aucune IA, dans aucune offre** : formulaire, référentiels publics et règles explicites. Tout est
envoyé par e-mail (pas de WhatsApp ni de SMS). La conformité (offre rédigée conforme d'office,
information des candidats, absence de rejet automatique, journal, suppression des données) est
appliquée dans les deux offres, sans réglage ni message pour le dirigeant.

Ce qui distingue Premium tient en une phrase : **plusieurs recrutements à la fois**, plus la prise
de rendez-vous en ligne par les candidats et l'export.

Les limites sont appliquées côté serveur (`backend/app/services/plans.py`, réponse HTTP 402) et
non seulement masquées dans l'interface. Les prix affichés se règlent dans `.env`
(`PRICE_MONTHLY_EUR`, `PRICE_YEARLY_EUR`) et doivent correspondre aux prix créés dans Stripe.

## 2. Pourquoi ces prix : le marché

| Éditeur | Offre d'entrée | Ce qu'elle inclut | Fiabilité |
|---|---|---|---|
| Breezy HR | Gratuit (« Bootstrap ») ; payant dès 157 $/mois en annuel, 189 $ en mensuel (« Startup ») | Gratuit : 1 poste ou vivier actif ; payant : postes illimités | [FAIT] breezy.hr/pricing |
| Zoho Recruit | Gratuit ; « Standard » facturé par recruteur | Gratuit : 1 offre active par licence ; Standard : 10 offres actives par licence | [FAIT] pour les limites (zoho.com) ; prix affiché seulement via un calculateur ; environ 25 à 30 $ par recruteur et par mois selon des comparateurs [SECONDAIRE] |
| Flatchr (France) | « Starter » 49 €/mois | 1 emplacement (= une campagne active), utilisateurs illimités ; « Pro » 479 €/mois pour 10 emplacements | [SECONDAIRE] ; « Expert » à 599 €/mois selon un comparateur, « sur devis » selon un autre |
| Jobaffinity | Environ 79 € par utilisateur et par mois | — | [À VÉRIFIER] |
| Taleez, Teamtailor, Recruitee, Welcome to the Jungle | Sur devis | — | [À VÉRIFIER] |

Ce que le tableau établit, et ce qu'il n'établit pas :

- **Le gratuit limité à un poste actif est la norme du freemium ATS** (Breezy, Zoho, vérifiés sur
  leurs pages). WayLoop s'y aligne.
- **49 € par mois est le prix d'entrée français le plus bas relevé pour un poste actif** (Flatchr
  Starter). WayLoop Premium est au même prix mais sans limite de postes ; l'annuel à 39 € HT/mois
  passe sous ce seuil. Le retrait de l'IA ne change pas ce positionnement : chez les éditeurs
  relevés, le prix d'entrée se fixe d'abord sur le nombre de postes actifs.
- **Indépendance des sources.** Les chiffres Flatchr viennent de deux comparateurs français
  (adopteunlogicielfrancais.fr, appvizer.fr) qui reprennent selon toute vraisemblance la page de
  l'éditeur : ils ne se confirment pas l'un l'autre, et ils divergent sur l'offre Expert. La
  mention HT ou TTC n'y est pas toujours précise. À contrôler sur flatchr.io avant toute
  communication commerciale comparative.
- Les tarifs SaaS changent souvent ; ce relevé date du 2 octobre 2026.

## 3. Pourquoi aucune IA

1. **Coût.** Sans modèle de langage, le coût marginal d'un utilisateur, gratuit ou payant, se
   limite à l'hébergement et aux e-mails : il reste prévisible quel que soit le volume.
2. **Lisibilité.** Le formulaire produit des critères explicites (années, niveau, permis…) que le
   candidat renseigne lui-même ; la comparaison au seuil est une règle affichée telle quelle. La
   lecture du CV par règles sert à **confirmer** une réponse ou à **signaler un écart**, jamais à
   écarter quelqu'un.
3. **Réglementation.** Voir `conformite.md` § 2 bis : un logiciel dont les règles sont entièrement
   définies par des humains pourrait ne pas relever de la définition de « système d'IA » de l'AI Act
   ([À VÉRIFIER] avec un avocat). Le RGPD et le Code du travail s'appliquent dans tous les cas.

## 4. Paiement

Stripe Checkout (abonnement mensuel ou annuel, essai de 14 jours), portail client Stripe pour les
factures et la résiliation, webhook signé et idempotent (`/webhooks/stripe`). Voir
`deploiement.md` § 10. Les données de carte ne transitent jamais par WayLoop.

## Sources

- Breezy HR, page de prix : https://breezy.hr/pricing (consultée le 2 octobre 2026)
- Zoho Recruit, page de prix : https://www.zoho.com/recruit/pricing.html (consultée le 2 octobre 2026)
- Flatchr, comparateurs : https://adopteunlogicielfrancais.fr/flatchr/ et
  https://www.appvizer.fr/ressources-humaines/recrutement/flatchr (consultés le 2 octobre 2026)
- Zoho Recruit, comparateur : https://www.noon.ai/blog/articles/108-zoho-recruit-pricing-2026
