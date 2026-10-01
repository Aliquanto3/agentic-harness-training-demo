"""Story 12 benchmark: Headroom offline check, embedding and reranking candidates.

Never adds a dependency to the project: measurement packages come from
`uv run --with ...`. Run from the repository root:

    uv run --with headroom-ai==0.38.0 python tools/bench/story12_bench.py headroom
    uv run --with huggingface-hub --with fastembed \\
        python tools/bench/story12_bench.py embed --download

Every measurement runs in a fresh child process (clean RSS) that installs the
project network guard (AD-15) before any third-party import, with the proxy
variables removed (story 1e), and records every `socket.getaddrinfo` and
`socket.connect` attempt. Only the standard library is imported at module
level, so `tests/test_story12_bench.py` can test the pure logic.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

HEADROOM_VERSION = "0.38.0"
# Headroom's own token count, in both variants: the same model as the adapter
# (`wavestack.compression.headroom_adapter.COUNTING_MODEL`, checked equal by
# `tests/test_story12_bench.py`; only the standard library is imported here).
# `cl100k_base` is in every copy of litellm; `o200k_base` (`gpt-4o`) was missing
# on the target PC, and tiktoken tried to download it (lot F).
COUNTING_MODEL = "gpt-4"
PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy")
HEAVY_MODULES = ("torch", "transformers", "onnxruntime", "sentence_transformers")
HEAVY_DISTRIBUTIONS = ("torch", "transformers", "onnxruntime", "sentence-transformers")

# Verdict thresholds (Design Notes of the story; to validate on the target PC).
HEADROOM_RSS_BUDGET_MB = 300
EMBED_RECALL_MIN = 0.75
EMBED_RSS_BUDGET_MB = 600
RERANK_RSS_BUDGET_MB = 800

# Configured variant: set before `import headroom` (AD-15 adoption rule).
# TIKTOKEN_CACHE_DIR is added at run time: the cache vendored by litellm.
HEADROOM_OFFLINE_ENV = {
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    "HEADROOM_OFFLINE": "1",
    "HEADROOM_BEACON": "off",
    "HEADROOM_UPDATE_CHECK": "off",
    "DO_NOT_TRACK": "1",
    "HF_HUB_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_XET": "1",
}
HEADROOM_ENV_NAMES = (*HEADROOM_OFFLINE_ENV, "TIKTOKEN_CACHE_DIR", "CUSTOM_TIKTOKEN_CACHE_DIR")

DOWNLOAD_HOSTS = ["huggingface.co", "*.hf.co"]

OK_LICENSE_TOKENS = (
    "MIT",
    "BSD",
    "APACHE",
    "PSF",
    "PYTHON SOFTWARE FOUNDATION",
    "MPL",
    "MOZILLA",
    "ISC",
    "CNRI",
    "UNLICENSE",
    "ZLIB",
)
# Substrings that forbid a licence (NFR-10); "NC", "BSL" and "SSPL" are matched as words.
FORBIDDEN_LICENSE_TOKENS = (
    "AGPL",
    "NON-COMMERCIAL",
    "NONCOMMERCIAL",
    "BUSINESS SOURCE",
    "PROPRIETARY",
    "GEMMA",
)
FORBIDDEN_LICENSE_WORDS = {"NC", "BSL", "SSPL", "GPL", "GPLV2", "GPLV3", "GPL-2.0", "GPL-3.0"}


# --------------------------------------------------------------------------
# French mini dataset (non confidential, NFR-11): one gold document per query,
# paraphrased with little lexical overlap.
# --------------------------------------------------------------------------

DOCUMENTS: dict[str, str] = {
    "loire": (
        "La Loire est le plus long fleuve de France : elle parcourt environ 1 000 kilomètres "
        "du mont Gerbier-de-Jonc jusqu'à l'océan Atlantique, près de Saint-Nazaire."
    ),
    "baguette": (
        "La baguette de tradition française ne contient que de la farine, de l'eau, du sel "
        "et de la levure ou du levain, sans aucun additif."
    ),
    "mfa": (
        "L'authentification multifacteur exige au moins deux preuves d'identité distinctes, "
        "par exemple un mot de passe et un code reçu sur le téléphone."
    ),
    "rgpd": (
        "Le RGPD impose de notifier une violation de données personnelles à la CNIL dans un "
        "délai de 72 heures après en avoir pris connaissance."
    ),
    "photosynthese": (
        "La photosynthèse permet aux plantes de transformer la lumière du soleil, l'eau et le "
        "dioxyde de carbone en sucres, en rejetant de l'oxygène."
    ),
    "tour_eiffel": (
        "La tour Eiffel a été construite pour l'Exposition universelle de 1889 et mesure "
        "aujourd'hui environ 330 mètres avec ses antennes."
    ),
    "sauvegarde": (
        "La règle 3-2-1 recommande de conserver trois copies des données, sur deux supports "
        "différents, dont une hors site."
    ),
    "velo": (
        "Le vélo à assistance électrique ajoute un moteur qui aide le cycliste tant qu'il "
        "pédale, jusqu'à 25 km/h en Europe."
    ),
    "hebergement": (
        "Un modèle de langage exécuté sur le poste de l'utilisateur ne transmet pas les "
        "requêtes à un fournisseur externe, contrairement à un modèle appelé par API."
    ),
    "abeilles": (
        "Les abeilles indiquent l'emplacement des fleurs à leurs congénères par une danse en "
        "huit, dite danse frétillante."
    ),
}

QUERIES: list[tuple[str, str]] = [
    ("Quel cours d'eau français est le plus long ?", "loire"),
    ("Quels ingrédients a-t-on le droit de mettre dans un pain tradition ?", "baguette"),
    ("Comment renforcer la connexion à un compte au-delà du simple secret ?", "mfa"),
    (
        "Combien de temps une entreprise a-t-elle pour signaler une fuite d'informations "
        "à l'autorité de contrôle ?",
        "rgpd",
    ),
    ("Comment les végétaux fabriquent-ils leur nourriture grâce au soleil ?", "photosynthese"),
    (
        "Pour quel événement a-t-on bâti le monument métallique le plus célèbre de Paris ?",
        "tour_eiffel",
    ),
    (
        "Quelle méthode conseille-t-on pour ne pas perdre ses fichiers après un sinistre ?",
        "sauvegarde",
    ),
    ("Jusqu'à quelle vitesse un moteur peut-il épauler quelqu'un sur un VAE ?", "velo"),
    (
        "Pourquoi faire tourner une IA en local protège-t-il la confidentialité des questions ?",
        "hebergement",
    ),
    (
        "Comment les insectes d'une ruche s'indiquent-ils où trouver de la nourriture ?",
        "abeilles",
    ),
]


def check_dataset() -> list[str]:
    """Problems in the mini dataset (empty list when it is consistent)."""
    problems = []
    for query, gold in QUERIES:
        if gold not in DOCUMENTS:
            problems.append(f"requête sans document de référence : {query!r} -> {gold!r}")
    golds = [gold for _, gold in QUERIES]
    if len(set(golds)) != len(golds):
        problems.append("deux requêtes visent le même document")
    return problems


def ranks_of_gold(scores: list[list[float]], doc_ids: list[str], golds: list[str]) -> list[int]:
    """1-based rank of each gold document, from one score row per query (higher is better)."""
    ranks = []
    for row, gold in zip(scores, golds, strict=True):
        order = sorted(range(len(doc_ids)), key=lambda i: row[i], reverse=True)
        ranks.append(1 + [doc_ids[i] for i in order].index(gold))
    return ranks


def recall_at(ranks: list[int], k: int) -> float:
    return round(sum(1 for r in ranks if r <= k) / len(ranks), 3) if ranks else 0.0


def mrr(ranks: list[int]) -> float:
    return round(sum(1 / r for r in ranks) / len(ranks), 3) if ranks else 0.0


# --------------------------------------------------------------------------
# Candidates. Facts read on the Hugging Face model cards on 2026-09-26 (HF MCP):
# licence, file size, dimension, languages. Not measured here.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    id: str
    role: str  # "embedding" | "reranker"
    backend: str  # "llama_cpp" | "fastembed"
    repo: str
    filename: str
    license: str
    size_mb: int
    dim: int | None
    french: str
    pooling: str  # "cls" | "mean" | "last" | "rank" | "onnx"
    query_prefix: str = ""
    doc_prefix: str = ""
    suffix_special: str = ""
    note: str = ""


CANDIDATES: list[Candidate] = [
    Candidate(
        id="granite107m_q8",
        role="embedding",
        backend="llama_cpp",
        repo="bartowski/granite-embedding-107m-multilingual-GGUF",
        filename="granite-embedding-107m-multilingual-Q8_0.gguf",
        license="Apache-2.0",
        size_mb=121,
        dim=384,
        french="oui, dans les 12 langues de la carte IBM",
        pooling="cls",
        note="IBM (ibm-granite), XLM-RoBERTa, quantifié avec llama.cpp par bartowski",
    ),
    Candidate(
        id="bgem3_q4km",
        role="embedding",
        backend="llama_cpp",
        repo="gpustack/bge-m3-GGUF",
        filename="bge-m3-Q4_K_M.gguf",
        license="MIT",
        size_mb=438,
        dim=1024,
        french="oui (multilingue, 100+ langues)",
        pooling="cls",
        note="BAAI, XLM-RoBERTa large, plus lourd, qualité de référence",
    ),
    Candidate(
        id="qwen3emb06_q8",
        role="embedding",
        backend="llama_cpp",
        repo="Qwen/Qwen3-Embedding-0.6B-GGUF",
        filename="Qwen3-Embedding-0.6B-Q8_0.gguf",
        license="Apache-2.0",
        size_mb=639,
        dim=1024,
        french="oui (multilingue, 100+ langues)",
        pooling="last",
        query_prefix=(
            "Instruct: Given a web search query, retrieve relevant passages that answer "
            "the query\nQuery: "
        ),
        suffix_special="<|endoftext|>",
        note="GGUF officiel Qwen, décodeur 0.6B : le plus lent des trois",
    ),
    Candidate(
        id="bgererank_m3_q4km",
        role="reranker",
        backend="llama_cpp",
        repo="gpustack/bge-reranker-v2-m3-GGUF",
        filename="bge-reranker-v2-m3-Q4_K_M.gguf",
        license="Apache-2.0",
        size_mb=438,
        dim=None,
        french="oui (multilingue)",
        pooling="rank",
        note="seul reranker multilingue Apache avec un GGUF de llama.cpp principal",
    ),
    Candidate(
        id="fe_minilm_multi",
        role="embedding",
        backend="fastembed",
        repo="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        filename="(catalogue fastembed, ONNX quantifié qdrant)",
        license="Apache-2.0",
        size_mb=220,
        dim=384,
        french="oui (50+ langues)",
        pooling="onnx",
        note="repli fastembed, dans le catalogue",
    ),
    Candidate(
        id="fe_mmarco_rerank",
        role="reranker",
        backend="fastembed",
        repo="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        filename="onnx/model_quint8_avx2.onnx",
        license="Apache-2.0",
        size_mb=118,
        dim=None,
        french="oui (fr dans mMARCO)",
        pooling="onnx",
        note="repli fastembed, modèle ajouté par add_custom_model (catalogue sans reranker "
        "multilingue compatible : jina v2 est CC-BY-NC-4.0)",
    ),
]

EXCLUDED = [
    ("jinaai/jina-reranker-v2-base-multilingual", "CC-BY-NC-4.0 : non commercial (NFR-10)"),
    ("google/embeddinggemma-300m", "licence Gemma, restrictive (NFR-10)"),
    (
        "Alibaba-NLP/gte-multilingual-reranker-base",
        "GGUF lisible par llama-box seulement, pas par llama.cpp principal",
    ),
    (
        "Qwen/Qwen3-Reranker-0.6B",
        "gabarit de reranking à reproduire à la main dans llama-cpp-python ; GGUF communautaires",
    ),
    (
        "cstr/multilingual-e5-small-GGUF",
        "conversion faite pour CrispEmbed : « Failed to load model » avec llama-cpp-python "
        "0.3.35 (PC cible, 2026-09-27)",
    ),
]

RECOMMENDED = {"embedding": "granite107m_q8", "reranker": "bgererank_m3_q4km"}
# Former candidates, so `embed --only` says why they are gone.
REMOVED = {
    "e5small_q8": "retiré des candidats : ne se charge pas avec llama-cpp-python 0.3.35 "
    "(PC cible, 2026-09-27)",
}


def unknown_candidates_message(only: list[str] | None) -> str | None:
    """French message naming the ids of `--only` that are not candidates, else None."""
    known = {c.id for c in CANDIDATES}
    unknown = [i for i in only or [] if i not in known]
    if not unknown:
        return None
    lines = [
        f"Candidat inconnu : {i}" + (f" ({REMOVED[i]})" if i in REMOVED else "") for i in unknown
    ]
    lines.append(f"Candidats : {', '.join(c.id for c in CANDIDATES)}.")
    return "\n".join(lines)


def candidate(candidate_id: str) -> Candidate:
    for c in CANDIDATES:
        if c.id == candidate_id:
            return c
    raise KeyError(candidate_id)


# --------------------------------------------------------------------------
# Pure helpers: licences, network attempts, strace, verdicts.
# --------------------------------------------------------------------------


def classify_license(text: str) -> str:
    """'ok', 'forbidden' or 'unknown' for a licence string (NFR-10)."""
    upper = (text or "").upper()
    words = set(re.findall(r"[A-Z0-9.+]+(?:-[A-Z0-9.+]+)*", upper))
    words |= {part for w in words for part in w.split("-")} | {w.rstrip("+") for w in words}
    if "LGPL" in upper or "LESSER" in upper:
        return "unknown"  # LGPL: acceptable for an unmodified dependency, to check by hand
    if any(tok in upper for tok in FORBIDDEN_LICENSE_TOKENS) or words & FORBIDDEN_LICENSE_WORDS:
        return "forbidden"
    if "GENERAL PUBLIC" in upper or "AFFERO" in upper:
        return "forbidden"
    if any(tok in upper for tok in OK_LICENSE_TOKENS):
        return "ok"
    return "unknown"


def _is_loopback(host: str) -> bool:
    return host in {"localhost", "::1"} or host.startswith("127.")


def summarize_attempts(attempts: list[list[str]]) -> list[str]:
    """Distinct non-loopback destinations from recorded (event, host) attempts."""
    hosts = {host for _event, host in attempts if host and not _is_loopback(host)}
    return sorted(hosts)


_STRACE_IPV4 = re.compile(r'sin_port=htons\((\d+)\), sin_addr=inet_addr\("([\d.]+)"\)')
_STRACE_IPV6 = re.compile(r'sin6_port=htons\((\d+)\).*?inet_pton\(AF_INET6, "([^"]+)"')


def parse_strace_connects(text: str) -> list[str]:
    """Non-loopback `host:port` targets of `connect()` in an strace log."""
    targets = set()
    for line in text.splitlines():
        if "connect(" not in line or "AF_UNIX" in line or "AF_NETLINK" in line:
            continue
        match = _STRACE_IPV4.search(line) or _STRACE_IPV6.search(line)
        if match:
            port, host = match.groups()
            if not _is_loopback(host):
                targets.add(f"{host}:{port}")
    return sorted(targets)


def headroom_verdict(report: dict) -> dict:
    """Five criteria of the story, all required, from the parent's report."""
    conf = report.get("configured") or {}
    closure = report.get("closure") or []
    criteria = []

    py_hosts = summarize_attempts(conf.get("attempts", []))
    native = conf.get("native_connects")
    net_ok = not py_hosts and not native and not conf.get("fatal")
    native_txt = (
        "natif non observé (strace absent)"
        if native is None
        else f"{len(native)} connexion(s) native(s)"
    )
    criteria.append(
        {
            "id": "network",
            "label": "Hors ligne, aucune tentative réseau (import et compression)",
            "ok": net_ok,
            "detail": f"{len(py_hosts)} hôte(s) Python {py_hosts or ''}, {native_txt}".strip(),
        }
    )

    heavy_loaded = conf.get("heavy_modules_loaded", [])
    heavy_installed = [d["name"] for d in closure if d["name"].lower() in HEAVY_DISTRIBUTIONS]
    criteria.append(
        {
            "id": "no_torch",
            "label": "Sans torch (ni transformers, ni onnxruntime)",
            "ok": not heavy_loaded and not heavy_installed and "fatal" not in conf,
            "detail": f"chargés : {heavy_loaded or 'aucun'} ; "
            f"installés par headroom-ai : {heavy_installed or 'aucun'}",
        }
    )

    rss_added = conf.get("rss_added_mb")
    criteria.append(
        {
            "id": "budget",
            "label": f"RSS ajouté ≤ {HEADROOM_RSS_BUDGET_MB} Mo (part du budget AD-8)",
            "ok": rss_added is not None and rss_added <= HEADROOM_RSS_BUDGET_MB,
            "detail": f"{rss_added} Mo ajoutés au pic (import + compression), "
            f"pic {conf.get('rss_peak_mb')} Mo",
        }
    )

    bad = [f"{d['name']} ({d['license']})" for d in closure if d["class"] == "forbidden"]
    unknown = [f"{d['name']} ({d['license']})" for d in closure if d["class"] == "unknown"]
    criteria.append(
        {
            "id": "license",
            "label": "Licences compatibles (NFR-10)",
            "ok": bool(closure) and not bad,
            "detail": f"{len(closure)} paquets ; interdites : {bad or 'aucune'} ; "
            f"à vérifier : {unknown or 'aucune'}",
        }
    )

    samples = conf.get("samples", [])
    failed = [s["id"] for s in samples if s.get("error")]
    netns = report.get("netns")
    adoption_ok = bool(samples) and not failed and net_ok and netns is not False
    netns_txt = {True: "réussi", False: "échoué", None: "non disponible"}[netns]
    criteria.append(
        {
            "id": "adoption",
            "label": "Règle d'adoption AD-15 : fonctionne hors ligne",
            "ok": adoption_ok,
            "detail": f"échantillons en échec : {failed or 'aucun'} ; "
            f"sans aucun réseau (unshare -rn) : {netns_txt}",
        }
    )
    return {"retained": all(c["ok"] for c in criteria), "criteria": criteria}


