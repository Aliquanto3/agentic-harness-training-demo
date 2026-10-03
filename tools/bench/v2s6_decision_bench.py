"""V2 story 6 benchmark: the prior test of the decision models (CAP-6), extended by story 7
(mDeBERTa, multilingual MiniLM, Decision 2.0 Kai; memory watchdog in the child) and story 8
(tev1 0.8B served by Ollama 0.35 on `/v1/systemone`: the RAM counts the child and the Ollama
processes, the offline criterion is checked on the server side too) and story 9 (Julia-1 and
Laya, decision encoders served on the same endpoint by a portable llama-server b11378 that
the bench starts on the loopback and stops in any case; the binary is never downloaded by the
bench, the GGUF once with `--download`, pinned to a commit and a sha256).

Measures each candidate of `decision-model-candidates.md` (spec-wavestack-v2) on the six
criteria of the prior test, next to the default SLM, on twenty fixed prompts drawn from the
V1 scenarios. Never adds a dependency to the project: measurement packages come from
`uv run --with ...`. Run from the repository root (exact commands in the report
`_bmad-output/implementation-artifacts/rapport-test-prealable-modeles-de-decision.md`):

    uv run python tools/bench/v2s6_decision_bench.py list
    uv run --with onnxruntime --with tokenizers --with huggingface-hub \\
        python tools/bench/v2s6_decision_bench.py \\
        measure deberta_xsmall --download --slm <GGUF du SLM par défaut>

Like `story12_bench.py`, whose helpers it reuses: every measurement runs in a fresh child
process that installs the project network guard (AD-15) before any third-party import, with
the proxy variables removed, and records every resolution and connection attempt. Only the
standard library is imported at module level, so `tests/test_v2s6_decision_bench.py` can
test the pure logic.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


def _load_story12():
    """The story 12 bench, loaded under a private name: its helpers are reused, not copied."""
    path = Path(__file__).resolve().with_name("story12_bench.py")
    name = "_v2s6_story12_helpers"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(module)
    return module


s12 = _load_story12()

SCRIPT = "tools/bench/v2s6_decision_bench.py"

# Criteria thresholds (Design Notes of the story; to validate on the target PC's survey).
RAM_BUDGET_MB = 4096  # NFR-2: the peak of the whole process, default SLM included
LATENCY_MEDIAN_MAX_MS = 1000
LATENCY_MAX_MS = 3000
NVIDIA_COMPLEXITY_THRESHOLD = 0.3  # indicative cost decision of the level-1 classifier
SLM_N_CTX = 4096
JUDGE_MAX_TOKENS = 8
CHILD_TIMEOUT_S = 1800

# --------------------------------------------------------------------------
# The two decision tasks, with their written criteria, and the twenty prompts.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    short: str  # label for the classifiers that take short labels (GLiFormer)
    text: str  # the written rule: NLI hypothesis, SLM judge prompt


TASKS: dict[str, dict[str, Criterion]] = {
    "cost": {
        "simple": Criterion(
            "demande simple",
            "Une réponse courte suffit : un fait, une définition, un calcul ou une seule action.",
        ),
        "complexe": Criterion(
            "demande complexe",
            "La demande exige plusieurs étapes : lire ou chercher, puis analyser, comparer "
            "ou rédiger.",
        ),
    },
    "specialty": {
        "securite": Criterion(
            "cybersécurité",
            "La demande porte sur la cybersécurité : identités, accès, authentification, "
            "incidents ou alertes.",
        ),
        "documents": Criterion(
            "documents internes",
            "La demande porte sur un document interne de l'entreprise ou sur un fichier "
            "fourni : politique, procédure, journal ou note.",
        ),
        "recherche": Criterion(
            "recherche en ligne",
            "La demande exige de chercher une information à l'extérieur : site web, catalogue "
            "de données public ou documentation en ligne.",
        ),
        "general": Criterion(
            "culture générale",
            "La demande relève de la culture générale, du calcul ou de la conversation, sans "
            "document ni recherche.",
        ),
    },
}


@dataclass(frozen=True)
class Prompt:
    scenario: str  # source: `scenarios.<id>.prompts` of content/scenarios.yaml
    index: int
    text: str
    cost: str  # expected label, written by the agent: indicative, never a criterion
    specialty: str

    @property
    def id(self) -> str:
        return f"{self.scenario}.{self.index}"

    def expected(self, task: str) -> str:
        return getattr(self, task)


PROMPTS: list[Prompt] = [
    Prompt("bare_llm", 0, "Quelle heure est-il ?", "simple", "general"),
    Prompt(
        "reasoning",
        0,
        "Un train part de Paris à 14 h 47 et roule 2 h 38. Il a ensuite 25 minutes de retard. "
        "À quelle heure arrive-t-il ?",
        "complexe",
        "general",
    ),
    Prompt("system_prompt", 0, "Présente-toi en quelques phrases.", "simple", "general"),
    Prompt(
        "global_memory",
        1,
        "Rappelle-moi mon prénom, puis donne-moi des conseils pour préparer une formation.",
        "complexe",
        "general",
    ),
    Prompt("native_tools", 1, "Combien font 1234 multiplié par 5678 ?", "simple", "general"),
    Prompt(
        "caveman",
        0,
        "Explique en quelques phrases ce qu'est un harnais d'agent.",
        "simple",
        "general",
    ),
    Prompt(
        "native_tools",
        2,
        "Lis le fichier recette_crepes.txt et donne-moi la liste des ingrédients.",
        "simple",
        "documents",
    ),
    Prompt(
        "rag",
        1,
        "Quel plafond de remboursement s'applique à une nuit d'hôtel à Paris chez Exemplia ?",
        "simple",
        "documents",
    ),
    Prompt(
        "hooks",
        0,
        "Lis le fichier confidentiel/budget_projet.txt et résume-le.",
        "complexe",
        "documents",
    ),
    Prompt(
        "compression",
        0,
        "Appelle l'outil read_file sur journal_serveur.log, puis dis-moi quelle erreur grave la "
        "sauvegarde de cette nuit a rencontrée.",
        "complexe",
        "documents",
    ),
    Prompt(
        "compression",
        1,
        "Dans le journal_serveur.log, à quelle heure le lot 12 a-t-il été copié ?",
        "simple",
        "documents",
    ),
    Prompt(
        "network_tools",
        0,
        "Quels sont les jours fériés en France cette année ?",
        "simple",
        "recherche",
    ),
    Prompt(
        "network_tools",
        1,
        "Résume l'article Wikipédia sur le Mont-Saint-Michel.",
        "complexe",
        "recherche",
    ),
    Prompt(
        "mcp_lazy",
        1,
        "Cherche sur data.gouv.fr les jeux de données publics sur la qualité de l'air.",
        "simple",
        "recherche",
    ),
    Prompt(
        "sovereignty",
        0,
        "Cherche sur data.gouv.fr des jeux de données publics sur la cybersécurité en France, "
        "avec l'outil datagouv__search_datasets, sans répondre de tête. Réponds en 5 lignes au "
        "plus : trois jeux au plus, chacun avec son lien data.gouv.fr en premier.",
        "complexe",
        "recherche",
    ),
    Prompt(
        "rag",
        0,
        "Combien de caractères doit compter au minimum un mot de passe chez Exemplia ?",
        "simple",
        "securite",
    ),
    Prompt(
        "soc",
        0,
        "Lis le fichier alertes_siem.log (nom exact, à recopier tel quel), regroupe les alertes "
        "qui relèvent d'un même incident et reconstitue sa chronologie en 8 lignes au plus, avec "
        "pour chaque étape la tactique MITRE ATT&CK probable.",
        "complexe",
        "securite",
    ),
    Prompt(
        "soc",
        1,
        "Pour qualifier cet incident, vérifie le rôle et le titulaire du compte adm.leroy en "
        "t'aidant des fichiers disponibles. Si une lecture t'est refusée, ne la contourne pas : "
        "dis-le et propose de transmettre la vérification à un analyste SOC habilité, en 3 "
        "lignes au plus.",
        "complexe",
        "securite",
    ),
    Prompt(
        "iam",
        0,
        "Dans Microsoft Entra ID, comment exiger l'authentification multifacteur pour tous les "
        "administrateurs ? Cherche avec l'outil mslearn__microsoft_docs_search, puis réponds en "
        "5 lignes au plus : d'abord deux liens Microsoft Learn tirés du résultat, puis "
        "l'explication.",
        "complexe",
        "securite",
    ),
    Prompt(
        "iam",
        1,
        "Qu'est-ce que Privileged Identity Management dans Entra ID, et à quoi sert "
        "l'activation juste-à-temps d'un rôle ? Cherche avec l'outil "
        "mslearn__microsoft_docs_search, puis réponds en 5 lignes au plus : d'abord deux liens "
        "Microsoft Learn tirés du résultat, puis l'explication.",
        "complexe",
        "securite",
    ),
]


def check_prompts() -> list[str]:
    """Problems in the prompt set (empty list when it is consistent)."""
    problems = []
    ids = [p.id for p in PROMPTS]
    if len(set(ids)) != len(ids):
        problems.append("deux prompts ont la même source")
    if len({p.text for p in PROMPTS}) != len(PROMPTS):
        problems.append("deux prompts ont le même texte")
    for p in PROMPTS:
        for task, labels in TASKS.items():
            if p.expected(task) not in labels:
                problems.append(f"{p.id} : étiquette {task} inconnue {p.expected(task)!r}")
    for task, labels in TASKS.items():
        missing = set(labels) - {p.expected(task) for p in PROMPTS}
        if missing:
            problems.append(f"tâche {task} : aucune étiquette attendue {sorted(missing)}")
    return problems


# --------------------------------------------------------------------------
# Candidates. Facts read on the Hugging Face model cards on 2026-10-01, and 2026-10-03 for
# story 7 (HF MCP, no download): licence, files, labels. Each `doc_name` is the start of the
# first cell of its row in `decision-model-candidates.md` (or the row starts with its id).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    id: str
    doc_name: str
    tier: str  # "1", "2", "3", "cyber" or "-"
    backend: str | None  # None: not measured (office verdict, or the `decision10` command)
    repos: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (repo, files) downloaded
    onnx_file: str = ""
    model_license: str = ""
    license_class: str = ""  # "ok" | "unknown" | "forbidden"; empty: classified from the text
    with_packages: tuple[str, ...] = ()  # the `uv run --with` of its command
    modules: tuple[str, ...] = ()  # importable modules the measurement needs
    roots: tuple[str, ...] = ()  # distributions whose closure is the "added packages"
    remote_code: str = "aucun"  # code of the model run by the bench, and its review
    office: str = ""  # verdict without measurement
    office_reason: str = ""
    note: str = ""
    revision: str = ""  # reviewed commit: download and measure pinned to it (empty: `main`)
    full_snapshot: bool = False  # download the whole repository (files: presence witnesses)
    trust_remote_code: bool = False  # runs code shipped by the model repository
    # Story 8: a model served by a local server (Ollama), outside the measurement child.
    server_url: str = ""  # loopback base URL of the server (empty: loaded in the child)
    server_model: str = ""  # the server's model name (Ollama tag, llama-server alias)
    generative: bool = False  # causal model: under the single generative model rule
    # Story 9: which server ("ollama", "llama_server"; empty: loaded in the child). Its value
    # is also the prefix of the server-side fields of the report (`ollama_rss_peak_mb`…).
    server: str = ""
    gguf_sha256: str = ""  # llama-server: sha256 of the GGUF at the pinned `revision`


_NLI_MODULES = ("onnxruntime", "tokenizers", "numpy", "huggingface_hub")
# tokenizers and huggingface-hub only come with the `compression` extra: not the core project.
_NLI_PACKAGES = ("onnxruntime", "tokenizers", "huggingface-hub")
# Decision 2.0 Kai: the commit whose shipped code (`modeling_decision2.py`,
# `pipeline_decision2.py`, `configuration_decision2.py`, `decision2/`) was reviewed (story 7).
DECISION20_REPO = "vllm-sr/Decision-2.0-Kai-0.6B"
DECISION20_REVISION = "881bee413681d80ebeac86afcda8b4138dae516e"
DECISION20_INSTRUCTIONS = "Classe la demande de l'utilisateur selon les critères."
_DECISION20_PACKAGES = ("torch", "transformers", "safetensors", "huggingface-hub")
# Story 8: tev1 0.8B (Together AI) served by Ollama 0.35 on `/v1/systemone`, loopback only.
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
TEV1_MODEL = "tev1:0.8b"
TEV1_LICENSE = (
    "non déclarée pour les poids affinés (carte HF togethercomputer/Tev1-0.8B-experimental, "
    "lue le 2026-10-03 : « The release license for these fine-tuned weights is being "
    "finalized ») ; le paquet Ollama porte Apache-2.0 (base Qwen3.5, Alibaba Cloud) et MIT "
    "(open-jev, scripts d'entraînement)"
)
# The request format read before writing the client, cited in the measure's JSON.
SYSTEMONE_API = {
    "doc": "https://docs.ollama.com/api/systemone",
    "read_on": "2026-10-03",
    "server": "Ollama 0.35 (requis : 0.35.0 ou plus), API Jev de TypeSafe",
    "request": "POST /v1/systemone {model, state, questions: {<id>: {type: choice | noul | "
    "score, instructions, criteria}}, keep_alive?} ; choice : 2 à 26 critères {clé: texte} ; "
    "1 à 64 questions ; 64 Kio sans image",
    "response": "{model, answers: {<id>: {type, choice, probabilities: {clé: p}, confidence}}, "
    "usage} ; erreur : HTTP 400, 404 (modèle non téléchargé, jamais tiré implicitement), "
    '413 ou 500 avec {"error": <texte>}',
    "label": "une question choice par tâche, options = étiquettes du banc ; étiquette "
    "retenue = option de plus forte probabilité",
}
SYSTEMONE_TIMEOUT_S = 120
OLLAMA_PULL_TIMEOUT_S = 1800
OLLAMA_SAMPLE_PERIOD_S = 0.25
# Abort threshold of the Ollama processes (server + model), above NFR-2's budget: the child's
# watchdog only sees the child, and the model process grows with each request (story 8).
# The same threshold applies to llama-server (story 9). It is a safety stop for the shared
# 16 Go PC, never a criterion: the RAM criterion judges child + server against 4 096 Mo. The
# 2 048 Mo margin over the budget lets an over-budget server still finish the measure (its
# latency and agreement recorded), while the stop comes long before the PC swaps.
OLLAMA_ABORT_MB = RAM_BUDGET_MB + 2048

# Story 9: decision encoders served on `/v1/systemone` by a portable llama-server (PR #29818
# of ggml-org/llama.cpp, merged on 2026-10-02 as a4cb4c61…), started and stopped by the bench.
# The binary is downloaded once by hand, never by the bench; the GGUF once with `--download`.
LLAMA_BUILD = "11378"
LLAMA_RELEASE = f"b{LLAMA_BUILD}"
LLAMA_ZIP = f"llama-{LLAMA_RELEASE}-bin-win-cpu-x64.zip"
LLAMA_ZIP_SHA256 = "11bcb3aea659bce73f62305e3812764f935d90f44de1e70cd2b68aa3c9f41b8d"  # GitHub
# `llama-server.exe` of that archive, read on the target PC on 2026-10-03 (unzipped as is): a
# 9 KB launcher; the server's code is in `llama-server-impl.dll`, pinned too. The engine's
# other DLLs (`llama.dll`, `llama-common.dll`, `ggml*.dll`) are not checked.
LLAMA_EXE_SHA256 = "6d2e001e3e366dd64f24578bad2ff461bcfdea4a0c86b134c280a952401eee20"
LLAMA_IMPL_SHA256 = "68f82bb0491f057728f5c4b1f0036b0b4e50113a1fd2bb16eda14fd4a41bd62e"
LLAMA_RELEASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/tag/{LLAMA_RELEASE}"
LLAMA_SERVER_ENV = "WAVESTACK_LLAMA_SERVER"
LLAMA_START_TIMEOUT_S = 120
LLAMA_STOP_TIMEOUT_S = 15
LLAMA_SYSTEMONE_API = {
    "doc": f"https://github.com/ggml-org/llama.cpp/blob/{LLAMA_RELEASE}/tools/server/README.md "
    "(« POST /v1/systemone: TypeSafe-compatible System One API »)",
    "code": f"tools/server/server-decision.cpp et tools/server/tests/unit/test_systemone.py au "
    f"tag {LLAMA_RELEASE} (commit edd6e2bbdad5930899a93db8fa73c3b61c7b9bcc), qui contient la "
    "PR #29818 (fusion a4cb4c61fd9d9c2066c7c1747821d3d65b8943bd)",
    "read_on": "2026-10-03",
    "server": f"llama-server {LLAMA_RELEASE} (CPU, Windows x64), API TypeSafe",
    "request": "POST /v1/systemone {state, questions: {<id>: {type: choice | score | noul, "
    "instructions, criteria}}, images?} ; choice : {option: description ou null}, au plus 255 "
    "options pour le type laya ; pas de flux ; questions répondues indépendamment",
    "response": "{model, answers: {<id>: {type, choice, probabilities: {option: p}, "
    "confidence}}, usage: {input_tokens, output_tokens: 0}} ; erreur : 400 (requête invalide), "
    "501 (modèle qui n'est pas un modèle de décision)",
    "model_type": "Julia-1 et Laya : type laya (journal du serveur « decision model type: "
    "laya ») : tout le prompt d'une question en un lot, qui doit tenir dans --ubatch-size "
    "(512 par défaut)",
    "label": "une question choice par tâche, options = étiquettes du banc ; étiquette "
    "retenue = option de plus forte probabilité (même règle que la story 8)",
}
JULIA1_REPO = "ggml-org/Julia-1-GGUF"
JULIA1_FILE = "Julia-1-Q8_0.gguf"
JULIA1_REVISION = "16fee17949206fbf58da9347daea44d792a81211"
JULIA1_SHA256 = "1ea6a7e87156eeeda88cb7a36a61265b37ba7b993897b7289b99aea5b5e47069"
LAYA_REPO = "ggml-org/Laya-GGUF"
LAYA_FILE = "Laya-Q8_0.gguf"
LAYA_REVISION = "da4b4753d62197659d8c90103cd4c43bef9afea6"
LAYA_SHA256 = "c06528c5746d3bb8baa72a27938be95abbfd0b226f8471e8a9e365ed0bb066d2"
_LLAMA_REMOTE_CODE = (
    f"aucun code du modèle exécuté par le banc ; moteur : llama-server {LLAMA_RELEASE} "
    "(binaire portable hors dépôt, version et sha256 consignés), GGUF servi par chemin local (-m)"
)
SERVER_LABELS = {"ollama": "Ollama", "llama_server": "llama-server"}

CANDIDATES: list[Candidate] = [
    Candidate(
        id="decision10",
        doc_name="Decision 1.0",
        tier="2",
        backend=None,
        model_license="Apache-2.0",
        note="revérification (GGUF, ONNX, chemin CPU) par la commande decision10 ; mesuré "
        "seulement si un chemin CPU apparaît (nouvelle story)",
    ),
    Candidate(
        id="deberta_base",
        doc_name="DeBERTa-v3 zero-shot NLI",
        tier="2",
        backend="nli_onnx",
        repos=(
            (
                "MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
                ("config.json", "tokenizer.json", "onnx/model.onnx"),
            ),
        ),
        onnx_file="onnx/model.onnx",
        model_license="MIT",
        with_packages=_NLI_PACKAGES,
        modules=_NLI_MODULES,
        roots=_NLI_PACKAGES,
        note="ONNX fp32 de 739 Mo ; entraîné en anglais",
    ),
    Candidate(
        id="deberta_xsmall",
        doc_name="DeBERTa-v3 zero-shot NLI",
        tier="2",
        backend="nli_onnx",
        repos=(
            (
                "MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33",
                ("config.json", "tokenizer.json", "onnx/model_quantized.onnx"),
            ),
        ),
        onnx_file="onnx/model_quantized.onnx",
        model_license="MIT",
        with_packages=_NLI_PACKAGES,
        modules=_NLI_MODULES,
        roots=_NLI_PACKAGES,
        note="ONNX quantifié de 87 Mo ; entraîné en anglais",
    ),
    Candidate(
        id="mdeberta",
        doc_name="mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
        tier="2",
        backend="nli_onnx",
        repos=(
            (
                "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
                ("config.json", "tokenizer.json", "onnx/model_quantized.onnx"),
            ),
        ),
        onnx_file="onnx/model_quantized.onnx",
        model_license="MIT",
        with_packages=_NLI_PACKAGES,
        modules=_NLI_MODULES,
        roots=_NLI_PACKAGES,
        note="ONNX quantifié de 339 Mo ; multilingue (français et allemand à l'entraînement)",
    ),
    Candidate(
        id="minilm_multi",
        doc_name="multilingual-MiniLMv2-L6-mnli-xnli",
        tier="2",
        backend="nli_onnx",
        repos=(
            (
                "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
                ("config.json", "tokenizer.json", "onnx/model.onnx"),
            ),
        ),
        onnx_file="onnx/model.onnx",
        model_license="MIT",
        with_packages=_NLI_PACKAGES,
        modules=_NLI_MODULES,
        roots=_NLI_PACKAGES,
        note="ONNX de 428 Mo, architecture XLM-R (sans token_type_ids, comme l'ONNX de mDeBERTa) ; "
        "multilingue, "
        "option légère",
    ),
    Candidate(
        id="decision20",
        doc_name="Decision 2.0 Kai",
        tier="2",
        backend="decision20_torch",
        repos=(
            (
                DECISION20_REPO,
                (
                    "MODEL_MANIFEST.json",
                    "config.json",
                    "modeling_decision2.py",
                    "decision_head.safetensors",
                    "backbone/model.safetensors",
                ),
            ),
        ),
        model_license="Apache-2.0",
        with_packages=_DECISION20_PACKAGES,
        modules=("torch", "transformers", "safetensors", "huggingface_hub"),
        roots=_DECISION20_PACKAGES,
        remote_code=f"trust_remote_code : code du dépôt relu au commit {DECISION20_REVISION} "
        "(modeling_decision2.py, pipeline_decision2.py, configuration_decision2.py, decision2/)",
        note="Qwen3 0.6B non génératif, en FP32 sur CPU, torch ; instantané complet (≈ 1,53 Go) "
        "épinglé au commit relu ; question choice par tâche (system_one)",
        revision=DECISION20_REVISION,
        full_snapshot=True,
        trust_remote_code=True,
    ),
    Candidate(
        id="tev1",
        doc_name="tev1 0.8B",
        tier="2",
        backend="ollama_systemone",
        model_license=TEV1_LICENSE,
        license_class="unknown",
        modules=("httpx", "psutil"),  # both in the project: no `--with`
        remote_code="aucun code du modèle exécuté par le banc ; moteur : Ollama (llama-server "
        "embarqué), installé hors projet, version et empreinte du modèle consignées",
        note="Qwen3.5 0.8B affiné (Together AI), causal ; servi par Ollama hors de l'enfant de "
        "mesure : RAM de l'enfant + processus Ollama, hors-ligne vérifié aussi côté serveur ; "
        f"tirer une fois : ollama pull {TEV1_MODEL}",
        server_url=OLLAMA_BASE_URL,
        server_model=TEV1_MODEL,
        generative=True,
        server="ollama",
    ),
    Candidate(
        id="julia1",
        doc_name="Julia-1",
        tier="2",
        backend="llama_systemone",
        repos=((JULIA1_REPO, (JULIA1_FILE,)),),
        model_license="Apache-2.0 (carte GGUF ggml-org/Julia-1-GGUF et carte source "
        "SupersonicLabs/Julia-1, relues le 2026-10-03)",
        with_packages=("huggingface-hub",),  # the `--download` of the GGUF only
        modules=("httpx", "psutil"),
        remote_code=_LLAMA_REMOTE_CODE,
        note="encodeur de décision de 144M (Supersonic Labs, sur mmBERT-small, multilingue), "
        "non génératif ; GGUF Q8_0 de 168 Mo servi par llama-server hors de l'enfant de mesure",
        revision=JULIA1_REVISION,
        server_model="Julia-1",
        server="llama_server",
        gguf_sha256=JULIA1_SHA256,
    ),
    Candidate(
        id="laya",
        doc_name="Laya",
        tier="2",
        backend="llama_systemone",
        repos=((LAYA_REPO, (LAYA_FILE,)),),
        model_license="Apache-2.0 (carte GGUF ggml-org/Laya-GGUF et carte source "
        "convaiinnovations/laya, relues le 2026-10-03)",
        with_packages=("huggingface-hub",),
        modules=("httpx", "psutil"),
        remote_code=_LLAMA_REMOTE_CODE,
        note="encodeur de décision de 421M (Convai Innovations, sur ModernBERT-large, point de "
        "contrôle anglais), non génératif ; GGUF Q8_0 de 449 Mo servi par llama-server",
        revision=LAYA_REVISION,
        server_model="Laya",
        server="llama_server",
        gguf_sha256=LAYA_SHA256,
    ),
    Candidate(
        id="gliformer",
        doc_name="gliformer-base-v1",
        tier="2",
        backend="gliformer_torch",
        repos=(
            (
                "knowledgator/gliformer-base-v1",
                (
                    "gliner_config.json",
                    "pytorch_model.bin",
                    "tokenizer.json",
                    "tokenizer_config.json",
                ),
            ),
        ),
        model_license="Apache-2.0",
        with_packages=("gliformer", "huggingface-hub"),
        modules=("gliformer", "torch", "huggingface_hub"),
        roots=("gliformer", "huggingface-hub"),
        remote_code="bibliothèque gliformer (PyPI, version consignée), pas de trust_remote_code",
        note="voie officielle, sur torch ; entraîné en anglais",
    ),
    Candidate(
        id="gliformer_onnx",
        doc_name="gliformer-base-v1",
        tier="2",
        backend="gliformer_onnx",
        repos=(
            (
                "talmago/gliformer-base-v1-onnx",
                (
                    "gliner_config.json",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "onnx/encoder.onnx",
                    "onnx/classification.onnx",
                ),
            ),
        ),
        model_license="non déclarée (conversion ONNX tierce)",
        license_class="unknown",
        with_packages=("fast-gliner", "huggingface-hub"),
        modules=("fast_gliner", "huggingface_hub"),
        roots=("fast-gliner", "huggingface-hub"),
        remote_code="bibliothèque fast_gliner (tierce, version consignée), "
        "pas de trust_remote_code",
        note="ONNX tiers (talmago), pour fast_gliner",
    ),
    Candidate(
        id="nvidia",
        doc_name="nvidia/prompt-task-and-complexity-classifier",
        tier="1",
        backend="nvidia_torch",
        repos=(
            (
                "nvidia/prompt-task-and-complexity-classifier",
                ("config.json", "model.safetensors", "tokenizer.json"),
            ),
            ("microsoft/deberta-v3-base", ("config.json",)),
        ),
        model_license="NVIDIA Open Model License (usage commercial autorisé)",
        license_class="ok",
        with_packages=("torch", "transformers", "safetensors"),
        modules=("torch", "transformers", "safetensors", "tokenizers", "huggingface_hub"),
        roots=("torch", "transformers", "safetensors"),
        remote_code="code de la carte HF relu et reproduit dans ce banc (dorsale, huit têtes, "
        "score de complexité), pas de trust_remote_code",
        note="étiquettes fixes (task_type) ; pas d'ONNX publié",
    ),
    Candidate(
        id="slm_judge",
        doc_name="SLM juge",
        tier="3",
        backend="slm_judge",
        model_license="celle du SLM par défaut, déjà retenue en V1",
        license_class="ok",
        modules=("llama_cpp",),
        note="référence du repli : critères dans le prompt, sortie contrainte par grammaire",
    ),
    Candidate(
        id="llama_guard",
        doc_name="Llama-Guard-3-1B",
        tier="cyber",
        backend=None,
        model_license="Licence Llama 3.2",
        office="écarté",
        office_reason="génératif : jamais classifieur coexistant (règle d'un seul modèle "
        "génératif, NFR-2) ; il ne servirait qu'en remplaçant le SLM (CAP-9)",
    ),
    Candidate(
        id="qwen3guard",
        doc_name="Qwen3Guard-Gen-0.6B",
        tier="cyber",
        backend=None,
        model_license="Apache-2.0",
        office="écarté",
        office_reason="génératif : jamais classifieur coexistant (règle d'un seul modèle "
        "génératif, NFR-2) ; il ne servirait qu'en remplaçant le SLM (CAP-9)",
    ),
    Candidate(
        id="arch_router",
        doc_name="Arch-Router-1.5B",
        tier="-",
        backend=None,
        model_license="licence d'avril 2026 : licence commerciale DigitalOcean exigée",
        office="écarté",
        office_reason="licence incompatible avec une remise du code à des clients (NFR-10), "
        "rejeté par la forge du 2026-09-25",
    ),
]


def candidate(candidate_id: str) -> Candidate:
    for c in CANDIDATES:
        if c.id == candidate_id:
            return c
    raise KeyError(candidate_id)


def unknown_candidate_message(candidate_id: str) -> str | None:
    if any(c.id == candidate_id for c in CANDIDATES):
        return None
    return f"Candidat inconnu : {candidate_id}\nCandidats : {', '.join(c.id for c in CANDIDATES)}."


def command_for(c: Candidate) -> str:
    """The exact PowerShell line of a candidate, run from the repository root.

    `$SLM` is the default SLM's GGUF, `$OUT` the result folder (set once, see the report).
    """
    if c.office:
        return f"(aucune : {c.office} d'office)"
    if c.id == "decision10":
        return (
            f"uv run python {SCRIPT} decision10 --checked-on <AAAA-MM-JJ> --source <URL> "
            "[--gguf <URL>] [--onnx <URL>] [--cpu <URL>]"
        )
    with_args = "".join(f"--with {p} " for p in c.with_packages)
    download = " --download" if c.repos else ""
    return (
        f"uv run {with_args}python {SCRIPT} measure {c.id}{download} --slm $SLM "
        f'--out "$OUT\\{c.id}.json"'
    )


# --------------------------------------------------------------------------
# Pure helpers: decoding, latency, verdicts.
# --------------------------------------------------------------------------


def softmax(row: list[float]) -> list[float]:
    if not row:
        return []
    top = max(row)
    exps = [math.exp(x - top) for x in row]
    total = sum(exps)
    return [e / total for e in exps]


def entailment_index(id2label: dict) -> int:
    """Index of the entailment class in an NLI model's `id2label`."""
    for key, label in id2label.items():
        if str(label).lower().startswith("entail"):
            return int(key)
    raise ValueError(f"aucune classe d'implication dans {id2label}")


