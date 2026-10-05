# Rapport de validation — WaveStack, Atelier MCP (lot 4)

- **DESIGN.md :** `DESIGN.md`
- **EXPERIENCE.md :** `EXPERIENCE.md`
- **Date :** 2026-10-05

## Verdict global

Les ajouts du lot 4 (« Atelier MCP en séquence ») sont un contrat adéquat après correctifs. La rubrique les jugeait adéquats avec deux points hauts : l'ordre des colonnes, qui démentait le temps fort « le modèle ne parle jamais au serveur », et le contrat d'événements des nouveautés, qui n'était pas engagé. Le premier est corrigé par décision d'Anaël (SLM à gauche de l'hôte). Le second est écrit en « Données attendues par la page » et renvoyé à bmad-architecture comme question bloquante avant le build.

La revue d'accessibilité déplace le centre de gravité : neuf points hauts, tous corrigés dans les spines. Ils portent sur la flèche courante, les noms et annonces, le focus, le mode projection désormais étendu à /mcp, les tailles et les cibles. Plusieurs retouches touchent le module commun du lot 2 : elles valent aussi pour l'Atelier Harnais et sont listées comme telles. La revue structure et prose a surtout harmonisé les termes (qui choisit, temps fort, origines des flèches) et rendu les références explicites.

## Verdicts par catégorie

- 1. Couverture des parcours — adéquat
- 2. Complétude des jetons — fort
- 3. Couverture des composants — adéquat
- 4. Couverture des états — adéquat
- 5. Couverture des références visuelles — fort
- 6. Surcharge et sur-spécification — adéquat
- 7. Discipline d'héritage — adéquat
- 8. Adéquation de forme — adéquat

## Constats par gravité

### Critiques (0)

### Hauts (11)

**1. Couverture des parcours** — Ordre des colonnes contraire au temps fort (§ EXPERIENCE, Volet Séquence)
Suite : Corrigé : Utilisateur · SLM · Hôte · Client · Serveur · Source (décision d'Anaël du 2026-10-05) ; maquette alignée.

**7. Discipline d'héritage** — Contrat d'événements non engagé (§ EXPERIENCE, Données attendues par la page)
Suite : Reporté à bmad-architecture : faits attendus listés, question ouverte bloquante avant le build.

**Accessibilité** — A11Y-01 Flèche courante invisible en clair
Suite : Corrigé : repère ▶, anneau d'encre sous le halo (retouche lot 2), aria-current, annonce nommée.

**Accessibilité** — A11Y-02 Nom des flèches incomplet
Suite : Corrigé : gabarit ordonné dans ui.yaml, fragments masqués plutôt qu'aria-label.

**Accessibilité** — A11Y-03 Aucune annonce
Suite : Corrigé : région status par page, alert pour les échecs.

**Accessibilité** — A11Y-04 Focus perdu, défilement imposé
Suite : Corrigé : ajout incrémental, phase focalisée jamais repliée, défilement suspendu et puce « ↓ n nouveaux messages ».

**Accessibilité** — A11Y-05 « Pourquoi… ? » hors clavier
Suite : Corrigé : bouton distinct dans un titre de niveau 3.

**Accessibilité** — A11Y-06 Pas de mode projection sur /mcp
Suite : Corrigé : mode projection étendu à /mcp (décision d'Anaël), mise en page sur la rampe.

**Accessibilité** — A11Y-07 Textes sous 12 px
Suite : Corrigé : aucun texte sous label.

**Accessibilité** — A11Y-08 Cibles sous 32 px
Suite : Corrigé : hit-target-min pour toute commande.

**Accessibilité** — A11Y-09 Architecture seulement visuelle
Suite : Corrigé : groupes nommés, nom accessible des serveurs et clients.

### Moyens (19)

**1. Couverture des parcours** — Flow MCP-2 : « après 10 s » et ConnectError incohérents avec le code (§ EXPERIENCE, Flow MCP-2)
Suite : Corrigé : refus immédiat ; délai dépassé décrit à part avec le délai de wavestack.toml.

**1. Couverture des parcours** — Persistance du ✖ non écrite (§ EXPERIENCE, Volet Architecture)
Suite : Corrigé : dernier échec par serveur gardé par la page jusqu'à une nouvelle tentative [ASSUMPTION].

**1. Couverture des parcours** — Aides longues : pas de table clé → emplacement (§ EXPERIENCE, Textes et aides)
Suite : Corrigé : table ajoutée ; écart au plan sur methods.* justifié.

**3. Couverture des composants** — Composants mcp-* absents d'EXPERIENCE (§ EXPERIENCE, section lot 4)
Suite : Corrigé : identifiants cités à leur comportement.

**4. Couverture des états** — « Arrêter » contredit la story 6 (§ EXPERIENCE, Volet Serveurs et commandes)
Suite : Corrigé : actif en mcp_lab seulement.

**4. Couverture des états** — État « arrêté » absent (§ EXPERIENCE, États)
Suite : Corrigé ; en mode « par le modèle », la génération seule s'arrête [ASSUMPTION].

**4. Couverture des états** — Lazy loading contre « second appel d'outil » (§ EXPERIENCE, États)
Suite : Corrigé : load_tool_doc ne compte pas.

**7. Discipline d'héritage** — Effet sur le cache de l'Atelier Harnais (§ EXPERIENCE, États)
Suite : Corrigé : cause « Atelier MCP » de « Préfixe non réutilisé ».

**7. Discipline d'héritage** — Dérive harnais / hôte / client MCP (§ EXPERIENCE, Voix et Données attendues)
Suite : Corrigé : clés ui.yaml et mcp_lab.yaml à reformuler listées.

**8. Adéquation de forme** — Halo vert sur le serveur connecté au repos (§ DESIGN, Serveurs et commandes)
Suite : Corrigé : bordure primary ; halo seulement quand la flèche courante le touche.

**8. Adéquation de forme** — Antenne verte hors du direct (§ EXPERIENCE, Volet Architecture)
Suite : Corrigé : en direct seulement, pendant une génération.

**8. Adéquation de forme** — Fond d'encre sur ce que le modèle lit (§ DESIGN, mcp-model-chip)
Suite : Corrigé : contour d'encre pour ce qu'il lit, fond d'encre pour ce qu'il produit.

**8. Adéquation de forme** — Analogie du restaurant dans le désordre (§ EXPERIENCE, Phases)
Suite : Corrigé : capacités, initialized, puis la carte.

**Accessibilité** — A11Y-10 à A11Y-21 (contraste des estompés, tablist, radiogroup, stepper, lignes de vie, traits, mouvement, bulles, structure de liste, tabindex itinérant, aria-disabled, ellipses)
Suite : Corrigés dans EXPERIENCE (Accessibilité, Langues) et DESIGN (mcp-arch-client sans opacité, mcp-lifeline en muted, motifs de tirets distincts).

**Structure et prose** — Deux puces mcp-screen contradictoires
Suite : Corrigé : ancienne puce marquée « remplacée au lot 4 ».

**Structure et prose** — Badges contraires à la Voix
Suite : Corrigé : « choisi par le modèle / choisie par l'application / choisi par l'utilisateur » partout.

**Structure et prose** — « Ce que le build doit ajouter » hors sujet
Suite : Partiel : devenu « Données attendues par la page », contrat de données gardé dans la spine, tests retirés.

**Structure et prose** — Références introuvables (plan, vues, D2, D5)
Suite : Corrigé : lien vers le plan, vues nommées.

**Structure et prose** — 12 étapes noyées dans une phrase
Suite : Corrigé : liste numérotée.

### Bas (3)

**Accessibilité** — A11Y-22 à A11Y-26 (fieldset, aria-expanded, lang=en, émojis, noms des boutons de volet)
Suite : Corrigés dans EXPERIENCE.

**Structure et prose** — Climax, « aujourd'hui », « spines », « en retrait », « client » ambigu, « supposée », « puce blanche »
Suite : Corrigés.

**Structure et prose** — Promouvoir chaque mcp-* en puce de premier niveau
Suite : Non retenu : regroupement par volet gardé, identifiants listés en tête de puce.

## Fichiers des relectures
- `review-rubric.md`
- `review-accessibilite.md`
- `review-structure-prose.md`