def _passes(result: dict, rss_budget: int, mrr_floor: float | None) -> bool:
    """Measured, within its RSS budget, and good enough.

    Without a floor (an embedding, or a reranker with no measured embedding),
    good enough is recall@1 >= EMBED_RECALL_MIN; a reranker must otherwise keep
    or improve the MRR of the chosen embedding.
    """
    if result.get("status") != "measured":
        return False
    rss_added = result.get("rss_added_mb")
    if rss_added is None or rss_added > rss_budget:
        return False
    if mrr_floor is None:
        return (result.get("recall_at_1") or 0) >= EMBED_RECALL_MIN
    return (result.get("mrr") or 0) >= mrr_floor


def embed_verdict(results: list[dict]) -> dict:
    """Chosen embedding and reranker: measured, fastembed fallback, or provisional."""
    by_role = {"embedding": [], "reranker": []}
    for r in results:
        by_role[r["role"]].append(r)

    def pick(role: str, budget: int, floor: float | None) -> dict:
        rows = by_role[role]
        for backend, status in (("llama_cpp", "mesuré"), ("fastembed", "repli fastembed")):
            ok = [r for r in rows if r["backend"] == backend and _passes(r, budget, floor)]
            if ok:
                best = min(ok, key=lambda r: (r["size_mb"], -(r.get("mrr") or 0)))
                return {"id": best["id"], "status": status, "measured": True}
        if any(r.get("status") == "measured" for r in rows):
            return {
                "id": None,
                "status": "aucun candidat mesuré ne passe les seuils",
                "measured": True,
            }
        return {
            "id": RECOMMENDED[role],
            "status": "provisoire, mesure sur PC cible à faire",
            "measured": False,
        }

    emb = pick("embedding", EMBED_RSS_BUDGET_MB, None)
    floor = None
    if emb["measured"] and emb["id"]:
        floor = next(r.get("mrr") for r in results if r["id"] == emb["id"])
    rer = pick("reranker", RERANK_RSS_BUDGET_MB, floor)
    return {"embedding": emb, "reranker": rer}