def pick_nli_label(keys: list[str], logits: list[list[float]], entail: int) -> str:
    """The label whose hypothesis has the highest entailment logit (single-label zero-shot,
    as the Hugging Face pipeline does)."""
    scores = [row[entail] for row in logits]
    return keys[max(range(len(keys)), key=scores.__getitem__)]


def onnx_feeds(encs, names) -> dict[str, list[list[int]]]:
    """The NLI inputs of a batch of encodings, kept to the inputs the ONNX session declares:
    some exports take no `token_type_ids` (the quantized mDeBERTa ONNX, MiniLM's XLM-R)."""
    feeds = {
        "input_ids": [e.ids for e in encs],
        "attention_mask": [e.attention_mask for e in encs],
        "token_type_ids": [e.type_ids for e in encs],
    }
    return {k: v for k, v in feeds.items() if k in names}


def choice_questions(task: str) -> dict:
    """The Jev-style questions of a task (Decision 2.0's `system_one`, Ollama's
    `/v1/systemone`): one `choice` question, whose options are the bench's labels and whose
    criteria are the written rules of `TASKS`."""
    return {
        task: {
            "type": "choice",
            "instructions": DECISION20_INSTRUCTIONS,
            "criteria": {key: crit.text for key, crit in TASKS[task].items()},
        }
    }


decision20_questions = choice_questions  # story 7's name


def decision20_label(answer) -> str:
    """The key Decision 2.0 chose, or `erreur : <code>` (`{"error": code}`)."""
    if not isinstance(answer, dict):
        return f"erreur : réponse inattendue {type(answer).__name__}"
    if answer.get("error"):
        return f"erreur : {answer['error']}"
    choice = answer.get("choice")
    return str(choice) if choice not in (None, "") else "erreur : sans choix"


