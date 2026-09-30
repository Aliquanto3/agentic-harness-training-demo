"""Languages (2/5, AD-19): the interface's texts, `content/ui.yaml` (French) and its
translations `content/i18n/{en,de}/ui.yaml`, served by `GET /api/ui_texts` to `i18n.js`.

A tree of sections whose leaves are non-empty strings; keys in English, `snake_case`; a
plural is a `{one, other}` pair, chosen by `Intl.PluralRules` in the browser."""

from __future__ import annotations

from functools import cache
from typing import Any

import yaml

from wavestack import config

UiTexts = dict[str, Any]


class UiTextsError(ValueError):
    """`ui.yaml` does not have the expected shape: the path of the first fault says where."""


def _check(tree: Any, path: str) -> None:
    if not isinstance(tree, dict) or not tree:
        raise UiTextsError(f"{path or 'ui.yaml'} : une section non vide est attendue")
    for key, value in tree.items():
        where = f"{path}.{key}" if path else str(key)
        if not isinstance(key, str) or not key:
            raise UiTextsError(f"{where} : clé invalide")
        if isinstance(value, dict):
            _check(value, where)
        elif not isinstance(value, str) or not value.strip():
            raise UiTextsError(f"{where} : un texte non vide est attendu")


def _filled(french: UiTexts, translated: UiTexts, path: str = "") -> UiTexts:
    """`translated` on the French tree: a key it lacks takes the French value; a section
    where French has a text (or the reverse), or a key French lacks, is an error."""
    for key in translated:
        if key not in french:
            raise UiTextsError(f"{path}{key} : clé absente du français")
    filled: UiTexts = {}
    for key, value in french.items():
        if key not in translated:
            filled[key] = value
        elif isinstance(value, dict) != isinstance(translated[key], dict):
            raise UiTextsError(f"{path}{key} : pas la même forme qu'en français")
        elif isinstance(value, dict):
            filled[key] = _filled(value, translated[key], f"{path}{key}.")
        else:
            filled[key] = translated[key]
    return filled


def _read(lang: str) -> UiTexts:
    path = config.content_file("ui.yaml", lang)
    tree = yaml.safe_load(path.read_text(encoding="utf-8"))
    _check(tree, "")
    return tree


@cache
def load_ui_texts(lang: str | None = None) -> UiTexts:
    """The texts in `lang` (the setting's language when `None`), each key the translation
    lacks filled by the French value. Raises on a missing or invalid file (French or
    translated); the session traces it and falls back on French (AD-19)."""
    lang = config.as_language(lang if lang is not None else config.current_language())
    french = _read(config.DEFAULT_LANGUAGE)
    if lang == config.DEFAULT_LANGUAGE:
        return french
    return _filled(french, _read(lang))
