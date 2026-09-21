"""Lazy, memory-bounded local embeddings for agent capability discovery."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections.abc import Sequence

try:
    # Unix only, and used solely for the RSS high-water line logged after the
    # model loads. A bare `import resource` at module scope made this whole
    # service -- and therefore every import path that reaches it -- fail on
    # Windows, which is the platform this project was originally written on.
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

logger = logging.getLogger(__name__)
_model = None
_model_lock = asyncio.Lock()


class EmbeddingsUnavailable(RuntimeError):
    """Raised when local embeddings are disabled or cannot be produced."""


def embeddings_enabled() -> bool:
    return os.getenv("EMBEDDINGS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def capability_text(name: str, description: str | None, system_prompt: str) -> str:
    return "\n\n".join(part.strip() for part in (name, description or "", system_prompt) if part and part.strip())


def capability_hash(text: str) -> str:
    identity = f"{EMBEDDING_MODEL}\0{EMBEDDING_DIM}\0{_QUERY_PREFIX}\0{text}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _load_model():
    global _model
    if _model is None:
        try:
            from fastembed import TextEmbedding

            threads = max(1, int(os.getenv("EMBEDDING_THREADS", "1")))
            cache_dir = os.getenv("FASTEMBED_CACHE_DIR") or None
            _model = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=cache_dir, threads=threads)
            if resource is None:
                logger.info("Loaded embedding model %s", EMBEDDING_MODEL)
            else:
                # Worth logging: an OOM here arrives as a SIGKILL with no
                # traceback, so this line is the only forensic trace left.
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
                logger.info("Loaded embedding model %s (RSS high-water %.1f MiB)", EMBEDDING_MODEL, rss)
        except Exception as exc:
            raise EmbeddingsUnavailable(f"Could not load embedding model: {exc}") from exc
    return _model


def _embed_sync(texts: Sequence[str]) -> list[list[float]]:
    try:
        vectors = [vector.tolist() for vector in _load_model().embed(list(texts))]
    except EmbeddingsUnavailable:
        raise
    except Exception as exc:
        raise EmbeddingsUnavailable(f"Embedding inference failed: {exc}") from exc
    if any(len(vector) != EMBEDDING_DIM for vector in vectors):
        raise EmbeddingsUnavailable("Embedding model returned an unexpected vector dimension")
    return vectors


async def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    if not embeddings_enabled():
        raise EmbeddingsUnavailable("Embeddings are disabled by EMBEDDINGS_ENABLED")
    if not texts:
        return []
    async with _model_lock:
        return await asyncio.to_thread(_embed_sync, texts)


async def embed_query(text: str) -> list[float]:
    if not text.strip():
        raise EmbeddingsUnavailable("Cannot embed an empty query")
    return (await embed_documents([_QUERY_PREFIX + text.strip()]))[0]
