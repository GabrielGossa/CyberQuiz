"""Retrieval-Augmented Generation helpers for CyberQuiz.

This module encapsulates the interaction with a ChromaDB persistent vector store
so that the Ollama-based generator can ground new questions on validated
knowledge.  The implementation has been written defensively: when optional
dependencies such as :mod:`chromadb` or :mod:`sentence_transformers` are not
available, the functions gracefully no-op and surface a dedicated exception so
that the rest of the application can continue to work in a degraded mode.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Optional imports -----------------------------------------------------------

try:  # pragma: no cover - import guard depends on environment availability
    import chromadb
    from chromadb.api.models import Collection
    from chromadb.utils import embedding_functions
except Exception:  # pragma: no cover - any error disables RAG features
    chromadb = None  # type: ignore[assignment]
    Collection = Any  # type: ignore[misc,assignment]
    embedding_functions = None  # type: ignore[assignment]


# ----------------------------------------------------------------------------
# Exceptions and data containers
# ----------------------------------------------------------------------------


class RAGNotAvailableError(RuntimeError):
    """Raised when the vector store or embedding backend cannot be used."""


@dataclass
class RetrievedDocument:
    """Simple container representing a knowledge snippet returned by Chroma."""

    question_id: str
    texte: str
    theme: str
    reponse: str
    source: str


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = BASE_DIR / "cyberquiz.db"
VECTOR_DIR = BASE_DIR / "ai" / "chroma_db"
COLLECTION_NAME = "cyberquiz_questions"


# ----------------------------------------------------------------------------
# Lazy singletons
# ----------------------------------------------------------------------------


_client: Optional["chromadb.PersistentClient"] = None
_collection: Optional[Collection] = None
_embedding_function: Optional[Any] = None


def _require_dependencies() -> None:
    """Ensure ChromaDB and the embedding backend are available."""

    if chromadb is None or embedding_functions is None:
        raise RAGNotAvailableError(
            "ChromaDB ou sentence-transformers ne sont pas installés. "
            "Les fonctionnalités RAG sont désactivées."
        )


def _get_embedding_function() -> Any:
    """Return the shared sentence-transformer embedding function."""

    global _embedding_function
    if _embedding_function is None:
        _require_dependencies()
        try:
            _embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(  # type: ignore[operator]
                model_name="all-MiniLM-L6-v2"
            )
        except Exception as exc:  # pragma: no cover - backend specific failure
            raise RAGNotAvailableError(
                "Impossible de charger le modèle d'embedding all-MiniLM-L6-v2."
            ) from exc
    return _embedding_function


def _get_client() -> "chromadb.PersistentClient":
    """Return a persistent ChromaDB client stored as a singleton."""

    global _client
    if _client is None:
        _require_dependencies()
        VECTOR_DIR.mkdir(parents=True, exist_ok=True)
        try:
            _client = chromadb.PersistentClient(path=str(VECTOR_DIR))  # type: ignore[assignment]
        except Exception as exc:  # pragma: no cover - backend specific failure
            raise RAGNotAvailableError(
                "Impossible d'initialiser la base vectorielle persistante."
            ) from exc
    return _client


def _get_collection() -> Collection:
    """Return (and cache) the collection that stores quiz questions."""

    global _collection
    if _collection is None:
        client = _get_client()
        embedding_function = _get_embedding_function()
        try:
            _collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=embedding_function,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # pragma: no cover - backend specific failure
            raise RAGNotAvailableError(
                "Impossible de récupérer la collection vectorielle."
            ) from exc
    return _collection


# ----------------------------------------------------------------------------
# Public helpers
# ----------------------------------------------------------------------------


def is_available() -> bool:
    """Return ``True`` when the vector store stack can be used."""

    try:
        _get_collection()
    except RAGNotAvailableError:
        return False
    return True


def clear_collection() -> None:
    """Remove every document from the vector store."""

    collection = _get_collection()
    collection.delete()  # type: ignore[no-untyped-call]


def _chunked(iterable: Iterable[Any], size: int = 64) -> Iterable[List[Any]]:
    """Yield successive chunks from *iterable* of length *size*."""

    chunk: List[Any] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def build_vector_db_from_sqlite() -> int:
    """Read validated questions from SQLite and index them in Chroma.

    The existing collection is wiped to avoid stale entries and then repopulated
    with the current validated knowledge base.

    Returns
    -------
    int
        Number of questions indexed in the vector store.
    """

    collection = _get_collection()
    clear_collection()

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, texte, theme, reponse, source FROM questions WHERE statut = ?",
            ("valide",),
        ).fetchall()

    if not rows:
        return 0

    documents: List[str] = []
    metadatas: List[Dict[str, str]] = []
    ids: List[str] = []

    for row in rows:
        ids.append(str(row["id"]))
        documents.append(str(row["texte"]))
        metadatas.append(
            {
                "theme": str(row["theme"] or ""),
                "reponse": "1" if bool(row["reponse"]) else "0",
                "source": str(row["source"] or ""),
            }
        )

    for docs_chunk, metas_chunk, ids_chunk in zip(
        _chunked(documents), _chunked(metadatas), _chunked(ids)
    ):
        collection.add(
            documents=docs_chunk,
            metadatas=metas_chunk,
            ids=ids_chunk,
        )

    return len(rows)


def upsert_question(
    question_id: int,
    texte: str,
    theme: Optional[str],
    reponse: bool,
    source: Optional[str],
) -> None:
    """Insert or update a validated question inside the vector store."""

    collection = _get_collection()
    collection.upsert(  # type: ignore[no-untyped-call]
        documents=[texte],
        metadatas=[
            {
                "theme": theme or "",
                "reponse": "1" if reponse else "0",
                "source": source or "",
            }
        ],
        ids=[str(question_id)],
    )


def remove_question(question_id: int) -> None:
    """Delete a document from the vector store if it exists."""

    collection = _get_collection()
    collection.delete(ids=[str(question_id)])  # type: ignore[no-untyped-call]


def ensure_populated() -> int:
    """Ensure that the collection contains at least one document.

    Returns the number of stored documents, rebuilding the vector database from
    SQLite when the collection is empty.
    """

    collection = _get_collection()
    try:
        count = collection.count()  # type: ignore[no-untyped-call]
    except Exception as exc:  # pragma: no cover
        raise RAGNotAvailableError("Impossible de compter les documents RAG.") from exc

    if count:
        return count
    return build_vector_db_from_sqlite()


def query_similar(
    query_text: str,
    *,
    theme: Optional[str] = None,
    top_k: int = 5,
) -> List[RetrievedDocument]:
    """Return knowledge snippets close to ``query_text``.

    Parameters
    ----------
    query_text:
        Text used to search similar items in the vector store.
    theme:
        Optional theme filter that narrows down the retrieval scope.
    top_k:
        Maximum number of elements to return.
    """

    if not query_text.strip():
        query_text = "cybersécurité"

    collection = _get_collection()
    ensure_populated()

    where: Optional[Dict[str, str]] = {"theme": theme} if theme else None

    try:
        results = collection.query(  # type: ignore[no-untyped-call]
            query_texts=[query_text],
            n_results=top_k,
            where=where,
        )
    except Exception as exc:  # pragma: no cover - backend specific failure
        raise RAGNotAvailableError("La requête vectorielle a échoué.") from exc

    documents = results.get("documents") or []
    metadatas = results.get("metadatas") or []
    ids = results.get("ids") or []

    if not documents:
        return []

    retrieved: List[RetrievedDocument] = []
    docs_for_query = documents[0]
    metas_for_query = metadatas[0] if metadatas else [{} for _ in docs_for_query]
    ids_for_query = ids[0] if ids else [""] * len(docs_for_query)

    for doc_id, doc_text, metadata in zip(ids_for_query, docs_for_query, metas_for_query):
        retrieved.append(
            RetrievedDocument(
                question_id=str(doc_id),
                texte=str(doc_text),
                theme=str(metadata.get("theme", "")),
                reponse=str(metadata.get("reponse", "")),
                source=str(metadata.get("source", "")),
            )
        )

    return retrieved


def build_context_block(theme: Optional[str], query_hint: Optional[str], limit: int = 5) -> str:
    """Generate a textual block describing retrieved knowledge examples."""

    try:
        documents = query_similar(query_hint or "cybersécurité", theme=theme, top_k=limit)
    except RAGNotAvailableError:
        return ""

    if not documents:
        return ""

    lines = []
    for doc in documents:
        response = "Vrai" if doc.reponse == "1" else "Faux"
        theme_display = doc.theme or "général"
        lines.append(
            f"- Thème: {theme_display} | Réponse: {response} | {doc.texte}"
        )

    header = "Connaissances existantes à ne pas répéter :"
    return "\n".join([header, *lines])


__all__ = [
    "RAGNotAvailableError",
    "RetrievedDocument",
    "build_context_block",
    "build_vector_db_from_sqlite",
    "ensure_populated",
    "is_available",
    "query_similar",
    "remove_question",
    "upsert_question",
]

