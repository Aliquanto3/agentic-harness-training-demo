"""V2 story 6 benchmark: the prior test of the decision models (CAP-6).

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
# Candidates. Facts read on the Hugging Face model cards on 2026-10-01 (HF MCP, no
# download): licence, files, labels. Each `doc_name` is the first cell of its row in
# `decision-model-candidates.md`.
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


_NLI_MODULES = ("onnxruntime", "tokenizers", "numpy", "huggingface_hub")
# tokenizers and huggingface-hub only come with the `compression` extra: not the core project.
_NLI_PACKAGES = ("onnxruntime", "tokenizers", "huggingface-hub")

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
    prompt through both tasks, timed one by one."""
    t0 = clock()
    for task in TASKS:
        decide(PROMPTS[0].text, task)
    warmup_ms = round((clock() - t0) * 1000, 1)
    rows = []
    for p in PROMPTS:
        for task in TASKS:
            t1 = clock()
            label = decide(p.text, task)
            rows.append(
                {
                    "prompt": p.id,
                    "task": task,
                    "label": label,
                    "expected": p.expected(task),
                    "ms": round((clock() - t1) * 1000, 1),
                }
            )
    return warmup_ms, rows


def agreement(rows: list[dict], task: str, fixed: bool = False) -> str:
    """Indicative agreement with the expected labels; `fixed`: the model answers with its own
    labels for this task (level 1), so there is nothing to compare."""
    if fixed:
        return "sans objet (étiquettes fixes du modèle)"
    task_rows = [r for r in rows if r["task"] == task]
    hits = sum(1 for r in task_rows if r["label"] == r["expected"])
    return f"{hits}/{len(task_rows)}"


