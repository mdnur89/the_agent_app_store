"""Canonical home for session persistence.

These functions used to be duplicated verbatim between this module and a
monolithic `db/crud.py`; `core/` imported the monolith while `api/` imported
these, so the two copies sat one edit away from silently diverging on
whichever call path you did not happen to test. The monolith was deleted and
every importer repointed here -- keep new session queries in this file so there
is exactly one definition to change.
"""
from typing import Optional
from prisma.models import Session
from db.client import db

async def switch_user_agent(user_id: str, new_agent_id: str) -> Session:
    await db.session.update_many(
        where={"user_id": user_id, "isActive": True},
        data={"isActive": False}
    )
    session = await db.session.create(
        data={
            "user_id": user_id,
            "agent_id": new_agent_id,
            "isActive": True
        }
    )
    return session

async def get_active_session(user_id: str) -> Optional[Session]:
    """The user's current conversation, or None if they have not picked an agent.

    Moved here from the deleted `db/crud.py`. Belongs with sessions rather than
    users because "which agent am I talking to" is session state: switching
    agents deactivates one row and creates another (see switch_user_agent),
    so a user has many sessions and at most one active.
    """
    return await db.session.find_first(
        where={"user_id": user_id, "isActive": True},
        include={"agent": True}  # include the agent to know system_prompt
    )

async def get_session(session_id: str) -> Optional[Session]:
    """Existence check for a client-supplied session id.

    Added so the chat route can 404 an unknown id at the boundary instead of
    letting it reach MessageRouter, where the miss surfaces as agent dialogue.
    Deliberately does not `include` the agent: callers that need the agent
    re-query with the relation, and this stays a cheap lookup.
    """
    return await db.session.find_unique(where={"id": session_id})