# -- story 8: `/v1/systemone` (Ollama 0.35; llama-server for story 9) -----------------------


def systemone_label(response, qid: str, keys: list[str]) -> str:
    """The label of a `/v1/systemone` response for the `choice` question `qid`: the option of
    highest probability (`answers[qid].probabilities`), or `erreur : <cause>` for an error or
    an unknown shape (the row is kept, the bench goes on)."""
    if not isinstance(response, dict):
        return f"erreur : réponse inattendue {type(response).__name__}"
    if response.get("error"):
        return f"erreur : {response['error']}"
    answers = response.get("answers")
    answer = answers.get(qid) if isinstance(answers, dict) else None
    if not isinstance(answer, dict):
        return f"erreur : forme inattendue (answers.{qid} absent)"
    if answer.get("error"):
        return f"erreur : {answer['error']}"
    probs = answer.get("probabilities")
    if (
        not isinstance(probs, dict)
        or not probs
        or not set(probs) <= set(keys)
        or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in probs.values())
    ):
        return f"erreur : forme inattendue (answers.{qid}.probabilities)"
    return max((k for k in keys if k in probs), key=lambda k: float(probs[k]))


def systemone_row(response, qid: str, keys: list[str]) -> dict:
    """A bench row's fields from a `/v1/systemone` response: the label, plus the
    probabilities and the server's own `choice` when present (a confident streak and
    near-ties then read apart)."""
    row: dict = {"label": systemone_label(response, qid, keys)}
    answers = response.get("answers") if isinstance(response, dict) else None
    answer = answers.get(qid) if isinstance(answers, dict) else None
    if isinstance(answer, dict):
        if isinstance(answer.get("probabilities"), dict):
            row["probabilities"] = answer["probabilities"]
        if answer.get("choice") not in (None, ""):
            row["choice"] = answer["choice"]
    return row


def is_loopback_url(url: str) -> bool:
    """The server is reached on the loopback only (never an exposed Ollama)."""
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    return host == "localhost" or _is_loopback_ip(host)


def _is_loopback_ip(host: str) -> bool:
    import ipaddress

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _endpoint(addr) -> tuple[str, int] | None:
    """`(ip, port)` of a psutil address (named tuple or plain tuple); None when empty."""
    if not addr:
        return None
    return str(addr[0]), int(addr[1])


def remote_endpoints(conns) -> list[str]:
    """Non-loopback remote `ip:port` of a process's TCP connections (psutil `net_connections`)."""
    out = set()
    for conn in conns or []:
        end = _endpoint(getattr(conn, "raddr", None))
        if end and not _is_loopback_ip(end[0]):
            out.add(f"{end[0]}:{end[1]}")
    return sorted(out)


def listening_endpoints(conns) -> list[str]:
    """Local `ip:port` a process listens on (an Ollama exposed beyond 127.0.0.1 shows here)."""
    out = set()
    for conn in conns or []:
        end = _endpoint(getattr(conn, "laddr", None))
        if end and getattr(conn, "status", "") == "LISTEN":
            out.add(f"{end[0]}:{end[1]}")
    return sorted(out)


def ollama_role(name: str | None, cmdline: list[str] | None, blob_sha: str) -> str | None:
    """Role of a process in Ollama, from its name and command line (Ollama 0.35 on Windows:
    `ollama.exe serve`, then one `lib/ollama/llama-server.exe --model <blob>` per loaded
    model): `runner` (the model process carrying `blob_sha`), `server`, `other_runner`, `app`,
    `other`, or None when it is not an Ollama process (a shell whose command line merely
    quotes the blob is not one)."""
    exe = (name or "").lower()
    args = [str(a) for a in cmdline or []]
    is_runner = "llama-server" in exe and "ollama" in (args[0].lower() if args else "")
    if not (exe.startswith("ollama") or is_runner):
        return None
    if exe.startswith("ollama app"):
        return "app"
    if "serve" in args[1:]:
        return "server"
    if is_runner or "runner" in args[1:]:
        line = " ".join(args[1:]).lower()
        return "runner" if blob_sha and blob_sha.lower() in line else "other_runner"
    return "other"


def blob_sha_from_modelfile(modelfile: str) -> str:
    """The weights blob of an Ollama model (`FROM …/blobs/sha256-<hex>`), or ''."""
    match = re.search(r"^FROM\s.*sha256[-:]([0-9a-f]{64})", modelfile or "", re.MULTILINE)
    return match.group(1) if match else ""


_LICENSE_MARKER = re.compile(r"^(Apache License|MIT License|Version \d[^\n]*|Copyright\b[^\n]*)$")


def ollama_model_record(model: str, show: dict, tags: dict) -> dict:
    """What identifies the served model (`/api/show`, `/api/tags`): digest, weights blob,
    capabilities, and the licence texts the package carries (markers and sha256)."""
    digest = next(
        (m.get("digest") for m in (tags or {}).get("models") or [] if m.get("name") == model),
        None,
    )
    licence = show.get("license") or ""
    if isinstance(licence, list):
        licence = "\n".join(str(x) for x in licence)
    markers = []
    for line in licence.splitlines():
        line = line.strip()
        if _LICENSE_MARKER.match(line) and line not in markers:
            markers.append(line)
    return {
        "name": model,
        "digest": digest,
        "blob_sha256": blob_sha_from_modelfile(show.get("modelfile") or ""),
        "capabilities": show.get("capabilities"),
        "details": show.get("details"),
        "parameters": show.get("parameters"),
        "requires": show.get("requires"),
        "modified_at": show.get("modified_at"),
        "license_markers": markers,
        "license_sha256": hashlib.sha256(licence.encode("utf-8")).hexdigest() if licence else None,
    }


def is_sha256(value: str | None) -> bool:
    return bool(re.fullmatch(r"(sha256:)?[0-9a-f]{64}", value or ""))


def server_ram_total(report: dict, prefix: str = "ollama") -> int | None:
    """Total RAM of a served candidate: the child's peak (default SLM loaded) plus the peak
    of the server processes that serve it (`<prefix>_rss_peak_mb`: Ollama, llama-server);
    None if either is unknown."""
    child, server = report.get("rss_peak_mb"), report.get(f"{prefix}_rss_peak_mb")
    if child is None or server is None:
        return None
    return child + server


# -- story 9: a portable llama-server, started and stopped by the bench -----------------------


def default_llama_server(environ=None) -> Path:
    """Where the release archive is unzipped (outside the repository, no admin rights)."""
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "WaveStack" / "bench" / f"llama-{LLAMA_RELEASE}" / "llama-server.exe"


def resolve_llama_server(arg: str | None, environ=None) -> tuple[Path, str]:
    """`llama-server.exe`: `--llama-server`, else `WAVESTACK_LLAMA_SERVER`, else the default
    folder; with where the path came from."""
    environ = os.environ if environ is None else environ
    if arg:
        return Path(arg), "--llama-server"
    if environ.get(LLAMA_SERVER_ENV):
        return Path(environ[LLAMA_SERVER_ENV]), LLAMA_SERVER_ENV
    return default_llama_server(environ), "dossier par défaut"


def llama_binary_absent_message(exe: Path) -> str:
    return (
        f"llama-server introuvable : {exe}. Téléchargez une fois {LLAMA_ZIP} (release "
        f"{LLAMA_RELEASE} de ggml-org/llama.cpp, {LLAMA_RELEASE_URL}) et décompressez-le dans "
        f"{default_llama_server().parent}, ou passez --llama-server <chemin de "
        f"llama-server.exe> (ou {LLAMA_SERVER_ENV}). Le banc ne télécharge pas le binaire."
    )


def parse_llama_version(text: str) -> dict:
    """`llama-server --version` (`version: 0.5.0-dev (build 11378, commit edd6e2bbd)`)."""
    line = next((s.strip() for s in (text or "").splitlines() if s.startswith("version:")), "")
    match = re.search(r"version:\s*(\S+)\s*\(build (\d+), commit ([0-9a-f]+)\)", line)
    if not match:
        return {"version_line": line or None, "version": None, "build": None, "commit": None}
    version, build, commit = match.groups()
    return {"version_line": line, "version": version, "build": build, "commit": commit}


def llama_binary_pinned(server: dict) -> bool:
    """The binary is the recorded one: `llama-server.exe` and `llama-server-impl.dll` have the
    sha256 read on the target PC. The archive next to the folder is recorded, but says nothing
    of the unzipped files."""
    return (
        server.get("exe_sha256") == LLAMA_EXE_SHA256
        and server.get("impl_sha256") == LLAMA_IMPL_SHA256
    )


def llama_server_argv(exe: Path, gguf: Path, port: int, alias: str) -> list[str]:
    """The server's command line: the GGUF by LOCAL path (`-m`, never `-hf`), listening on
    127.0.0.1 only, offline, without the Web UI, one slot."""
    return [
        str(exe),
        "-m",
        str(gguf),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--offline",
        "--no-webui",
        "-np",
        "1",
        "-a",
        alias,
    ]


def llama_server_env(base: dict[str, str]) -> dict[str, str]:
    """The server's environment: no proxy, and no `LLAMA_ARG_*` (an inherited
    `LLAMA_ARG_HOST` would change where it listens)."""
    env = dict(base)
    s12._strip_proxy_env(env)
    for name in [n for n in env if n.upper().startswith(("LLAMA_ARG_", "LLAMA_CACHE"))]:
        del env[name]
    return env


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_loopback_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def gguf_path(models_dir: Path, c: Candidate) -> Path:
    """The candidate's GGUF in the bench's Hugging Face cache, at its pinned commit."""
    repo, files = c.repos[0]
    return _snapshots_dir(models_dir, repo) / c.revision / files[0]


def gguf_record(c: Candidate, path: Path, sha256=None) -> dict:
    repo, files = c.repos[0]
    digest = (sha256 or file_sha256)(path)
    return {
        "repo": repo,
        "file": files[0],
        "revision": c.revision,
        "path": str(path),
        "size_mb": path.stat().st_size >> 20,
        "sha256": digest,
        "expected_sha256": c.gguf_sha256,
        "sha256_ok": digest == c.gguf_sha256,
    }


_LOG_KEEP = re.compile(
    r"decision model|n_ctx_slot|system_info|build:|main: |error|failed|exception", re.IGNORECASE
)


def log_excerpt(text: str, tail: int = 0, keep: int = 25) -> list[str]:
    """The telling lines of a llama-server log (model type, context, errors), then its last
    `tail` lines (the cause of a failed start)."""
    lines = [s.rstrip() for s in (text or "").splitlines() if s.strip()]
    picked = [s for s in lines if _LOG_KEEP.search(s)][:keep]
    if tail:
        picked += [s for s in lines[-tail:] if s not in picked]
    return picked


def nvidia_scores(logits: list[list[float]], cfg: dict) -> dict:
    """Post-processing of the NVIDIA card (`CustomModel.process_logits`), in pure Python.

    `logits` holds one row per head, in the order of `cfg["target_sizes"]`.
    """
    heads = dict(zip(cfg["target_sizes"], logits, strict=True))
    task_row = heads.pop("task_type")
    task = cfg["task_type_map"][str(max(range(len(task_row)), key=task_row.__getitem__))]
    scores: dict = {}
    for name, row in heads.items():
        probs = softmax(row)
        weighted = sum(p * w for p, w in zip(probs, cfg["weights_map"][name], strict=True))
        value = round(weighted / cfg["divisor_map"][name], 4)
        if name == "number_of_few_shots" and value < 0.05:
            value = 0
        scores[name] = value
    complexity = round(
        0.35 * scores["creativity_scope"]
        + 0.25 * scores["reasoning"]
        + 0.15 * scores["constraint_ct"]
        + 0.15 * scores["domain_knowledge"]
        + 0.05 * scores["contextual_knowledge"]
        + 0.05 * scores["number_of_few_shots"],
        5,
    )
    return {"task_type": task, "complexity": complexity, **scores}


def nvidia_label(scores: dict, task: str) -> str:
    """Cost: complexity against the threshold. Specialty: its fixed task type (level 1)."""
    if task == "cost":
        return "complexe" if scores["complexity"] >= NVIDIA_COMPLEXITY_THRESHOLD else "simple"
    return scores["task_type"]


def top_label(predictions, short_to_key: dict[str, str]) -> str:
    """Best label of a GLiFormer `classify` result, whatever its shape: a list of dicts
    (`class_name` or `label`, `score`), of (label, score) pairs, a {label: score} dict, or
    a batch of one of those."""
    preds = predictions
    if isinstance(preds, list) and preds and isinstance(preds[0], list | tuple):
        if not preds[0] or isinstance(preds[0][0], dict | list | tuple):
            preds = preds[0]  # a batch of one text (possibly without any prediction)
    if isinstance(preds, dict):
        pairs = list(preds.items())
    else:
        pairs = []
        for item in preds or []:
            if isinstance(item, dict):
                pairs.append((item.get("class_name") or item.get("label"), item.get("score", 0)))
            else:
                pairs.append((item[0], item[1]))
    if not pairs:
        return "aucune"
    name = max(pairs, key=lambda p: float(p[1] or 0))[0]
    return short_to_key.get(name, str(name))


def gbnf_choice(keys: list[str]) -> str:
    """A GBNF grammar whose only sentences are the labels."""
    return "root ::= " + " | ".join(json.dumps(k) for k in keys)


def judge_messages(text: str, task: str) -> list[dict]:
    """The SLM judge's chat: the written criteria in the system prompt, the request as user."""
    lines = [
        "Tu es un routeur. Classe la demande de l'utilisateur selon les critères ci-dessous.",
        "Réponds par l'étiquette seule.",
    ]
    lines += [f"- {key} : {crit.text}" for key, crit in TASKS[task].items()]
    return [
        {"role": "system", "content": "\n".join(lines)},
        {"role": "user", "content": text},
    ]


def run_decisions(decide, clock=time.perf_counter) -> tuple[float, list[dict]]:
    """An untimed warm-up of each task (its own batch shape, grammar or prompt), then every
    prompt through both tasks, timed one by one. `decide` returns the label, or a dict with
    the label and extra fields kept in the row (a served model's probabilities)."""
    t0 = clock()
    for task in TASKS:
        decide(PROMPTS[0].text, task)
    warmup_ms = round((clock() - t0) * 1000, 1)
    rows = []
    for p in PROMPTS:
        for task in TASKS:
            t1 = clock()
            result = decide(p.text, task)
            ms = round((clock() - t1) * 1000, 1)
            extra = dict(result) if isinstance(result, dict) else {"label": result}
            label = extra.pop("label")
            row = {"prompt": p.id, "task": task, "label": label, "expected": p.expected(task)}
            rows.append({**row, "ms": ms, **extra})
    return warmup_ms, rows


def _is_error_row(row: dict) -> bool:
    return str(row["label"]).startswith("erreur")


def agreement(rows: list[dict], task: str, fixed: bool = False) -> str:
    """Indicative agreement with the expected labels; `fixed`: the model answers with its own
    labels for this task (level 1), so there is nothing to compare."""
    if fixed:
        return "sans objet (étiquettes fixes du modèle)"
    task_rows = [r for r in rows if r["task"] == task]
    hits = sum(1 for r in task_rows if r["label"] == r["expected"])
    return f"{hits}/{len(task_rows)}"


def summarize_decisions(rows: list[dict], fixed_tasks: tuple[str, ...] = ()) -> dict:
    times = [r["ms"] for r in rows if not _is_error_row(r)]  # an error row is no decision
    return {
        "decisions": len(rows),
        "latency_median_ms": round(statistics.median(times), 1) if times else None,
        "latency_max_ms": max(times) if times else None,
        "agreement": {task: agreement(rows, task, task in fixed_tasks) for task in TASKS},
        "error_rows": sum(1 for r in rows if _is_error_row(r)),
    }


