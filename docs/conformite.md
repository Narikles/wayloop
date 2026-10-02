# Conformité : ce que le code couvre, ce qui reste à faire

Ce document ne remplace pas un avis juridique. Il sert de support à la revue par un avocat
spécialisé (RGPD, AI Act, droit du travail) avant toute commercialisation.

Marqueurs de fiabilité, comme dans le dossier de construction :
**[FAIT]** vérifié sur le texte officiel ou une source primaire ce 2 octobre 2026 ·
**[CONNU]** règle établie, non revérifiée aujourd'hui sur le texte · **[À VÉRIFIER]** non confirmé,
ou sources secondaires qui divergent.

## 0. Principe : conforme d'office, sans rien demander au dirigeant

Le dirigeant n'a ni réglage de conformité à faire, ni message « rien à signaler » à lire :

- **L'offre est conforme par construction** : elle est rédigée à partir des champs typés du
  formulaire (modèle de texte, sans IA), et ce qui peut être corrigé l'est sans intervention :
  « (H/F) » ajouté à tout intitulé qui n'a pas déjà la double forme, reformulation sûre des
  mentions à risque (« bonne présentation » → « tenue adaptée à l'accueil de la clientèle »,
  « langue maternelle » → « niveau C1 »…).
- **Seule une mention impossible à corriger sans changer le sens voulu** (limite d'âge, sexe,
  situation de famille, « habiter à proximité »…) est signalée, **sous le champ concerné**, avec un
  bouton « Retirer ». Elle ne peut pas être publiée.
- **Conservation, information des candidats, journal, purge** : appliqués d'office (24 mois après
  le dernier contact ; accusé de réception avec l'information RGPD et la méthode de présélection).
  Ces réglages ont été retirés de l'écran Paramètres.

Code : `modules/compliance.py` (`sanitize`, `remove_mention`), `modules/form.py`,
`orchestrator._save_offer`. Les messages destinés aux candidats (information légale) restent
complets : seule l'interface du dirigeant est allégée.

## 1. Correspondance exigences → produit (dossier §7.4)

| Exigence | Réponse dans le code | Fichier |
|---|---|---|
| Pas de décision fondée exclusivement sur un traitement automatisé (RGPD art. 22) | Aucun rejet automatique ; les groupes ne sont que des suggestions ; toutes les candidatures restent consultables ; validation humaine de la sélection, de la décision et des réponses | `orchestrator.py`, `modules/screening.py` |
| Explicabilité, supervision humaine | Statut critère par critère : réponse du candidat, comparaison au seuil fixé par le dirigeant (règle affichée), extrait du CV qui confirme ou contredit ; ajout possible de n'importe quel candidat (indicateur « repêchés ») | `modules/screening.py`, `modules/form.py` |
| Traçabilité | Chaque étape préparée (avec la version des règles) et chaque décision humaine ; chaîne d'empreintes vérifiable ; déclencheur PostgreSQL interdisant modification et suppression hors purge de rétention ; page « Historique » pour le dirigeant | `audit.py`, `migrations/versions/0001_*` |
| Information des candidats (RGPD art. 13-14 ; Code du travail L1221-8) | Accusé de réception avec finalité, durée, droits, lien « mes données » et description de la méthode de présélection ; notice complète publique ; rappel sous le formulaire de candidature | `modules/communication.py`, `pages/public/OfferPage.tsx` |
| Non-discrimination | Offre conforme d'office (§ 0) ; critères contrôlés à la saisie ; masquage des informations sans rapport avec le poste avant l'examen du CV ; tests par CV jumeaux | `modules/compliance.py`, `modules/masking.py`, `tests/test_bias.py` |
| Limitation de la conservation | Échéancier calculé pour chaque candidat ; purge automatique (fichiers, texte, faits, notes, messages) ; retrait immédiat à la demande du candidat | `services/purge.py` |
| Questions d'entretien licites (L1221-6) | Questions choisies dans une banque liée au poste ; garde-fous sur toute question modifiée : vie privée, famille, santé, convictions, origine, âge, résidence, rémunération antérieure | `modules/question_bank.py`, `modules/interview.py` |
| Pas de collecte de profils sur Internet | Le produit ne traite que les candidatures reçues. Les API publiques interrogées (ROME, Géoplateforme, annuaire des entreprises) portent sur les métiers, les communes et l'entreprise cliente, jamais sur des personnes | `services/referentiels.py` |
| Questions de présélection en lien avec le poste (L1221-6) | Générées uniquement à partir des critères saisis, eux-mêmes contrôlés ; réponse libre limitée à 500 caractères ; réponses confrontées au CV | `modules/form.py` |
| Pas de ciblage des offres | Diffusion non ciblée : page publique de l'offre avec données structurées (Google pour l'emploi), lien direct, flux des plateformes partenaires ; aucun ciblage publicitaire de candidats | `services/publication.py` |

