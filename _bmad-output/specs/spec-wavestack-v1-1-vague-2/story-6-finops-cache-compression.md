---
id: SPEC-wavestack-v1-1-vague-2-story-6
status: review
companions:
  - SPEC.md
  - finops.md
  - brownfield.md
  - ux/DESIGN.md
  - ux/EXPERIENCE.md
---

# Story 6 : FinOps visible, économie du cache cloud et gain de la compression (partie 1 de CAP-7)

## Ce qui est livré

- **Cache de prompt (cloud)** : `models/cloud_base.py` ajoute `cache_savings()`, appelé dans `run_call`. `model_call_ended` porte désormais, seulement quand l'appel a lu ou écrit du cache (`cache_read_tokens`/`cache_write_tokens` > 0) :
  - `cache_read_tokens`, `cache_write_tokens` ;
  - `cache_full_usd` : le prix plein de l'entrée, sans aucun cache ;
  - `cache_write_usd` : l'écriture de cet appel, à son propre prix — une ligne distincte, jamais une économie ;
  - `cache_saved_usd` : l'économie nette (prix plein − payé), jamais négative.
  - Absent (toutes les clés) quand l'appel n'a ni lu ni écrit de cache, comme le demande EXPERIENCE.md (« Lignes FinOps »).
- **Gain de la compression (Headroom)** : `session/app_session.py` (`_transform_context`) ajoute `saved_usd` à `compression_ended` : les tokens économisés × le prix d'entrée du modèle cloud actif ; `None` sur un modèle local ou sans prix déclaré (zéro dollar, tokens affichés quand même — finops.md).
- **Interface** (`web/static/app.js`, zone du compteur d'appel) :
  - une ligne « Cache de prompt : *n* tokens relus · *x* $ économisés » dans le compteur de l'appel (`callBody`), repliée sur place (`<details>`/`<summary>`, le motif déjà utilisé par `compressionBody`) avec son calcul (prix plein, payé, écriture, source `usage.prompt_tokens_details.cached_tokens`) ;
  - le gain de la compression, déjà affiché en tokens dans sa propre étape d'orchestration (`compressionFigure`), porte maintenant le montant économisé en dollars quand il existe.
  - les deux montants restent marqués « ≈ » quand leur usage est estimé (jamais de chiffre tiers non vérifié affiché).
- Schémas de traçabilité (`trace/catalog.py`) : `ModelCallEndedPayload` et `CompressionEndedPayload` déclarent les nouveaux champs.
- i18n : clés `main.orch.cache.*` et `main.orch.compression.saved_usd` ajoutées en fr, en, de.

## Décisions

- Les montants sont déjà agrégeables par tour et par séance : `cache_saved_usd` et `saved_usd` sont des champs numériques simples dans des événements que la story 9 (bilan de séance) pourra sommer sans changement supplémentaire côté backend.
- La compression garde sa propre ligne d'orchestration existante (icône 🗜️, `compressionBody`) plutôt que d'être dupliquée dans le compteur de l'appel : c'est la ligne qui porte déjà le détail par candidat (CAP-8), seul le montant en dollars manquait.
- L'écriture en cache de cet appel est montrée séparément du gain (jamais confondue avec une économie), mais sans historique inter-tours (« 0 token sur ce tour (…au tour précédent) » de la maquette) : une fonctionnalité en plus de ce que CAP-7 (partie 1) demande, laissée de côté.

## Hors périmètre (reste à faire)

- CAP-7 partie 2 : ligne « Sous-agent » dédiée (actuellement sommé dans le total sans ligne à part, `app_session.py:1031-1036` selon brownfield.md) et ligne « KV-cache local » (`timings.cache_n`, ignoré aujourd'hui, `models/servers.py:520-522`).
- Le bilan de séance (barres sans optimisation / coût réel, « économisé » de la barre commune) : story 9.
- La colorisation DESIGN.md des lignes FinOps (`{colors.accent-soft}` etc.) : aucun jeton de couleur n'est encore câblé dans `app.css` pour `token-counter`/`disclosure-row` ; laissé par cohérence avec l'existant.

## Tests

- `tests/test_cloud_cap.py` : `cache_savings()` (absence sans cache, calcul du prix plein / de l'écriture / de l'économie nette, économie jamais négative) et un test de bout en bout qui vérifie les nouveaux champs de `model_call_ended`.
- `tests/test_compression.py` : `saved_usd` absent sur un modèle local, présent et correct sur un modèle cloud avec prix déclaré.

## E2E à rejouer

Aucun scénario E2E ajouté ou modifié par cette story (changement backend + zone JS déjà couverte par les tests Python de bout en bout). À vérifier à l'oeil au prochain passage E2E de l'atelier LLM cloud : la ligne « Cache de prompt » se déplie dans Orchestration sur un appel avec cache.
