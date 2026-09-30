"""The model table (story 25, CAP-34, CAP-35): every model available, with its publisher, size,
hosting, window and capabilities, grouped and sorted here (AD-1), never in the browser.

One truth of the capabilities (AD-6): the same inputs as the session's load go through
`capabilities_for` — a file or an Ollama blob: its GGUF header, read in pure Python
(`gguf_meta`); llama-server: no architecture and the template of `/props`, as its adapter —
and a cloud model through `cloud_capabilities`. The window is `window_for` (AD-9), as the
gauge's. Nothing loads, probes nor tokenizes a model: a header is read once per (path, size,
modification time); Ollama's `details` come from the `/api/tags` already read by discovery.

The publishers are content (`content/models/publishers.yaml`, AD-19): an invalid file breaks
nothing, every model goes to « Autres éditeurs » and the table says why.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Iterable, Sequence
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from wavestack import config
from wavestack.cloud import price_fr, price_reason_fr
from wavestack.context.window import window_for
from wavestack.models import gguf_meta
from wavestack.models.capabilities import (
    CLOUD_FAMILY,
    REASONING_FR,
    Capabilities,
    ReasoningMode,
    capabilities_for,
    cloud_capabilities,
    reasoning_mode,
    tools_summary,
)
from wavestack.models.discovery import ModelCandidate
from wavestack.models.engine import EngineMetadata

log = logging.getLogger(__name__)

PUBLISHERS_FILE = Path("models") / "publishers.yaml"
OTHER_ID = "other"
GIB = 1024**3
MIB = 1024**2


# ---------- the publishers' table (AD-19) ----------


class Publisher(BaseModel):
    """A publisher: its architecture prefixes (`general.architecture`, Ollama's family, the
    registry's family) and its name patterns (regular expressions, case-insensitive)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label_text: str = Field(min_length=1)
    architectures: list[str] = []
    names: list[str] = []
    # Its names win over the architecture (a distilled model keeps its base's: DeepSeek-R1
    # distilled on Qwen is `qwen2` for Ollama).
    names_first: bool = False
    _patterns: list[re.Pattern[str]] = PrivateAttr(default_factory=list)

    @field_validator("names")
    @classmethod
    def _valid_patterns(cls, value: list[str]) -> list[str]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as exc:  # not a ValueError: pydantic would let it through
                raise ValueError(f"expression régulière invalide « {pattern} » : {exc}") from exc
        return value

    def model_post_init(self, _: Any) -> None:
        self._patterns = [re.compile(p, re.IGNORECASE) for p in self.names]

    def matches_architecture(self, architecture: str) -> bool:
        return any(architecture.startswith(p.casefold()) for p in self.architectures if p)

    def matches_name(self, name: str) -> bool:
        return any(p.search(name) for p in self._patterns)


class ServedByFr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1)
    ollama: str = Field(min_length=1)
    llama_server: str = Field(min_length=1)


class HostingFr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local: str = Field(min_length=1)
    network: str = Field(min_length=1)


class PublishersContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legend_text: str = Field(min_length=1)
    served_by_text: ServedByFr
    hosting_text: HostingFr
    other_text: str = Field(min_length=1)
    publishers: list[Publisher]

    @model_validator(mode="after")
    def _distinct_ids(self) -> PublishersContent:
        """An id names one group: twice, or `other` (« Autres éditeurs »), would merge two."""
        ids = [p.id for p in self.publishers]
        if OTHER_ID in ids:
            raise ValueError(f"l'identifiant « {OTHER_ID} » est réservé à « Autres éditeurs »")
        if len(set(ids)) != len(ids):
            twice = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"identifiant en double : {', '.join(twice)}")
        return self


# Only when `publishers.yaml` is unreadable: the table still shows every model, under
# « Autres éditeurs », with the reason (AD-19: never a crash).
_FALLBACK = PublishersContent(
    legend_text=(
        "Légende : « Local » ou « RÉSEAU » dit où tourne le modèle, puis vient qui le sert "
        "(fichier, Ollama, llama-server ou fournisseur cloud)."
    ),
    served_by_text=ServedByFr(file="fichier", ollama="Ollama", llama_server="llama-server"),
    hosting_text=HostingFr(local="Sur ce poste", network="Réseau"),
    other_text="Autres éditeurs",
    publishers=[],
)


def publishers_path(lang: str = config.DEFAULT_LANGUAGE) -> Path:
    return config.content_file(PUBLISHERS_FILE, lang)


def _cause(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first.get("loc", ())) or "racine"
        return f"{where} : {first.get('msg', '')}"
    return str(exc) or type(exc).__name__


