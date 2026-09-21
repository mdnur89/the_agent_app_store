from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from db.agents.embeddings import vector_literal
from db.client import db
from services.embeddings.service import EmbeddingsUnavailable, embed_query, embeddings_enabled

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentMatch:
    id: str
    name: str
    description: str | None
    score: float
    match_type: str


def _match(row: dict, match_type: str) -> AgentMatch:
    score = max(0.0, min(1.0, float(row.get("score") or 0)))
    return AgentMatch(row["id"], row["name"], row.get("description"), score, match_type)


def _like_pattern(token: str) -> str:
    return "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def _keyword_search(query: str, limit: int, excluded: str | None, viewer: str | None) -> list[AgentMatch]:
    tokens = list(dict.fromkeys(re.findall(r"[\w-]+", query, flags=re.UNICODE)))[:12]
    if not tokens:
        return []
    params: list[object] = [excluded, viewer]
    clauses = []
    for token in tokens:
        params.append(_like_pattern(token))
        pos = len(params)
        clauses.append(
            f'(name ILIKE ${pos} ESCAPE \'\\\' OR description ILIKE ${pos} ESCAPE \'\\\' '
            f'OR system_prompt ILIKE ${pos} ESCAPE \'\\\')'
        )
    rows = await db.query_raw(
        f'''SELECT id, name, description FROM "Agent"
             WHERE "isActive" = true
               AND ($1::text IS NULL OR id <> $1)
               AND (visibility = 'public' OR owner_id = $2)
               AND ({" OR ".join(clauses)})
             ORDER BY name LIMIT {limit}''',
        *params,
    )
    return [_match(row, "keyword") for row in rows]


async def search_agents_by_capability(
    query: str,
    limit: int = 3,
    exclude_agent_id: str | None = None,
    *,
    viewer_user_id: str | None = None,
) -> list[AgentMatch]:
    limit = max(1, min(int(limit), 50))
    semantic: list[AgentMatch] = []
    if embeddings_enabled():
        try:
            vector = await embed_query(query)
        except EmbeddingsUnavailable as exc:
            logger.warning("Semantic query embedding unavailable: %s", exc)
        else:
            try:
                # Over-fetch: older pgvector versions filter visibility after
                # the approximate HNSW scan and may otherwise under-fill.
                rows = await db.query_raw(
                    f'''SELECT id, name, description,
                               1 - (capability_embedding <=> $1::vector) AS score
                          FROM "Agent"
                         WHERE capability_embedding IS NOT NULL
                           AND "isActive" = true
                           AND ($2::text IS NULL OR id <> $2)
                           AND (visibility = 'public' OR owner_id = $3)
                         ORDER BY capability_embedding <=> $1::vector
                         LIMIT {limit * 4}''',
                    vector_literal(vector), exclude_agent_id, viewer_user_id,
                )
                semantic = [_match(row, "semantic") for row in rows[:limit]]
            except Exception:
                logger.exception("Semantic agent search failed; falling back to keywords")
    if len(semantic) >= limit:
        return semantic
    try:
        keyword = await _keyword_search(query, limit, exclude_agent_id, viewer_user_id)
    except Exception:
        logger.exception("Keyword agent search failed")
        return semantic
    seen = {match.id for match in semantic}
    return (semantic + [match for match in keyword if match.id not in seen])[:limit]
