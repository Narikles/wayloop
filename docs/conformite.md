# Conformité : ce que le code couvre, ce qui reste à faire

Ce document ne remplace pas un avis juridique. Il sert de support à la revue par un avocat
spécialisé (RGPD, AI Act, droit du travail) avant toute commercialisation.

Marqueurs de fiabilité : **[FAIT]** vérifié sur le texte officiel ou une source primaire (date
indiquée) · **[SECONDAIRE]** analyse de cabinet d'avocats ou de presse, non confirmée sur le
texte · **[CONNU]** règle établie, non revérifiée sur le texte · **[À VÉRIFIER]** non confirmé, ou
interprétation ouverte.

## 0. Principes

- **Conforme d'office, sans réglage pour le dirigeant.** L'offre est rédigée à partir des champs
  typés du formulaire ; « (H/F) » est ajouté à tout intitulé qui n'a pas la double forme, les
  mentions à risque sont reformulées (« bonne présentation » → « tenue adaptée à l'accueil de la
  clientèle »…). Seule une mention impossible à corriger sans changer le sens (limite d'âge, sexe,
  situation de famille, « habiter à proximité »…) est signalée sous son champ, avec « Retirer » ;
  elle ne peut pas être publiée. Code : `modules/compliance.py`, `modules/form.py`.
- **L'IA rédige, elle n'évalue jamais.** Le seul appel à un modèle de langage transforme la phrase
  du dirigeant en brouillon d'offre (description, critères, trois questions). Le brouillon passe
  ensuite par le même formulaire et les mêmes contrôles que s'il avait été saisi à la main.
  Aucune candidature, aucun CV, aucune réponse, aucune note n'est envoyé au modèle ; aucun
  classement ni filtrage des candidats n'utilise d'IA. `tests/test_free_plan.py`
  (`test_ai_only_drafts_offers`) vérifie que seul le module de rédaction importe l'assistant.
