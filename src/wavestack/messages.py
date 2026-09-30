"""Languages (5/5, AD-19): the texts the backend writes, `content/messages.yaml` (French)
and its translations `content/i18n/{en,de}/messages.yaml`, produced by `msg(key, lang)`.

The same tree as `ui.yaml` (sections, keys in English `snake_case`, `{name}` variables, a
plural as a `{one, other}` pair); a translation has the same keys and, key by key, the
same variables. The language is always an argument: the session passes its own, never
`settings.json`'s. A key a translation lacks, or a translation that cannot be read, gives
the French text; an unknown key or a missing variable is a programming error, raised."""

from __future__ import annotations

import re
from functools import cache
from typing import Any

import yaml

from wavestack import config
from wavestack.ui_texts import UiTextsError, check_tree, filled_tree

# `{name}`: the only substitution, so a brace elsewhere in a text is left as it is.
_VARIABLE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_PLURAL = frozenset({"one", "other"})


class MessagesError(UiTextsError):
    """`messages.yaml` does not have the expected shape, or a translation's variables are
    not the French ones: the path of the first fault says where."""


class MessageError(LookupError):
    """An unknown key, or a variable the text names and the call does not give: a
    programming error, never shown as a text (the tests catch it)."""


def flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, str | dict[str, str]]:
    """`a.b.c` → text, a plural `{one, other}` kept whole under its key."""
    flat: dict[str, str | dict[str, str]] = {}
    for key, value in tree.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and set(value) == _PLURAL:
            flat[name] = value
        elif isinstance(value, dict):
            flat |= flatten(value, f"{name}.")
        else:
            flat[name] = value
    return flat


def variables(text: str | dict[str, str]) -> frozenset[str]:
    """The `{name}` variables of a text (of both forms of a plural)."""
    texts = text.values() if isinstance(text, dict) else (text,)
    return frozenset(v for t in texts for v in _VARIABLE.findall(t))


def _read(lang: str) -> dict[str, Any]:
    path = config.content_file("messages.yaml", lang)
    tree = yaml.safe_load(path.read_text(encoding="utf-8"))
    check_tree(tree, "", "messages.yaml", MessagesError)
    return tree


@cache
def load_messages(lang: str) -> dict[str, str | dict[str, str]]:
    """Every message in `lang`, flattened (`a.b.c`), each key the translation lacks filled
    by the French text. Raises on a missing or invalid file, or a translated text whose
    variables are not the French ones; the session traces it once (`_localized`)."""
    lang = config.as_language(lang)
    french_tree = _read(config.DEFAULT_LANGUAGE)
    french = flatten(french_tree)
    if lang == config.DEFAULT_LANGUAGE:
        return french
    filled = flatten(filled_tree(french_tree, _read(lang), error=MessagesError))
    for key, text in filled.items():
        if isinstance(text, dict) != isinstance(french[key], dict):
            raise MessagesError(f"{key} : pas la même forme qu'en français")
        if variables(text) != variables(french[key]):
            raise MessagesError(f"{key} : pas les mêmes variables qu'en français")
    return filled


@cache
def _catalog(lang: str) -> dict[str, str | dict[str, str]]:
    """The messages `msg` reads: `lang`'s, or French when its file cannot be read."""
    try:
        return load_messages(lang)
    except Exception:  # noqa: BLE001 - traced by the session (`_localized`), then French
        return load_messages(config.DEFAULT_LANGUAGE)


def clear_caches() -> None:
    load_messages.cache_clear()
    _catalog.cache_clear()


def plural_form(count: int | float, lang: str) -> str:
    """`one` or `other`: French counts 0 and 1 as singular, English and German 1 only."""
    if lang == config.DEFAULT_LANGUAGE:
        return "one" if abs(count) < 2 else "other"
    return "one" if count == 1 else "other"


def msg(key: str, lang: str, /, **kw: Any) -> str:
    """The text `key` in `lang`, its `{name}` variables replaced by `kw`; a plural takes
    its form from `count`. Raises `MessageError` on an unknown key or a missing variable."""
    lang = config.as_language(lang)
    catalog = _catalog(lang)
    if key not in catalog:
        raise MessageError(f"unknown message key {key!r}")
    text = catalog[key]
    if isinstance(text, dict):
        if "count" not in kw:
            raise MessageError(f"{key}: a plural needs `count`")
        text = text[plural_form(kw["count"], lang)]

    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in kw:
            raise MessageError(f"{key}: missing variable {name!r}")
        return str(kw[name])

    return _VARIABLE.sub(value, text)


class Message:
    """A text not yet rendered: its key and variables. `render(lang)` writes it in `lang`;
    `str()` in French (logs, tests). A variable that is itself a `Message` is rendered in
    the same language."""

    __slots__ = ("key", "kw")

    def __init__(self, key: str, /, **kw: Any) -> None:
        self.key = key
        self.kw = kw

    def render(self, lang: str) -> str:
        kw = {k: _rendered(v, lang) for k, v in self.kw.items()}
        return msg(self.key, lang, **kw)

    def __str__(self) -> str:
        return self.render(config.DEFAULT_LANGUAGE)

    def __repr__(self) -> str:
        return f"Message({self.key!r}, **{self.kw!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Message) and (self.key, self.kw) == (other.key, other.kw)

    def __hash__(self) -> int:
        return hash(self.key)


class KeyedError(Exception):
    """An exception raised far from the session, carrying its text as a key and its
    variables: `str()` gives the French (logs, existing tests), `render(lang)` the text in
    the session's language, where it is placed in an event, a state or the context. A
    `Message` or a plain text (a third party's, never translated) is taken as it is."""

    def __init__(self, key: str | Message, /, **kw: Any) -> None:
        self.message = key if isinstance(key, Message) else Message(key, **kw)
        super().__init__(self.message.key)

    @classmethod
    def verbatim(cls, text: str) -> KeyedError:
        """A text written elsewhere (a third party's error), kept in its language."""
        return cls(Message("common.verbatim", text=text))

    def render(self, lang: str) -> str:
        return self.message.render(lang)

    def __str__(self) -> str:
        return self.render(config.DEFAULT_LANGUAGE)


def render(value: Any, lang: str) -> str:
    """`value` in `lang`: a `Message` or a `KeyedError` rendered, anything else `str()`."""
    if isinstance(value, Message | KeyedError):
        return value.render(lang)
    return str(value)


def _rendered(value: Any, lang: str) -> Any:
    """A variable: a `Message` or a `KeyedError` rendered in `lang`, anything else kept."""
    return value.render(lang) if isinstance(value, Message | KeyedError) else value
