---
title: EXPERIENCE — Atelier LLM, la boucle du modèle (lot 6)
status: final
created: 2026-10-05
updated: 2026-10-05
sources:
  - ../../../implementation-artifacts/plan-corrections-2026-10-04.md
  - ../ux-agentic-harness-training-demo-2026-09-22/EXPERIENCE.md
  - DESIGN.md
---

# Atelier LLM, la boucle du modèle — Experience Spine (delta du lot 6)

Delta du lot 6 sur l'EXPERIENCE.md principal. Il remplace, pour la page `/llm`, les
composants « Puce de token » (section 1), « Schéma de vectorisation », « Réglages
d'échantillonnage » et « Distribution vivante », et renumérote les sections suivantes. Les
jetons cités sont ceux du DESIGN.md principal, les composants ceux de [DESIGN.md](DESIGN.md).
Maquette de référence : [mockups/llm-loop.html](mockups/llm-loop.html) (v3).

## Foundation

- **Surface** : page `/llm` (« Atelier LLM »), poste Windows, Edge ou Chrome, souvent
  projetée. Cibles : 1600 × 1000 et 1366 × 768. Pas de mobile.
- **Système d'interface** : le schéma commun du lot 2 (`static/diagram.js`) : blocs,
  allumage, explication au clic, pas à pas (`createStepper`). Le lot 6 l'étend par ajout.