# --------------------------------------------------------------------------
# Process plumbing shared by the children.
# --------------------------------------------------------------------------


def _strip_proxy_env(env: dict[str, str]) -> None:
    for name in list(env):
        if name.lower() in PROXY_VARS:
            del env[name]


def _record_and_guard(
    allowed_hosts: list[str], strip_proxy: bool = True
) -> tuple[list[list[str]], str]:
    """Record every resolution/connection attempt, then install the project guard.

    The recording hook is added first: audit hooks run in order, and the guard
    raising must not hide the attempt from the record. Measurements strip the
    proxy (a loopback proxy would carry any destination past the guard, story
    1e); a download keeps it, since the target PC only reaches out through it.
    """
    attempts: list[list[str]] = []

    def record(event: str, args: tuple) -> None:
        if event == "socket.getaddrinfo":
            host = args[0]
            if host is None:  # passive lookup (a local bind), not a destination
                return
            if isinstance(host, bytes):
                host = host.decode("ascii", "replace")
            attempts.append([event, str(host)])
        elif event == "socket.connect":
            address = args[1]
            if isinstance(address, tuple) and address:
                attempts.append([event, str(address[0])])

    sys.addaudithook(record)
    if strip_proxy:
        _strip_proxy_env(os.environ)
        import urllib.request

        urllib.request.getproxies_registry = lambda: {}  # Windows registry proxy (story 1e)
    try:
        from wavestack.net.guard import install, office_proxies
    except ImportError:
        return attempts, "absente (lancer depuis le dépôt avec uv run)"
    install(allowed_hosts=allowed_hosts)
    if not strip_proxy:
        # Story 1e: the guard confiscates the proxy for WaveStack's factory alone; this
        # bench downloads with `huggingface_hub` and `fastembed` directly, so it hands the
        # copy back to the environment, knowingly reopening the 1e hole for its own
        # downloads: behind a loopback proxy the guard sees 127.0.0.1 only, never the host
        # the tunnel reaches. A developer's tool, never WaveStack itself (AD-15).
        for scheme, url in office_proxies().items():
            os.environ[f"{scheme}_proxy"] = url
    return attempts, "wavestack.net.guard"


