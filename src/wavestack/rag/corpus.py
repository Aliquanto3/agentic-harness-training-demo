"""The demonstration corpus and its chunking (story 15, AD-19).

`content/rag.yaml` declares the documents and the brick's texts; one chunking function
serves the index script and the tests.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from wavestack import config

# A sentence ends with one of these, followed by a space (or the text's end).
_SENTENCE_END = re.compile(r"[.!?…»](?=\s)")
_BLANK_LINE = re.compile(r"\n\s*\n")
# An HTML comment of a document (its « texte fictif » notice) is never indexed.
_COMMENT = re.compile(r"<!--.*?-->", re.S)


class CorpusDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    title_text: str = Field(min_length=1)
    file: str = Field(min_length=1)  # relative to `content/`


class RagContent(BaseModel):
    """`content/rag.yaml`: the corpus and every French text of the brick."""

    model_config = ConfigDict(extra="forbid")

    notice_text: str = Field(min_length=1)
    intro_text: str = Field(min_length=1)
    excerpt_format_text: str = Field(min_length=1)
    placement_text: str = Field(min_length=1)
    phase_label_text: str = Field(min_length=1)
    index_label_text: str = Field(min_length=1)
    download_label_text: str = Field(min_length=1)
    build_label_text: str = Field(min_length=1)
    # Story 16: the reranking sub-option's texts.
    rerank_label_text: str = Field(min_length=1)
    rerank_phase_label_text: str = Field(min_length=1)
    rerank_search_placement_text: str = Field(min_length=1)  # {candidates}, {keep}
    rerank_placement_text: str = Field(min_length=1)  # {keep}
    rerank_download_label_text: str = Field(min_length=1)  # {size_mb}
    documents: list[CorpusDocument] = Field(min_length=1)

    @field_validator("excerpt_format_text")
    @classmethod
    def _known_fields(cls, value: str) -> str:
        value.format(position=1, title_text="", text="")  # raises on an unknown field
        return value

    @field_validator("download_label_text", "rerank_download_label_text")
    @classmethod
    def _size_field(cls, value: str) -> str:
        value.format(size_mb=1)
        return value

    @field_validator("rerank_search_placement_text", "rerank_placement_text")
    @classmethod
    def _rerank_fields(cls, value: str) -> str:
        value.format(candidates=1, keep=1)  # raises on an unknown field
        return value

    def excerpt(self, position: int, title_text: str, text: str) -> str:
        return self.excerpt_format_text.format(position=position, title_text=title_text, text=text)


class Chunk(NamedTuple):
    """An excerpt of a document: its document, and its rank in it (from 1)."""

    doc_id: str
    title_text: str
    position: int
    text: str


def load_rag_content(lang: str | None = None) -> RagContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_file("rag.yaml", lang)
    return RagContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _cut_long(paragraph: str, max_chars: int) -> list[str]:
    """A paragraph longer than `max_chars`, cut at a sentence's end, else at the limit."""
    pieces = []
    rest = paragraph
    while len(rest) > max_chars:
        ends = [m.end() for m in _SENTENCE_END.finditer(rest[: max_chars + 1])]
        cut = ends[-1] if ends else max_chars
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


def split_text(text: str, max_chars: int) -> list[str]:
    """Paragraphs (separated by a blank line) merged while they fit in `max_chars`; a longer
    paragraph is cut at a sentence's end, else at the limit."""
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in _BLANK_LINE.split(text.replace("\r\n", "\n"))):
        if not paragraph:
            continue
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks += _cut_long(paragraph, max_chars)
            continue
        merged = f"{current}\n\n{paragraph}" if current else paragraph
        if len(merged) <= max_chars:
            current = merged
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def chunk_corpus(content: RagContent, max_chars: int) -> list[Chunk]:
    """Every document of the corpus, read from `content/` and chunked, in declared order."""
    chunks: list[Chunk] = []
    for doc in content.documents:
        # The corpus stays French whatever the language, and so does its index (story 4).
        path = config.content_file(doc.file, config.DEFAULT_LANGUAGE)
        text = _COMMENT.sub("", path.read_text(encoding="utf-8-sig"))
        for position, piece in enumerate(split_text(text, max_chars), start=1):
            chunks.append(Chunk(doc.id, doc.title_text, position, piece))
    return chunks