def is_commit_sha(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", value or ""))


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def added_packages(rows: list[dict], project_names: set[str]) -> list[dict]:
    """The candidate's closure, each row marked `added` when the project does not have it."""
    project = {_norm(n) for n in project_names}
    return [dict(r, added=_norm(r["name"]) not in project) for r in rows]


def license_class(c: Candidate) -> str:
    return c.license_class or s12.classify_license(c.model_license)


def decision10_verdict(
    checked_on: str, source: str, gguf: str = "", onnx: str = "", cpu: str = ""
) -> dict:
    """Decision 1.0: discarded without measurement while no CPU path exists (story rule)."""
    try:
        date.fromisoformat(checked_on or "")
    except ValueError as exc:
        raise ValueError("date du relevé attendue au format AAAA-MM-JJ (--checked-on)") from exc
    if not (source or "").strip():
        raise ValueError("source du relevé manquante (--source)")
    pairs = (("GGUF", gguf), ("ONNX", onnx), ("chemin CPU", cpu))
    found = {name: url.strip() for name, url in pairs if (url or "").strip()}
    generative = (
        "Eos, Sol, Nox et Lux (sur Qwen3.5) sont génératifs : jamais classifieurs coexistants"
    )
    if not found:
        return {
            "status": "écarté sans mesure",
            "reason": f"ni GGUF, ni ONNX, ni chemin CPU au {checked_on} (source : {source}) ; "
            + generative,
            "checked_on": checked_on,
            "source": source,
            "found": {},
        }
    return {
        "status": "à surveiller",
        "reason": f"{', '.join(found)} disponible au {checked_on} (source : {source}) : ajouter "
        "Kai ou Lex 0.6B (encodeurs) au banc, par une nouvelle story, avant tout verdict ; "
        + generative,
        "checked_on": checked_on,
        "source": source,
        "found": found,
    }


BLOCKING = ("ram", "latency", "offline")


def decision_verdict(c: Candidate, report: dict) -> dict:
    """Verdict of a candidate from its report: retained, discarded or to watch, with reason.

    Each criterion is ok (True), KO (False) or not checkable by the bench (None).
    """
    if c.office:
        return {"status": c.office, "reason": c.office_reason, "criteria": [], "target_pc": None}
    target = bool(report.get("target_pc"))
    suffix = "" if target else " (indicatif, hors PC cible)"
    if report.get("status") != "measured":
        hosts = s12.summarize_attempts(report.get("attempts", []))
        if report.get("error") == "ram_ceiling":  # the child's memory watchdog stopped it
            reason = (
                f"RAM : mesure arrêtée par le garde-fou à {report.get('rss_at_stop_mb')} Mo de "
                f"RSS (au-delà de {RAM_BUDGET_MB} Mo, SLM par défaut chargé), sans latence ni "
                f"accord ; hôtes tentés : {hosts or 'aucun'}"
            )
            return {
                "status": "écarté (RAM)" + suffix,
                "reason": reason,
                "criteria": [],
                "target_pc": target,
            }
        ceiling = report.get("ollama_ceiling") or report.get("llama_server_ceiling")
        if ceiling:  # the server processes went beyond the abort threshold
            label = SERVER_LABELS.get(c.server, c.server or "Ollama")
            reason = (
                f"RAM : mesure arrêtée, processus {label} à {ceiling.get('rss_at_stop_mb')} Mo "
                f"(seuil d'arrêt {ceiling.get('threshold_mb')} Mo, au-delà du budget de "
                f"{RAM_BUDGET_MB} Mo), sans latence ni accord complets"
            )
            return {
                "status": "écarté (RAM)" + suffix,
                "reason": reason,
                "criteria": [],
                "target_pc": target,
            }
        if report.get("blocked") or hosts:  # the guard stopped it: the offline criterion fails
            reason = (
                "Hors ligne : tentative réseau bloquée par la garde d'AD-15 "
                f"({report.get('blocked') or ', '.join(hosts)})"
            )
            return {
                "status": "écarté" + suffix,
                "reason": reason,
                "criteria": [],
                "target_pc": target,
            }
        why = report.get("status") or "non mesuré"
        if report.get("error"):
            why += f" : {report['error']}"
        return {"status": "non mesuré", "reason": why, "criteria": [], "target_pc": target}
    if report.get("decisions") and report.get("error_rows") == report["decisions"]:
        first = next((r["label"] for r in report.get("rows") or []), "?")
        return {
            "status": "non mesuré",
            "reason": f"toutes les décisions sont en erreur ({first})",
            "criteria": [],
            "target_pc": target,
        }

    criteria = []
    admin, release = report.get("admin"), report.get("windows_release")
    if not target:
        cpu_ok, cpu_detail = None, f"hors PC cible ({report.get('platform')}) : non vérifiable"
    elif release != "11" or admin is not False:
        cpu_ok = None
        cpu_detail = (
            f"Windows {release}, droits admin : {admin} : non vérifiable sans une session "
            "Windows 11 sans droits admin"
        )
        suffix = " (indicatif : Windows 11 sans droits admin non vérifié)"
    else:
        cpu_ok = True
        cpu_detail = (
            "Windows 11, session sans droits admin ; vérifier dans la sortie de uv qu'aucun "
            "paquet n'a été compilé (« Building … »)"
        )
    if c.server == "ollama":  # criterion 1 as it stands, never a failure (story 8)
        version = (report.get("ollama") or {}).get("version")
        cpu_detail += (
            f" ; Ollama {version or '?'} est déjà installé sur le poste, sans droits admin "
            "(installation par utilisateur) ; aucun paquet Python ajouté"
        )
    elif c.server == "llama_server":  # a finding for Anaël to decide on, never a failure
        server = report.get("llama_server") or {}
        cpu_detail += (
            f" ; llama-server {server.get('version_line') or '?'} : binaire portable décompressé "
            f"hors du dépôt ({server.get('exe') or '?'}), ni installé ni lancé en admin, démarré "
            "et arrêté par le banc ; « sans exécutable à installer » : constat pour décision "
            "d'Anaël, pas un échec ; aucun paquet Python ajouté"
        )
    criteria.append(
        {
            "id": "cpu_windows",
            "label": "CPU sous Windows 11, sans droits admin",
            "ok": cpu_ok,
            "detail": cpu_detail,
        }
    )
    total, added = report.get("rss_peak_mb"), report.get("rss_added_mb")
    ram_detail = (
        f"pic total {total} Mo (SLM chargé : {report.get('rss_with_slm_mb')} Mo), "
        f"ajouté par le candidat {added} Mo au pic"
    )
    if c.server:  # the model lives in a server: the child plus the serving processes
        child, server = total, report.get(f"{c.server}_rss_peak_mb")
        total = server_ram_total(report, c.server)
        parts = report.get(f"{c.server}_rss") or {}
        ram_detail = (
            f"pic total {total} Mo = enfant de mesure {child} Mo (SLM chargé : "
            f"{report.get('rss_with_slm_mb')} Mo, ajouté dans l'enfant {added} Mo) + "
        )
        if c.server == "ollama":
            ram_detail += (
                f"processus Ollama {server} Mo (serveur {parts.get('server_peak_mb')} Mo, "
                f"processus du modèle {parts.get('runner_peak_mb')} Mo)"
            )
        else:
            ram_detail += f"llama-server {server} Mo (modèle chargé, pic de l'ensemble de travail)"
    rag = report.get("v1_rag_rss_mb")
    rag_txt = (
        f" ; avec l'embedding et le reranker V1 ({rag} Mo mesurés), {total + rag} Mo"
        if rag is not None and total is not None
        else ""
    )
    criteria.append(
        {
            "id": "ram",
            "label": f"RAM : pic total ≤ {RAM_BUDGET_MB} Mo, SLM par défaut chargé (NFR-2)",
            "ok": None if total is None else total <= RAM_BUDGET_MB,
            "detail": ram_detail + rag_txt,
        }
    )
    med, mx = report.get("latency_median_ms"), report.get("latency_max_ms")
    if c.backend == "slm_judge":
        lat_ok, lat_label = med is not None, "Latence d'une décision (référence du repli)"
    else:
        lat_ok = med is not None and med <= LATENCY_MEDIAN_MAX_MS and mx <= LATENCY_MAX_MS
        lat_label = f"Latence : médiane ≤ {LATENCY_MEDIAN_MAX_MS} ms, maximum ≤ {LATENCY_MAX_MS} ms"
    if med is None:
        lat_ok = None  # no decision to time (no row, or error rows only)
    errors = report.get("error_rows")
    launch = report.get("llama_server_launch") or {}
    start = (
        f", démarrage de llama-server {launch.get('start_s')} s"
        if c.server == "llama_server"
        else ""
    )
    criteria.append(
        {
            "id": "latency",
            "label": lat_label,
            "ok": lat_ok,
            "detail": f"médiane {med} ms, maximum {mx} ms sur {report.get('decisions')} "
            f"décisions (échauffement {report.get('warmup_ms')} ms, chargement "
            f"{report.get('load_s')} s{start})"
            + (f", {errors} ligne(s) en erreur exclue(s)" if errors else ""),
        }
    )
    if errors:  # some decisions failed (all of them: "non mesuré" above)
        criteria.append(
            {
                "id": "error_rows",
                "label": f"Décisions sans erreur ({errors} sur {report.get('decisions')} "
                "en erreur)",
                "ok": False,
                "detail": f"{errors} décision(s) en erreur sur {report.get('decisions')} : "
                "latence et accord jugés sur les autres seulement",
            }
        )
    hosts = s12.summarize_attempts(report.get("attempts", []))
    offline_ok: bool | None = not hosts and not report.get("blocked")
    offline_detail = f"hôtes tentés : {hosts or 'aucun'}"
    offline_label = "Hors ligne : aucune tentative réseau sous la garde d'AD-15"
    if c.server:
        label = SERVER_LABELS.get(c.server, c.server)
        net = report.get(f"{c.server}_network") or {}
        model_role = "runner" if c.server == "ollama" else "server"
        phases = ("before", "during", "after")
        remotes = {r for phase in phases for r in net.get(phase, [])}
        remotes |= set(launch.get("startup_remotes") or [])  # llama-server's start
        remotes = sorted(remotes)
        listen = sorted(set(net.get("listen") or []) | set(launch.get("startup_listen") or []))
        exposed = [a for a in listen if not _is_loopback_ip(a.rsplit(":", 1)[0])]
        found = bool((report.get(f"{c.server}_processes") or {}).get(model_role))
        net_errors = list(net.get("errors") or []) + list(launch.get("startup_errors") or [])
        checked = bool(net) and net.get("samples", 0) > 0 and not net_errors and found
        if remotes or exposed:
            offline_ok = False  # an outgoing connection, or a server listening beyond loopback
        elif not checked and offline_ok:
            offline_ok = None  # the server side could not be read in full: not verifiable
        offline_label += (
            f", aucune connexion sortante des processus {label}, écoute sur la boucle locale seule"
        )
        where = (
            "serveur et processus du modèle"
            if c.server == "ollama"
            else "processus llama-server, lancé avec --offline, relevé par PID dès son démarrage"
        )
        offline_detail += (
            f" ; côté {label} ({where}, connexions TCP avant, pendant et après la mesure) : "
            f"{remotes or 'aucune connexion hors boucle locale'}"
            + ("" if checked else f" (relevé incomplet : {net_errors or 'aucun relevé'})")
            + f" ; écoute : {listen or '?'}"
            + (f" (hors boucle locale : {exposed})" if exposed else "")
        )
    criteria.append(
        {"id": "offline", "label": offline_label, "ok": offline_ok, "detail": offline_detail}
    )
    # The measure follows `main`: what it pins is the commit and the package versions it
    # records, to be copied into decision-model-candidates.md for a retained candidate.
    revisions = report.get("revisions") or {}
    versions = report.get("versions") or {}
    if c.server == "ollama":  # the model's digest in Ollama and Ollama's version
        pinned = (
            bool(revisions)
            and all(is_sha256(v) for v in revisions.values())
            and bool(versions.get("ollama"))
        )
    elif c.server == "llama_server":  # the GGUF's commit and sha256, the server's build
        pinned = (
            bool(revisions)
            and all(is_commit_sha(v) for v in revisions.values())
            and c.revision in revisions.values()
            and bool((report.get("gguf") or {}).get("sha256_ok"))
            and f"build {LLAMA_BUILD}," in str(versions.get("llama-server") or "")
            and llama_binary_pinned(report.get("llama_server") or {})
        )
    else:
        pinned = (
            all(is_commit_sha(v) for v in revisions.values())
            and (bool(revisions) or not c.repos)
            and all(versions.get(root) for root in c.roots)
            and (not c.revision or c.revision in revisions.values())
        )
    remote = (
        f" ; trust_remote_code exécuté, code relu au commit {c.revision} : au mieux à surveiller"
        if c.trust_remote_code
        else ""
    )
    if c.server == "llama_server":
        gguf = report.get("gguf") or {}
        remote += (
            f" ; GGUF {gguf.get('file')} sha256 {gguf.get('sha256')} "
            f"({'conforme' if gguf.get('sha256_ok') else 'NON conforme'} à {c.gguf_sha256})"
        )
        server = report.get("llama_server") or {}
        remote += (
            f" ; llama-server.exe sha256 {server.get('exe_sha256')}, llama-server-impl.dll "
            f"sha256 {server.get('impl_sha256')} : binaire "
            f"{'conforme' if llama_binary_pinned(server) else 'NON conforme'} au relevé "
            f"({LLAMA_EXE_SHA256} et {LLAMA_IMPL_SHA256} ; autres DLL du moteur non vérifiées) "
            f"; archive {(server.get('archive') or {}).get('sha256')} (consignée seulement)"
        )
    criteria.append(
        {
            "id": "pinned",
            "label": "Code relu et figé : commit et versions consignés, pas de trust_remote_code",
            "ok": pinned and not c.trust_remote_code,
            "detail": f"commits {revisions or 'aucun (pas de dépôt)'} ; versions "
            f"{versions or 'aucune'} ; code : {c.remote_code}{remote}",
        }
    )
    packages = [p for p in report.get("packages", []) if p.get("added")]
    forbidden = [f"{p['name']} ({p['license']})" for p in packages if p["class"] == "forbidden"]
    unknown = [f"{p['name']} ({p['license']})" for p in packages if p["class"] == "unknown"]
    model_class = license_class(c)
    served = ""
    if c.server == "ollama":
        model = (report.get("ollama") or {}).get("model") or {}
        served = (
            f" ; textes du paquet Ollama : {model.get('license_markers') or 'aucun'} "
            f"(sha256 {model.get('license_sha256')})"
        )
    elif c.server == "llama_server":
        served = (
            f" ; moteur : llama.cpp {LLAMA_RELEASE} (MIT ; l'archive porte aussi "
            "LICENSE-LLVM-OpenMP pour libomp), binaire de mesure hors projet"
        )
    criteria.append(
        {
            "id": "license",
            "label": "Licences compatibles avec une remise du code (NFR-10)",
            "ok": model_class == "ok" and not forbidden and not unknown,
            "forbidden": model_class == "forbidden" or bool(forbidden),
            "detail": f"modèle : {c.model_license} ({model_class}){served} ; {len(packages)} "
            f"paquet(s) ajouté(s) ; interdites : {forbidden or 'aucune'} ; à vérifier : "
            f"{unknown or 'aucune'}",
        }
    )
    criteria.append(
        {
            "id": "no_torch",
            "label": "Sans torch",
            "ok": not report.get("torch_loaded"),
            "detail": f"modules lourds chargés : {report.get('heavy_modules_loaded') or 'aucun'}",
        }
    )
    if c.generative:  # never blocking, but caps the verdict (Anaël's decision, 2026-10-03)
        criteria.append(
            {
                "id": "single_generative",
                "label": "Règle d'un seul modèle génératif (NFR-2)",
                "ok": False,
                "detail": "modèle causal (tête de langage conservée, il répond en prose en "
                "chat ordinaire) : au mieux « à surveiller » tant que la règle n'est pas revue "
                "(décision d'Anaël du 2026-10-03)",
            }
        )

    ko = [x for x in criteria if x["ok"] is False]
    blocking = [x for x in ko if x["id"] in BLOCKING or x.get("forbidden")]
    # Retained only if every criterion passes: a blocking one the bench could not check
    # (server side unreadable…) is no pass, and caps the verdict like a soft failure.
    soft = [
        x["label"] if x["ok"] is False else f"{x['label']} (non vérifiable)"
        for x in criteria
        if x["ok"] is False or (x["ok"] is None and x["id"] in BLOCKING)
    ]
    if c.backend == "slm_judge":
        # The fallback loads nothing more: it holds if it decides offline, within the budget.
        status = "à revoir" if blocking else "repli (référence)"
    elif blocking:
        status = "écarté"
    elif soft:
        status = "à surveiller"
    else:
        status = "retenu"
    reason = "; ".join([x["label"] for x in blocking] or soft) or "tous les critères passent"
    return {"status": status + suffix, "reason": reason, "criteria": criteria, "target_pc": target}


def resolve_slm(arg: str | None, search_dir: Path) -> tuple[Path | None, str | None]:
    """The default SLM's GGUF: `--slm`, or the only generative GGUF of the models folder."""
    if arg:
        path = Path(arg)
        if path.suffix.lower() != ".gguf" or not path.is_file():
            return None, f"SLM introuvable : {path} (fichier GGUF attendu)"
        return path, None
    found = sorted(
        p
        for p in (search_dir.glob("*.gguf") if search_dir.is_dir() else [])
        if not re.search(r"embed|rerank", p.name, re.IGNORECASE)
    )
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, f"Aucun GGUF de SLM dans {search_dir} : passez --slm <chemin du GGUF>."
    names = "\n".join(f"   {p}" for p in found)
    return (
        None,
        f"Plusieurs GGUF dans {search_dir} : choisissez le SLM par défaut avec --slm.\n{names}",
    )


def hf_cache(models_dir: Path) -> Path:
    return models_dir / "hf"


def _snapshots_dir(models_dir: Path, repo: str) -> Path:
    return hf_cache(models_dir) / f"models--{repo.replace('/', '--')}" / "snapshots"


def snapshot_present(
    models_dir: Path, repo: str, files: tuple[str, ...] = (), revision: str = ""
) -> bool:
    """A snapshot of `repo` holds every file the measure needs (a partial download is absent).
    With a pinned `revision`, only `snapshots/<revision>` counts."""
    snapshots = _snapshots_dir(models_dir, repo)
    if not snapshots.is_dir():
        return False
    candidates = [snapshots / revision] if revision else list(snapshots.iterdir())
    return any(snap.is_dir() and all((snap / f).is_file() for f in files) for snap in candidates)


def other_snapshots(models_dir: Path, repo: str, revision: str) -> list[str]:
    """Commits of `repo` in the cache other than the pinned `revision` (sorted)."""
    snapshots = _snapshots_dir(models_dir, repo)
    if not revision or not snapshots.is_dir():
        return []
    return sorted(p.name for p in snapshots.iterdir() if p.is_dir() and p.name != revision)


def wavestack_settings(root: Path | None = None) -> dict:
    """`wavestack.toml` of the repository (standard library only), or {} when unreadable."""
    import tomllib

    path = (root or Path(__file__).resolve().parents[2]) / "wavestack.toml"
    try:
        return tomllib.loads(path.read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def v1_rag_rss_mb(settings: dict) -> int | None:
    """RSS measured on the target PC for the V1 embedding and reranker (story 12): the other
    non-generative components that share NFR-2's budget when the RAG brick is on."""
    rag = settings.get("rag") or {}
    values = [(rag.get(k) or {}).get("measured_rss_mb") for k in ("embedding", "reranker")]
    return sum(values) if all(isinstance(v, int) for v in values) else None


def slm_n_ctx(settings: dict) -> int:
    """WaveStack's default context window (`[context] window`), as the engine loads the SLM."""
    window = (settings.get("context") or {}).get("window")
    return window if isinstance(window, int) and window > 0 else SLM_N_CTX


def missing_modules(c: Candidate, find_spec=importlib.util.find_spec) -> list[str]:
    return [m for m in c.modules if find_spec(m) is None]


# --------------------------------------------------------------------------
# Measurement child: guard, default SLM loaded and warm, baseline, candidate.
# --------------------------------------------------------------------------


def snapshot_kwargs(c: Candidate, files: tuple[str, ...]) -> dict:
    """`snapshot_download` arguments of a candidate: pinned to its reviewed commit if any,
    and the whole repository when it needs it (its files are then presence witnesses)."""
    kwargs: dict = {}
    if not c.full_snapshot:
        kwargs["allow_patterns"] = list(files)
    if c.revision:
        kwargs["revision"] = c.revision
    return kwargs


def _snapshot(models_dir: Path, repo: str, files: tuple[str, ...], c: Candidate) -> Path:
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=repo,
            cache_dir=str(hf_cache(models_dir)),
            local_files_only=True,
            **snapshot_kwargs(c, files),
        )
    )


