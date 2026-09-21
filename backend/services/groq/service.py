"""The one shared AsyncGroq client.

This module used to be a stub (`GroqLLMServiceStub`) that nothing imported,
while the real client lived inline in core/router.py. Voice needs the same
client for Whisper and Orpheus, and a service importing from `core/` would
invert the layering -- `core/` orchestrates services, not the other way round.
So the client moved down here and core/router.py now imports it.

Built on first use rather than at module scope: AsyncGroq raises when handed
no api_key, so constructing it at import made a missing GROQ_API_KEY an
*import* error that took down the health endpoint, every CRUD route and the
whole test suite -- none of which need Groq. Deferring keeps that failure
local to the request that actually needs the LLM.

Cached because the client holds a connection pool; rebuilding it per call
would leak sockets.
"""

from __future__ import annotations

import os

from groq import AsyncGroq

_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Add it to backend/.env for local "
                "runs, or to the service's environment variables when deployed."
            )
        _client = AsyncGroq(api_key=api_key)
    return _client
