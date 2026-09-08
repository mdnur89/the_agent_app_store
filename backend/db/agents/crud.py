"""Canonical home for agent persistence.

These functions used to be duplicated verbatim between this module and a
monolithic `db/crud.py`; `core/` imported the monolith while `api/` imported
these, so the two copies sat one edit away from silently diverging on
whichever call path you did not happen to test. The monolith was deleted and
every importer repointed here -- keep new agent queries in this file so there
is exactly one definition to change.
"""
from typing import List, Optional, Dict, Any
from prisma.models import Agent
from db.client import db

async def create_agent(name: str, system_prompt: str, description: Optional[str] = None, 
                       voice_type: str = "default", llm_model: str = "llama-3.1-8b-instant", 
                       isActive: bool = True) -> Agent:
    return await db.agent.create(
        data={
            "name": name,
            "system_prompt": system_prompt,
            "description": description,
            "voice_type": voice_type,
            "llm_model": llm_model,
            "isActive": isActive
        }
    )

async def get_active_agents() -> List[Agent]:
    return await db.agent.find_many(where={"isActive": True})

async def get_all_agents() -> List[Agent]:
    return await db.agent.find_many()

async def get_agent(agent_id: str) -> Optional[Agent]:
    return await db.agent.find_unique(where={"id": agent_id})

async def update_agent(agent_id: str, data: Dict[str, Any]) -> Optional[Agent]:
    return await db.agent.update(where={"id": agent_id}, data=data)

async def delete_agent(agent_id: str) -> Optional[Agent]:
    return await db.agent.delete(where={"id": agent_id})

async def sync_core_agents(core_agents: List[dict]):
    """Upsert the JSON-defined core agents into the DB on startup.

    Moved here from the deleted `db/crud.py`. The `backend/agents/<category>/`
    tree is the source of truth for system agents, so this runs on every boot
    to reconcile the DB with what is on disk -- that is what lets a contributor
    add an agent by committing one JSON file, with the directory name becoming
    its category (see main.py startup). Upsert rather than insert because boots
    are repeated; keyed on the id declared in the JSON, not a generated uuid,
    so the same file maps to the same row across restarts and redeploys.
    """
    for agent_data in core_agents:
        existing = await db.agent.find_unique(where={"id": agent_data["id"]})
        if existing:
            await db.agent.update(where={"id": agent_data["id"]}, data=agent_data)
        else:
            await db.agent.create(data=agent_data)