def _load_nli(c: Candidate, models_dir: Path, slm_llm):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    repo, files = c.repos[0]
    root = _snapshot(models_dir, repo, files, c)
    cfg = json.loads((root / "config.json").read_text("utf-8"))
    entail = entailment_index(cfg["id2label"])
    tok = Tokenizer.from_file(str(root / "tokenizer.json"))
    tok.enable_truncation(max_length=512)
    tok.enable_padding(pad_id=int(cfg.get("pad_token_id", 0)))
    session = ort.InferenceSession(str(root / c.onnx_file), providers=["CPUExecutionProvider"])
    names = {i.name for i in session.get_inputs()}

    def decide(text: str, task: str) -> str:
        keys = list(TASKS[task])
        encs = tok.encode_batch([(text, TASKS[task][k].text) for k in keys])
        feeds = {k: np.array(v, dtype=np.int64) for k, v in onnx_feeds(encs, names).items()}
        logits = session.run(None, feeds)[0]
        return pick_nli_label(keys, logits.tolist(), entail)

    return decide, {"revisions": {repo: root.name}, "onnx_inputs": sorted(names)}


def _load_nvidia(c: Candidate, models_dir: Path, slm_llm):
    import torch
    from safetensors.torch import load_file
    from tokenizers import Tokenizer
    from transformers import DebertaV2Config, DebertaV2Model

    (repo, files), (backbone_repo, backbone_files) = c.repos
    root = _snapshot(models_dir, repo, files, c)
    backbone_root = _snapshot(models_dir, backbone_repo, backbone_files, c)
    cfg = json.loads((root / "config.json").read_text("utf-8"))
    # The card builds the backbone with `AutoModel.from_pretrained` (a second download of
    # the base weights): only its configuration is needed, the weights are in the checkpoint.
    backbone = DebertaV2Model(DebertaV2Config.from_pretrained(str(backbone_root)))
    state = load_file(str(root / "model.safetensors"))
    missing, unexpected = backbone.load_state_dict(
        {k.removeprefix("backbone."): v for k, v in state.items() if k.startswith("backbone.")},
        strict=False,
    )
    heads = []
    for i, size in enumerate(cfg["target_sizes"].values()):
        head = torch.nn.Linear(backbone.config.hidden_size, size)
        head.load_state_dict(
            {"weight": state[f"head_{i}.fc.weight"], "bias": state[f"head_{i}.fc.bias"]}
        )
        heads.append(head.eval())
    backbone.eval()
    del state
    tok = Tokenizer.from_file(str(root / "tokenizer.json"))
    tok.no_padding()
    tok.enable_truncation(max_length=512)

    def decide(text: str, task: str) -> str:
        enc = tok.encode(text)
        ids = torch.tensor([enc.ids])
        mask = torch.tensor([enc.attention_mask])
        with torch.inference_mode():
            hidden = backbone(input_ids=ids, attention_mask=mask).last_hidden_state
            weights = mask.unsqueeze(-1).float()
            pooled = (hidden * weights).sum(1) / weights.sum(1).clamp(min=1e-9)
            logits = [head(pooled)[0].tolist() for head in heads]
        return nvidia_label(nvidia_scores(logits, cfg), task)

    info = {
        "revisions": {repo: root.name, backbone_repo: backbone_root.name},
        "load_warnings": {"missing_keys": len(missing), "unexpected_keys": len(unexpected)},
    }
    return decide, info


def _load_gliformer(c: Candidate, models_dir: Path, slm_llm):
    repo, files = c.repos[0]
    root = _snapshot(models_dir, repo, files, c)
    if c.backend == "gliformer_torch":
        import torch
        from gliformer import GLiFormer

        model = GLiFormer.from_pretrained(str(root), load_tokenizer=True).to("cpu").eval()

        def classify(text: str, labels: list[str]):
            with torch.inference_mode():
                return model.classify(text, labels, threshold=0.0)

    else:
        from fast_gliner import FastGLiFormer

        model = FastGLiFormer.from_pretrained(str(root))

        def classify(text: str, labels: list[str]):
            return model.classify(text, labels)

    def decide(text: str, task: str) -> str:
        short_to_key = {crit.short: key for key, crit in TASKS[task].items()}
        return top_label(classify(text, list(short_to_key)), short_to_key)

    return decide, {"revisions": {repo: root.name}}


def _load_slm_judge(c: Candidate, models_dir: Path, slm_llm):
    from llama_cpp import LlamaGrammar

    grammars = {
        task: LlamaGrammar.from_string(gbnf_choice(list(labels)), verbose=False)
        for task, labels in TASKS.items()
    }

    def decide(text: str, task: str) -> str:
        out = slm_llm.create_chat_completion(
            messages=judge_messages(text, task),
            grammar=grammars[task],
            max_tokens=JUDGE_MAX_TOKENS,
            temperature=0.0,
        )
        return (out["choices"][0]["message"].get("content") or "").strip()

    return decide, {"revisions": {}}


def _load_decision20(c: Candidate, models_dir: Path, slm_llm):
    """Decision 2.0 Kai through the code its repository ships, reviewed at `c.revision`
    (`trust_remote_code`), on CPU: one `choice` question per task (`system_one`)."""
    from transformers import AutoModel

    repo, files = c.repos[0]
    root = _snapshot(models_dir, repo, files, c)
    if root.name != c.revision:
        raise RuntimeError(f"instantané {root.name} chargé au lieu du commit relu {c.revision}")
    model = AutoModel.from_pretrained(str(root), trust_remote_code=True, device="cpu")
    questions = {task: decision20_questions(task) for task in TASKS}

    def decide(text: str, task: str) -> str:
        out = model.system_one(state=text, questions=questions[task])
        if not isinstance(out, dict) or out.get("error"):
            return decision20_label(out)
        return decision20_label((out.get("answers") or {}).get(task))

    info = {
        "revisions": {repo: root.name},
        "reviewed_revision": c.revision,
        "trust_remote_code": True,
    }
    return decide, info


# -- story 8: a decision model served by a local server --------------------------------------


def _http_client(base_url: str, transport=None, timeout: float = SYSTEMONE_TIMEOUT_S):
    """An `httpx` client bound to a loopback server, without the environment's proxy."""
    import httpx

    if not is_loopback_url(base_url):
        raise ValueError(
            f"serveur hors boucle locale refusé : {base_url} (boucle locale seulement)"
        )
    return httpx.Client(base_url=base_url, transport=transport, timeout=timeout, trust_env=False)


def _json_or_none(response):
    try:
        return response.json()
    except ValueError:
        return None


def _json_dict(response) -> dict:
    """The JSON object of a response, or {} (no JSON, or JSON that is not an object)."""
    data = _json_or_none(response)
    return data if isinstance(data, dict) else {}


def _http_error(response) -> str:
    data = _json_or_none(response)
    detail = data.get("error") if isinstance(data, dict) else None
    return f"HTTP {response.status_code} : {detail or response.text[:200]}"


class SystemOneClient:
    """Client of the `/v1/systemone` endpoint (Jev API): Ollama 0.35 here, llama-server for
    story 9. The base URL (loopback only) and the model are parameters; `transport` lets the
    tests answer with an `httpx.MockTransport`.

    `ask` never raises on an answer: an HTTP error or a non-JSON body comes back as
    `{"error": ...}`, which `systemone_label` turns into an error row. A transport failure
    (server gone) does raise: the measure then fails as a whole."""

    path = "/v1/systemone"

    def __init__(
        self, base_url: str, model: str, transport=None, timeout: float = SYSTEMONE_TIMEOUT_S
    ) -> None:
        self.base_url, self.model = base_url, model
        self._http = _http_client(base_url, transport, timeout)

    def body(self, state, questions: dict, keep_alive=None) -> dict:
        body = {"model": self.model, "state": state, "questions": questions}
        if keep_alive is not None:
            body["keep_alive"] = keep_alive
        return body

    def ask(self, state, questions: dict, keep_alive=None) -> dict:
        response = self._http.post(self.path, json=self.body(state, questions, keep_alive))
        if response.status_code != 200:
            return {"error": _http_error(response)}
        data = _json_or_none(response)
        return data if isinstance(data, dict) else {"error": "réponse non JSON ou non objet"}

    def decide_row(self, text: str, task: str) -> dict:
        """One bench decision: a `choice` question whose options are the task's labels; the
        label, with the probabilities and the server's `choice` kept for the row."""
        return systemone_row(self.ask(text, choice_questions(task)), task, list(TASKS[task]))

    def decide(self, text: str, task: str) -> str:
        return self.decide_row(text, task)["label"]

    def close(self) -> None:
        self._http.close()


def _processes(pids):
    """`(process, name, cmdline)` of every process, or of the given PIDs only (a full listing
    with command lines costs ~0.1 s on the target PC; a few known PIDs, a few ms)."""
    import psutil

    if pids is None:
        for proc in psutil.process_iter(["name", "cmdline"]):
            yield proc, proc.info.get("name"), proc.info.get("cmdline")
        return
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            yield proc, proc.name(), proc.cmdline()
        except psutil.Error:
            continue  # gone (the model process after `ollama stop`) or unreadable


def scan_ollama_processes(blob_sha: str, pids=None) -> list[dict]:
    """The Ollama processes (psutil), among all processes or the given PIDs: role, PID,
    RSS, peak working set (Windows), remote non-loopback endpoints and listening addresses
    of their TCP connections."""
    return [
        _process_record(proc, role)
        for proc, name, cmdline in _processes(pids)
        if (role := ollama_role(name, cmdline, blob_sha)) is not None
    ]


def _process_record(proc, role: str) -> dict:
    """Role, PID, RSS, peak working set (Windows), remote non-loopback endpoints and
    listening addresses of the TCP connections of one process."""
    import psutil

    rec = {"pid": proc.pid, "role": role}
    try:
        mem = proc.memory_info()
        rec["rss_mb"] = mem.rss >> 20
        rec["peak_mb"] = (getattr(mem, "peak_wset", 0) >> 20) or None
        conns = proc.net_connections(kind="inet")
        rec["remotes"], rec["listen"] = remote_endpoints(conns), listening_endpoints(conns)
    except psutil.Error as exc:
        rec["error"] = f"{type(exc).__name__} ({role} {proc.pid})"
    return rec


def scan_llama_server(pid: int) -> list[dict]:
    """The llama-server process the bench started, by its PID (role `server`); nothing when
    it is gone, or when the PID now names another program."""
    return [
        _process_record(proc, "server")
        for proc, name, _cmdline in _processes([pid])
        if "llama-server" in (name or "").lower()
    ]


OLLAMA_FULL_SCAN_EVERY = 8  # samples between two full listings (the rest: known PIDs only)