def summarize_decisions(rows: list[dict], fixed_tasks: tuple[str, ...] = ()) -> dict:
    times = [r["ms"] for r in rows]
    return {
        "decisions": len(rows),
        "latency_median_ms": round(statistics.median(times), 1) if times else None,
        "latency_max_ms": max(times) if times else None,
        "agreement": {task: agreement(rows, task, task in fixed_tasks) for task in TASKS},
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
    criteria.append(
        {
            "id": "cpu_windows",
            "label": "CPU sous Windows 11, sans droits admin",
            "ok": cpu_ok,
            "detail": cpu_detail,
        }
    )
    total, added = report.get("rss_peak_mb"), report.get("rss_added_mb")
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
            "detail": f"pic total {total} Mo (SLM chargé : {report.get('rss_with_slm_mb')} Mo), "
            f"ajouté par le candidat {added} Mo au pic{rag_txt}",
        }
    )
    med, mx = report.get("latency_median_ms"), report.get("latency_max_ms")
    if c.backend == "slm_judge":
        lat_ok, lat_label = med is not None, "Latence d'une décision (référence du repli)"
    else:
        lat_ok = med is not None and med <= LATENCY_MEDIAN_MAX_MS and mx <= LATENCY_MAX_MS
        lat_label = f"Latence : médiane ≤ {LATENCY_MEDIAN_MAX_MS} ms, maximum ≤ {LATENCY_MAX_MS} ms"
    criteria.append(
        {
            "id": "latency",
            "label": lat_label,
            "ok": lat_ok,
            "detail": f"médiane {med} ms, maximum {mx} ms sur {report.get('decisions')} "
            f"décisions (échauffement {report.get('warmup_ms')} ms, chargement "
            f"{report.get('load_s')} s)",
        }
    )
    hosts = s12.summarize_attempts(report.get("attempts", []))
    criteria.append(
        {
            "id": "offline",
            "label": "Hors ligne : aucune tentative réseau sous la garde d'AD-15",
            "ok": not hosts and not report.get("blocked"),
            "detail": f"hôtes tentés : {hosts or 'aucun'}",
        }
    )
    # The measure follows `main`: what it pins is the commit and the package versions it
    # records, to be copied into decision-model-candidates.md for a retained candidate.
    revisions = report.get("revisions") or {}
    versions = report.get("versions") or {}
    pinned = (
        all(is_commit_sha(v) for v in revisions.values())
        and (bool(revisions) or not c.repos)
        and all(versions.get(root) for root in c.roots)
    )
    criteria.append(
        {
            "id": "pinned",
            "label": "Code relu et figé : commit et versions consignés, pas de trust_remote_code",
            "ok": pinned,
            "detail": f"commits {revisions or 'aucun (pas de dépôt)'} ; versions "
            f"{versions or 'aucune'} ; code : {c.remote_code}",
        }
    )
    packages = [p for p in report.get("packages", []) if p.get("added")]
    forbidden = [f"{p['name']} ({p['license']})" for p in packages if p["class"] == "forbidden"]
    unknown = [f"{p['name']} ({p['license']})" for p in packages if p["class"] == "unknown"]
    model_class = license_class(c)
    criteria.append(
        {
            "id": "license",
            "label": "Licences compatibles avec une remise du code (NFR-10)",
            "ok": model_class == "ok" and not forbidden and not unknown,
            "forbidden": model_class == "forbidden" or bool(forbidden),
            "detail": f"modèle : {c.model_license} ({model_class}) ; {len(packages)} paquet(s) "
            f"ajouté(s) ; interdites : {forbidden or 'aucune'} ; à vérifier : "
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

    ko = [x for x in criteria if x["ok"] is False]
    blocking = [x for x in ko if x["id"] in BLOCKING or x.get("forbidden")]
    if c.backend == "slm_judge":
        # The fallback loads nothing more: it holds if it decides offline, within the budget.
        status = "à revoir" if blocking else "repli (référence)"
    elif blocking:
        status = "écarté"
    elif ko:
        status = "à surveiller"
    else:
        status = "retenu"
    reason = "; ".join(x["label"] for x in (blocking or ko)) or "tous les critères passent"
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


def snapshot_present(models_dir: Path, repo: str, files: tuple[str, ...] = ()) -> bool:
    """A snapshot of `repo` holds every file the measure needs (a partial download is absent)."""
    snapshots = hf_cache(models_dir) / f"models--{repo.replace('/', '--')}" / "snapshots"
    if not snapshots.is_dir():
        return False
    return any(all((snap / f).is_file() for f in files) for snap in snapshots.iterdir())


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


def _snapshot(models_dir: Path, repo: str, files: tuple[str, ...]) -> Path:
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=repo,
            allow_patterns=list(files),
            cache_dir=str(hf_cache(models_dir)),
            local_files_only=True,
        )
    )


def _load_nli(c: Candidate, models_dir: Path, slm_llm):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    repo, files = c.repos[0]
    root = _snapshot(models_dir, repo, files)
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
        feeds = {
            "input_ids": np.array([e.ids for e in encs], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encs], dtype=np.int64),
            "token_type_ids": np.array([e.type_ids for e in encs], dtype=np.int64),
        }
        logits = session.run(None, {k: v for k, v in feeds.items() if k in names})[0]
        return pick_nli_label(keys, logits.tolist(), entail)

    return decide, {"revisions": {repo: root.name}, "onnx_inputs": sorted(names)}


def _load_nvidia(c: Candidate, models_dir: Path, slm_llm):
    import torch
    from safetensors.torch import load_file
    from tokenizers import Tokenizer
    from transformers import DebertaV2Config, DebertaV2Model

    (repo, files), (backbone_repo, backbone_files) = c.repos
    root = _snapshot(models_dir, repo, files)
    backbone_root = _snapshot(models_dir, backbone_repo, backbone_files)
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
    root = _snapshot(models_dir, repo, files)
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


LOADERS = {
    "nli_onnx": _load_nli,
    "nvidia_torch": _load_nvidia,
    "gliformer_torch": _load_gliformer,
    "gliformer_onnx": _load_gliformer,
    "slm_judge": _load_slm_judge,
}


