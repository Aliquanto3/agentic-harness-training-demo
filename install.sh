#!/usr/bin/env bash
# Installe uv, WaveStack et le modele Qwen par defaut sans droits administrateur, puis
# lance l'application. Idempotent : relancer ce script ne retelecharge ni le projet ni
# le modele s'ils sont deja presents.
#
# Surcharges (dossiers d'installation, utiles aussi pour les tests) :
#   WAVESTACK_INSTALL_DIR, WAVESTACK_DATA_DIR, WAVESTACK_UV_INSTALL_DIR,
#   WAVESTACK_NO_LAUNCH=1 (n'ouvre pas l'application), WAVESTACK_DRY_RUN=1 (mode a blanc).
set -euo pipefail

# Memes valeurs que README.md (une seule source de verite : voir tests/test_installers.py)
QWEN_URL="https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf"
QWEN_FILE="Qwen3.5-2B-Q4_K_M.gguf"
REPO_URL="https://github.com/Aliquanto3/agentic-harness-training-demo.git"

INSTALL_DIR="${WAVESTACK_INSTALL_DIR:-}"
DATA_DIR="${WAVESTACK_DATA_DIR:-}"
UV_INSTALL_DIR_OVERRIDE="${WAVESTACK_UV_INSTALL_DIR:-}"
NO_LAUNCH="${WAVESTACK_NO_LAUNCH:-}"
DRY_RUN="${WAVESTACK_DRY_RUN:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# -- Dossier du projet : sur place si on est deja dans un clone ou un zip, sinon un
#    dossier visible sous Documents.
if [ -z "$INSTALL_DIR" ]; then
    if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
        INSTALL_DIR="$SCRIPT_DIR"
    else
        INSTALL_DIR="$HOME/Documents/WaveStack"
    fi
fi

# -- Dossier de donnees : venv, caches et modeles, jamais sous Documents.
if [ -z "$DATA_DIR" ]; then
    DATA_DIR="$HOME/.local/share/wavestack"
fi
VENV_DIR="$DATA_DIR/venv"
CACHE_DIR="$DATA_DIR/uv-cache"
MODELS_DIR="$DATA_DIR/models"
MODEL_PATH="$MODELS_DIR/$QWEN_FILE"

echo "Projet      : $INSTALL_DIR"
echo "Donnees     : $DATA_DIR"
echo "Modele Qwen : $MODEL_PATH"

if [ -n "$DRY_RUN" ]; then
    echo "(mode a blanc : aucune commande reseau ou d'installation executee)"
    exit 0
fi

# -- uv, dans le profil utilisateur, sans droits administrateur.
if ! command -v uv >/dev/null 2>&1; then
    echo "Installation de uv..."
    if [ -n "$UV_INSTALL_DIR_OVERRIDE" ]; then
        export UV_INSTALL_DIR="$UV_INSTALL_DIR_OVERRIDE"
    fi
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${UV_INSTALL_DIR_OVERRIDE:-$HOME/.local/bin}:$PATH"
fi

# -- Projet : clone si absent ; inchange s'il est deja la (idempotent).
if [ ! -f "$INSTALL_DIR/pyproject.toml" ]; then
    echo "Recuperation de WaveStack dans $INSTALL_DIR..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "WaveStack deja present dans $INSTALL_DIR, pas de nouveau clone."
fi

# -- Modele Qwen : telecharge si absent (idempotent).
mkdir -p "$MODELS_DIR"
if [ ! -f "$MODEL_PATH" ]; then
    echo "Telechargement du modele Qwen (1,3 Go)..."
    curl -fL -o "$MODEL_PATH" "$QWEN_URL"
else
    echo "Modele Qwen deja present, pas de nouveau telechargement."
fi

# -- Venv et caches sous le dossier de donnees, jamais sous Documents.
export UV_PROJECT_ENVIRONMENT="$VENV_DIR"
export UV_CACHE_DIR="$CACHE_DIR"

if [ -z "$NO_LAUNCH" ]; then
    echo "Lancement de WaveStack..."
    (cd "$INSTALL_DIR" && uv run wavestack)
fi

echo
echo "Pour relancer WaveStack plus tard : reexecutez install.sh dans ce dossier."
