"""
In-memory passage index over the knowledge files and the uploaded documents.

Hybrid search, no vector database:
- cosine similarity between multilingual sentence embeddings (numpy), plus
- a fixed boost for every risk concept (agent, discount, urgency, threat, secrecy) that
  the query and the passage share, whatever language each one is written in.

The boost is needed. On its own the embedding model ranks "pay only to the official
account" above "we never use agents or offer discounts" for an agent's discount offer,
in every language including English, because both passages are about paying tuition.
"""

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.documents.concepts import concepts_in
from app.documents.languages import detect_languages

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "seed" / "knowledge"

# Knowledge file name prefix -> the kind of source it is.
KNOWLEDGE_SOURCES = {
    "spiu_payment_policy": "policy",
    "providers_fees": "provider",
    "scam_advisory": "advisory",
}

_SECTION = re.compile(r"^## (?P<title>.+?)(?:\s*<!-- clause: (?P<clause>[\w-]+) -->)?\s*$", re.MULTILINE)
_MIN_PASSAGE_CHARS = 8
CONCEPT_BOOST = 0.15  # added to the cosine similarity for each shared risk concept


@dataclass(frozen=True)
class Passage:
    text: str
    file: str
    language: str
    source: str  # policy | provider | advisory | document
    title: str | None = None
    clause: str | None = None  # stable id of a knowledge clause, shared across languages
    document_id: int | None = None


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float  # similarity plus the concept boost: what the ranking uses
    similarity: float  # cosine similarity of the embeddings alone
    shared_concepts: list[str]  # risk concepts found in both the query and the passage


def knowledge_passages() -> list[Passage]:
    """One passage per "## " section of every knowledge file."""
    passages = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        source = next((kind for prefix, kind in KNOWLEDGE_SOURCES.items() if path.name.startswith(prefix)), None)
        if source is None:
            continue
        language = path.stem.rsplit("_", 1)[-1]
        text = path.read_text(encoding="utf-8")
        sections = list(_SECTION.finditer(text))
        for section, following in zip(sections, [*sections[1:], None]):
            body = text[section.end() : following.start() if following else len(text)].strip()
            if body:
                passages.append(
                    Passage(
                        text=body,
                        file=path.name,
                        language=language,
                        source=source,
                        title=section["title"].strip(),
                        clause=section["clause"],
                    )
                )
    return passages


def document_passages(document_id: int, filename: str, text: str) -> list[Passage]:
    """One passage per non-trivial line of a document."""
    return [
        Passage(text=line.strip(), file=filename, language=detect_languages(line)[0], source="document", document_id=document_id)
        for line in text.splitlines()
        if len(line.strip()) >= _MIN_PASSAGE_CHARS
    ]


class _Embedder:
    """The embedding model and every vector computed so far. One for the whole process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model: Any = None
        self._vectors: dict[str, Any] = {}  # text -> vector

    def embed(self, texts: list[str]) -> Any:
        import numpy

        with self._lock:
            missing = [text for text in dict.fromkeys(texts) if text not in self._vectors]
            if missing:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(MODEL_NAME)
                vectors = self._model.encode(missing, normalize_embeddings=True, show_progress_bar=False)
                self._vectors.update(zip(missing, vectors))
            return numpy.stack([self._vectors[text] for text in texts])


_embedder = _Embedder()


class PassageIndex:
    """
    The knowledge files plus the documents of one database. The live database has the
    module-level `index`; an isolated copy of the database gets an index of its own, so
    its documents never show up in the live one.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._knowledge: list[Passage] | None = None
        self._documents: list[Passage] = []

    def _embed(self, texts: list[str]) -> Any:
        return _embedder.embed(texts)

    def reset(self) -> None:
        """Forget every document passage. Called by the demo reset."""
        with self._lock:
            self._documents = []

    def add_document(self, document_id: int, filename: str, text: str) -> None:
        with self._lock:
            self._documents = [item for item in self._documents if item.document_id != document_id]
            self._documents += document_passages(document_id, filename, text)

    def has_document(self, document_id: int) -> bool:
        with self._lock:
            return any(item.document_id == document_id for item in self._documents)

    def search(self, query: str, k: int = 3, source: str | None = None) -> list[Hit]:
        """The k passages closest in meaning to the query, optionally from one kind of source."""
        with self._lock:
            if self._knowledge is None:
                self._knowledge = knowledge_passages()
            candidates = [
                passage for passage in [*self._knowledge, *self._documents] if source is None or passage.source == source
            ]
            if not candidates or not query.strip():
                return []
            vectors = self._embed([passage.text for passage in candidates])
            similarities = vectors @ self._embed([query])[0]
            wanted = concepts_in(query)
            hits = []
            for passage, similarity in zip(candidates, similarities):
                shared = sorted(wanted & concepts_in(passage.text))
                score = float(similarity) + CONCEPT_BOOST * len(shared)
                hits.append(Hit(passage, round(score, 4), round(float(similarity), 4), shared))
            return sorted(hits, key=lambda hit: -hit.score)[:k]

    def warm_up(self) -> None:
        """Load the model and embed the knowledge files, so the first search is fast."""
        self.search("payment policy", k=1)


index = PassageIndex()


def search(query: str, k: int = 3, source: str | None = None) -> list[Hit]:
    return index.search(query, k, source)