def _rss_mb() -> int:
    import psutil

    return psutil.Process().memory_info().rss >> 20


def _peak_rss_mb() -> int | None:
    """The process's RSS high-water mark, in MB; it never goes down. Linux: `VmHWM` of
    /proc/self/status (`ru_maxrss` keeps the parent's high-water mark across fork and
    exec); Windows: `peak_wset`; elsewhere `ru_maxrss`."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", encoding="ascii", errors="replace") as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        return int(line.split()[1]) >> 10  # kB
        except (OSError, ValueError, IndexError):
            pass
    try:
        import psutil

        info = psutil.Process().memory_info()
        if hasattr(info, "peak_wset"):  # Windows
            return info.peak_wset >> 20
    except ImportError:
        pass
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak >> 20 if sys.platform == "darwin" else peak >> 10
    except (ImportError, AttributeError):
        return None


def _baseline_rss() -> dict:
    """RSS and high-water mark before loading: what the process had already reached."""
    return {"rss_before_load_mb": _rss_mb(), "peak_before_load_mb": _peak_rss_mb()}


def _loaded_rss() -> dict:
    """RSS with the model loaded (the fallback without a high-water mark), and the
    high-water mark after the measure."""
    return {"rss_loaded_mb": _rss_mb(), "rss_peak_mb": _peak_rss_mb()}


def added_rss_mb(
    base: int | None, peak_at_base: int | None, peak: int | None, loaded: tuple = ()
) -> int | None:
    """What a measure adds to the process (lot F): the high-water mark after it minus the
    baseline. The mark never goes down, so the baseline is the larger of the RSS and the
    mark before the measure. Without a mark: the largest RSS read while loaded."""
    if base is None:
        return None
    if peak is None:
        peak, peak_at_base = max((v for v in loaded if v is not None), default=None), None
    if peak is None:
        return None
    return max(0, peak - max(base, peak_at_base or 0))


def _blocked_host(exc: BaseException) -> str | None:
    try:
        from wavestack.net.guard import find_blocked
    except ImportError:
        return None
    blocked = find_blocked(exc)
    return str(blocked) if blocked else None


def _run_child(cmd: list[str], env: dict[str, str], timeout: int = 900) -> dict:
    env = dict(env, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"fatal": f"délai de {timeout} s dépassé"}
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                break
    return {"fatal": f"code {proc.returncode} : {proc.stderr.strip()[-600:]}"}


def _tool_available(argv: list[str]) -> bool:
    if not sys.platform.startswith("linux") or not shutil.which(argv[0]):
        return False
    try:
        return subprocess.run(argv, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# --------------------------------------------------------------------------
# Headroom.
# --------------------------------------------------------------------------


def headroom_samples() -> list[dict]:
    """Tool results in French: JSON, logs, prose (a rag_excerpt stand-in)."""
    rows = [
        {
            "id": i,
            "date": f"2026-09-{1 + i % 28:02d}",
            "service": "sauvegarde" if i % 3 else "authentification",
            "niveau": "INFO",
            "message": "Opération terminée",
            "utilisateur": f"user{i:03d}",
            "commentaire": "",
        }
        for i in range(120)
    ]
    rows[67].update(niveau="ERREUR", message="Échec de la sauvegarde nocturne")
    logs = "\n".join(
        f"2026-09-26T10:{i // 60:02d}:{i % 60:02d} INFO worker-3 tâche {i} terminée en 12 ms"
        for i in range(150)
    ).replace("tâche 97 terminée en 12 ms", "FATAL disque plein sur /var/lib/wavestack, tâche 97")
    prose = " ".join(
        [
            "Un harnais agentique entoure le modèle de langage de tout ce qui lui manque :",
            "une mémoire de la conversation, un prompt système, des outils, une recherche",
            "documentaire et des garde-fous. Le modèle, seul, ne fait que prédire la suite",
            "d'un texte ; c'est le harnais qui décide quoi lui montrer, dans quel ordre, et",
            "qui exécute les actions qu'il demande. Chaque brique ajoute des tokens au",
            "contexte, donc du temps de calcul et de la mémoire, ce qui compte beaucoup sur",
            "un poste sans carte graphique. La compression du contexte vise précisément à",
            "retirer ce qui n'aide pas le modèle : répétitions, champs vides, listes trop",
            "longues. Pour un consultant, la leçon principale reste la question de",
            "l'hébergement : où tournent le harnais, les données et le modèle, et quelles",
            "informations quittent le poste à chaque appel. Un modèle local garde les",
            "requêtes sur la machine, alors qu'un modèle appelé par API les envoie chez un",
            "fournisseur, avec ses propres règles de conservation et d'entraînement. Le",
            "RAG ajoute des extraits de documents au message de l'utilisateur ; le",
            "reranking les réordonne avant de les placer dans le contexte. Les hooks",
            "s'exécutent à des points fixes du tour et peuvent bloquer un outil réseau",
            "avant son envoi. Un sous-agent reçoit un contexte minimal et ne renvoie que",
            "son résultat, ce qui économise des tokens dans le contexte principal.",
        ]
        * 2
    )
    return [
        {
            "id": "json_tool_result",
            "marker": "Échec de la sauvegarde",
            "text": json.dumps(rows, ensure_ascii=False),
        },
        {"id": "log_tool_result", "marker": "disque plein", "text": logs},
        {"id": "prose_rag_excerpt", "marker": "question de", "text": prose},
    ]


def _headroom_child(variant: str) -> dict:
    attempts, guard = _record_and_guard(allowed_hosts=[])
    out: dict = {
        "variant": variant,
        "guard": guard,
        "python": platform.python_version(),
        "counting_model": COUNTING_MODEL,
    }
    rss0, peak0 = _rss_mb(), _peak_rss_mb()
    t0 = time.monotonic()
    try:
        from headroom import compress
    except Exception as exc:  # noqa: BLE001 - a failed import is a finding
        out.update(import_error=repr(exc)[:400], blocked=_blocked_host(exc), attempts=attempts)
        return out
    out["import_s"] = round(time.monotonic() - t0, 3)
    out["rss_before_import_mb"] = rss0
    out["rss_after_import_mb"] = _rss_mb()
    kompress = "disabled" if variant == "configured" else None
    samples = []
    for sample in headroom_samples():
        messages = [
            {"role": "user", "content": "Qu'est-ce qui pose problème dans ce résultat ?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": sample["text"]},
        ]
        row: dict = {"id": sample["id"], "chars_before": len(sample["text"])}
        t1 = time.monotonic()
        try:
            result = compress(
                messages, model=COUNTING_MODEL, kompress_model=kompress, protect_recent=0
            )
            after = str(result.messages[-1].get("content"))
            row.update(
                tokens_before=result.tokens_before,
                tokens_after=result.tokens_after,
                chars_after=len(after),
                marker_kept=sample["marker"] in after,
                transforms=[str(t) for t in result.transforms_applied][:5],
            )
        except Exception as exc:  # noqa: BLE001 - recorded, criterion fails
            row.update(error=repr(exc)[:300], blocked=_blocked_host(exc))
        row["seconds"] = round(time.monotonic() - t1, 3)
        if not row.get("error"):
            # Second call on a slightly different text: lazy imports are warm, but the
            # result cannot come from a cache keyed on the content.
            warm = [*messages[:2], dict(messages[2], content=sample["text"] + "\n ")]
            t2 = time.monotonic()
            try:
                compress(warm, model=COUNTING_MODEL, kompress_model=kompress, protect_recent=0)
                row["seconds_warm"] = round(time.monotonic() - t2, 3)
            except Exception as exc:  # noqa: BLE001 - recorded, criterion fails
                row.update(error=f"second appel : {exc!r}"[:300], blocked=_blocked_host(exc))
        samples.append(row)
    out["samples"] = samples
    out["rss_after_compress_mb"] = _rss_mb()
    out["rss_peak_mb"] = _peak_rss_mb()
    out["peak_before_import_mb"] = peak0
    # Same definition as the embedding bench: the peak minus the baseline (lot F).
    out["rss_added_mb"] = added_rss_mb(
        rss0, peak0, out["rss_peak_mb"], (out["rss_after_compress_mb"],)
    )
    out["heavy_modules_loaded"] = [m for m in HEAVY_MODULES if m in sys.modules]
    time.sleep(2)  # leave a background beacon or update check the time to fire
    import threading

    out["threads"] = sorted({t.name for t in threading.enumerate()})
    out["attempts"] = attempts
    return out


def dependency_closure(root: str = "headroom-ai") -> list[dict]:
    """Installed distributions reachable from `root` (extras ignored), with licences."""
    from importlib.metadata import PackageNotFoundError, distribution

    def norm(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).lower()

    seen: dict[str, dict] = {}
    todo = [root]
    while todo:
        name = norm(todo.pop())
        if name in seen:
            continue
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            continue
        meta = dist.metadata
        lic = meta.get("License-Expression") or ""
        if not lic:
            classifiers = [
                c.split("::")[-1].strip()
                for c in (meta.get_all("Classifier") or [])
                if c.startswith("License ::")
            ]
            lic = "; ".join(classifiers) or (meta.get("License") or "?").splitlines()[0][:80]
        seen[name] = {
            "name": meta["Name"],
            "version": meta["Version"],
            "license": lic,
            "class": classify_license(lic),
        }
        for req in dist.requires or []:
            if re.search(r"\bextra\s*==", req):
                continue
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req)
            if match:
                todo.append(match.group(1))
    return sorted(seen.values(), key=lambda d: d["name"].lower())


def _tiktoken_cache_dir() -> str | None:
    spec = importlib.util.find_spec("litellm")
    if not spec or not spec.submodule_search_locations:
        return None
    path = Path(next(iter(spec.submodule_search_locations))) / "litellm_core_utils" / "tokenizers"
    return str(path) if path.is_dir() else None


def headroom_missing_message() -> str:
    return (
        f"headroom-ai n'est pas installé dans cet environnement. Lancez depuis la racine du "
        f"dépôt : uv run --with headroom-ai=={HEADROOM_VERSION} python "
        f"tools/bench/story12_bench.py headroom (aucune dépendance n'est ajoutée au projet)."
    )


def run_headroom(use_strace: bool = True) -> tuple[int, dict]:
    if importlib.util.find_spec("headroom") is None:
        print(headroom_missing_message())
        return 2, {}
    from importlib.metadata import version

    report: dict = {
        "headroom_version": version("headroom-ai"),
        "platform": platform.platform(),
        "rss_added_method": "pic",
    }
    base_env = dict(os.environ)
    _strip_proxy_env(base_env)
    for name in HEADROOM_ENV_NAMES:
        base_env.pop(name, None)
    configured_env = dict(base_env, **HEADROOM_OFFLINE_ENV)
    tk_cache = _tiktoken_cache_dir()
    if tk_cache:
        configured_env["TIKTOKEN_CACHE_DIR"] = tk_cache
    report["tiktoken_cache_dir"] = tk_cache
    report["configured_env"] = {
        k: configured_env[k] for k in HEADROOM_ENV_NAMES if k in configured_env
    }

    strace_ok = use_strace and _tool_available(["strace", "-qq", "-e", "trace=connect", "true"])
    report["strace"] = strace_ok
    child = [sys.executable, str(Path(__file__).resolve()), "_headroom-child", "--variant"]
    with tempfile.TemporaryDirectory() as tmp:
        for variant, env in (("naive", base_env), ("configured", configured_env)):
            cmd = [*child, variant]
            trace = Path(tmp) / f"{variant}.strace"
            if strace_ok:
                cmd = ["strace", "-f", "-qq", "-e", "trace=connect", "-o", str(trace), *cmd]
            result = _run_child(cmd, env)
            if strace_ok and trace.exists():
                result["native_connects"] = parse_strace_connects(
                    trace.read_text("utf-8", "replace")
                )
            report[variant] = result

    netns = None
    if _tool_available(["unshare", "-rn", "true"]):
        result = _run_child(["unshare", "-rn", *child, "configured"], configured_env)
        samples = result.get("samples") or []
        netns = bool(samples) and not any(s.get("error") for s in samples)
        report["netns_detail"] = {
            "rss_added_mb": result.get("rss_added_mb"),
            "fatal": result.get("fatal"),
        }
    report["netns"] = netns
    report["closure"] = dependency_closure()
    report["verdict"] = headroom_verdict(report)
    return 0, report


def print_headroom(report: dict) -> None:
    print(f"== Headroom (headroom-ai {report['headroom_version']}) — {report['platform']}")
    print(f"   modèle de comptage de Headroom : {COUNTING_MODEL} (table cl100k_base)")
    for variant, title in (("naive", "naïve (aucune variable)"), ("configured", "configurée")):
        r = report.get(variant) or {}
        print(f"\n-- Variante {title}")
        if r.get("fatal") or r.get("import_error"):
            print(f"   échec : {r.get('fatal') or r.get('import_error')}")
        print(
            f"   garde : {r.get('guard')} ; import {r.get('import_s')} s ; RSS avant import "
            f"{r.get('rss_before_import_mb')} Mo, après import {r.get('rss_after_import_mb')} Mo,"
            f" après compression {r.get('rss_after_compress_mb')} Mo (pic {r.get('rss_peak_mb')})"
        )
        for s in r.get("samples", []):
            if s.get("error"):
                print(f"   {s['id']:<18} ERREUR {s['error']} (garde : {s.get('blocked')})")
            else:
                print(
                    f"   {s['id']:<18} {s['tokens_before']:>6} -> {s['tokens_after']:>6} tokens"
                    f" en {s['seconds']} s (à chaud {s.get('seconds_warm')} s) ;"
                    f" repère conservé : {s['marker_kept']}"
                )
        hosts = summarize_attempts(r.get("attempts", []))
        print(f"   tentatives réseau Python : {hosts or 'aucune'}")
        native = r.get("native_connects")
        native_txt = "non observé" if native is None else native or "aucune"
        print(f"   connexions natives (strace) : {native_txt}")
        print(f"   modules lourds chargés : {r.get('heavy_modules_loaded') or 'aucun'}")
    print(f"\n-- Hors réseau complet (unshare -rn) : {report.get('netns')}")
    closure = report.get("closure", [])
    print(f"-- Fermeture des dépendances de headroom-ai : {len(closure)} paquets")
    for d in closure:
        if d["class"] != "ok":
            print(f"   {d['class']:<9} {d['name']} {d['version']} : {d['license']}")
    verdict = report["verdict"]
    print("\n== Verdict Headroom : " + ("RETENU" if verdict["retained"] else "ÉCARTÉ"))
    for c in verdict["criteria"]:
        print(f"   [{'ok' if c['ok'] else 'KO'}] {c['label']} — {c['detail']}")


# --------------------------------------------------------------------------
# Embedding and reranking.
# --------------------------------------------------------------------------


def model_path(models_dir: Path, c: Candidate) -> Path:
    return models_dir / c.repo.replace("/", "__") / c.filename


def _fastembed_cache(models_dir: Path) -> Path:
    return models_dir / "fastembed"


def _register_fastembed_custom() -> None:
    from fastembed.common.model_description import ModelSource
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    c = candidate("fe_mmarco_rerank")
    known = {m["model"] for m in TextCrossEncoder.list_supported_models()}
    if c.repo not in known:
        TextCrossEncoder.add_custom_model(
            model=c.repo,
            sources=ModelSource(hf=c.repo),
            model_file=c.filename,
            license="apache-2.0",
            size_in_gb=c.size_mb / 1000,
        )


def _fastembed_model(c: Candidate, models_dir: Path, local_only: bool):
    cache = str(_fastembed_cache(models_dir))
    if c.role == "embedding":
        from fastembed import TextEmbedding

        return TextEmbedding(model_name=c.repo, cache_dir=cache, local_files_only=local_only)
    _register_fastembed_custom()
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=c.repo, cache_dir=cache, local_files_only=local_only)


def _fastembed_cached(models_dir: Path, c: Candidate) -> bool:
    """fastembed keeps the Hugging Face cache layout: models--{owner}--{name}[-onnx...]."""
    cache = _fastembed_cache(models_dir)
    name = c.repo.split("/")[-1]
    return cache.is_dir() and any(cache.glob(f"models--*{name}*"))


def _llama_scores_embedding(c: Candidate, path: Path) -> tuple[list[list[float]], dict]:
    import llama_cpp

    pooling = {
        "cls": llama_cpp.LLAMA_POOLING_TYPE_CLS,
        "mean": llama_cpp.LLAMA_POOLING_TYPE_MEAN,
        "last": llama_cpp.LLAMA_POOLING_TYPE_LAST,
    }[c.pooling]
    baseline = _baseline_rss()
    t0 = time.monotonic()
    llm = llama_cpp.Llama(
        model_path=str(path),
        embedding=True,
        pooling_type=pooling,
        n_ctx=512,
        n_batch=512,
        n_ubatch=512,
        n_threads=os.cpu_count(),
        verbose=False,
    )
    load_s = time.monotonic() - t0
    rss_loaded = _rss_mb()
    suffix = (
        llm.tokenize(c.suffix_special.encode(), add_bos=False, special=True)
        if c.suffix_special
        else []
    )

    def embed(text: str) -> list[float]:
        tokens = llm.tokenize(text.encode("utf-8"), add_bos=True, special=False)[:500] + suffix
        vec = _decode_sequence(llm, tokens)[: llm.n_embd()]
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    t1 = time.monotonic()
    docs = [embed(c.doc_prefix + text) for text in DOCUMENTS.values()]
    queries = [embed(c.query_prefix + q) for q, _ in QUERIES]
    n_texts = len(docs) + len(queries)
    per_text_ms = (time.monotonic() - t1) * 1000 / n_texts
    scores = [[sum(a * b for a, b in zip(q, d, strict=True)) for d in docs] for q in queries]
    stats = {
        "load_s": round(load_s, 2),
        "ms_per_item": round(per_text_ms, 1),
        **baseline,
        "rss_after_load_mb": rss_loaded,
        "pooling_used": str(llm.pooling_type()),
        # What an adapter that passes no pooling_type would get (story 15):
        # 1 = mean, 2 = cls, 3 = last, absent = llama.cpp falls back to none.
        "pooling_gguf": _gguf_pooling(llm),
        "n_embd": llm.n_embd(),
        **_loaded_rss(),
    }
    llm.close()
    return scores, stats


def _gguf_pooling(llm) -> str:
    """The `<arch>.pooling_type` key of the GGUF metadata, or 'absent'."""
    meta = getattr(llm, "metadata", None) or {}
    arch = meta.get("general.architecture", "")
    return str(meta.get(f"{arch}.pooling_type", "absent"))


def _decode_sequence(llm, tokens: list[int]) -> list[float]:
    """One sequence through llama.cpp, pooled output (what `Llama.embed` does per text).

    `Llama.embed` reads `n_embd` floats per sequence, but a RANK-pooled reranker
    only writes `n_cls_out` of them: reading the pooled pointer directly is the
    safe path for both.
    """
    import llama_cpp

    llm._ctx.kv_cache_clear()
    llm._batch.reset()
    llm._batch.add_sequence(tokens, 0, True)
    llm._ctx.decode(llm._batch)
    ptr = llama_cpp.llama_get_embeddings_seq(llm._ctx.ctx, 0)
    size = 1 if llm.pooling_type() == llama_cpp.LLAMA_POOLING_TYPE_RANK else llm.n_embd()
    values = [float(ptr[i]) for i in range(size)]
    llm._batch.reset()
    return values


def _llama_scores_rerank(c: Candidate, path: Path) -> tuple[list[list[float]], dict]:
    import llama_cpp

    baseline = _baseline_rss()
    t0 = time.monotonic()
    llm = llama_cpp.Llama(
        model_path=str(path),
        embedding=True,
        pooling_type=llama_cpp.LLAMA_POOLING_TYPE_RANK,
        n_ctx=1024,
        n_batch=1024,
        n_ubatch=1024,
        n_threads=os.cpu_count(),
        verbose=False,
    )
    load_s = time.monotonic() - t0
    rss_loaded = _rss_mb()
    vocab = llama_cpp.llama_model_get_vocab(llm._model.model)

    def flag(fn_name: str) -> bool:
        fn = getattr(llama_cpp, fn_name, None)
        return bool(fn(vocab)) if fn else True

    add_bos, add_eos, add_sep = (flag(f"llama_vocab_get_add_{k}") for k in ("bos", "eos", "sep"))
    bos, eos = llama_cpp.llama_vocab_bos(vocab), llama_cpp.llama_vocab_eos(vocab)
    sep = llama_cpp.llama_vocab_sep(vocab)

    def pair_tokens(query: str, doc: str) -> list[int]:
        # Same layout as llama.cpp's server `format_rerank`: [BOS] q [EOS] [SEP] d [EOS].
        q = llm.tokenize(query.encode("utf-8"), add_bos=False, special=False)
        d = llm.tokenize(doc.encode("utf-8"), add_bos=False, special=False)
        tokens = ([bos] if add_bos else []) + q + ([eos] if add_eos else [])
        tokens += ([sep] if add_sep else []) + d + ([eos] if add_eos else [])
        return tokens[:1000]

    t1 = time.monotonic()
    scores = [
        [_decode_sequence(llm, pair_tokens(q, d))[0] for d in DOCUMENTS.values()]
        for q, _ in QUERIES
    ]
    per_pair_ms = (time.monotonic() - t1) * 1000 / (len(QUERIES) * len(DOCUMENTS))
    stats = {
        "load_s": round(load_s, 2),
        "ms_per_item": round(per_pair_ms, 1),
        **baseline,
        "rss_after_load_mb": rss_loaded,
        **_loaded_rss(),
    }
    llm.close()
    return scores, stats


def _fastembed_scores(c: Candidate, models_dir: Path) -> tuple[list[list[float]], dict]:
    baseline = _baseline_rss()
    t0 = time.monotonic()
    model = _fastembed_model(c, models_dir, local_only=True)
    load_s = time.monotonic() - t0
    rss_loaded = _rss_mb()
    t1 = time.monotonic()
    if c.role == "embedding":
        docs = [list(v) for v in model.passage_embed(list(DOCUMENTS.values()))]
        queries = [list(v) for v in model.query_embed([q for q, _ in QUERIES])]

        def cos(a: list[float], b: list[float]) -> float:
            na = sum(x * x for x in a) ** 0.5 or 1.0
            nb = sum(x * x for x in b) ** 0.5 or 1.0
            return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)

        scores = [[cos(q, d) for d in docs] for q in queries]
        items = len(docs) + len(queries)
    else:
        scores = [[float(s) for s in model.rerank(q, list(DOCUMENTS.values()))] for q, _ in QUERIES]
        items = len(QUERIES) * len(DOCUMENTS)
    stats = {
        "load_s": round(load_s, 2),
        "ms_per_item": round((time.monotonic() - t1) * 1000 / items, 1),
        **baseline,
        "rss_after_load_mb": rss_loaded,
        **_loaded_rss(),
    }
    return scores, stats


def _embed_child(candidate_id: str, models_dir: Path) -> dict:
    attempts, guard = _record_and_guard(allowed_hosts=[])
    c = candidate(candidate_id)
    out: dict = {"id": c.id, "guard": guard}
    if c.backend == "llama_cpp":
        import llama_cpp  # noqa: F401 - imported before the RSS baseline

        path = model_path(models_dir, c)
        runner = _llama_scores_embedding if c.role == "embedding" else _llama_scores_rerank
        scores, stats = runner(c, path)
    else:
        import fastembed  # noqa: F401 - imported before the RSS baseline

        scores, stats = _fastembed_scores(c, models_dir)
    out.update(measured_result(scores, stats, rss_after_run_mb=_rss_mb()))
    out["attempts"] = attempts
    return out


def measured_result(scores: list[list[float]], stats: dict, rss_after_run_mb: int) -> dict:
    """A measured candidate's row: quality, then the RSS its model adds (`rss_added_mb`).

    The added RSS is the peak minus the baseline (`added_rss_mb`, lot F). The RSS
    after `close()` falls back near the baseline (3 to 6 MB shown on the target PC,
    for +428 to +900 MB really used): `rss_after_run_mb` stays as information only.
    """
    ranks = ranks_of_gold(scores, list(DOCUMENTS), [gold for _, gold in QUERIES])
    row = dict(stats)
    row.update(
        status="measured",
        ranks=ranks,
        recall_at_1=recall_at(ranks, 1),
        recall_at_3=recall_at(ranks, 3),
        mrr=mrr(ranks),
        rss_after_run_mb=rss_after_run_mb,
    )
    row["rss_added_mb"] = added_rss_mb(
        row.get("rss_before_load_mb"),
        row.get("peak_before_load_mb"),
        row.get("rss_peak_mb"),
        (row.get("rss_after_load_mb"), row.get("rss_loaded_mb")),
    )
    return row


def download_candidates(models_dir: Path, selected: list[Candidate]) -> dict:
    """Fetch the candidates into `models_dir`, under the guard (HF hosts only).

    Same settings as WaveStack (AD-15): Xet and HF telemetry off, the system
    trust store (TLS inspection on the corporate network), the proxy kept.
    """
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    attempts, guard = _record_and_guard(allowed_hosts=DOWNLOAD_HOSTS, strip_proxy=False)
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
    errors: dict[str, str] = {}
    have_hub = importlib.util.find_spec("huggingface_hub") is not None
    have_fastembed = importlib.util.find_spec("fastembed") is not None
    for c in selected:
        try:
            if c.backend == "llama_cpp":
                if not have_hub:
                    errors[c.id] = "huggingface-hub absent (ajouter --with huggingface-hub)"
                    continue
                from huggingface_hub import hf_hub_download

                target = model_path(models_dir, c)
                if not target.exists():
                    hf_hub_download(repo_id=c.repo, filename=c.filename, local_dir=target.parent)
            elif have_fastembed:
                _fastembed_model(c, models_dir, local_only=False)
        except Exception as exc:  # noqa: BLE001 - one failure does not stop the others
            errors[c.id] = repr(exc)[:300]
    return {"guard": guard, "hosts": summarize_attempts(attempts), "errors": errors}


def _default_runner(c: Candidate, models_dir: Path) -> dict:
    env = dict(os.environ)
    _strip_proxy_env(env)
    env["HF_HUB_OFFLINE"] = "1"
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_embed-child",
        "--candidate",
        c.id,
        "--models-dir",
        str(models_dir),
    ]
    return _run_child(cmd, env)


def availability(c: Candidate, models_dir: Path, find_spec=importlib.util.find_spec) -> str | None:
    """None when the candidate can be measured, else the French reason why not."""
    if c.backend == "llama_cpp":
        if find_spec("llama_cpp") is None:
            return "non mesuré (llama-cpp-python absent)"
        if not model_path(models_dir, c).exists():
            return "absent (lancer avec --download sur un poste qui a le réseau)"
        return None
    if find_spec("fastembed") is None:
        return "non mesuré (fastembed absent)"
    if not _fastembed_cached(models_dir, c):
        return "absent (lancer avec --download sur un poste qui a le réseau)"
    return None


def run_embed(
    models_dir: Path,
    download: bool = False,
    only: list[str] | None = None,
    runner=_default_runner,
    downloader=download_candidates,
    find_spec=importlib.util.find_spec,
) -> dict:
    selected = [c for c in CANDIDATES if not only or c.id in only]
    report: dict = {
        "models_dir": str(models_dir),
        "platform": platform.platform(),
        "rss_added_method": "pic",  # peak minus baseline (lot F); absent: after close()
    }
    if download:
        models_dir.mkdir(parents=True, exist_ok=True)
        report["download"] = downloader(models_dir, selected)
    results = []
    for c in selected:
        row = {"id": c.id, "role": c.role, "backend": c.backend, "size_mb": c.size_mb}
        reason = availability(c, models_dir, find_spec)
        if reason:
            row["status"] = reason
        else:
            try:
                measured = runner(c, models_dir)
            except Exception as exc:  # noqa: BLE001 - one failure does not stop the others
                measured = {"fatal": repr(exc)[:300]}
            if measured.get("fatal"):
                row["status"] = "erreur"
                row["error"] = measured["fatal"]
            else:
                row.update(measured)
        results.append(row)
    report["results"] = results
    report["verdict"] = embed_verdict(results)
    return report


def print_embed(report: dict) -> None:
    print(f"== Embedding et reranking — {report['platform']}")
    if "download" in report:
        d = report["download"]
        print(f"   téléchargement : hôtes contactés {d['hosts'] or 'aucun'}")
        print(f"   erreurs de téléchargement : {d['errors'] or 'aucune'} (garde : {d['guard']})")
    print("\n-- Candidats (licence, taille, dimension et français lus sur les cartes HF)")
    rows = {r["id"]: r for r in report["results"]}
    for c in CANDIDATES:
        r = rows.get(c.id)
        if not r:
            continue
        print(
            f"   {c.id:<18} {c.role:<9} {c.backend:<9} {c.license:<10} {c.size_mb:>4} Mo "
            f"dim {c.dim or '-':<5} fr : {c.french}"
        )
        print(f"      {c.repo}/{c.filename}")
        if r.get("status") == "measured":
            print(
                f"      mesuré : recall@1 {r['recall_at_1']}, MRR {r['mrr']}, "
                f"{r['ms_per_item']} ms/élément, chargement {r['load_s']} s, RSS ajouté "
                f"{r['rss_added_mb']} Mo (au pic), "
                f"réseau {summarize_attempts(r.get('attempts', [])) or 'aucun'}"
            )
            if "pooling_gguf" in r:
                print(
                    f"      pooling : utilisé {r['pooling_used']}, déclaré dans le GGUF "
                    f"{r['pooling_gguf']} (1 = mean, 2 = cls, 3 = last)"
                )
        else:
            print(f"      {r.get('status')} {r.get('error', '')}".rstrip())
        if c.note:
            print(f"      note : {c.note}")
    print("\n-- Écartés d'office")
    for repo, why in EXCLUDED:
        print(f"   {repo} : {why}")
    v = report["verdict"]
    print("\n== Verdict")
    for role, title in (("embedding", "Embedding"), ("reranker", "Reranking")):
        print(f"   {title} : {v[role]['id'] or '-'} — {v[role]['status']}")


# --------------------------------------------------------------------------
# Entry point.
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Banc de la story 12 (Headroom, embedding).")
    sub = parser.add_subparsers(dest="command", required=True)
    p_head = sub.add_parser("headroom", help="vérifie headroom-ai hors ligne")
    p_head.add_argument("--no-strace", action="store_true")
    p_head.add_argument("--json", action="store_true")
    p_emb = sub.add_parser("embed", help="banc des modèles d'embedding et de reranking")
    p_emb.add_argument("--models-dir", default=str(Path.home() / ".cache" / "wavestack-bench"))
    p_emb.add_argument("--download", action="store_true")
    p_emb.add_argument("--only", nargs="*")
    p_emb.add_argument("--json", action="store_true")
    p_hc = sub.add_parser("_headroom-child")
    p_hc.add_argument("--variant", choices=("naive", "configured"), required=True)
    p_ec = sub.add_parser("_embed-child")
    p_ec.add_argument("--candidate", required=True)
    p_ec.add_argument("--models-dir", required=True)
    args = parser.parse_args(argv)
    try:  # French text on a Windows console or a redirected file
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    if args.command == "_headroom-child":
        print(json.dumps(_headroom_child(args.variant), ensure_ascii=False))
        return 0
    if args.command == "_embed-child":
        print(json.dumps(_embed_child(args.candidate, Path(args.models_dir)), ensure_ascii=False))
        return 0
    if args.command == "headroom":
        code, report = run_headroom(use_strace=not args.no_strace)
        if code:
            return code
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=1))
        else:
            print_headroom(report)
        return 0
    problems = check_dataset()
    if problems:
        print("\n".join(problems))
        return 1
    unknown = unknown_candidates_message(args.only)
    if unknown:
        print(unknown)
        return 2
    report = run_embed(Path(args.models_dir), download=args.download, only=args.only)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print_embed(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