@cache
def load_publishers(lang: str = config.DEFAULT_LANGUAGE) -> tuple[PublishersContent, str | None]:
    """`content/models/publishers.yaml` in `lang` (languages 3/5: the session's, never
    `settings.json`'s), patterns compiled. An invalid translation: the French table, and
    the reason naming the translated file (AD-19). On any other error, an empty table
    (every model in « Autres éditeurs ») and the French reason naming the file."""
    path = publishers_path(lang)
    translated = lang != config.DEFAULT_LANGUAGE and path != publishers_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return PublishersContent.model_validate(data), None
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
        where = f"i18n/{lang}/" if translated else ""
        log.warning("content/%s%s invalide : %s", where, PUBLISHERS_FILE.as_posix(), exc)
        if translated:
            content, error_text = load_publishers()
            return content, error_text or (
                f"Fichier content/i18n/{lang}/models/publishers.yaml invalide ({_cause(exc)}) : "
                "le texte français de ce fichier le remplace. Corrigez le fichier, puis "
                "relancez WaveStack."
            )
        return _FALLBACK, (
            f"Fichier content/models/publishers.yaml invalide ({_cause(exc)}) : tous les "
            "modèles sont rangés dans « Autres éditeurs ». Corrigez le fichier, puis relancez "
            "WaveStack."
        )


def publisher_for(
    architectures: Iterable[str | None],
    names: Iterable[str | None],
    lang: str = config.DEFAULT_LANGUAGE,
) -> Publisher:
    """The publisher of a model: first by the names of the publishers marked `names_first`,
    then by its architectures (the header's, Ollama's family, the registry's family, in that
    order; `unknown` and `openai_chat` say nothing), then by its names (`general.basename`,
    `general.name`, the name shown, a cloud `model`), each in the table's order; « Autres
    éditeurs » otherwise. `lang`: the language of its label (the patterns are the same in
    every language)."""
    content, _ = load_publishers(lang)
    names = [n for n in names if n]
    for name in names:
        for publisher in content.publishers:
            if publisher.names_first and publisher.matches_name(name):
                return publisher
    for arch in architectures:
        key = (arch or "").strip().casefold()
        if not key or key in ("unknown", CLOUD_FAMILY):
            continue
        for publisher in content.publishers:
            if publisher.matches_architecture(key):
                return publisher
    for name in names:
        for publisher in content.publishers:
            if publisher.matches_name(name):
                return publisher
    return Publisher(id=OTHER_ID, label_text=content.other_text)


# ---------- sizes ----------

# « 2B », « 0.6B », « 270M », « 8x7B », « 30B-A3B » (the first figure), alone or in a name
# between non-alphanumeric bounds: « Q4_K_M » and « 3.5 » are no sizes.
_PARAMS = re.compile(
    r"(?<![A-Za-z0-9.])(?:(\d+)[x×])?(\d+(?:[.,]\d+)?)([BM])(?![A-Za-z0-9])", re.IGNORECASE
)


def _params(text: str | None) -> tuple[float, str] | None:
    """The parameters (billions) and their label in `text`, or `None`."""
    if not text:
        return None
    match = _PARAMS.search(text)
    if match is None:
        return None
    experts, number, unit = match.groups()
    value = float(number.replace(",", ".")) * (int(experts) if experts else 1)
    if unit.upper() == "M":
        value /= 1000
    label = match.group(0)[:-1] + unit.upper()
    return value, label


def parse_params(text: str | None) -> float | None:
    """The parameters in billions a size label or a name says (« 8x7B » = 56, « 270M » =
    0.27, « 30B-A3B » = 30), else `None`."""
    found = _params(text)
    return found[0] if found else None


def _first_params(sources: Sequence[str | None]) -> tuple[float | None, str | None]:
    for text in sources:
        found = _params(text)
        if found:
            return found
    return None, None


def _fr_int(n: int) -> str:
    """« 4 096 »: French thousands separator (narrow no-break space)."""
    return f"{n:,}".replace(",", " ")


def params_fr(params_label: str) -> str:
    """« 0.6B » written the French way: « 0,6 B »."""
    return re.sub(r"(\d)\.(\d)", r"\1,\2", params_label[:-1]) + "\u00a0" + params_label[-1]


def size_fr(params_label: str | None, size_bytes: int | None) -> str:
    """« 2 B · 1,3 Go », « 0,6 B », « 1,4 Go », « 45 Mo » (below 0,1 Go), or « — » when
    nothing says it. 1 Go = 1024³ bytes, 1 Mo = 1024² bytes."""
    parts = []
    if params_label:
        parts.append(params_fr(params_label))
    if size_bytes:
        if size_bytes < GIB / 10:
            parts.append(f"{max(1, round(size_bytes / MIB))}\u00a0Mo")
        else:
            parts.append(f"{size_bytes / GIB:.1f}".replace(".", ",") + "\u00a0Go")
    return " · ".join(parts) or "—"