## 2. AI Act

- **Ce que fait le code.** WayLoop n'utilise plus aucun modèle d'IA (ni modèle de langage, ni
  apprentissage) : le dirigeant fixe des seuils explicites, la réponse du candidat est comparée à ce
  seuil par une règle affichée telle quelle, le CV est lu par des règles fixes (expressions et
  mots-clés) pour confirmer une réponse ou signaler un écart. Les modules d'IA, de transcription
  vocale et la messagerie WhatsApp/SMS ont été retirés du code (`tests/test_free_plan.py` vérifie
  leur absence).
- **[FAIT, source primaire, texte non contraignant]** Les lignes directrices de la Commission sur la
  définition d'un « système d'IA » (version datée du 29 juillet 2025) rappellent, d'après le
  considérant 12 du règlement (UE) 2024/1689, que la définition ne couvre pas les « systèmes fondés
  sur des règles définies uniquement par des personnes physiques pour exécuter automatiquement des
  opérations » (points 26, 40 et 46). Elles précisent qu'elles ne sont pas contraignantes ; seule la
  CJUE interprète le règlement (point 7).
- **[À VÉRIFIER avec un avocat]** Conséquence probable : WayLoop sortirait du champ « système
  d'IA », donc des obligations « haut risque » de l'annexe III (recrutement). Cette qualification
  dépend du détail des règles (`modules/cv_rules.py`, `modules/screening.py`) et doit être validée.
  Si elle ne l'était pas, le code fournit déjà la matière d'un dossier : journal, versions des
  règles, tests de régression et de biais, indicateurs.
- Dans tous les cas, le RGPD (art. 22 notamment), le Code du travail et l'interdiction de
  discriminer s'appliquent pleinement.

## 3. RGPD

- **Rôles.** La PME est responsable de traitement ; l'éditeur est sous-traitant (art. 28) : un
  contrat de sous-traitance type est à rédiger. Sous-traitants ultérieurs : hébergeur, service
  d'envoi d'e-mails ; Stripe pour le paiement de l'abonnement (données de l'entreprise cliente
  seulement). Aucune donnée de candidat n'est envoyée à un fournisseur d'IA.
- **Diffusion de l'offre.** La page publique de l'offre, son plan du site, les flux partenaires et
  l'API d'indexation de Google ne contiennent que l'offre (poste, entreprise, lieu, salaire) :
  aucune donnée de candidat. L'adresse du dirigeant n'y figure pas.
- **Réutilisation des données** pour améliorer le produit : non implémentée. Si vous la faites, vous
  devenez responsable de traitement pour cette finalité (à trancher avec un juriste).
- **[À VÉRIFIER] Analyse d'impact (AIPD).** Probablement requise (évaluation de personnes,
  traitement à grande échelle si le produit se diffuse) ; à confirmer sur la liste publiée par la
  CNIL.
- **[À VÉRIFIER] Durées de conservation.** La CNIL a publié un référentiel sur les durées de
  conservation en RH (avril 2026, source primaire non consultée ici). Deux synthèses secondaires
  le résument différemment : l'une retient 2 ans après le dernier contact pour un candidat non
  retenu, l'autre évoque aussi une conservation jusqu'à 5 ans à des fins de preuve en cas de
  litige. Ces synthèses dérivent du même texte et ne s'accordent pas sur le statut (base active ou
  archivage). Le produit applique 24 mois après le dernier contact, sans réglage pour le dirigeant
  (`RETENTION_MONTHS_AFTER_LAST_CONTACT` côté serveur) ; un archivage intermédiaire de preuve, à
  accès restreint, n'est pas implémenté.