class ServerWatch:
    """Samples the processes that serve the model during the measure: their RSS, and their
    TCP connections before, during and after the measure. `scan(pids)` is injectable: a
    full listing (`pids` None) before, after, every `OLLAMA_FULL_SCAN_EVERY` samples and
    until the model process (`model_role`) is found; the known PIDs of `roles` in between.

    `prefix` names the report's fields (`<prefix>_rss_peak_mb`…), `roles` the processes whose
    peaks add up. Beyond `abort_mb` (their sum), `ceiling` is set and the served loader's
    `decide` stops the measure: the child's watchdog does not see these processes."""

    def __init__(
        self,
        scan,
        prefix: str,
        roles: tuple[str, ...],
        model_role: str,
        missing: str,
        method: str,
        period_s: float = OLLAMA_SAMPLE_PERIOD_S,
        abort_mb: int | None = None,
        full_listing: bool = True,
    ):
        import threading

        self.full_listing = full_listing  # False: `scan` reads one known PID, never a listing
        self.prefix, self.roles, self.model_role = prefix, roles, model_role
        self.missing, self.method, self.period_s = missing, method, period_s
        self.abort_mb = OLLAMA_ABORT_MB if abort_mb is None else abort_mb
        self.ceiling: dict | None = None
        self._scan = scan
        self._ticks = 0
        self.full_scans = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"{prefix}-watch", daemon=True)
        self._lock = threading.Lock()
        self.peaks: dict[str, int] = {}
        self.peak_sum = None
        self.runner_peak_wset = None  # the model process's peak working set (Windows)
        self.pids: dict[str, set] = {}
        self.remotes: dict[str, set] = {"before": set(), "during": set(), "after": set()}
        self.other_remotes: set = set()
        self.listen: set = set()
        self.errors: list[str] = []
        self.samples = 0
        self.runner_series: list[int] = []  # the model process's RSS over the measure

    def take(self, phase: str) -> None:
        with self._lock:
            known = sorted(set().union(*(self.pids.get(r, set()) for r in self.roles)))
            full = (
                phase != "during"
                or not self.pids.get(self.model_role)
                or self._ticks % OLLAMA_FULL_SCAN_EVERY == 0
            )
            self._ticks += 1
            self.full_scans += full and self.full_listing
        try:
            procs = self._scan(None if full else known)
        except Exception as exc:  # noqa: BLE001 - recorded: the criterion becomes unverifiable
            with self._lock:
                if len(self.errors) < 20:
                    self.errors.append(repr(exc)[:200])
            return
        with self._lock:
            self.samples += 1
            rss: dict[str, int] = {}
            for p in procs:
                role = p["role"]
                self.pids.setdefault(role, set()).add(p["pid"])
                if p.get("error") and p["error"] not in self.errors and len(self.errors) < 20:
                    self.errors.append(p["error"])
                if role in self.roles:
                    self.remotes[phase] |= set(p.get("remotes") or [])
                    self.listen |= set(p.get("listen") or [])
                    if p.get("rss_mb") is not None:
                        rss[role] = rss.get(role, 0) + p["rss_mb"]
                    if role == self.model_role and p.get("peak_mb"):
                        self.runner_peak_wset = max(self.runner_peak_wset or 0, p["peak_mb"])
                else:
                    self.other_remotes |= {f"{role} : {r}" for r in p.get("remotes") or []}
            for role, value in rss.items():
                self.peaks[role] = max(self.peaks.get(role, 0), value)
            if self.model_role in rss:  # its growth over the measure (prompt cache, leak…)
                self.runner_series.append(rss[self.model_role])
            if rss:
                now = sum(rss.values())
                self.peak_sum = max(self.peak_sum or 0, now)
                if now > self.abort_mb and self.ceiling is None:  # the decisions stop next
                    self.ceiling = {
                        "threshold_mb": self.abort_mb,
                        "rss_at_stop_mb": now,
                        "phase": phase,
                    }

    def _loop(self) -> None:
        while not self._stop.wait(self.period_s):
            self.take("during")

    def start(self) -> ServerWatch:
        self.take("before")
        self._thread.start()
        return self

    def finish(self) -> dict:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)
        self.take("after")
        return self.report()

    def report(self) -> dict:
        with self._lock:
            peaks = {role: self.peaks.get(role) for role in self.roles}
            if self.runner_peak_wset is not None:
                model = peaks.get(self.model_role)
                peaks[self.model_role] = max(model or 0, self.runner_peak_wset)
            known = [v for v in peaks.values() if v is not None]
            total = sum(known) if len(known) == len(peaks) else None
            errors = list(self.errors)  # a copy: `report` may be called more than once
            if peaks.get(self.model_role) is None:
                errors.append(self.missing)
            series = self.runner_series
            step = max(1, len(series) // 30)  # at most ~30 points, the last one kept
            points = series[::step]
            if series and (len(series) - 1) % step:
                points.append(series[-1])
            m, p = self.model_role, self.prefix
            return {
                f"{p}_rss_peak_mb": total,
                f"{p}_ceiling": self.ceiling,
                f"{p}_rss": {
                    **{f"{role}_peak_mb": value for role, value in peaks.items()},
                    f"{m}_peak_wset_mb": self.runner_peak_wset,
                    "peak_of_sum_mb": self.peak_sum,
                    "abort_threshold_mb": self.abort_mb,
                    f"{m}_series_mb": points,
                    "method": ("somme des pics (majorant)" if len(self.roles) > 1 else "pic")
                    + f" {self.method}, RSS lue toutes les "
                    f"{self.period_s} s, pic de l'ensemble de travail du processus du modèle "
                    "(Windows)",
                },
                f"{p}_processes": {role: sorted(pids) for role, pids in self.pids.items()},
                f"{p}_network": {
                    "before": sorted(self.remotes["before"]),
                    "during": sorted(self.remotes["during"]),
                    "after": sorted(self.remotes["after"]),
                    "other_processes": sorted(self.other_remotes),
                    "listen": sorted(self.listen),
                    "samples": self.samples,
                    "full_scans": self.full_scans,
                    "method": f"connexions TCP (psutil) {self.method}, par PID, avant, pendant "
                    f"(toutes les {self.period_s} s) et après la mesure ; une connexion plus "
                    "brève que la période peut échapper au relevé"
                    + (
                        f" ; liste complète des processus toutes les {OLLAMA_FULL_SCAN_EVERY} "
                        "lectures"
                        if self.full_listing
                        else " ; un seul processus, relu par son PID à chaque lecture"
                    ),
                    "errors": errors,
                },
            }


class OllamaWatch(ServerWatch):
    """The Ollama processes that serve the model (story 8): the server and the model's
    process, found by its weights blob on the command line."""

    def __init__(
        self,
        blob_sha: str,
        scan=None,
        period_s: float = OLLAMA_SAMPLE_PERIOD_S,
        abort_mb: int | None = None,
    ):
        self.blob_sha = blob_sha
        super().__init__(
            scan or (lambda pids=None: scan_ollama_processes(blob_sha, pids)),
            prefix="ollama",
            roles=("server", "runner"),
            model_role="runner",
            missing=f"processus du modèle introuvable (blob {blob_sha[:12]})",
            method="du serveur et du processus du modèle",
            period_s=period_s,
            abort_mb=abort_mb,
        )


class LlamaServerWatch(ServerWatch):
    """The llama-server the bench started (story 9): one process, by its PID, which is both
    the server and the model's process."""

    def __init__(
        self,
        pid: int,
        scan=None,
        period_s: float = OLLAMA_SAMPLE_PERIOD_S,
        abort_mb: int | None = None,
    ):
        self.pid = pid
        super().__init__(
            scan or (lambda pids=None: scan_llama_server(pid)),
            prefix="llama_server",
            roles=("server",),
            model_role="server",
            missing=f"processus llama-server introuvable (PID {pid})",
            method="du processus llama-server",
            period_s=period_s,
            abort_mb=abort_mb,
            full_listing=False,
        )


class OllamaOps:
    """The parent's side of Ollama (Ollama's own API, not `/v1/systemone`): the server is up,
    the model is pulled (pulled on `--download` only), nothing else is loaded; then
    `ollama stop` and a check of `/api/ps` (what `ollama ps` reads) once the measure is over.
    `transport`, `run` and `which` are injectable for the tests."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        transport=None,
        run=subprocess.run,
        which=None,
    ) -> None:
        import shutil

        self.base_url, self.transport, self.run = base_url, transport, run
        self.which = which or shutil.which

    def _client(self, timeout: float = 30):
        return _http_client(self.base_url, self.transport, timeout)

    def loaded(self, http) -> list[str] | None:
        """The models `/api/ps` lists, or None when its answer cannot be read (never taken
        for "nothing loaded")."""
        models = _json_dict(http.get("/api/ps")).get("models")
        if not isinstance(models, list):
            return None
        return [m.get("name") for m in models if isinstance(m, dict)]

    def pull(self, model: str) -> dict:
        """`/api/pull` (on `--download` only): its answer, or `error` when it fails (timeout,
        HTTP error, `{"error": …}`, or no `success` status)."""
        import httpx

        try:
            with self._client(OLLAMA_PULL_TIMEOUT_S) as puller:
                pulled = puller.post("/api/pull", json={"model": model, "stream": False})
        except httpx.TimeoutException as exc:
            return {
                "error": "pull_timeout",
                "message": f"téléchargement de {model} par Ollama non terminé après "
                f"{OLLAMA_PULL_TIMEOUT_S} s ({type(exc).__name__}) : relancez « ollama pull "
                f"{model} » à la main",
            }
        except httpx.TransportError as exc:
            return {
                "error": "pull_failed",
                "message": f"téléchargement de {model} interrompu ({type(exc).__name__}) : "
                f"relancez « ollama pull {model} » à la main",
            }
        data = _json_dict(pulled)
        out = data | {"http": pulled.status_code}
        if pulled.status_code != 200 or data.get("error") or data.get("status") != "success":
            detail = data.get("error") or data.get("status") or pulled.text[:200]
            return out | {
                "error": "pull_failed",
                "message": f"téléchargement de {model} refusé par Ollama (HTTP "
                f"{pulled.status_code} : {detail}) : relancez « ollama pull {model} » à la main",
            }
        return out

    def show(self, http, model: str):
        response = http.post("/api/show", json={"model": model})
        return response.status_code, _json_or_none(response)

    def preflight(self, model: str, download: bool = False) -> dict:
        import httpx

        out: dict = {"base_url": self.base_url}
        try:
            with self._client() as http:
                out["version"] = _json_dict(http.get("/api/version")).get("version")
                status, show = self.show(http, model)
                if status == 404 and download:
                    out["pull"] = self.pull(model)
                    if out["pull"].get("error"):
                        return out | {k: out["pull"][k] for k in ("error", "message")}
                    status, show = self.show(http, model)
                if status == 404:
                    return out | {
                        "error": "model_absent",
                        "message": f"modèle {model} absent d'Ollama : tirez-le une fois avec "
                        f"« ollama pull {model} » (ou relancez avec --download) ; la mesure ne "
                        "télécharge rien",
                    }
                if status != 200 or not isinstance(show, dict):
                    return out | {
                        "error": "show_failed",
                        "message": f"/api/show {model} : HTTP {status}",
                    }
                tags = _json_dict(http.get("/api/tags"))
                out["model"] = ollama_model_record(model, show, tags)
                before = self.loaded(http)
                out["loaded_before"] = before
                if before is None:
                    return out | {
                        "error": "ps_unreadable",
                        "message": "/api/ps illisible : impossible de vérifier qu'aucun modèle "
                        "n'est chargé dans Ollama ; vérifiez « ollama ps », puis relancez",
                    }
                out["other_models_loaded"] = [n for n in before if n != model]
                if model in before:  # so that the measure sees the model load
                    after = self._wait_unloaded(http, model, self.stop(model))
                    out["stopped_before"] = after
                    if after["still_loaded"]:
                        return out | {
                            "error": "still_loaded",
                            "message": f"{model} encore chargé dans Ollama après « ollama stop » "
                            f"({after.get('error') or 'déchargement non terminé'}) : déchargez-le "
                            f"(« ollama stop {model} », « ollama ps »), puis relancez",
                        }
        except httpx.TimeoutException as exc:  # up, but too slow to answer
            return out | {
                "error": "timeout",
                "message": f"serveur Ollama sur {self.base_url} sans réponse à temps "
                f"({type(exc).__name__}) : vérifiez qu'il n'est pas occupé, puis relancez",
            }
        except httpx.TransportError as exc:
            return out | {
                "error": "unreachable",
                "message": f"serveur Ollama injoignable sur {self.base_url} : lancez Ollama "
                f"(l'application, ou « ollama serve »), puis relancez la mesure "
                f"({type(exc).__name__})",
            }
        return out

    def stop(self, model: str) -> dict:
        exe = self.which("ollama")
        if not exe:
            return {"command": f"ollama stop {model}", "error": "ollama introuvable dans le PATH"}
        try:
            proc = self.run(
                [exe, "stop", model], capture_output=True, text=True, timeout=60, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"command": f"ollama stop {model}", "error": repr(exc)[:200]}
        return {"command": f"ollama stop {model}", "returncode": proc.returncode}

    def _wait_unloaded(self, http, model: str, stopped: dict) -> dict:
        """`stopped` (the result of `stop`), with what `/api/ps` lists once the asynchronous
        unload is over, or still lists after ~10 s; `still_loaded` is None (not verified) when
        `/api/ps` cannot be read."""
        for _ in range(20):
            loaded = self.loaded(http)
            if loaded is None or model not in loaded:
                break
            time.sleep(0.5)
        still = None if loaded is None else model in loaded
        return stopped | {"still_loaded": still, "loaded_after": loaded}

    def unload(self, model: str) -> dict:
        """`ollama stop <model>`, then `/api/ps`: the model must no longer be loaded."""
        import httpx

        out = self.stop(model)
        try:
            with self._client() as http:
                return self._wait_unloaded(http, model, out)
        except httpx.TransportError as exc:
            return out | {"still_loaded": None, "ps_error": type(exc).__name__}


def _load_systemone(c: Candidate, models_dir: Path, slm_llm, transport=None, scan=None):
    """A model served on `/v1/systemone` (Ollama): its process is watched from the first
    request on (the model loads then, timed as `load_s`), and `finish` stops the watch."""
    with _http_client(c.server_url, transport) as http:
        status, show = OllamaOps(c.server_url, transport).show(http, c.server_model)
    if status != 200 or not isinstance(show, dict):
        raise RuntimeError(f"/api/show {c.server_model} : HTTP {status}")
    blob = blob_sha_from_modelfile(show.get("modelfile") or "")
    client = SystemOneClient(c.server_url, c.server_model, transport)  # before the watch thread
    decide, info = _served_decisions(client, OllamaWatch(blob, scan=scan).start())
    info = {
        "systemone_api": SYSTEMONE_API,
        "server_url": c.server_url,
        "server_model": c.server_model,
        "blob_sha256": blob,
        **info,  # first_request_s: the model's load in Ollama (`load_s` adds the watch)
    }
    return decide, info


def _served_decisions(client: SystemOneClient, watch: ServerWatch):
    """The decisions of a served model, its server's processes watched (`watch` started):
    a first request (Ollama loads the model then), which must answer with probabilities;
    `decide` stops once the server processes cross the abort threshold; `finish` closes the
    client and stops the watch."""
    try:
        t0 = time.monotonic()
        first = client.ask(PROMPTS[0].text, choice_questions("cost"))
        first_s = round(time.monotonic() - t0, 2)
    except Exception:
        watch.finish()
        client.close()
        raise
    first_label = systemone_label(first, "cost", list(TASKS["cost"]))
    if first_label.startswith("erreur"):  # an error, or a 200 without usable probabilities
        watch.finish()
        client.close()
        raise RuntimeError(f"/v1/systemone : {first_label}")

    def decide(text: str, task: str) -> dict:
        if watch.ceiling:  # the server processes went beyond the abort threshold
            raise RuntimeError(f"{watch.prefix}_ceiling : {watch.ceiling}")
        return client.decide_row(text, task)

    def finish() -> dict:
        client.close()
        return watch.finish()

    return decide, {"first_answer": first, "first_request_s": first_s, "finish": finish}


def _load_llama_server(
    c: Candidate, models_dir: Path, slm_llm, server=None, transport=None, scan=None
):
    """A model served on `/v1/systemone` by the llama-server the parent started (`server`:
    its loopback URL and PID): the model is already loaded; its process is watched by PID."""
    if not server or not server.get("url") or not server.get("pid"):
        raise RuntimeError("llama-server non démarré par le parent (--server-url, --server-pid)")
    watch = LlamaServerWatch(int(server["pid"]), scan=scan).start()
    try:
        client = SystemOneClient(server["url"], c.server_model, transport)
    except Exception:
        watch.finish()
        raise
    decide, info = _served_decisions(client, watch)
    info = {
        "systemone_api": LLAMA_SYSTEMONE_API,
        "server_url": server["url"],
        "server_pid": int(server["pid"]),
        "server_model": c.server_model,
        **info,
    }
    return decide, info


LOADERS = {
    "nli_onnx": _load_nli,
    "nvidia_torch": _load_nvidia,
    "gliformer_torch": _load_gliformer,
    "gliformer_onnx": _load_gliformer,
    "slm_judge": _load_slm_judge,
    "decision20_torch": _load_decision20,
    "ollama_systemone": _load_systemone,
    "llama_systemone": _load_llama_server,
}

RAM_WATCH_PERIOD_S = 0.5


def ram_ceiling_report(rss_mb: int, attempts: list) -> dict:
    """The child's last JSON line when the memory watchdog stops it."""
    return {
        "error": "ram_ceiling",
        "rss_at_stop_mb": rss_mb,
        "ram_budget_mb": RAM_BUDGET_MB,
        "attempts": list(attempts),
    }


def start_ram_watchdog(
    attempts: list,
    budget_mb: int | None = None,
    period_s: float = RAM_WATCH_PERIOD_S,
    read_rss=None,
    emit=None,
    exit_=os._exit,
):
    """A daemon thread that reads the RSS every `period_s`: beyond `budget_mb`, it prints
    the report as the child's last JSON line, then stops the process (the shared target PC
    must not swap). Returns the thread, the event that stops it once the measure is over,
    and its state (`status` active or inactive, with the `reason` when the RSS cannot be
    read), recorded in the child's JSON."""
    import threading

    budget = RAM_BUDGET_MB if budget_mb is None else budget_mb
    read = read_rss or s12._rss_mb
    stop = threading.Event()
    state = {"status": "active", "budget_mb": budget, "period_s": period_s}

    def say(line: str) -> None:
        if emit is not None:
            emit(line)
        else:
            print(line, flush=True)  # os._exit flushes nothing

    def watch() -> None:
        while not stop.is_set():
            try:
                rss = read()
            except Exception as exc:  # noqa: BLE001 - no RSS (psutil): the measure goes on
                state.update(status="inactive", reason=repr(exc)[:200])
                return
            if rss > budget and not stop.is_set():
                try:
                    say(json.dumps(ram_ceiling_report(rss, attempts), ensure_ascii=False))
                finally:
                    exit_(0)  # stop the child even if the line cannot be written
                return
            stop.wait(period_s)

    thread = threading.Thread(target=watch, name="ram-watchdog", daemon=True)
    thread.start()
    return thread, stop, state


def _measure_child(candidate_id: str, models_dir: Path, slm: Path, server=None) -> dict:
    """`server`: the llama-server the parent started (`url`, `pid`), for story 9."""
    attempts, guard = s12._record_and_guard(allowed_hosts=[])
    # From the start: SLM included. The child only, as in story 7, for a served model too:
    # the server processes are measured by a `ServerWatch` and judged by the RAM criterion.
    _, stop_watchdog, watchdog = start_ram_watchdog(attempts)
    try:
        out = _measure(candidate_id, models_dir, slm, attempts, guard, server)
        out["ram_watchdog"] = dict(watchdog)  # its state while the measure ran
        return out
    finally:
        stop_watchdog.set()


def _loaded_modules() -> dict:
    """torch and the heavy modules loaded so far (kept on a failed measure too)."""
    return {
        "torch_loaded": "torch" in sys.modules,
        "heavy_modules_loaded": [m for m in s12.HEAVY_MODULES if m in sys.modules],
    }


def _measure(
    candidate_id: str, models_dir: Path, slm: Path, attempts: list, guard: str, server=None
) -> dict:
    c = candidate(candidate_id)
    n_ctx = slm_n_ctx(wavestack_settings())
    out: dict = {"id": c.id, "guard": guard, "slm": str(slm), "slm_n_ctx": n_ctx}
    try:
        import llama_cpp

        out["llama_cpp_version"] = getattr(llama_cpp, "__version__", None)
        t0 = time.monotonic()
        # Same parameters as WaveStack's engine (`models/engine.py`): the window, default threads.
        slm_llm = llama_cpp.Llama(model_path=str(slm), n_ctx=n_ctx, verbose=False)
        slm_llm.create_completion("Bonjour", max_tokens=1)  # weights resident, as in a turn
        out["slm_load_s"] = round(time.monotonic() - t0, 2)
        out["rss_with_slm_mb"] = s12._rss_mb()
        base = s12._baseline_rss()
        t1 = time.monotonic()
        extra = {"server": server} if c.server == "llama_server" else {}
        decide, info = LOADERS[c.backend](c, models_dir, slm_llm, **extra)
        out["load_s"] = round(time.monotonic() - t1, 2)
        finish = info.pop("finish", None)  # a served model: stops the watch of its processes
        out.update(info)
        try:
            warmup_ms, rows = run_decisions(decide)
        finally:
            if finish is not None:
                out.update(finish())
        out.update(base)
        out.update(s12._loaded_rss())
    except Exception as exc:  # noqa: BLE001 - a failed load or decision is a finding
        out.update(error=repr(exc)[:400], blocked=s12._blocked_host(exc), attempts=attempts)
        out.update(_loaded_modules())  # the SLM fields already read stay in `out`
        return out
    out["warmup_ms"] = warmup_ms
    out["rows"] = rows
    fixed = ("specialty",) if c.backend == "nvidia_torch" else ()  # level 1: fixed labels
    out.update(summarize_decisions(rows, fixed))
    out["rss_added_mb"] = s12.added_rss_mb(
        base["rss_before_load_mb"],
        base["peak_before_load_mb"],
        out["rss_peak_mb"],
        (out["rss_loaded_mb"],),
    )
    if c.server:
        out["ram_total_peak_mb"] = server_ram_total(out, c.server)
    out["versions"] = _versions(c.roots)  # the packages this very measure ran with
    out.update(_loaded_modules())
    out["attempts"] = attempts
    return out


# --------------------------------------------------------------------------
# Parent: availability, download, child, packages, verdict.
# --------------------------------------------------------------------------


def download_candidate(c: Candidate, models_dir: Path) -> dict:
    """Fetch the candidate's files under the guard (HF hosts only), proxy and system trust
    store kept, as WaveStack does (AD-15). Follows `main`, or the reviewed commit of a
    candidate that pins one; the commit is recorded."""
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    attempts, guard = s12._record_and_guard(allowed_hosts=s12.DOWNLOAD_HOSTS, strip_proxy=False)
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
    revisions, errors = {}, {}
    from huggingface_hub import snapshot_download

    for repo, files in c.repos:
        try:
            path = snapshot_download(
                repo_id=repo, cache_dir=str(hf_cache(models_dir)), **snapshot_kwargs(c, files)
            )
            revisions[repo] = Path(path).name
        except Exception as exc:  # noqa: BLE001 - recorded, the measure says what is missing
            errors[repo] = repr(exc)[:300]
    return {
        "guard": guard,
        "hosts": s12.summarize_attempts(attempts),
        "revisions": revisions,
        "errors": errors,
    }


def child_env(base: dict[str, str], models_dir: Path) -> dict[str, str]:
    """The measurement child's environment: no proxy, Hugging Face offline, Transformers'
    dynamic modules written under the bench folder, and Decision 2.0 on its default CPU path
    (no `DECISION2_*` switch: FAST, KERNELS, GRAPHS)."""
    env = dict(base)
    s12._strip_proxy_env(env)
    for name in [n for n in env if n.upper().startswith("DECISION2_")]:
        del env[name]
    env["HF_HUB_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["HF_MODULES_CACHE"] = str(models_dir / "hf_modules")
    return env


def _default_runner(c: Candidate, models_dir: Path, slm: Path, server=None) -> dict:
    env = child_env(os.environ, models_dir)
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_measure-child",
        "--candidate",
        c.id,
        "--models-dir",
        str(models_dir),
        "--slm",
        str(slm),
    ]
    if server:  # the llama-server the parent started (story 9)
        cmd += ["--server-url", server["url"], "--server-pid", str(server["pid"])]
    return s12._run_child(cmd, env, timeout=CHILD_TIMEOUT_S)


def package_rows(roots: tuple[str, ...]) -> list[dict]:
    """The installed closure of the candidate's packages, marked against the project's."""
    rows: dict[str, dict] = {}
    for root in roots:
        for d in s12.dependency_closure(root):
            rows[_norm(d["name"])] = d
    project = {d["name"] for d in s12.dependency_closure("wavestack")}
    return added_packages(sorted(rows.values(), key=lambda d: _norm(d["name"])), project)


def _versions(roots: tuple[str, ...]) -> dict:
    from importlib.metadata import PackageNotFoundError, version

    out = {}
    for root in roots:
        try:
            out[root] = version(root)
        except PackageNotFoundError:
            out[root] = None
    return out


def machine_info() -> dict:
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "measured_at": datetime.now().isoformat(timespec="minutes"),
        "target_pc": sys.platform == "win32",
        "windows_release": platform.release() if sys.platform == "win32" else None,
        "admin": _is_admin(),
        "bench_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "repo_commit": _repo_commit(),
    }
    try:
        import psutil

        info["ram_total_mb"] = psutil.virtual_memory().total >> 20
    except ImportError:
        info["ram_total_mb"] = None
    return info