- **Le dirigeant décide de tout.** Les automatisations exécutent une décision déjà prise par un
  humain (envoyer le remerciement à quelqu'un classé « Refusé ») ou rappellent ce qui attend
  (relance, récapitulatif) ; aucune ne refuse ni ne sélectionne quelqu'un.

## 1. Correspondance exigences → produit

| Exigence | Réponse dans le code | Fichier |
|---|---|---|
| Pas de décision fondée exclusivement sur un traitement automatisé (RGPD art. 22) | Aucun rejet automatique : seul le dirigeant classe une candidature « Refusé » ; le remerciement part ensuite, après un délai d'annulation d'une heure. Les groupes de la synthèse ne sont que des suggestions ; toutes les candidatures restent consultables | `orchestrator.py`, `services/automations.py`, `modules/screening.py` |
| Explicabilité, supervision humaine | Synthèse critère par critère : réponse du candidat, seuil fixé par le dirigeant (règle affichée), extrait du CV qui confirme ou contredit ; les réponses libres aux questions de présélection sont montrées telles quelles, jamais notées | `modules/screening.py`, `modules/form.py` |
| Traçabilité | Journal chaîné : brouillon IA (modèle, version de la consigne), publication, déplacements dans le pipeline, notes, refus programmés et annulés, envois ; déclencheur PostgreSQL interdisant modification et suppression hors purge | `audit.py`, `migrations/` |
| Information des candidats (RGPD art. 13-14 ; Code du travail L1221-8) | Accusé de réception avec finalité, durée, droits, lien « mes données » et méthode de présélection, quel que soit le canal : formulaire, e-mail reçu, ajout manuel (case cochée par défaut). Un candidat ajouté sans adresse e-mail porte la mention « Sans e-mail : informez la personne vous-même » | `modules/communication.py`, `orchestrator._acknowledge_received` |
| Non-discrimination | Offre conforme d'office (§ 0) ; critères contrôlés à la saisie ; garde-fous sur les questions de présélection libres (vie privée, famille, santé, convictions, origine, âge, résidence, rémunération antérieure) ; masquage avant lecture du CV ; tests par CV jumeaux | `modules/compliance.py`, `modules/form.py` (`_question_violation`), `modules/masking.py` |
| Limitation de la conservation | Purge à 24 mois après le dernier contact : CV, texte, réponses, notes, messages (dont le contenu des e-mails reçus) ; retrait immédiat à la demande du candidat. Seule l'empreinte du Message-ID d'un e-mail reçu est gardée, pour ne pas le traiter deux fois | `services/purge.py`, `services/inbound.py` |
| Questions en lien direct avec le poste (L1221-6) | Questions issues des critères ; trois questions libres au plus, contrôlées ; réponse limitée à 500 caractères | `modules/form.py` |
| Pas de collecte de profils sur Internet (L1221-9) | Le produit ne traite que les candidatures reçues ou transmises au dirigeant. Les messages LinkedIn ne sont pas relevés : le dirigeant ajoute lui-même la personne qui l'a contacté | `orchestrator.add_candidate` |
| Pas de ciblage des offres | Diffusion non ciblée : page publique, Google pour l'emploi, textes à coller sur les sites ; aucun ciblage publicitaire | `services/publication.py` |
| Notes internes | Visibles par l'équipe de l'entreprise seulement, chiffrées, purgées avec la candidature ; le candidat peut en obtenir communication au titre du droit d'accès (art. 15) : les rédiger en conséquence | `models.CandidateNote` |

## 2. AI Act

### 2.1 Calendrier

- **[FAIT, EUR-Lex, 3 octobre 2026]** Le règlement (UE) 2026/1744 du 8 juillet 2026 (« Digital
  Omnibus on AI »), en vigueur depuis le 27 juillet 2026, modifie le règlement (UE) 2024/1689 :
  les obligations des systèmes à haut risque de l'annexe III (dont le recrutement) s'appliquent
  à partir du **2 décembre 2027** ; celles de l'annexe I, à partir du 2 août 2028.
- **[FAIT, même source, considérant]** Pour le marquage des contenus générés (art. 50(2)), un délai
  de quatre mois est accordé aux seuls fournisseurs dont le système était sur le marché avant le
  2 août 2026. **[SECONDAIRE]** Deux cabinets (Orrick, Lewis Silkin) en tirent la même lecture :
  2 décembre 2026 pour ces systèmes, application immédiate pour les autres. Ces analyses
  dérivent du même texte ; elles confirment la lecture, pas un fait distinct.

### 2.2 Ce que fait l'assistant, et ce qu'il ne fait pas

L'annexe III, point 4 a), vise les systèmes destinés au recrutement ou à la sélection,
« notamment pour publier des offres d'emploi ciblées, analyser et filtrer les candidatures et
évaluer les candidats » **[CONNU]**. L'assistant de WayLoop ne cible pas la diffusion, ne filtre
rien et n'évalue personne : il rédige un texte que l'employeur relit, corrige et publie.

**[À VÉRIFIER avec un avocat]** Deux lectures sont possibles :

1. l'assistant n'entre pas dans l'annexe III, faute de toucher à l'accès des candidats à
   l'emploi ;
2. il y entre (« destiné à être utilisé pour le recrutement »), mais relève de l'exception de
   l'article 6(3) : tâche procédurale étroite, ou amélioration du résultat d'une activité humaine
   déjà réalisée (la phrase du dirigeant, puis sa relecture). Le fournisseur doit alors documenter
   cette évaluation avant la mise sur le marché (art. 6(4)) et enregistrer le système (art. 49(2)),
   enregistrement maintenu sous une forme allégée par le règlement 2026/1744 **[SECONDAIRE]**.

Dans les deux cas, un dossier court est à rédiger dès maintenant : finalité, absence de données
de candidats, contrôle humain, journalisation (`offer.drafted` avec modèle et version de la
consigne `assistant-offre@2026-10-03`).

**Pourquoi l'IA ne lit pas les CV.** Trier ou noter des candidatures avec un modèle relèverait
sans ambiguïté de l'annexe III, point 4 a) : gestion des risques, gouvernance des données,
documentation technique, contrôle humain, exactitude, évaluation de conformité, à partir du
2 décembre 2027. La synthèse des réponses reste faite par des règles écrites par des humains. Les
lignes directrices de la Commission sur la définition d'un « système d'IA » (29 juillet 2025)
indiquent que de tels systèmes « fondés sur des règles définies uniquement par des personnes
physiques » sont hors définition **[FAIT, texte non contraignant ; seule la CJUE interprète le
règlement]**.

### 2.3 Point ouvert : marquage des textes générés (art. 50(2))

L'article 50(2) impose aux fournisseurs de systèmes d'IA générant du texte de marquer les sorties
dans un format lisible par machine, « dans la mesure où cela est techniquement possible », sauf
fonction d'assistance à l'édition courante ou absence de modification substantielle des données
fournies **[CONNU]**. WayLoop intègre le modèle sous son propre nom : il serait vraisemblablement
« fournisseur » de ce système **[À VÉRIFIER]**, et une phrase développée en plusieurs paragraphes
dépasse l'édition courante. Mis en service après le 2 août 2026, l'assistant ne bénéficierait pas
du délai de quatre mois.

Ce que fait le code : provenance enregistrée pour chaque recrutement (moteur, modèle, version de
la consigne), mention « Brouillon rédigé avec l'assistant IA, relu par vous » dans l'espace du
dirigeant. Ce qu'il ne fait pas : aucun marquage lisible par machine sur la page publique de
l'offre. **À trancher avec un avocat**, en tenant compte du code de bonnes pratiques de la
Commission sur le marquage et l'étiquetage des contenus générés **[À VÉRIFIER : état d'avancement
non revérifié]**. L'article 50(4) (textes publiés pour informer le public sur des questions
d'intérêt public) ne paraît pas viser une offre d'emploi, relue et publiée sous la responsabilité
éditoriale de l'employeur.

