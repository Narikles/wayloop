# Feuille de route : ce qui est fait, ce qui ne l'est pas

Correspondance entre la directive produit (`WayLoop_Product_Roadmap.pdf`, octobre 2026) et le
code livré. La structure existante (cinq pages par recrutement, formulaire guidé, moteur de
règles, conformité d'office) est conservée ; le nouvel angle s'y greffe.

## Fonctions demandées

| Demande | État | Détail |
|---|---|---|
| Création d'offre assistée : une phrase → description de 3-4 paragraphes, 5-6 critères clés, 3 questions techniques de présélection (Claude Haiku) | Fait | Résumé du poste, missions, jusqu'à 6 critères, 3 questions ; relu dans le formulaire avant publication. Repli par règles sans clé d'API. `modules/assistant.py` |
| Publication honnête : liste de contrôle par site, texte adapté (LinkedIn, Indeed, Pôle emploi, relais locaux), bouton Copier | Fait | Case « Publiée » par site, texte prêt à coller, lien suivi `?src=`, alerte « À mettre à jour » si l'offre change, rappel de retrait à la clôture. Pôle emploi s'appelle France Travail depuis le 1er janvier 2024. `services/publication.py`, page Offre |
| Toutes les réponses au même endroit : adresse e-mail dédiée, messages LinkedIn, formulaire, provenance affichée | Fait, sauf la relève des messages LinkedIn | Adresse par offre (`offres+<code>@…`, relevée en IMAP), formulaire, ajout manuel d'un candidat reçu ailleurs. Les messages LinkedIn ne peuvent pas être relevés automatiquement (voir plus bas). `services/inbound.py`, `orchestrator.add_candidate` |
| Pipeline Kanban : Reçu → À évaluer → Présélectionné → Entretien prévu → Refusé / Embauché ; CV, questionnaire, notes, historique | Fait | Glisser-déposer ou menu « Déplacer » (clavier, mobile) ; fiche avec CV, réponses, synthèse, notes d'équipe, historique. Vue liste conservée |
| Remerciement automatique des refusés | Fait (Pro) | Programmé une heure après le classement « Refusé », annulable jusque-là |
| Relance automatique après X jours | Fait (Pro) | Une seule relance, délai réglable de 1 à 30 jours |
| Récapitulatif hebdomadaire | Fait (Pro) | Chaque lundi à 8 h (heure de Paris), par e-mail, à toute l'équipe |
| Alerte en temps réel à chaque candidature (phase 2) | Fait, par e-mail | Toutes les offres ; compteurs « nouvelles candidatures » dans l'interface |
| Offres : Gratuit / 15-30 € / 50-100 € | Fait | Gratuit, Pro 25 € HT, Agence 79 € HT ; limites appliquées côté serveur. `docs/tarifs.md` |
| Indicateurs | Fait | Page « Indicateurs » : candidatures par provenance, délais, issue |

## Écarts assumés, et pourquoi

- **Messages LinkedIn.** L'API de messagerie de LinkedIn est réservée à ses partenaires : aucune
  application tierce ne peut relever les messages reçus par un dirigeant. Deux parades : le texte
  LinkedIn contient le lien de candidature suivi (le candidat atterrit dans le pipeline, provenance
  « LinkedIn »), et « Ajouter un candidat » enregistre en quelques secondes une personne qui a
  écrit directement.
- **Publication automatique sur LinkedIn, Indeed, France Travail.** Possible seulement après une
  convention ou une intégration négociée avec chaque plateforme ; d'ici là, le copier-coller
  assisté est la solution honnête. Les flux XML partenaires sont prêts (`PUBLICATION_FEEDS`).
- **Adresse unique `offres@wayloop.com`.** Remplacée par une adresse par offre sur le domaine de
  l'instance (`offres+<code>@…`) : c'est ce qui permet de rattacher un e-mail au bon recrutement
  sans lire son contenu.
- **L'IA ne lit pas les CV.** Trier ou noter des candidatures avec un modèle placerait le produit
  dans les systèmes à haut risque de l'AI Act (annexe III, point 4 a)), avec des obligations à
  partir du 2 décembre 2027. La synthèse reste faite par des règles explicites. `docs/conformite.md`
- **Coût de l'IA.** Au prix public de Claude Haiku 4.5, un brouillon coûte moins d'un centime
  d'euro : le poste de coût prévu peut être revu à la baisse. `docs/tarifs.md` § 3

## Pas encore fait

| Sujet | Pourquoi / piste |
|---|---|
| Synchronisation Google / Microsoft Agenda | Invitation `.ics` jointe en attendant ; API Google Calendar ou Microsoft Graph |
| Notifications sur téléphone (push, SMS) | E-mail seulement ; une application mobile ou un service SMS ajouterait un coût par message |
| Réception automatique des candidatures Indeed | Demande l'intégration ATS d'Indeed (accord) ; en attendant, lien suivi et ajout manuel |
| Marquage lisible par machine des textes générés (AI Act, art. 50(2)) | À trancher avec un avocat ; la provenance de chaque brouillon est déjà enregistrée |
| Espace multisite, réseaux de franchise | Offre Agence comme base (plusieurs utilisateurs) ; sur devis |
