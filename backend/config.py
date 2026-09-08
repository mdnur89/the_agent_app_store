"""Loads `backend/.env` into os.environ, once, before anything reads config.

Import this FIRST -- above any local import -- in every entrypoint.

Two separate bugs made this necessary:

1. Ordering. `main.py` called load_dotenv() *after* importing the local
   packages, but `core/router.py` builds its Groq client at module scope, so
   the key was read before the file that defines it had been loaded. That only
   ever worked by accident: `core/router.py` imports the db layer first, and
   instantiating `Prisma()` happens to call load_dotenv() as a side effect.
   Swapping two import lines, or a prisma-client-py release dropping that
   behaviour, would have broken local dev with a confusing GroqError at import.

2. Working directory. Prisma's incidental load passes the *relative* path
   '.env', so it only resolves when the process is launched from inside
   backend/. Running `uvicorn backend.main:app` from the repo root silently
   found no .env and fell back to whatever was in the ambient environment.

Anchoring on __file__ fixes both: the same file loads no matter where uvicorn
is invoked from, and it lands in os.environ before any consumer imports.

Real environment variables win over .env (override=False), so the values set
in the Render/Vercel dashboards are authoritative in deployment and a stray
committed .env can never shadow them.
"""

from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ENV_PATH = BACKEND_DIR / ".env"

# No-op when the file is absent, which is the normal case in production where
# the platform injects real environment variables instead.
load_dotenv(ENV_PATH, override=False)