### 2.4 Dans tous les cas

Le RGPD (art. 22 notamment), le Code du travail et l'interdiction de discriminer s'appliquent
pleinement, avec ou sans IA.

## 3. RGPD

- **Rôles.** La PME est responsable de traitement ; l'éditeur est sous-traitant (art. 28) : un
  contrat de sous-traitance type est à rédiger. Sous-traitants ultérieurs : hébergeur, service
  d'envoi d'e-mails, fournisseur de la boîte de réception (e-mails des candidats), Stripe (données
  de l'entreprise cliente seulement), Anthropic pour la rédaction des offres.
- **Fournisseur d'IA.** Seule la phrase décrivant le poste lui est envoyée ; l'interface demande
  de n'y mettre ni nom ni critère personnel. **[À VÉRIFIER]** Conditions contractuelles du
  fournisseur (non-réutilisation des données, durée de conservation, transfert hors UE et
  garanties) à reporter dans la liste des sous-traitants remise aux clients.
- **E-mails reçus.** Un e-mail envoyé à l'adresse de l'offre (`offres+<jeton>@…`) devient une
  candidature : l'empreinte du message évite les doublons, les réponses automatiques et les
  rejets de messagerie sont ignorés, le CV joint est chiffré, et le candidat reçoit l'accusé de
  réception avec l'information RGPD. Un e-mail transféré par le dirigeant depuis sa propre boîte
  est rattaché à l'expéditeur d'origine, qui reçoit l'accusé de réception. Le texte du message
  (3 000 caractères au plus) devient le message de la candidature, chiffré comme le reste.
- **Diffusion de l'offre.** Page publique, plan du site, flux partenaires et textes à coller ne
  contiennent que l'offre (poste, entreprise, lieu, salaire) et un lien de candidature : aucune
  donnée de candidat.
- **Réutilisation des données** pour améliorer le produit : non implémentée. Si vous la faites,
  vous devenez responsable de traitement pour cette finalité.
- **[À VÉRIFIER] Analyse d'impact (AIPD).** Probablement requise (évaluation de personnes,
  traitement à grande échelle si le produit se diffuse) ; à confirmer sur la liste de la CNIL.