- **Hébergement** : base et fichiers dans l'UE (voir `deploiement.md`).
- **Données publiques réutilisées.** Référentiel ROME 4.0 de France Travail sous Licence Ouverte
  [FAIT : mention présente dans le fichier exporté], cité dans l'interface et par l'API
  (`attribution`) ; Géoplateforme (IGN) pour les communes ; API Recherche d'entreprises (DINUM)
  pour le SIREN de l'entreprise cliente.
- **Sécurité** : chiffrement des données candidats au repos, liens temporaires, journal sans donnée
  personnelle en clair.

## 4. Code du travail

| Article | Contenu | Fiabilité | Traduction dans le produit |
|---|---|---|---|
| L5331-2 | Pas de limite d'âge dans une offre, sauf texte | [FAIT] Légifrance | Mention signalée, impossible à publier (`age_limit`) |
| L5331-4 | Offre rédigée en français | [FAIT] Légifrance | Texte majoritairement étranger signalé (`language`) |
| L5331-3 | Pas d'allégation inexacte (existence, nature, rémunération, lieu) | [FAIT] Légifrance | L'offre ne reprend que les champs saisis par le dirigeant ; pas de contrôle automatique de leur exactitude |
| L1142-1 | Interdiction de mentionner le sexe ou la situation de famille du candidat recherché | [FAIT] Code du travail numérique | « (H/F) » ajouté d'office ; mentions de sexe ou de situation de famille impossibles à publier |
| R1142-1 | Exceptions (emplois où le sexe est déterminant) | [CONNU] | Non géré : un tel poste passe par une rédaction hors outil |
| L1132-1 | Critères de discrimination prohibés (âge, sexe, origine, situation de famille, santé, lieu de résidence…) | [CONNU] | Offre conforme d'office, critères contrôlés, masquage, garde-fous d'entretien |
| L1221-6 | Informations demandées en lien direct et nécessaire avec le poste | [CONNU] | Questions issues des critères ; garde-fous de la grille |
| L1221-8 | Information du candidat sur les méthodes d'aide au recrutement, pertinence | [CONNU] | Accusé de réception, formulaire, notice |
| L1221-9 | Pas de collecte par un dispositif non porté à la connaissance du candidat | [CONNU] | Aucune collecte externe |
| L2312-38 | Information du CSE sur les méthodes d'aide au recrutement | [À VÉRIFIER] | À la charge de l'entreprise ; un modèle de note d'information est à fournir avec le contrat (la case « CSE » a été retirée de l'écran) |

## 5. Transparence salariale (directive (UE) 2023/970)

- **[FAIT]** L'article 5 impose d'informer le candidat de la rémunération initiale ou de sa
  fourchette, dans l'offre ou avant l'entretien, et interdit de l'interroger sur sa rémunération
  antérieure. Délai de transposition : 7 juin 2026.
- **[À VÉRIFIER — source unique]** Projet de loi de transposition présenté en Conseil des ministres
  le 10 septembre 2026, déposé au Sénat (procédure accélérée), non encore voté ; il prévoit une
  fourchette dans toute offre publiée (source : un cabinet d'avocats, FD Avocats ; non recoupé).
- **Dans le produit** : rémunération obligatoire dans le formulaire, toujours affichée dans l'offre ;
  un texte retouché à la main sans rémunération ne peut pas être enregistré ; « prétentions
  salariales » signalé ; question sur le salaire actuel interdite dans la grille.

## 6. Avant de commercialiser

1. Revue de ce document et des règles de `modules/compliance.py` par un avocat, y compris la
   qualification au regard de l'AI Act (§ 2).
2. Contrat de sous-traitance éditeur ↔ PME ; contrats avec l'hébergeur et le service d'e-mails.
3. AIPD ; registre des traitements de l'éditeur.
4. Modèle de note d'information du CSE (L2312-38) remis aux clients concernés.
5. `scripts/regression.py` et `scripts/bias_check.py` relancés et archivés à chaque changement des
   règles ou du masquage.