- **Règle AD-1** : la page ne calcule aucun chiffre. Tokens, identifiants et dimensions
  viennent de `llm_tokenized` ; probabilités et chances de `POST /api/llm_lab/distribution`
  (celles de l'exemple de `POST /api/llm_lab/example_distribution`, correction C du 2026-10-05) ;
  le token tiré du moteur (`llm_step`), ou, sans modèle qui tire, celui que la session tire
  dans l'exemple (`POST /api/llm_lab/example_draw`, correction F du 2026-10-05) ; l'architecture de
  `llm_tokenized.dimensions.architecture`.
- **Portée (D4)** : la TRANSFORMATION détaille le transformeur décodeur dense (Qwen3, Llama,
  Gemma). Un modèle hybride ou MoE garde le même dessin, sous un bandeau qui dit en quoi il
  est inexact.

## Information Architecture

Décision d'Anaël (2026-10-05) : les trois étapes **remplacent les sections 1 et 2**.

```
/llm
├─ en-tête (titre, modèle actif, intro)
├─ 1 INPUT            — texte saisi, « Découper en tokens », texte → tokens → identifiants   (réel)
│     │ les identifiants entrent dans le modèle
├─ 2 TRANSFORMATION   — embeddings, couches (attention, MLP), dernier vecteur             (illustratif)
│     │ le vecteur du dernier token est comparé à tout le vocabulaire
├─ 3 OUTPUT           — logits → tirage (réglages) → token tiré, « Ajouter à la suite » ↺   (réel)
├─ 4 Chargement du modèle      (ex-section 3, inchangée)
├─ 5 Lecture du prompt         (ex-section 4, inchangée)
├─ 6 Génération                (ex-section 5 : « Générer », puces, comparaison A/B)
└─ 7 Raisonnement              (ex-section 6, inchangée)
```

- Le champ de texte et « Découper en tokens » passent dans l'INPUT ; les réglages
  d'échantillonnage (et « Revenir aux valeurs du harnais ») dans la partie Tirage de
  l'OUTPUT, sans doublon. « Générer » (section 6) envoie le texte de l'INPUT avec les
  réglages de l'OUTPUT, comme avant.
- « Les questions que vous vous posez » : celles de la tokenisation dans l'INPUT, celles de
  l'échantillonnage dans l'OUTPUT ; six encarts au total, comme avant.
- **Compatibilité** : les ids et classes lus par les tests et l'E2E sont conservés sur les
  nouveaux éléments (`#llm-prompt`, `#tokenize-button`, `#token-chips`, `#token-counts`,
  `#embedding-diagram` sur la carte TRANSFORMATION, `#sampling-controls .sampling-row`,
  `#distribution`, `#distribution-bars .dist-row` avec leurs `.dist-cell.is-model` et
  `.is-chance` dans le graphique du Tirage, `#distribution-token`, `#distribution-empty`).

## Voice and Tone

Phrases courtes, au présent, vocabulaire du glossaire, aucune formule mathématique. Le
schéma dit la vérité sur lui-même sans s'excuser : « illustratif », « le moteur n'expose
pas ».

| Où | Texte (fr) |
| --- | --- |
| Titres d'étape | INPUT · le texte devient des nombres — TRANSFORMATION · les nombres traversent les couches du modèle — OUTPUT · du vecteur au token suivant |
| Étiquettes | Réel · tokenizer du modèle — Illustratif · vraies dimensions — Réel · probabilités et tirage |
| Liens entre étapes | les identifiants entrent dans le modèle — le vecteur du dernier token est comparé à tout le vocabulaire |
| INPUT, pas 1 à 3 | **Texte.** Le texte tapé, tel quel. Le modèle ne le lira jamais en lettres. — **Tokens.** Le tokenizer découpe le texte en morceaux pris dans un vocabulaire fixe : souvent un mot avec l'espace qui le précède (␣), parfois un bout de mot. — **Identifiants.** Chaque token est remplacé par son numéro dans le vocabulaire. À partir d'ici, le modèle ne voit plus que ces nombres. |
| TRANSFORMATION, pas 1 à 7 | Embeddings : chaque identifiant va chercher sa ligne — Couche 1 · attention : les tokens se regardent — Couche 1 · MLP : chaque token, seul, passe dans un réseau plus large — Couche 2 · attention — Couche 2 · MLP — … et ainsi de suite, couche après couche — Le vecteur du dernier token part vers l'OUTPUT (explications : maquette v3, `TRANSFO_FRAMES`) |
| Note sous le canevas | Le moteur n'expose ni les poids d'attention ni les états cachés : {n} tokens, 8 nombres par vecteur et une poignée de neurones montrent la forme du calcul ; les couleurs sont inventées, les chiffres du panneau sont ceux du modèle. |
| Bandeau hybride | ⚠ Schéma simplifié, inexact pour cette architecture. {modèle} est hybride : seule une couche sur {intervalle} fait de l'attention complète ; les autres sont des couches récurrentes (un état de taille fixe), dessinées ici comme des couches d'attention. |
| Bandeau hybride sans intervalle | … {modèle} est hybride : ses couches alternent attention complète et couches récurrentes (un état de taille fixe), dessinées ici comme des couches d'attention. |
| Bandeau MoE | ⚠ Schéma simplifié, inexact pour cette architecture. Le MLP de {modèle} est un mélange d'experts : pour chaque token, un routeur choisit {actifs} experts sur {experts}. Le schéma en dessine 6, dont 2 actifs. |
| Architecture non lue | Architecture non lue pour ce modèle : schéma du transformeur décodeur dense par défaut. |
| Logits | un score par token du vocabulaire, ramené en probabilité : les 6 plus probables après « {fin du texte} » |
| Tirage | bougez un réglage : la chance de chaque mot change, la probabilité du modèle (au-dessus) ne bouge pas |
| Écarté | écarté (top-k) — écarté (top-p) — écarté (min-p) |
| Gardés | {gardés} gardés sur {lus} · la chance est partagée entre eux seuls (le reste du vocabulaire, {reste}, n'est pas tiré ici). |
| Aide des réglages | les textes existants `sampling.settings.*.help_text` (au survol et au clic du nom) |
| Token tiré | 🎲 Tirer le token suivant — ↺ Ajouter à la suite — Retirer le dernier — derniers tirages : … |
| Sans moteur en processus | la raison existante `candidates.reason_text` (serveur, cloud), dans l'OUTPUT, sous le graphique du Tirage, après la note de l'exemple (correction C du 2026-10-05 : les graphiques d'exemple restent ; la raison n'est plus répétée sous « Tirer », pour que l'étape tienne à 1366 × 768) |
| Token tiré dans l'exemple (correction F du 2026-10-05) | Puce suivie du badge « exemple » ; nom accessible « {texte}, tiré dans l'exemple » |
| Exemple (correction C du 2026-10-05) | Badges « Exemple · tokens d'illustration », « Exemple · probabilités d'illustration » — Exemple : un texte découpé comme le ferait un tokenizer, avec des identifiants d'illustration. Découpez votre texte : ses vrais tokens remplaceront ceux-ci. — Exemple de découpage, pas celui de ce modèle : son tokenizer est chez son fournisseur. Pour votre texte, WaveStack donne seulement l'estimation ci-contre. — Exemple d'illustration, pas le calcul du modèle : les réglages le font bouger comme le vrai tirage. — Il ne bouge que l'exemple. |

## Component Patterns

| Composant | Comportement |
| --- | --- |
| Pas à pas d'étape | Un `createStepper` par étape, dans son en-tête. INPUT : 3 pas ; TRANSFORMATION : 7 pas ; OUTPUT : 3 pas (Logits, Tirage, Token tiré), halo sur la partie en cours. Le bouton de droite est « Tout montrer » (INPUT, TRANSFORMATION : dernier pas) et « Suivre le direct » (OUTPUT, pendant une génération). |
| INPUT | « Découper en tokens » remplit les colonnes et ouvre le pas 1 (texte d'un bloc : chaque colonne a la largeur de son morceau, aucun écart ajouté, correction D du 2026-10-05). Pas 2 : les colonnes s'écartent, chaque morceau se souligne, flèche et puce apparaissent. Pas 3 : flèche et identifiant. Compteurs : caractères, tokens, nombres. Un texte de plus de 512 tokens : 512 colonnes et « … et N de plus ». |
| TRANSFORMATION | Chaque pas redessine le canevas ; les cellules des vecteurs passent de l'état du pas précédent à celui du pas (0,5 s). Panneau : titre, explication, « En vrai, pour {modèle} », pile des couches (couche en cours en halo ; hybride : pleine = attention complète, tirets = récurrente). Les états des vecteurs sont pseudo-aléatoires à graine fixe : le même texte donne le même dessin. |
| OUTPUT · Logits | Les 6 candidats les plus probables (texte et probabilité du modèle) et le reste du vocabulaire, du dernier pas (au premier chargement, le pas automatique : une lecture des candidats du token suivant, sans tirage, correction E du 2026-10-05), sinon du token choisi en section 6. Le token tiré n'est nommé (légende) et marqué que tant que sa puce est montrée, en section 6 ou dans « Token tiré » ; après un rechargement, rien n'est nommé (correction D du 2026-10-05). |
| OUTPUT · Tirage | Les quatre réglages : chaque mouvement redemande la distribution (`/api/llm_lab/distribution`, 80 ms d'attente, la dernière réponse gagne) et redessine le graphique. Le nom de chaque réglage est un bouton : son explication au survol (`title`) et au clic, Entrée ou Espace (encart ancré, Échap le ferme). |
| OUTPUT · Token tiré | « Tirer le token suivant » appelle `POST /api/intentions/llm_step` : le moteur lit le texte de l'INPUT et les tokens déjà ajoutés, tire un token avec les réglages, et renvoie ses candidats. La puce tirée s'affiche, les Logits et le Tirage passent à ce token. « Tirer » à nouveau retire au sort au même endroit (le cache rend le pas rapide). « Ajouter à la suite » ajoute le token à l'INPUT (puce « produit ») et remonte à l'INPUT ; « Retirer le dernier » enlève le dernier ajout. Changer le texte de l'INPUT efface les ajouts. 64 ajouts au plus. Un réglage bougé efface la puce tirée, avec sa légende et sa ligne marquée dans les graphiques ; « derniers tirages » reste (règle de la maquette, correction D du 2026-10-05). Sans modèle qui tire (cloud, serveur, aucun modèle ; correction F du 2026-10-05) : « Tirer » tire dans l'exemple, par la session (`POST /api/llm_lab/example_draw`), un des candidats gardés selon les chances affichées, jamais le reste du vocabulaire ; puce marquée « exemple », ligne marquée dans les deux graphiques sans légende (aucun moteur n'a tiré), « derniers tirages » rempli, « Ajouter à la suite » et « Retirer le dernier » masqués (l'exemple n'a pas de suite) ; aucun événement, rien au journal du Harnais. Le bouton n'est grisé que pendant son propre tirage. Un moteur en processus qui montre encore l'exemple (avant découpage) garde le vrai tirage. |
| Bandeau D4 | En tête de la TRANSFORMATION quand `architecture.family` vaut `hybrid` ou `moe` ; raisons cumulées pour un hybride à experts. Jamais refermable. |

## State Patterns

| État | INPUT | TRANSFORMATION | OUTPUT |
| --- | --- | --- | --- |
| Premier chargement, moteur en processus au repos (correction C du 2026-10-05) | La page fait découper le texte du champ sans clic : colonnes réelles, badge « Réel » | Tokens réels, dimensions réelles | La page fait lire les candidats du token suivant sans clic (sauf distribution déjà gardée) : une lecture « candidats seuls » de la session (`llm_step` à `candidates_only`, corrections D et E du 2026-10-05), le moteur évalue le texte et lit les logits du token suivant sans en tirer aucun, aucun `llm_token` ; graphiques réels, étape au pas 1 (Logits), « Le moteur lit les probabilités du token suivant, sans en tirer… » pendant la lecture ; rien n'est montré tiré (ni puce, ni « derniers tirages », ni token tiré nommé ou marqué, « Ajouter » grisé), le journal du Harnais l'appelle « lecture des probabilités » ; « Tirer le token suivant » tire |
| Rechargement, moteur en processus, distribution déjà gardée (correction C) | Rien d'automatique : colonnes d'exemple jusqu'à « Découper en tokens » | Tokens d'exemple | Graphiques réels de la dernière génération (ou du dernier pas), badge « Réel », sans token nommé ni marqué (correction D) |
| Avant toute tokenisation | Colonnes d'**exemple** (`stages.transfo.example_tokens` et `example_ids`), badge « Exemple · tokens d'illustration », note « Exemple : … » ; ◀ ▶ les découpent pas à pas | Dessin avec les tokens d'exemple, dit « exemple » | Graphiques d'**exemple** (`stages.output.example`, tirés par la session pour les réglages affichés), badge « Exemple · probabilités d'illustration », note + « Tirez le token suivant… » |
| Tokenisé | Colonnes réelles, badge « Réel » | Tokens réels, dimensions réelles | Exemple jusqu'au premier pas |
| Pas tiré / génération avec candidats | Ajouts en puces « produit » | Les ajouts comptent comme tokens | Graphiques réels, badge « Réel » ; un ajout ou un retrait repasse à l'exemple |
| Serveur ou cloud | Cloud : colonnes d'exemple + « ≈ N tokens » du texte tapé, note « Exemple de découpage, pas celui de ce modèle » ; serveur : exemple puis colonnes réelles après « Découper » | Dimensions « inconnue » si non lues | Graphiques d'exemple avec la raison de session ; tous les curseurs actifs (un réglage non pris garde sa raison, « il ne bouge que l'exemple ») ; « Tirer » tire dans l'exemple (correction F du 2026-10-05), « Ajouter » et « Retirer » masqués |
| Session occupée (tour de l'atelier, chargement) | Boutons désactivés avec la raison (existant) | — | « Tirer » désactivé avec la raison (moteur en processus ; sans modèle qui tire, il tire toujours dans l'exemple, correction F du 2026-10-05) |
| Hybride / MoE | — | Bandeau ; MoE : routeur et experts au pas MLP | — |
| Architecture non lue | — | Note sous le panneau | — |

## Interaction Primitives

- ◀ ▶ dans chaque étape ; « Tout montrer » / « Suivre le direct ».
- Clic, Entrée ou Espace sur un nom de réglage ou un bloc : son explication ; Échap la ferme.
- Curseurs : glisser ou flèches du clavier ; le graphique suit.
- Aucune information portée par le seul survol (le `title` double l'encart au clic).

## Accessibility Floor

- Chaque colonne de l'INPUT a un nom accessible : « « chat » → token ␣chat → identifiant
  9558 ». Les flèches et cellules sont `aria-hidden`.
- Le canevas SVG est une image nommée par le titre du pas ; l'explication du panneau est une
  région `aria-live="polite"`.
- Les curseurs ont un nom (`aria-label` = nom du réglage) et le bouton d'aide est relié par
  `aria-describedby`.
- Les graphiques gardent texte et pourcentage en clair ; « écarté (…) » remplace la valeur.
- Contrastes AA dans les deux thèmes (balayage E2E existant) ; `prefers-reduced-motion`
  coupe les transitions.

## Key Flows

### Flux 1 — Pascal montre la boucle en salle (temps fort : le token revient dans l'INPUT)

Pascal, consultant, anime une formation de deux heures devant huit stagiaires ; le PC est
projeté, Qwen3.5-2B chargé dans WaveStack.

1. Il ouvre « LLM », tape « Le chat dort sur le » et clique « Découper en tokens ».
2. INPUT, ▶ ▶ : le texte se découpe en 5 morceaux, puis en 5 numéros : « le modèle ne voit
   que ça ».
3. TRANSFORMATION : il lit le bandeau (Qwen3.5 est hybride), puis avance : la table
   d'embedding, l'attention (« le » regarde surtout « chat »), le MLP qui s'élargit ; la pile
   montre 24 couches, une sur quatre en attention complète.
4. OUTPUT : « 🎲 Tirer le token suivant » ; le moteur tire « ␣canapé », les Logits montrent
   ␣canapé 38 %, ␣lit 22 %…
5. Il monte la température à 1,5 : les chances s'égalisent, ␣lit passe de 26 à 31 % ; il
   baisse top-p à 0,6 : ␣tapis et ␣toit sont « écarté (top-p) ».
6. Il retire au sort trois fois : ␣canapé, ␣lit, ␣canapé.
7. **Temps fort** : « ↺ Ajouter à la suite » ; la page remonte, ␣canapé apparaît en pointillés
   au bout de l'INPUT. « Voilà toute la génération : on recommence, avec un token de plus. »

### Flux 2 — Inès prépare sa session sur un modèle servi

1. Avec llama-server, l'INPUT s'ouvre sur l'exemple étiqueté, puis « Découper en tokens »
   donne les tokens exacts ; la TRANSFORMATION porte la note « Architecture non lue ».
2. L'OUTPUT montre l'exemple étiqueté : ses curseurs font bouger les barres, ce qui suffit à
   expliquer le tirage ; il dit que les vrais candidats ne sont lus qu'avec un modèle chargé
   dans WaveStack ; « Tirer » tire dans l'exemple, puce marquée « exemple » (correction F
   du 2026-10-05).
3. **Temps fort** : elle charge le GGUF dans WaveStack avant la session ; à l'ouverture de
   `/llm`, l'INPUT et l'OUTPUT montrent alors des valeurs réelles sans clic.

### Flux 3 — Anaël avec un modèle cloud (correction C du 2026-10-05)

1. Gemma chez Google AI Studio : à l'ouverture, l'INPUT montre l'exemple (« Exemple · tokens
   d'illustration ») que ◀ ▶ découpent pas à pas ; « Découper en tokens » ajoute
   l'estimation « ≈ N tokens » du texte tapé, l'exemple restant dit « pas celui de ce modèle ».
2. L'OUTPUT montre Logits et Tirage d'exemple ; température, top-k, top-p, min-p les font
   bouger, même top-k et min-p que le fournisseur ne prend pas (leur raison reste dite).

## Inspiration & Anti-patterns

- **Inspiration** : 3Blue1Brown, « But what is a GPT? » et « Attention in transformers ».
- **Anti-pattern** : présenter des poids d'attention ou des états cachés inventés comme réels.
- **Anti-pattern** : une étape plus haute que l'écran (le formateur perd le fil en défilant).

## Responsive & Platform

Deux cibles mesurées (1600 × 1000, 1366 × 768) ; sous 900 px, une colonne par étape. Mode
projection : la rampe agrandie de l'appli, la contrainte « une étape tient à l'écran »
restant à vérifier à 1366 × 768 projeté.

## Open Questions

- [ASSUMPTION] Modèle servi (llama-server) : architecture non lue, faute d'accès au chemin
  du GGUF hors de `models/servers.py` (lot 3). À reprendre après la fusion du lot 3.
- [ASSUMPTION] Ajouts de l'OUTPUT plafonnés à 64 tokens (lisibilité de l'INPUT, durée d'un pas).
