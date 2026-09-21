"""The sole raw-SQL boundary for Agent.capability_embedding."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from db.client import db
from services.embeddings.service import capability_hash, capability_text, embed_documents, embeddings_enabled

logger = logging.getLogger(__name__)


def vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(format(float(value), ".9g") for value in vector) + "]"


async def write_embedding(agent_id: str, vector: Sequence[float], content_hash: str) -> int:
    return await db.execute_raw(
        'UPDATE "Agent" SET capability_embedding = $1::vector, capability_hash = $2 WHERE id = $3',
        vector_literal(vector), content_hash, agent_id,
    )


async def get_embedding_state() -> dict[str, dict]:
    rows = await db.query_raw(
        'SELECT id, name, description, system_prompt, capability_hash, '
        '(capability_embedding IS NOT NULL) AS has_embedding FROM "Agent"'
    )
    return {row["id"]: row for row in rows}


async def ensure_vector_schema() -> None:
    try:
        await db.execute_raw('CREATE EXTENSION IF NOT EXISTS vector')
        await db.execute_raw(
            'CREATE INDEX IF NOT EXISTS agent_capability_embedding_hnsw '
            'ON "Agent" USING hnsw (capability_embedding vector_cosine_ops)'
        )
    except Exception:
        logger.exception("Could not ensure pgvector extension/index; keyword search remains available")


async def backfill_embeddings(force: bool = False, batch_size: int = 4) -> int:
    if not embeddings_enabled():
        logger.info("Embedding backfill skipped because EMBEDDINGS_ENABLED is false")
        return 0
    batch_size = max(1, int(batch_size))
    pending: list[tuple[str, str, str]] = []
    for agent_id, row in (await get_embedding_state()).items():
        text = capability_text(row["name"], row.get("description"), row["system_prompt"])
        digest = capability_hash(text)
        if force or not row["has_embedding"] or row.get("capability_hash") != digest:
            pending.append((agent_id, text, digest))
    written = 0
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        vectors = await embed_documents([item[1] for item in batch])
        for (agent_id, _text, digest), vector in zip(batch, vectors, strict=True):
            written += int(bool(await write_embedding(agent_id, vector, digest)))
    logger.info("Embedding backfill wrote %d agent vectors", written)
    return written
