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

# 2. Embedding et reranking : télécharge les candidats (≈ 2,0 Go en tout), puis mesure hors ligne
uv run --with huggingface-hub --with fastembed python tools/bench/story12_bench.py embed --download
```

Options utiles :

- `--json` : sortie complète en JSON, à joindre à la story 12 ;
- `embed --models-dir D:\modeles` : dossier des modèles (par défaut `~/.cache/wavestack-bench`) ;
- `embed --only granite107m_q8 bgererank_m3_q4km` : ne mesurer que certains candidats (un identifiant inconnu ou retiré est signalé, et le banc s'arrête) ;
- `headroom --no-strace` : ne pas lancer `strace` (Linux).

Le téléchargement passe par le proxy du poste et par le magasin de certificats du système, comme WaveStack. Si le proxy refuse `huggingface.co`, copiez les fichiers GGUF à la main dans `<models-dir>/<propriétaire>__<dépôt>/<fichier>` (le chemin exact est affiché pour chaque candidat), puis relancez sans `--download`.

## Lire le résultat

Chaque mesure tourne dans un processus enfant neuf, pour un RSS propre. Ce processus installe la garde réseau du projet avant tout import tiers, retire les variables de proxy et consigne chaque tentative réseau.

**RSS ajouté**, pour tout le banc (Headroom, embedding, reranking) : le pic de RSS du processus après la mesure, moins la base lue juste avant (la plus grande de la RSS et du pic déjà atteint à ce moment : le pic ne redescend jamais). Le pic est `VmHWM` sous Linux, `peak_wset` sous Windows. Avant le lot F, le banc lisait la RSS après la libération du modèle : 3 à 6 Mo affichés sur le PC cible, pour +428 Mo réels (granite) et +736 Mo (reranker). Le rapport JSON porte `"rss_added_method": "pic"` ; un rapport sans ce champ vient de l'ancienne mesure.

**Headroom.** Deux variantes sont comparées :

- **naïve** : aucune variable, compression ML laissée par défaut ;
- **configurée** : les variables qu'utilisera WaveStack (`LITELLM_LOCAL_MODEL_COST_MAP`, `TIKTOKEN_CACHE_DIR` vers le cache fourni par litellm, `HEADROOM_OFFLINE`, `HEADROOM_BEACON=off`, `HEADROOM_UPDATE_CHECK=off`, `DO_NOT_TRACK`) et `kompress_model="disabled"`.

Dans les deux variantes, Headroom compte ses tokens avec le même modèle que WaveStack, `gpt-4` (`COUNTING_MODEL`, table tiktoken `cl100k_base`, présente dans toutes les copies de litellm). Avec `gpt-4o`, il lui fallait `o200k_base`, absente du cache de litellm sur le PC cible : tiktoken tentait de la télécharger depuis `openaipublic.blob.core.windows.net`, et le verdict était « ÉCARTÉ » (lot F, 2026-09-27).

Le verdict « RETENU » exige cinq critères : aucune tentative réseau, pas de torch, RSS ajouté ≤ 300 Mo, licences compatibles, fonctionnement sans aucun réseau.

**Embedding et reranking.** Le mini jeu compte 10 documents et 10 questions en français, reformulées pour éviter les mots communs. Pour chaque candidat, le banc affiche recall@1, MRR, le temps par élément, le temps de chargement, le RSS ajouté et les accès réseau.

Le verdict retient :

- **pour l'embedding**, le plus petit GGUF avec recall@1 ≥ 0,75 et un RSS ajouté ≤ 600 Mo ;
- **pour le reranker**, un modèle qui garde ou améliore le MRR de cet embedding, avec un RSS ajouté ≤ 800 Mo.

Sinon, le banc se replie sur fastembed. Sans modèle sur le disque, le verdict reste « provisoire, mesure sur PC cible à faire ».

Ces seuils ont été fixés quand la mesure du RSS était fausse. Avec les pics relevés sur le PC cible, bge-m3 (+731 Mo) et Qwen3-Embedding (+900 Mo) dépassent les 600 Mo de l'embedding, et le reranker bge-v2-m3 (+736 Mo) passe de peu sous les 800 Mo : les verdicts d'un nouveau passage sur le PC cible peuvent changer. Granite (+428 Mo) reste retenu.

**Candidat retiré.** `e5small_q8` (`cstr/multilingual-e5-small-GGUF`, conversion faite pour CrispEmbed) ne se charge pas avec llama-cpp-python 0.3.35 (« Failed to load model », PC cible, 2026-09-27) : il ne fait plus partie des candidats et figure parmi les écartés d'office.

## Banc de la story 6 de la V2 : modèles de décision

`v2s6_decision_bench.py` mesure chaque candidat de `decision-model-candidates.md` (spec V2) à côté du SLM par défaut chargé : RAM, latence d'une décision, réseau, paquets ajoutés et licences, torch, révision épinglée. Il réutilise les aides de `story12_bench.py` (garde réseau, RSS au pic, licences) et n'ajoute, lui non plus, aucune dépendance au projet.

```bash
uv run python tools/bench/v2s6_decision_bench.py list   # candidats, commande de chacun, verdicts d'office
```

Certains candidats sont servis hors de l'enfant de mesure, sur `/v1/systemone` : `tev1` par Ollama (story 8), `julia1` et `laya` par un llama-server portable (story 9). Le banc ne télécharge jamais ce binaire : décompresser une fois `llama-b11378-bin-win-cpu-x64.zip` (release `b11378` de ggml-org/llama.cpp) dans `%LOCALAPPDATA%\WaveStack\bench\llama-b11378\`, ou passer `--llama-server <chemin>` (ou `WAVESTACK_LLAMA_SERVER`). Le banc lance le serveur sur 127.0.0.1, le GGUF par chemin local, et l'arrête à la fin quoi qu'il arrive.

Les commandes exactes du relevé, le sens des critères et le tableau à remplir sont dans `_bmad-output/implementation-artifacts/rapport-test-prealable-modeles-de-decision.md`. L'option `--out` écrit le résultat en JSON UTF-8 : sous PowerShell 5.1, une redirection `>` l'écrirait en UTF-16.

## Limites

- Les connexions ouvertes par du code natif échappent à la garde Python (plafond d'AD-15). Sous Linux, `strace` et `unshare -rn` les rendent visibles. Sous Windows, le banc ne voit que la garde Python.
- Une mesure faite ailleurs que sur le PC cible (HP EliteBook i5, 16 Go, Windows 11) reste indicative.
- Le mini jeu vérifie que le modèle comprend le français, pas qu'il est meilleur qu'un autre en général.
