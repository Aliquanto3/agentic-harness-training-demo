# Banc de la story 12 : Headroom, embedding et reranking

Ce script mesure, sur le poste où on le lance, ce qu'il faut savoir avant les stories 15 (RAG), 16 (reranking) et 20 (compression) :

- **Headroom** (`headroom-ai` 0.38.0) : fonctionne-t-il hors ligne sous la garde réseau, sans torch, dans le budget mémoire, avec des licences compatibles ?
- **Embedding et reranking** : quel modèle GGUF, chargé par llama-cpp-python (repli fastembed), sert le français, en combien de mémoire et de temps ?

Il n'ajoute **aucune dépendance au projet** : les paquets de mesure arrivent par `uv run --with`, dans un environnement éphémère. `pyproject.toml` et `uv.lock` ne changent pas.

## Lancer le banc

Depuis la racine du dépôt :

```bash
# 1. Headroom : aucun réseau nécessaire
uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom

# 2. Embedding et reranking : télécharge les candidats (≈ 2,1 Go en tout), puis mesure hors ligne
uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download
```

Options utiles :

- `--json` : sortie complète en JSON, à joindre à la story 12 ;
- `embed --models-dir D:\modeles` : dossier des modèles (par défaut `~/.cache/wavestack-bench`) ;
- `embed --only granite107m_q8 bgererank_m3_q4km` : ne mesurer que certains candidats ;
- `headroom --no-strace` : ne pas lancer `strace` (Linux).

Le téléchargement passe par le proxy du poste et par le magasin de certificats du système, comme WaveStack. Si le proxy refuse `huggingface.co`, copiez les fichiers GGUF à la main dans `<models-dir>/<propriétaire>__<dépôt>/<fichier>` (le chemin exact est affiché pour chaque candidat), puis relancez sans `--download`.

## Lire le résultat

Chaque mesure tourne dans un processus enfant neuf, pour un RSS propre. Ce processus installe la garde réseau du projet avant tout import tiers, retire les variables de proxy et consigne chaque tentative réseau.

**Headroom.** Deux variantes sont comparées :

- **naïve** : aucune variable, compression ML laissée par défaut ;
- **configurée** : les variables qu'utilisera WaveStack (`LITELLM_LOCAL_MODEL_COST_MAP`, `TIKTOKEN_CACHE_DIR` vers le cache fourni par litellm, `HEADROOM_OFFLINE`, `HEADROOM_BEACON=off`, `HEADROOM_UPDATE_CHECK=off`, `DO_NOT_TRACK`) et `kompress_model="disabled"`.

Le verdict « RETENU » exige cinq critères : aucune tentative réseau, pas de torch, RSS ajouté ≤ 300 Mo, licences compatibles, fonctionnement sans aucun réseau.

**Embedding et reranking.** Le mini jeu compte 10 documents et 10 questions en français, reformulées pour éviter les mots communs. Pour chaque candidat, le banc affiche recall@1, MRR, le temps par élément, le temps de chargement, le RSS ajouté et les accès réseau.

Le verdict retient :

- **pour l'embedding**, le plus petit GGUF avec recall@1 ≥ 0,75 et un RSS ajouté ≤ 600 Mo ;
- **pour le reranker**, un modèle qui garde ou améliore le MRR de cet embedding, avec un RSS ajouté ≤ 800 Mo.

Sinon, le banc se replie sur fastembed. Sans modèle sur le disque, le verdict reste « provisoire, mesure sur PC cible à faire ».

## Limites

- Les connexions ouvertes par du code natif échappent à la garde Python (plafond d'AD-15). Sous Linux, `strace` et `unshare -rn` les rendent visibles. Sous Windows, le banc ne voit que la garde Python.
- Une mesure faite ailleurs que sur le PC cible (HP EliteBook i5, 16 Go, Windows 11) reste indicative.
- Le mini jeu vérifie que le modèle comprend le français, pas qu'il est meilleur qu'un autre en général.