# ---------- the GGUF header, read once per (path, size, modification time) ----------

_HEADERS: dict[str, tuple[tuple[int, int], tuple[EngineMetadata, dict[str, Any]] | None]] = {}
_HEADERS_LOCK = threading.Lock()


def _positive(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _text(value: Any) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def _engine_metadata(raw: dict[str, Any]) -> EngineMetadata:
    """What `VocabTokenizer` reads in the same header: architecture, template, native
    context (`{arch}.context_length`)."""
    arch = _text(raw.get("general.architecture"))
    template = raw.get("tokenizer.chat_template")
    return EngineMetadata(
        architecture=arch,
        chat_template=template if isinstance(template, str) and template else None,
        native_context=_positive(raw.get(f"{arch}.context_length")) if arch else None,
        bos_token="",
        eos_token="",
        special_tokens=(),
    )


def header_metadata(path: str | None) -> tuple[EngineMetadata, dict[str, Any]] | None:
    """The `EngineMetadata` and the raw key/values of the GGUF header of `path`, read in
    pure Python and remembered by (path, size, `mtime_ns`); `None` when unreadable."""
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    stamp = (stat.st_size, stat.st_mtime_ns)
    key = os.path.normcase(os.path.abspath(path))
    with _HEADERS_LOCK:
        hit = _HEADERS.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    raw = gguf_meta.try_read_metadata(path)
    result = None if raw is None else (_engine_metadata(raw), raw)
    with _HEADERS_LOCK:
        _HEADERS[key] = (stamp, result)
    return result


# ---------- the entries ----------


class ModelEntry(BaseModel):
    """One available model, as the picker and the table show it (story 25)."""

    value: str  # the picker's value: `file:`, `server:` or `cloud:` + ref
    kind: Literal["file", "server", "cloud"]
    ref: str
    hosting: Literal["local", "network"]
    served_by_text: str  # « fichier », « Ollama », « llama-server », the cloud provider
    hosting_text: str | None = None  # a cloud model's declared hosting
    hosting_label_text: str  # the table's « Hébergement »: where, then who serves it
    prefix_text: str  # « Local · Ollama », « RÉSEAU · Groq »
    name: str
    label_text: str  # prefix · name · size (parameters only)
    title_text: str  # the option's tooltip when usable: path, address or hosting
    publisher_id: str
    publisher_text: str
    params_b: float | None = None
    params_label: str | None = None
    size_bytes: int | None = None
    size_text: str
    window: int | None = None
    native_context: int | None = None
    window_text: str
    window_reason_text: str | None = None  # where the window comes from (AD-9)
    tools: bool | None = None
    tools_text: str
    tools_reason_text: str | None = None
    reasoning: ReasoningMode
    reasoning_text: str
    reason_text: str | None = None  # why it reasons (or not) so
    usable: bool
    disabled_text: str | None = None
    # FinOps: a cloud model's declared prices, « 0,30 $ / 2,50 $ » per million tokens (input /
    # output); « — » for a local model, or a cloud one without `pricing`.
    price_text: str = "—"
    price_reason_text: str | None = None


def _capabilities(
    caps: Capabilities | None, unknown_text: str | None, window: int | None
) -> dict[str, Any]:
    """The table's columns from `caps` (the cards' rules, `capabilities.py`, the reasoning
    card's window rule included); `unknown_text`: why nothing was read, when it is so."""
    tools, tools_text, tools_reason = tools_summary(caps)
    mode, reason = reasoning_mode(caps, window)
    if caps is None and unknown_text:
        tools_reason = reason = unknown_text
    return {
        "tools": tools,
        "tools_text": tools_text,
        "tools_reason_text": tools_reason,
        "reasoning": mode,
        "reasoning_text": REASONING_FR[mode],
        "reason_text": reason,
    }


# AD-9: where the window comes from (`window_for`, `config.cloud_window`).
_WINDOW_SOURCE_FR = {
    "configured": "fenêtre configurée",
    "native": "contexte natif du modèle",
    "server": "contexte d'un emplacement du serveur",
    "override": "fenêtre déclarée pour ce modèle (window)",
    "tpm": "moitié du quota de tokens par minute (tpm)",
}


def _window(window: int | None, source: str | None, native: int | None) -> dict[str, Any]:
    reason = None
    if window:
        reason = _WINDOW_SOURCE_FR.get(source or "", source)
        if native:
            reason = f"{reason} ; contexte natif : {_fr_int(native)} tokens"
    return {
        "window": window,
        "native_context": native,
        "window_text": f"{_fr_int(window)} tokens" if window else "—",
        "window_reason_text": reason,
    }


def _label(prefix: str, name: str, params_label: str | None) -> str:
    return " · ".join(part for part in (prefix, name, params_label) if part)


def _local_entry(
    candidate: ModelCandidate,
    cfg: config.Config,
    window: int | None = None,
    lang: str = config.DEFAULT_LANGUAGE,
) -> ModelEntry:
    content, _ = load_publishers(lang)
    configured = cfg.context_window if window is None else window
    served = candidate.source == "server"
    engine = candidate.engine if served else None
    found = candidate.status != "incompatible"
    path = candidate.gguf_path if served else candidate.path
    # A file of this disk, relative paths resolved (an explicit path, a relative data dir);
    # llama-server reports the file it loaded: only an absolute path is this disk's. Its
    # header gives the publisher and the size, never the capabilities (`/props`).
    if engine == "llama_server":
        local = path if path and Path(path).is_absolute() else None
    else:
        local = os.path.abspath(path) if path else None
    header = header_metadata(local)
    raw = header[1] if header else {}
    meta: EngineMetadata | None
    if engine == "llama_server":
        meta = EngineMetadata(
            architecture=None,  # AD-6: llama-server exposes none, the template says it
            chat_template=candidate.server_template,
            native_context=candidate.native_context,
            bos_token="",
            eos_token="",
            special_tokens=(),
            server_context=candidate.server_context,
        )
    else:
        meta = header[0] if header else None
    caps = capabilities_for(meta) if meta is not None and found else None
    # AD-6: a model without a template fails to load (« Modèle incompatible »): not usable.
    incompatible = caps.incompatible_reason if caps else None
    usable = found and not incompatible
    if not found:
        unknown_text = candidate.reason or "Modèle inutilisable."
    else:
        unknown_text = "En-tête GGUF illisible : capacités inconnues."
    name = candidate.name or Path(path or "").name or candidate.ref or "modèle"
    publisher = publisher_for(
        [_text(raw.get("general.architecture")), candidate.architecture, candidate.publisher_hint]
        + ([caps.family] if caps else []),
        [_text(raw.get("general.basename")), _text(raw.get("general.name")), name],
        lang,
    )
    params_b, params_label = _first_params(
        [
            _text(raw.get("general.size_label")),
            candidate.size_label,
            candidate.params_label,
            name,
            _text(raw.get("general.name")),
        ]
    )
    size_bytes = candidate.size_bytes
    if size_bytes is None and local:
        try:
            size_bytes = Path(local).stat().st_size
        except OSError:
            size_bytes = None
    served_by = getattr(content.served_by_text, engine) if engine else content.served_by_text.file
    prefix = f"Local · {served_by}"
    window, source = window_for(meta, configured) if meta is not None and usable else (None, None)
    if served:
        kind, ref = "server", candidate.ref or name
        title = f"{candidate.provider} sur {candidate.server_url}"
    else:
        kind, ref = "file", candidate.path or ""
        title = candidate.path or name
    return ModelEntry(
        value=f"{kind}:{ref}",
        kind=kind,
        ref=ref,
        hosting="local",
        served_by_text=served_by,
        hosting_label_text=f"{content.hosting_text.local} · {served_by}",
        prefix_text=prefix,
        name=name,
        label_text=_label(prefix, name, params_label),
        title_text=title,
        publisher_id=publisher.id,
        publisher_text=publisher.label_text,
        params_b=params_b,
        params_label=params_label,
        size_bytes=size_bytes,
        size_text=size_fr(params_label, size_bytes),
        **_window(window, source, meta.native_context if meta is not None else None),
        **_capabilities(caps, unknown_text, window),
        usable=usable,
        disabled_text=None if usable else (incompatible or unknown_text),
    )


def local_entries(
    candidates: Iterable[ModelCandidate],
    cfg: config.Config,
    window: int | None = None,
    lang: str = config.DEFAULT_LANGUAGE,
) -> list[ModelEntry]:
    """Every local model the last diagnostic found: the files, once per path (a usable
    listing wins over an incompatible one), incompatible ones included (greyed, with their
    reason), and the models of already-running servers. `window` (story 26): the window
    configured now, else the launch's."""
    files: dict[str, ModelCandidate] = {}
    served: list[ModelCandidate] = []
    for candidate in candidates:
        if candidate.source == "server":
            served.append(candidate)
        elif candidate.path and (
            candidate.path not in files or files[candidate.path].status != "found"
        ):
            files[candidate.path] = candidate
    return [_local_entry(c, cfg, window, lang) for c in [*files.values(), *served]]


def cloud_entries(
    cfg: config.Config,
    rows: Iterable[dict[str, Any]] = (),
    window: int | None = None,
    lang: str = config.DEFAULT_LANGUAGE,
) -> list[ModelEntry]:
    """Every declared cloud model; `rows`: the diagnostic's `cloud_rows`, whose `disabled_text`
    says why one cannot be chosen now (no key…). `window` (story 26): as `local_entries`."""
    disabled = {row.get("id"): row.get("disabled_text") for row in rows}
    entries = []
    for entry in cfg.cloud_models[0]:
        caps = cloud_capabilities(entry)
        effective, source = config.cloud_window(
            entry, cfg.context_window if window is None else window
        )
        params_b, params_label = _first_params([entry.model])
        publisher = publisher_for([], [entry.model], lang)
        prefix = f"RÉSEAU · {entry.provider}"
        reason = disabled.get(entry.id)
        entries.append(
            ModelEntry(
                value=f"cloud:{entry.id}",
                kind="cloud",
                ref=entry.id,
                hosting="network",
                served_by_text=entry.provider,
                hosting_text=entry.hosting_text,
                hosting_label_text=f"{entry.provider} · {entry.hosting_text}",
                prefix_text=prefix,
                name=entry.model,
                label_text=_label(prefix, entry.model, params_label),
                title_text=f"{entry.provider} : {entry.hosting_text}",
                publisher_id=publisher.id,
                publisher_text=publisher.label_text,
                params_b=params_b,
                params_label=params_label,
                size_bytes=None,
                size_text=size_fr(params_label, None),
                **_window(effective, source, entry.context),
                **_capabilities(caps, None, effective),
                usable=not reason,
                disabled_text=reason or None,
                price_text=price_fr(entry) or "—",
                price_reason_text=price_reason_fr(entry) or "prix non déclaré",
            )
        )
    return entries


# ---------- groups ----------


class ModelGroup(BaseModel):
    hosting: Literal["local", "network"]
    publisher_id: str
    label_text: str  # « Sur ce poste · Qwen (Alibaba) »
    models: list[ModelEntry]


def sort_key(entry: ModelEntry) -> tuple[bool, float, bool, int, str]:
    """Known parameters first, by size; then known bytes, by size; then by name, whatever
    the case."""
    return (
        entry.params_b is None,
        entry.params_b or 0.0,
        entry.size_bytes is None,
        entry.size_bytes or 0,
        entry.name.casefold(),
    )


def group_models(
    entries: Iterable[ModelEntry], lang: str = config.DEFAULT_LANGUAGE
) -> list[ModelGroup]:
    """Local before network; in each, the publishers in the table's order, « Autres
    éditeurs » last; empty groups left out; models by `sort_key`."""
    content, _ = load_publishers(lang)
    order = {p.id: i for i, p in enumerate(content.publishers)}
    buckets: dict[tuple[str, str], list[ModelEntry]] = {}
    for entry in entries:
        buckets.setdefault((entry.hosting, entry.publisher_id), []).append(entry)
    keys = sorted(buckets, key=lambda k: (k[0] != "local", order.get(k[1], len(order))))
    groups = []
    for hosting, publisher_id in keys:
        models = sorted(buckets[(hosting, publisher_id)], key=sort_key)
        where = getattr(content.hosting_text, hosting)
        groups.append(
            ModelGroup(
                hosting=hosting,  # type: ignore[arg-type]
                publisher_id=publisher_id,
                label_text=f"{where} · {models[0].publisher_text}",
                models=models,
            )
        )
    return groups


def models_payload(
    candidates: Iterable[ModelCandidate],
    cfg: config.Config,
    cloud_rows: Iterable[dict[str, Any]] = (),
    window: int | None = None,
    lang: str = config.DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """`/api/diagnostic.models`: the legend, the groups, and why the publishers' table could
    not be read, if so. One answer serves the picker and the `/models` page. `window`
    (story 26): the window configured now (`AppSession.configured_window`); `lang`
    (languages 3/5): the session's language, for the publishers' texts."""
    content, error_text = load_publishers(lang)
    entries = local_entries(candidates, cfg, window, lang) + cloud_entries(
        cfg, cloud_rows, window, lang
    )
    return {
        "legend_text": content.legend_text,
        "groups": [g.model_dump(mode="json") for g in group_models(entries, lang)],
        "publishers_error_text": error_text,
    }