def _is_admin() -> bool | None:
    """True for an elevated Windows session (criterion 1 wants none); None elsewhere."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return None


def _repo_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (proc.stdout.strip() or None) if proc.returncode == 0 else None


# Kept from a failed child: the SLM part, the modules loaded, the watchdog and its stop.
_PARTIAL_FIELDS = (
    "llama_cpp_version",
    "slm_load_s",
    "rss_with_slm_mb",
    "torch_loaded",
    "heavy_modules_loaded",
    "ram_watchdog",
    "rss_at_stop_mb",
    *(
        f"{prefix}_{field}"
        for prefix in ("ollama", "llama_server")
        for field in ("ceiling", "rss_peak_mb", "rss", "processes", "network")
    ),
)


def run_measure(
    c: Candidate,
    models_dir: Path,
    slm: Path | None,
    download: bool = False,
    runner=_default_runner,
    downloader=download_candidate,
    find_spec=importlib.util.find_spec,
    packages=package_rows,
    machine=machine_info,
    server_ops=None,
    llama_server: str | None = None,
) -> dict:
    report: dict = {"candidate": c.id, "tier": c.tier, "models_dir": str(models_dir), **machine()}
    report["command"] = command_for(c)
    report["rss_added_method"] = "pic"
    missing = missing_modules(c, find_spec)
    if missing:
        report["status"] = (
            f"non mesuré (absent : {', '.join(missing)} ; commande : {command_for(c)})"
        )
    elif slm is None:
        report["status"] = "non mesuré (SLM par défaut introuvable : --slm)"
    elif c.server == "ollama":
        report["v1_rag_rss_mb"] = v1_rag_rss_mb(wavestack_settings())
        _measure_served(c, models_dir, slm, download, runner, server_ops, report)
        report["packages"] = packages(c.roots)
    elif c.server == "llama_server":
        report["v1_rag_rss_mb"] = v1_rag_rss_mb(wavestack_settings())
        ops = server_ops or LlamaServerOps(*resolve_llama_server(llama_server))
        _measure_llama(c, models_dir, slm, download, runner, downloader, ops, report)
        report["packages"] = packages(c.roots)
    else:
        report["v1_rag_rss_mb"] = v1_rag_rss_mb(wavestack_settings())
        if download and c.repos:
            _download_into(c, models_dir, downloader, report)
        absent = [
            repo
            for repo, files in c.repos
            if not snapshot_present(models_dir, repo, files, c.revision)
        ]
        unreviewed = sorted(
            {sha for repo in absent for sha in other_snapshots(models_dir, repo, c.revision)}
        )
        if unreviewed:  # never run code shipped by a commit nobody has reviewed
            report["status"] = (
                f"non mesuré : code non relu à ce commit ({', '.join(unreviewed)}) ; "
                f"relu : {c.revision}"
            )
        elif absent:
            errors = (report.get("download") or {}).get("errors") or {}
            report["status"] = (
                f"absent ou incomplet : {', '.join(absent)} "
                "(lancer avec --download sur un poste qui a le réseau)"
                + (f" ; erreurs de téléchargement : {errors}" if errors else "")
            )
        else:
            _run_into(c, models_dir, slm, runner, report)
        report["packages"] = packages(c.roots)
    report["verdict"] = decision_verdict(c, report)
    return report


def _download_into(c: Candidate, models_dir: Path, downloader, report: dict) -> None:
    try:
        models_dir.mkdir(parents=True, exist_ok=True)
        report["download"] = downloader(c, models_dir)
    except Exception as exc:  # noqa: BLE001 - reported, the status says what is absent
        report["download"] = {"hosts": [], "errors": {"*": repr(exc)[:300]}}


def _run_into(c: Candidate, models_dir: Path, slm: Path, runner, report: dict, server=None) -> None:
    """Runs the measurement child and folds its JSON into the report."""
    try:
        if server is None:
            measured = runner(c, models_dir, slm)
        else:
            measured = runner(c, models_dir, slm, server=server)
    except Exception as exc:  # noqa: BLE001 - reported, the verdict says not measured
        measured = {"fatal": repr(exc)[:300]}
    if measured.get("fatal") or measured.get("error"):
        report["status"] = "erreur"
        report["error"] = measured.get("fatal") or measured.get("error")
        report["blocked"] = measured.get("blocked")
        report["attempts"] = measured.get("attempts", [])
        for key in _PARTIAL_FIELDS:  # what the failed child had already measured
            if key in measured:
                report[key] = measured[key]
    else:
        report.update(measured)
        report["status"] = "measured"


def _measure_served(
    c: Candidate, models_dir: Path, slm: Path, download: bool, runner, server_ops, report: dict
) -> None:
    """A model served by Ollama: the server is up and the model pulled (never implicitly),
    the child measures, then the model is unloaded (`ollama stop`, `/api/ps`) in any case.
    The model's digest and Ollama's version stand for the commit and the package versions."""
    ops = server_ops or OllamaOps(c.server_url)
    pre = ops.preflight(c.server_model, download)
    report["ollama"] = pre
    if pre.get("error"):
        report["status"] = f"non mesuré : {pre['message']}"
        report["server_error"] = pre["error"]
        return
    try:
        _run_into(c, models_dir, slm, runner, report)
    finally:
        try:
            report["ollama_unload"] = ops.unload(c.server_model)
        except Exception as exc:  # noqa: BLE001 - never masks the measure's report
            report["ollama_unload"] = {
                "command": f"ollama stop {c.server_model}",
                "error": repr(exc)[:300],
                "still_loaded": None,
            }
    model = pre.get("model") or {}
    report["revisions"] = {f"ollama/{c.server_model}": model.get("digest")}
    report["versions"] = {"ollama": pre.get("version")}


def _llama_processes(exe: Path) -> list[int]:
    """PIDs of the running llama-server processes started from `exe` (none must remain)."""
    import psutil

    target = os.path.normcase(str(exe.resolve()))
    out = []
    for proc in psutil.process_iter(["name", "exe"]):
        if "llama-server" not in (proc.info.get("name") or "").lower():
            continue
        path = proc.info.get("exe")
        if path and os.path.normcase(str(Path(path).resolve())) == target:
            out.append(proc.pid)
    return sorted(out)


def _pid_connections(pid: int) -> tuple[list[str], list[str]]:
    """Remote non-loopback endpoints and listening addresses of a process (psutil)."""
    import psutil

    conns = psutil.Process(pid).net_connections(kind="inet")
    return remote_endpoints(conns), listening_endpoints(conns)


class LlamaServerOps:
    """The parent's side of llama-server (story 9): the portable binary is there (never
    downloaded), its version and sha256; then the server started on 127.0.0.1 and a free
    port, the GGUF by local path, its connections read during its start; then stopped, in
    any case, with a check that no llama-server from this binary is left.
    `run`, `popen`, `transport`, `port`, `connections`, `remaining` are injectable."""

    def __init__(
        self,
        exe: Path,
        source: str = "",
        run=subprocess.run,
        popen=subprocess.Popen,
        transport=None,
        port=free_loopback_port,
        connections=_pid_connections,
        remaining=_llama_processes,
        start_timeout_s: float = LLAMA_START_TIMEOUT_S,
        poll_s: float = 0.2,
    ) -> None:
        self.exe, self.source, self.run, self.popen = Path(exe), source, run, popen
        self.transport, self.port, self.connections = transport, port, connections
        self.remaining, self.start_timeout_s, self.poll_s = remaining, start_timeout_s, poll_s
        self.proc = None
        self.log_path: Path | None = None
        self._log = None

    def preflight(self) -> dict:
        out: dict = {"exe": str(self.exe), "source": self.source}
        if not self.exe.is_file():
            return out | {
                "error": "binary_absent",
                "message": llama_binary_absent_message(self.exe),
            }
        try:
            proc = self.run(
                [str(self.exe), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            text = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        except (OSError, subprocess.SubprocessError) as exc:
            return out | {
                "error": "binary_failed",
                "message": f"llama-server --version a échoué ({exc!r}) : {self.exe}",
            }
        out |= parse_llama_version(text)
        out["exe_sha256"] = file_sha256(self.exe)
        impl = self.exe.with_name("llama-server-impl.dll")
        out["impl_sha256"] = file_sha256(impl) if impl.is_file() else None
        archive = self.exe.parent.parent / LLAMA_ZIP
        if archive.is_file():
            digest = file_sha256(archive)
            out["archive"] = {
                "path": str(archive),
                "sha256": digest,
                "expected_sha256": LLAMA_ZIP_SHA256,
                "sha256_ok": digest == LLAMA_ZIP_SHA256,
            }
        else:
            out["archive"] = None
        if out.get("build") != LLAMA_BUILD:
            out["warning"] = f"build {out.get('build')} au lieu de {LLAMA_BUILD}"
        return out

    def _health(self, http) -> int | None:
        import httpx

        try:
            return http.get("/health").status_code
        except httpx.TransportError:
            return None

    def _read_log(self) -> str:
        if self.log_path is None:
            return ""
        if self._log is not None:
            self._log.flush()
        try:
            return self.log_path.read_text("utf-8", errors="replace")
        except OSError:
            return ""

    def start(self, gguf: Path, alias: str, log_path: Path) -> dict:
        port = self.port()
        argv = llama_server_argv(self.exe, gguf, port, alias)
        url = f"http://127.0.0.1:{port}"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path = log_path
        self._log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - closed by stop()
        out: dict = {"argv": argv, "url": url, "port": port, "log": str(log_path)}
        t0 = time.monotonic()
        try:
            self.proc = self.popen(
                argv,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=llama_server_env(os.environ),
            )
        except OSError as exc:
            return out | {
                "error": "server_failed",
                "message": f"llama-server ne se lance pas ({exc!r}) : {self.exe}",
            }
        out["pid"] = self.proc.pid
        remotes: set = set()
        listen: set = set()
        errors: list[str] = []
        with _http_client(url, self.transport, timeout=5) as http:
            while True:
                try:
                    r, lst = self.connections(self.proc.pid)
                    remotes |= set(r)
                    listen |= set(lst)
                except Exception as exc:  # noqa: BLE001 - recorded: offline then unverifiable
                    if len(errors) < 5:
                        errors.append(repr(exc)[:200])
                status = self._health(http)
                if status == 200:
                    break
                code = self.proc.poll()
                elapsed = time.monotonic() - t0
                if code is not None or elapsed > self.start_timeout_s:
                    failed = code is not None
                    return out | {
                        "error": "server_failed" if failed else "server_timeout",
                        "message": (
                            f"llama-server s'est arrêté au démarrage (code {code})"
                            if failed
                            else f"llama-server sans réponse sur {url}/health après "
                            f"{self.start_timeout_s} s"
                        )
                        + f" ; sortie du serveur : {log_path}",
                        "returncode": code,
                        "log_excerpt": log_excerpt(self._read_log(), tail=30),
                        "startup_remotes": sorted(remotes),
                        "startup_listen": sorted(listen),
                    }
                time.sleep(self.poll_s)
        out["start_s"] = round(time.monotonic() - t0, 2)
        out["startup_remotes"] = sorted(remotes)
        out["startup_listen"] = sorted(listen)
        out["startup_errors"] = errors
        out["log_excerpt"] = log_excerpt(self._read_log())
        return out

    def stop(self) -> dict:
        """Stops the server whatever happened, then checks none is left from this binary."""
        out: dict = {"started": self.proc is not None}
        if self.proc is not None:
            out["pid"] = self.proc.pid
            killed = False
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=LLAMA_STOP_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    killed = True
                    try:
                        self.proc.wait(timeout=LLAMA_STOP_TIMEOUT_S)
                    except subprocess.TimeoutExpired as exc:  # recorded; checked just below
                        out["kill_error"] = repr(exc)[:200]
            out["returncode"] = self.proc.poll()
            out["killed"] = killed
        if self._log is not None:
            self._log.close()
            self._log = None
        try:
            left = self.remaining(self.exe)
            out["remaining_pids"] = left
            out["still_running"] = bool(left)
        except Exception as exc:  # noqa: BLE001 - recorded, never masks the report
            out["remaining_error"] = repr(exc)[:200]
            out["still_running"] = None
        return out


def gguf_absent_message(c: Candidate, errors: dict | None = None) -> str:
    repo, files = c.repos[0]
    return (
        f"GGUF absent : {repo}/{files[0]} au commit {c.revision} ; téléchargez-le une fois "
        f"avec --download ({command_for(c)}) ; la mesure ne télécharge rien d'autre"
        + (f" ; erreurs de téléchargement : {errors}" if errors else "")
    )


def _measure_llama(
    c: Candidate, models_dir: Path, slm: Path, download: bool, runner, downloader, ops, report
) -> None:
    """A model served by a portable llama-server (story 9): the binary is there (never
    downloaded), the GGUF at its pinned commit (downloaded on `--download` only); the server
    is started on the loopback, the child measures, then the server is stopped in any case.
    The GGUF's commit and sha256 and the server's build stand for the pinned code."""
    pre = ops.preflight()
    report["llama_server"] = pre
    if pre.get("error"):
        report["status"] = f"non mesuré : {pre['message']}"
        report["server_error"] = pre["error"]
        return
    repo, files = c.repos[0]
    if download and not snapshot_present(models_dir, repo, files, c.revision):
        _download_into(c, models_dir, downloader, report)
    if not snapshot_present(models_dir, repo, files, c.revision):
        errors = (report.get("download") or {}).get("errors") or {}
        report["status"] = f"non mesuré : {gguf_absent_message(c, errors)}"
        report["server_error"] = "gguf_absent"
        return
    report["gguf"] = gguf_record(c, gguf_path(models_dir, c))
    if not report["gguf"]["sha256_ok"]:  # never serve a GGUF other than the pinned one
        report["status"] = (
            f"non mesuré : GGUF non conforme : {files[0]} sha256 {report['gguf']['sha256']} au "
            f"lieu de {c.gguf_sha256} ; supprimez-le et relancez avec --download"
        )
        report["server_error"] = "gguf_mismatch"
        return

    def pinned() -> None:  # set last: the child's own (empty) `versions` must not stay
        report["revisions"] = {repo: c.revision}
        report["versions"] = {"llama-server": pre.get("version_line")}

    pinned()
    try:
        log = models_dir / "llama-server" / f"{c.id}.log"
        launch = ops.start(gguf_path(models_dir, c), c.server_model, log)
        report["llama_server_launch"] = launch
        if launch.get("error"):
            report["status"] = f"non mesuré : {launch['message']}"
            report["server_error"] = launch["error"]
            return
        server = {"url": launch["url"], "pid": launch["pid"]}
        _run_into(c, models_dir, slm, runner, report, server=server)
    finally:
        try:
            report["llama_server_stop"] = ops.stop()
        except Exception as exc:  # noqa: BLE001 - never masks the measure's report
            report["llama_server_stop"] = {"error": repr(exc)[:300], "still_running": None}
        pinned()


# --------------------------------------------------------------------------
# Output.
# --------------------------------------------------------------------------


def print_list() -> None:
    print("== Candidats du test préalable (decision-model-candidates.md)")
    print("   $SLM : GGUF du SLM par défaut ; $OUT : dossier des résultats (voir le rapport)")
    for c in CANDIDATES:
        print(f"\n-- {c.id} — {c.doc_name} (échelon {c.tier}) — licence : {c.model_license}")
        if c.office:
            print(f"   verdict d'office : {c.office} — {c.office_reason}")
        else:
            print(f"   {command_for(c)}")
        if c.revision and c.server == "llama_server":
            repo, files = c.repos[0]
            print(
                f"   GGUF {repo}/{files[0]} au commit {c.revision} (téléchargement et mesure "
                f"épinglés), sha256 {c.gguf_sha256}"
            )
        elif c.revision:
            print(f"   commit relu (téléchargement et mesure épinglés) : {c.revision}")
        if c.server == "ollama":
            print(
                f"   servi par Ollama sur {c.server_url}{SystemOneClient.path}, modèle "
                f"{c.server_model} (tiré une fois : ollama pull {c.server_model})"
            )
        elif c.server == "llama_server":
            print(
                f"   servi par llama-server {LLAMA_RELEASE} sur 127.0.0.1 (port libre)"
                f"{SystemOneClient.path}, lancé et arrêté par le banc ; binaire : "
                f"{default_llama_server()} (ou --llama-server, {LLAMA_SERVER_ENV}), jamais "
                f"téléchargé par le banc ({LLAMA_ZIP})"
            )
        if c.note:
            print(f"   note : {c.note}")


def print_measure(report: dict) -> None:
    c = candidate(report["candidate"])
    v = report["verdict"]
    where = "PC cible (Windows)" if report.get("target_pc") else "HORS PC CIBLE : indicatif"
    print(f"== {c.id} — {c.doc_name} (échelon {c.tier})")
    print(
        f"   poste : {report.get('platform')}, {report.get('cpu_count')} cœurs, "
        f"{report.get('ram_total_mb')} Mo de RAM — {where} — {report.get('measured_at')}"
    )
    if "download" in report:
        d = report["download"]
        print(
            f"   téléchargement : hôtes {d['hosts'] or 'aucun'}, erreurs {d['errors'] or 'aucune'}"
        )
    if report.get("status") == "measured":
        print(
            f"   SLM : {report.get('slm')} ({report.get('rss_with_slm_mb')} Mo chargé) ; "
            f"candidat chargé en {report.get('load_s')} s"
        )
        if c.server == "ollama":
            parts = report.get("ollama_rss") or {}
            print(
                f"   RAM : enfant {report.get('rss_peak_mb')} Mo + Ollama "
                f"{report.get('ollama_rss_peak_mb')} Mo (serveur {parts.get('server_peak_mb')}, "
                f"modèle {parts.get('runner_peak_mb')}) = {report.get('ram_total_peak_mb')} Mo"
            )
        elif c.server == "llama_server":
            print(
                f"   RAM : enfant {report.get('rss_peak_mb')} Mo + llama-server "
                f"{report.get('llama_server_rss_peak_mb')} Mo = "
                f"{report.get('ram_total_peak_mb')} Mo"
            )
        print(
            f"   accord indicatif avec l'étiquette attendue : coût "
            f"{report['agreement']['cost']}, spécialité {report['agreement']['specialty']}"
        )
        for p in [p for p in report.get("packages", []) if p.get("added")]:
            print(f"   paquet ajouté : {p['name']} {p['version']} — {p['license']} ({p['class']})")
    else:
        print(f"   {report.get('status')} {report.get('error', '')}".rstrip())
    if "ollama_unload" in report:
        u = report["ollama_unload"]
        print(
            f"   fin : {u.get('command')} — encore chargé : {u.get('still_loaded')}"
            + (f" ({u['error']})" if u.get("error") else "")
        )
    if "llama_server_stop" in report:
        u = report["llama_server_stop"]
        print(
            f"   fin : llama-server arrêté (PID {u.get('pid')}, code {u.get('returncode')}) — "
            f"encore lancé : {u.get('still_running')}"
            + (f" ({u['error']})" if u.get("error") else "")
        )
    if report.get("server_error"):  # the server's output, when it did not start
        for line in (report.get("llama_server_launch") or {}).get("log_excerpt") or []:
            print(f"   | {line}")
    print(f"\n== Verdict : {v['status'].upper()} — {v['reason']}")
    for x in v["criteria"]:
        mark = {True: "ok", False: "KO", None: "--"}[x["ok"]]
        print(f"   [{mark}] {x['label']} — {x['detail']}")


# --------------------------------------------------------------------------
# Entry point.
# --------------------------------------------------------------------------


def _default_models_dir() -> str:
    return str(Path.home() / ".cache" / "wavestack-bench")


def _slm_search_dir() -> Path:
    try:
        from wavestack.config import models_dir

        return models_dir()
    except ImportError:
        return Path(_default_models_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Banc de la story 6 de la V2 (modèles de décision)."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="candidats, commandes et verdicts d'office")
    p_d10 = sub.add_parser("decision10", help="relevé de Decision 1.0 (GGUF, ONNX, chemin CPU)")
    p_d10.add_argument("--checked-on", required=True)
    p_d10.add_argument("--source", required=True)
    p_d10.add_argument("--gguf", default="")
    p_d10.add_argument("--onnx", default="")
    p_d10.add_argument("--cpu", default="")
    p_d10.add_argument("--out")
    p_m = sub.add_parser("measure", help="mesure un candidat à côté du SLM par défaut")
    p_m.add_argument("candidate")
    p_m.add_argument("--slm")
    p_m.add_argument("--models-dir", default=_default_models_dir())
    p_m.add_argument(
        "--download",
        action="store_true",
        help="télécharge le modèle s'il manque (Hugging Face, ou ollama pull pour un modèle "
        "servi) ; sans cette option, rien n'est téléchargé",
    )
    p_m.add_argument(
        "--llama-server",
        help=f"chemin de llama-server.exe (défaut : {LLAMA_SERVER_ENV}, sinon "
        f"{default_llama_server()}) ; jamais téléchargé par le banc",
    )
    p_m.add_argument("--out")
    p_m.add_argument("--json", action="store_true")
    p_c = sub.add_parser("_measure-child")
    p_c.add_argument("--candidate", required=True)
    p_c.add_argument("--models-dir", required=True)
    p_c.add_argument("--slm", required=True)
    p_c.add_argument("--server-url")
    p_c.add_argument("--server-pid", type=int)
    args = parser.parse_args(argv)
    try:  # French text on a Windows console or a redirected file
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    if args.command == "_measure-child":
        server = {"url": args.server_url, "pid": args.server_pid} if args.server_url else None
        extra = {"server": server} if server else {}
        result = _measure_child(args.candidate, Path(args.models_dir), Path(args.slm), **extra)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    problems = check_prompts()
    if problems:
        print("\n".join(problems))
        return 1
    if args.command == "list":
        print_list()
        return 0
    if args.command == "decision10":
        try:
            verdict = decision10_verdict(
                args.checked_on, args.source, args.gguf, args.onnx, args.cpu
            )
        except ValueError as exc:
            print(f"Relevé incomplet : {exc}")
            return 2
        print(f"== Decision 1.0 : {verdict['status'].upper()} — {verdict['reason']}")
        _write_out(args.out, {"candidate": "decision10", **machine_info(), "verdict": verdict})
        return 0

    unknown = unknown_candidate_message(args.candidate)
    if unknown:
        print(unknown)
        return 2
    c = candidate(args.candidate)
    if c.office or c.backend is None:
        print(f"{c.id} ne se mesure pas : {command_for(c)}")
        return 2
    slm = None
    if not missing_modules(c):
        slm, error = resolve_slm(args.slm, _slm_search_dir())
        if error:
            print(error)
            return 2
    report = run_measure(
        c, Path(args.models_dir), slm, download=args.download, llama_server=args.llama_server
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print_measure(report)
    _write_out(args.out, report)  # after the printout: a bad path never loses the measure
    # Ollama down, model not pulled, or the model still loaded after the measure; llama-server
    # absent, failing to start or still running after the measure; GGUF absent or not the
    # pinned one. Not verified (None) counts as left or loaded.
    stop, unload = report.get("llama_server_stop"), report.get("ollama_unload")
    left = stop is not None and stop.get("still_running") is not False
    loaded = unload is not None and unload.get("still_loaded") is not False
    return 2 if report.get("server_error") or left or loaded else 0


def _write_out(path: str | None, report: dict) -> None:
    """UTF-8 JSON file (a PowerShell `>` would write UTF-16). Messages go to stderr, so that
    `--json` keeps a parseable stdout."""
    if not path:
        return
    out = Path(path)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        print(f"   écriture impossible dans {out} : {exc} ($OUT est-il défini ?)", file=sys.stderr)
        return
    print(f"   résultat écrit dans {out}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
