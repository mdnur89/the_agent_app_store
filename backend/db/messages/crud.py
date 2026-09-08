"""Canonical home for message persistence.

These functions used to be duplicated verbatim between this module and a
monolithic `db/crud.py`; `core/` imported the monolith while `api/` imported
these, so the two copies sat one edit away from silently diverging on
whichever call path you did not happen to test. The monolith was deleted and
every importer repointed here -- keep new message queries in this file so there
is exactly one definition to change.
"""
from typing import List
from prisma.models import Message
from db.client import db

async def save_message(session_id: str, role: str, content: str) -> Message:
    return await db.message.create(
        data={
            "session_id": session_id,
            "role": role,
            "content": content
        }
    )

async def get_session_history(session_id: str, limit: int = 20) -> List[Message]:
    return await db.message.find_many(
        where={"session_id": session_id},
        order={"createdAt": "asc"},
        take=limit
    )
