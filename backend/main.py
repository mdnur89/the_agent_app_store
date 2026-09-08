# MUST be the first local import: populates os.environ from backend/.env so
# that modules reading config at import time see it. See config.py for the two
# bugs this ordering fixes -- do not move it below the imports that follow.
import config  # noqa: F401  (imported for its import-time side effect)

import asyncio
import logging

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from db.client import db
from transports.telegram.transport import start_telegram_bot
from api.agents.router import router as agents_router
from api.users.router import router as users_router

tags_metadata = [
    {
        "name": "Agents",
        "description": "Operations with specialized AI agents, including creation, listing, updating, deleting, and chatting.",
    },
    {
        "name": "Users",
        "description": "Operations with users, managing profiles and settings.",
    },
]

app = FastAPI(
    title="Agent App Store API",
    description="The centralized backend for routing requests across a swarm of specialized AI agents via web and Telegram transports.",
    version="1.0.0",
    contact={
        "name": "API Support",
        "url": "http://localhost:5173",
        "email": "support@agentappstore.com",
    },
    openapi_tags=tags_metadata,
)

# Add CORS middleware for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router, prefix="/api/agents", tags=["Agents"])
app.include_router(users_router, prefix="/api/users", tags=["Users"])

# Populated by startup_event and read by /api/health. A dict rather than a
# module-level `None` so the health handler sees mutations without a global
# declaration, and so more probe state can be added without reworking it.
_startup_state: dict[str, str | None] = {"db_error": "startup has not run yet"}


@app.on_event("startup")
async def startup_event():
    logger.info("Connecting to database...")
    try:
        await db.connect()
        logger.info("Connected to database.")
        
        import json
        import os
        from db.agents.crud import sync_core_agents
        
        # Sync modular agents
        agents_dir = os.path.join(os.path.dirname(__file__), "agents")
        core_agents = []
        if os.path.exists(agents_dir):
            for category in os.listdir(agents_dir):
                category_path = os.path.join(agents_dir, category)
                if os.path.isdir(category_path):
                    for filename in os.listdir(category_path):
                        if filename.endswith(".json"):
                            with open(os.path.join(category_path, filename), "r") as f:
                                try:
                                    agent_data = json.load(f)
                                    agent_data["category"] = category
                                    core_agents.append(agent_data)
                                except json.JSONDecodeError as e:
                                    logger.error(f"Error parsing {filename}: {e}")
            
        if core_agents:
            await sync_core_agents(core_agents)
            logger.info(f"Synced {len(core_agents)} modular agents to DB.")
            
        _startup_state["db_error"] = None

    except Exception as e:
        # Deliberately non-fatal: crashing here would put the service into a
        # restart loop on Render, which is harder to diagnose than a running
        # process that reports itself unhealthy. The tradeoff is that the
        # failure must be visible somewhere -- hence recording it for
        # /api/health, which is what makes the bad deploy fail loudly instead
        # of serving 500s behind a green status.
        logger.error(f"Failed to connect or sync DB: {e}")
        _startup_state["db_error"] = str(e)

    asyncio.create_task(start_telegram_bot())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Disconnecting from database...")
    await db.disconnect()

@app.get("/api/health", summary="Liveness and database readiness probe")
async def api_health(response: Response):
    """Report unhealthy unless the database is actually reachable.

    This used to return a hardcoded {"status": "ok"}, which made it worse than
    useless: startup swallows database failures so the process comes up and
    answers 200 regardless, while every data route 500s. A wrong DATABASE_URL
    therefore sailed past Render's health check and shipped, and the dashboard
    showed a healthy service that could not serve a single agent.

    It runs a live query rather than replaying a flag cached at startup, because
    the interesting failures happen later -- Supabase's pooler dropping the
    connection, credentials rotated, the free tier pausing an idle project. A
    probe that only echoed a boot-time result would report ok through all of
    them.

    The query touches the Agent table rather than being a bare `SELECT 1` so it
    covers the schema too, not just TCP reachability. `prisma db push` runs in
    the start command and can fail on its own (notably if the `vector`
    extension is missing, which the Agent.capability_embedding column needs);
    that leaves a perfectly connectable database with no tables in it, where
    `SELECT 1` passes happily and every real route still 500s. LIMIT 1 on an
    empty table is a hit, not a miss, so this stays true of a fresh install.

    503 (not an exception) so the body still carries the diagnosis, and because
    that is the status platforms read as "do not route traffic here".
    """
    try:
        await db.query_raw('SELECT 1 FROM "Agent" LIMIT 1')
    except Exception as e:
        response.status_code = 503
        return {
            # "not_ready" rather than "unreachable": this branch covers both a
            # database we cannot reach and one we can reach that has no schema
            # (see the probe rationale above). Naming it after only the first
            # cause sent readers hunting for a network fault when the real
            # answer was a `prisma db push` that never ran -- the `error` field
            # below distinguishes them.
            "status": "unhealthy",
            "database": "not_ready",
            # startup_error is the original boot failure, which is usually the
            # more useful of the two: by the time anyone reads this, the live
            # query tends to fail with a generic "not connected".
            "startup_error": _startup_state["db_error"],
            "error": str(e),
        }

    return {"status": "ok", "database": "connected"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
