"""Canonical agent persistence, visibility, and indexing operations."""

from __future__ import annotations

import logging
from typing import Any, Optional

from prisma.models import Agent

from db.client import db
from services.embeddings.service import capability_hash, capability_text, embed_documents

logger = logging.getLogger(__name__)

_AGENT_FIELDS = frozenset({
    "name", "description", "system_prompt", "voice_type", "llm_model",
    "isActive", "is_system", "category", "capabilities", "owner_id",
    "visibility", "published_at",
})
_EMBEDDING_FIELDS = frozenset({"name", "description", "system_prompt"})


def _db_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key in _AGENT_FIELDS}


async def _index_agent_safe(agent: Agent) -> None:
    try:
        from db.agents.embeddings import write_embedding

        text = capability_text(agent.name, agent.description, agent.system_prompt)
        vector = (await embed_documents([text]))[0]
        await write_embedding(agent.id, vector, capability_hash(text))
    except Exception:
        logger.exception("Could not index agent %s; keyword fallback will be used", agent.id)


async def create_agent(
    name: str,
    system_prompt: str,
    description: Optional[str] = None,
    voice_type: str = "default",
    llm_model: str = "llama-3.1-8b-instant",
    isActive: bool = True,
    *,
    owner_id: str,
) -> Agent:
    agent = await db.agent.create(data={
        "name": name, "system_prompt": system_prompt, "description": description,
        "voice_type": voice_type, "llm_model": llm_model, "isActive": isActive,
        "owner_id": owner_id, "is_system": False, "visibility": "private",
    })
    await _index_agent_safe(agent)
    return agent


def _visible_where(viewer_user_id: str | None, active_only: bool = False) -> dict[str, Any]:
    where: dict[str, Any] = {"OR": [{"visibility": "public"}]}
    if viewer_user_id:
        where["OR"].append({"owner_id": viewer_user_id})
    if active_only:
        where["isActive"] = True
    return where


async def list_visible_agents(viewer_user_id: str | None = None, active_only: bool = False) -> list[Agent]:
    return await db.agent.find_many(where=_visible_where(viewer_user_id, active_only))


async def get_active_agents() -> list[Agent]:
    return await list_visible_agents(active_only=True)


async def get_all_agents() -> list[Agent]:
    return await list_visible_agents()


async def get_agent(agent_id: str) -> Optional[Agent]:
    return await db.agent.find_unique(where={"id": agent_id})


async def get_visible_agent(agent_id: str, viewer_user_id: str | None = None) -> Optional[Agent]:
    return await db.agent.find_first(where={"id": agent_id, **_visible_where(viewer_user_id)})


async def update_agent(agent_id: str, data: dict[str, Any]) -> Optional[Agent]:
    agent = await db.agent.update(where={"id": agent_id}, data=_db_fields(data))
    if _EMBEDDING_FIELDS.intersection(data):
        await _index_agent_safe(agent)
    return agent


async def delete_agent(agent_id: str) -> Optional[Agent]:
    return await db.agent.delete(where={"id": agent_id})


async def set_published(agent_id: str, published: bool) -> Agent:
    from datetime import datetime, timezone

    return await db.agent.update(
        where={"id": agent_id},
        data={
            "visibility": "public" if published else "private",
            "published_at": datetime.now(timezone.utc) if published else None,
        },
    )


async def count_foreign_sessions(agent_id: str, owner_id: str) -> int:
    return await db.session.count(where={"agent_id": agent_id, "NOT": [{"user_id": owner_id}]})


async def sync_core_agents(core_agents: list[dict]) -> None:
    for source in core_agents:
        agent_id = source["id"]
        data = _db_fields(source)
        data.update({"is_system": True, "owner_id": None, "visibility": "public"})
        existing = await db.agent.find_unique(where={"id": agent_id})
        if existing:
            await db.agent.update(where={"id": agent_id}, data=data)
        else:
            await db.agent.create(data={"id": agent_id, **data})

    # No embedding work here on purpose. main._init_embeddings backfills after
    # the app has bound its port, so a cold model load cannot delay startup or
    # blow the health-check window. backfill_embeddings() hash-compares, so an
    # edited JSON file still gets re-indexed on the next boot -- while the
    # create/update API paths index immediately via _index_agent_safe.