def _measure_child(candidate_id: str, models_dir: Path, slm: Path) -> dict:
    attempts, guard = s12._record_and_guard(allowed_hosts=[])
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
        decide, info = LOADERS[c.backend](c, models_dir, slm_llm)
        out["load_s"] = round(time.monotonic() - t1, 2)
        out.update(info)
        warmup_ms, rows = run_decisions(decide)
        out.update(base)
        out.update(s12._loaded_rss())
    except Exception as exc:  # noqa: BLE001 - a failed load or decision is a finding
        out.update(error=repr(exc)[:400], blocked=s12._blocked_host(exc), attempts=attempts)
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
    out["versions"] = _versions(c.roots)  # the packages this very measure ran with
    out["torch_loaded"] = "torch" in sys.modules
    out["heavy_modules_loaded"] = [m for m in s12.HEAVY_MODULES if m in sys.modules]
    out["attempts"] = attempts
    return out


# --------------------------------------------------------------------------
# Parent: availability, download, child, packages, verdict.
# --------------------------------------------------------------------------


def download_candidate(c: Candidate, models_dir: Path) -> dict:
    """Fetch the candidate's files under the guard (HF hosts only), proxy and system trust
    store kept, as WaveStack does (AD-15). Follows `main`; the commit is recorded."""
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
                repo_id=repo, allow_patterns=list(files), cache_dir=str(hf_cache(models_dir))
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


def _default_runner(c: Candidate, models_dir: Path, slm: Path) -> dict:
    env = dict(os.environ)
    s12._strip_proxy_env(env)
    env["HF_HUB_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
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
    else:
        report["v1_rag_rss_mb"] = v1_rag_rss_mb(wavestack_settings())
        if download and c.repos:
            try:
                models_dir.mkdir(parents=True, exist_ok=True)
                report["download"] = downloader(c, models_dir)
            except Exception as exc:  # noqa: BLE001 - reported, the status says what is absent
                report["download"] = {"hosts": [], "errors": {"*": repr(exc)[:300]}}
        absent = [repo for repo, files in c.repos if not snapshot_present(models_dir, repo, files)]
        if absent:
            errors = (report.get("download") or {}).get("errors") or {}
            report["status"] = (
                f"absent ou incomplet : {', '.join(absent)} "
                "(lancer avec --download sur un poste qui a le réseau)"
                + (f" ; erreurs de téléchargement : {errors}" if errors else "")
            )
        else:
            try:
                measured = runner(c, models_dir, slm)
            except Exception as exc:  # noqa: BLE001 - reported, the verdict says not measured
                measured = {"fatal": repr(exc)[:300]}
            if measured.get("fatal") or measured.get("error"):
                report["status"] = "erreur"
                report["error"] = measured.get("fatal") or measured.get("error")
                report["blocked"] = measured.get("blocked")
                report["attempts"] = measured.get("attempts", [])
            else:
                report.update(measured)
                report["status"] = "measured"
        report["packages"] = packages(c.roots)
    report["verdict"] = decision_verdict(c, report)
    return report


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
        print(
            f"   accord indicatif avec l'étiquette attendue : coût "
            f"{report['agreement']['cost']}, spécialité {report['agreement']['specialty']}"
        )
        for p in [p for p in report.get("packages", []) if p.get("added")]:
            print(f"   paquet ajouté : {p['name']} {p['version']} — {p['license']} ({p['class']})")
    else:
        print(f"   {report.get('status')} {report.get('error', '')}".rstrip())
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
    p_m.add_argument("--download", action="store_true")
    p_m.add_argument("--out")
    p_m.add_argument("--json", action="store_true")
    p_c = sub.add_parser("_measure-child")
    p_c.add_argument("--candidate", required=True)
    p_c.add_argument("--models-dir", required=True)
    p_c.add_argument("--slm", required=True)
    args = parser.parse_args(argv)
    try:  # French text on a Windows console or a redirected file
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    if args.command == "_measure-child":
        result = _measure_child(args.candidate, Path(args.models_dir), Path(args.slm))
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
    report = run_measure(c, Path(args.models_dir), slm, download=args.download)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print_measure(report)
    _write_out(args.out, report)  # after the printout: a bad path never loses the measure
    return 0


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