- **[À VÉRIFIER] Durées de conservation.** Le référentiel CNIL sur les durées de conservation en
  RH (avril 2026) est résumé différemment par deux synthèses secondaires (2 ans après le dernier
  contact ; jusqu'à 5 ans à des fins de preuve). Le produit applique 24 mois après le dernier
  contact (`RETENTION_MONTHS_AFTER_LAST_CONTACT`) ; l'historique limité à 30 jours de l'offre
  Gratuite ne change rien à la conservation, seulement à l'affichage.
- **Hébergement** : base et fichiers dans l'UE (voir `deploiement.md`).
- **Sécurité** : chiffrement des données candidats et des notes au repos, liens temporaires,
  journal sans donnée personnelle en clair.

## 4. Code du travail

| Article | Contenu | Fiabilité | Traduction dans le produit |
|---|---|---|---|
| L5331-2 | Pas de limite d'âge dans une offre, sauf texte | [FAIT] Légifrance | Mention signalée, impossible à publier (`age_limit`) |
| L5331-4 | Offre rédigée en français | [FAIT] Légifrance | Texte majoritairement étranger signalé (`language`) |
| L5331-3 | Pas d'allégation inexacte (existence, nature, rémunération, lieu) | [FAIT] Légifrance | Le salaire, le lieu et le contrat saisis par le dirigeant priment sur le brouillon IA, qui n'en invente aucun ; l'exactitude reste de la responsabilité de l'employeur |
| L1142-1 | Interdiction de mentionner le sexe ou la situation de famille du candidat recherché | [FAIT] Code du travail numérique | « (H/F) » ajouté d'office ; mentions impossibles à publier |
| L1132-1 | Critères de discrimination prohibés | [CONNU] | Offre conforme d'office, critères et questions contrôlés, masquage, garde-fous d'entretien |
| L1221-6 | Informations demandées en lien direct et nécessaire avec le poste | [CONNU] | Questions issues des critères ; questions libres contrôlées |
| L1221-8 | Information du candidat sur les méthodes d'aide au recrutement | [CONNU] | Accusé de réception, formulaire, notice |
| L1221-9 | Pas de collecte par un dispositif non porté à la connaissance du candidat | [CONNU] | Aucune collecte externe |
| L2312-38 | Information du CSE sur les méthodes d'aide au recrutement | [À VÉRIFIER] | À la charge de l'entreprise ; modèle de note à fournir avec le contrat |

## 5. Transparence salariale (directive (UE) 2023/970)

- **[FAIT]** L'article 5 impose d'informer le candidat de la rémunération initiale ou de sa
  fourchette, dans l'offre ou avant l'entretien, et interdit de l'interroger sur sa rémunération
  antérieure. Délai de transposition : 7 juin 2026.
- **[À VÉRIFIER — source unique, relevé du 2 octobre 2026]** Projet de loi de transposition
  présenté en Conseil des ministres le 10 septembre 2026, non encore voté ; il prévoit une
  fourchette dans toute offre publiée.
- **Dans le produit** : rémunération obligatoire dans le formulaire (l'assistant ne la devine
  jamais : sans montant dans la phrase, le champ reste à remplir), toujours affichée dans l'offre et
  dans les textes à coller ; question sur le salaire actuel interdite dans les questions libres et
  dans la grille.

## 6. Avant de commercialiser

1. Revue de ce document par un avocat, en priorité la qualification de l'assistant (§ 2.2) et le
   marquage des textes générés (§ 2.3).
2. Contrat de sous-traitance éditeur ↔ PME ; contrats avec l'hébergeur, le service d'e-mails, le
   fournisseur de la boîte de réception et le fournisseur d'IA.
3. AIPD ; registre des traitements de l'éditeur.
4. Modèle de note d'information du CSE (L2312-38) remis aux clients concernés.
5. `scripts/regression.py` et `scripts/bias_check.py` relancés et archivés à chaque changement des
   règles ou du masquage.

## Sources

- Règlement (UE) 2026/1744 (Digital Omnibus on AI), EUR-Lex : https://eur-lex.europa.eu/eli/reg/2026/1744/oj (consulté le 3 octobre 2026)
- Orrick, « EU AI Act Update: Digital Omnibus Finalizes 8 Compliance Changes », juillet 2026 : https://www.orrick.com/en/Insights/2026/07/EU-AI-Act-Update-Digital-Omnibus-Finalizes-8-Compliance-Changes
- Lewis Silkin, « The Digital Omnibus on AI enters into force today », 27 juillet 2026 : https://www.lewissilkin.com/insights/2026/07/27/the-digital-omnibus-on-ai-enters-into-force-today-102nedo
- Règlement (UE) 2024/1689 (AI Act), art. 6, 49, 50 et annexe III ; lignes directrices de la Commission sur la définition d'un système d'IA (29 juillet 2025)
