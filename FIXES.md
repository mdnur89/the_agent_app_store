# Backend Fixes — Correctness, Consolidation & Deploy Safety

**Base commit:** `08a6f9a`
**Scope:** 14 files changed, +288 / −91, plus one new file (`backend/config.py`)
**Status:** committed to `main`

Five fixes to the FastAPI backend: two crash/500 bugs, one duplication hazard, one
security defect, and one deploy-safety gap. No feature work, no behaviour changes to
the agent swarm itself.

---

## 1. `process_web_message` violated its own return contract

**Severity:** bug — HTTP 500 on a routine input

`MessageRouter.process_web_message` returns `(reply, session_id)` rather than a bare
reply, because `transfer_to_agent` retires the current session and opens a new one —
the caller cannot assume the session it passed in is the session that answered.

One exit path returned a bare string instead:

```python
# core/router.py — before
if not session:
    return "Session not found."     # every other path returns a 2-tuple
```

The chat route unpacks two values, so any request carrying a `session_id` the
database no longer knows raised `ValueError` → **HTTP 500**. That is not an exotic
input: a browser holds `session_id` in React state across a DB reset or a
`prisma db push` that dropped rows.

**Fix:** all exit paths now return a 2-tuple; the annotation says `-> tuple[str, str]`
so a type checker catches the next regression. The unknown id is echoed back rather
than replaced, because inventing a session would silently migrate the user onto a
different conversation.

### The guard that actually matters

Fixing only the tuple would have converted the 500 into a **200 whose `reply` body was
the literal string `"Session not found."`** — rendered in the transcript as if the
agent had said it. The user would see the bot apologising while the client never
learns its state is stale.

So the ids are now validated at the API boundary (`api/agents/router.py`):

```python
if not await crud.get_agent(agent_id):
    raise HTTPException(status_code=404, detail="Agent not found")

if session_id:
    if not await session_crud.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
```

The router's fallback remains as defence in depth for future callers.

**Files:** `core/router.py`, `api/agents/router.py`, `db/sessions/crud.py` (new `get_session`)

---

## 2. Two parallel CRUD layers, one edit from divergence

**Severity:** maintenance hazard

The repo carried the same persistence functions twice:

| Location | Imported by |
| --- | --- |
| `db/crud.py` (monolith, 62 lines) | `core/`, `main.py`, `transports/`, `test_db.py` |
| `db/{users,agents,sessions,messages}/crud.py` | `api/` |

`get_or_create_user`, `switch_user_agent`, `save_message`, `get_session_history` and
`get_active_agents` existed verbatim in both. Because the two halves of the codebase
imported *different copies*, an edit to one would silently diverge on whichever call
path you did not happen to test.

**Fix:** the monolith is deleted; the per-domain modules are canonical, matching the
DDD layout the README already describes.

- `get_active_session` → `db/sessions/crud.py`
- `sync_core_agents` → `db/agents/crud.py`
- all six importers repointed
- each module carries a docstring recording why it is the single home

> **Dropped:** `get_agent_by_id` was dead code (no importers) and identical to
> `db/agents/crud.py::get_agent`, so it was not carried over.

---

## 3. TLS verification disabled in production

**Severity:** security

```python
# transports/telegram/transport.py — before
# Disable SSL verification for local dev to bypass Windows cert/proxy issues
request = HTTPXRequest(httpx_kwargs={"verify": False})
```

The comment says "local dev", but this is the only code path — it also runs on Render.
Certificate verification was off for **every Telegram API call, including those
carrying `TELEGRAM_BOT_TOKEN`**, leaving the bot exposed to anyone able to intercept
the connection and present their own certificate.

**Fix:** verify against certifi's CA bundle, which is the actual remedy for the
Windows failures the flag was working around (a missing or stale system trust store —
the file already sets `SSL_CERT_FILE`/`SSL_CERT_DIR` for exactly this reason).

The escape hatch survives for genuinely broken setups (a corporate MITM proxy) but is
now **opt-in and loud**:

```python
if os.getenv("TELEGRAM_INSECURE_SSL", "").lower() in ("1", "true", "yes"):
    logger.warning("TLS certificate verification is DISABLED. ...")
    verify = False
else:
    verify = certifi.where()
```

The old version failed open in silence, which is how it survived into a deployed
service unnoticed.

Same one-liner corrected in `test_bot.py` — it is the script people copy when
debugging the bot, so leaving the insecure flag there is how it grows back.
`certifi` was added to `requirements.txt`: it is imported directly but was only
arriving transitively via httpx.

---

## 4. `.env` loading worked only by accident

**Severity:** bug — latent, breaks on any import reorder

`core/router.py` built its Groq client at module scope, and `AsyncGroq` raises when
handed no key. `main.py` called `load_dotenv()` at line 19 — **after** line 14 had
already imported that module transitively.

It worked anyway for a reason nobody wrote down: `core/router.py` imports the db layer
first, and instantiating `Prisma()` calls `load_dotenv()` as a side effect. Swapping
two import lines, or prisma-client-py dropping that behaviour, would break local dev
with a confusing `GroqError` at import time.

A second defect hid behind the first: Prisma's incidental load passes the **relative**
path `'.env'`, so it only resolves when the process is launched from inside
`backend/`. Running uvicorn from the repo root silently found no `.env`.

**Fix — `backend/config.py` (new, 37 lines):** loads `backend/.env` anchored on
`__file__`, imported first by `main.py` and `db/client.py`.

```python
BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env", override=False)
```

`override=False` keeps Render/Vercel dashboard variables authoritative in deployment.
Importing it from `db/client.py` also covers the standalone scripts (`test_db.py`,
`check_msgs.py`), which have no startup hook of their own.

**Fix — lazy Groq client:** the client is now built on first use via
`get_groq_client()` and cached (it holds a connection pool). A missing key was
previously an *import* error that took down the health endpoint, the agent CRUD routes
and any test run — none of which need Groq. It now degrades to a per-request error
inside handlers that already catch exceptions and surface them as the agent's reply.

---

## 5. A dead database reported itself healthy

**Severity:** deploy safety

```python
# main.py — before
@app.get("/api/health")
async def api_health():
    return {"status": "ok"}
```

Startup catches database failures and continues, so the process reports
"Application startup complete" and answers **200** while every data route 500s. A
wrong `DATABASE_URL` therefore sailed past Render's health check and shipped, showing
a green service that could not serve a single agent.

**Fix:** the probe runs a live query and returns **503** with the diagnosis:

```python
try:
    await db.query_raw('SELECT 1 FROM "Agent" LIMIT 1')
except Exception as e:
    response.status_code = 503
    return {"status": "unhealthy", "database": "not_ready",
            "startup_error": _startup_state["db_error"], "error": str(e)}
```

Three deliberate choices:

- **A live query, not a flag cached at startup.** The interesting failures happen
  later — Supabase's pooler dropping the connection, credentials rotated, the free
  tier pausing an idle project.
- **It touches the `Agent` table, not a bare `SELECT 1`.** `prisma db push` can fail
  on its own — notably when the `vector` extension is missing, which
  `Agent.capability_embedding` needs — leaving a connectable database with no tables
  where `SELECT 1` passes and every route still 500s. `LIMIT 1` on an empty table is a
  hit, not a miss, so this stays true of a fresh install.
- **Startup stays non-fatal.** Crashing would put Render into a restart loop, which is
  harder to diagnose than a running process that reports itself unhealthy. The boot
  error is recorded and surfaced in the 503 body instead.

`render.yaml` gained `healthCheckPath: /api/health`, which is what makes a bad
`DATABASE_URL` fail the rollout rather than go live.

---

## Verification

Deps are not installed in the working environment, so everything below ran against a
throwaway Python 3.14 venv and a disposable PostgreSQL 18.6 cluster. Both were removed
afterwards; the project directory and the system Postgres instance were untouched.

### Toolchain

The project targets Python 3.10 (`render.yaml` pins `3.10.0`); the test machine runs
3.14.7 and Node 26.8.1. No compatibility problems surfaced.

| Check | Result |
| --- | --- |
| `pip install -r requirements.txt` on Python 3.14.7 | clean — fastapi 0.141.1, groq 1.7.0, ptb 22.8, prisma 0.15.0 |
| `prisma generate` (modular `prismaSchemaFolder`) | generated in 83 ms |
| `npm ci` + `vite build` on Node 26.8.1 | 33 modules, 247 kB, 112 ms |
| All `.py` compile | pass |
| AST check: 26 `db.*` imports resolve post-refactor | pass |

### Runtime behaviour

| Scenario | Expected | Actual |
| --- | --- | --- |
| Healthy DB, launched from `backend/` | 200 | `{"status":"ok","database":"connected"}` |
| DB unreachable | 503 | `not_ready` + `"All connection attempts failed"` |
| DB reachable, schema never pushed | 503 | `` "The table `public.Agent` does not exist" `` |
| Launched from repo root (`--app-dir`) | 200 | `.env` still resolved |
| No `GROQ_API_KEY` anywhere | app serves | 200; `import main` succeeds — previously a hard `GroqError` |

One defect was caught during this pass and corrected: the 503 body originally reported
`"database": "unreachable"` even when the database was reachable and only the schema
was missing — misleading in the exact endpoint meant to diagnose it. It now reports
`not_ready`, with the `error` field distinguishing the two causes.

---

## Known gaps (untouched)

Out of scope for this pass, but worth recording:

- **Semantic agent discovery is a stub.** The pgvector query in `db/search.py` is
  entirely commented out; `search_agents_by_capability` returns the first 3 agents and
  ignores the query. Nothing ever writes `capability_embedding`. The README describes
  this as implemented.
- **Voice is a stub.** `services/tts/service.py` and `core/pipeline/runner.py` return
  hardcoded strings; `pipecat-ai` is a dependency but unused.
- **No auth.** CORS is `allow_origins=["*"]` and web users are keyed into
  `User.telegram_id` via a `web_user_id` field defaulting to `"web-user-1"`.
- **`AgentForm.jsx` offers `gemini-1.5-flash`**, but all calls go to Groq, which does
  not serve Gemini models — selecting it produces a runtime error.
- **`deployment`** (extensionless) documents a stale Railway setup superseded by
  `render.yaml`, and leaks the original author's local Windows paths.
- **`AGENTS.md`** is referenced twice by the README but is listed in `.gitignore:76`,
  so contributors will never receive it.
- **No test suite.** `test_db.py`, `test_bot.py` and `check_msgs.py` are manual
  scripts, and `.github/` contains only issue templates.
- `npm audit` reports one high-severity advisory (`nanoid <3.3.18`, transitive via
  Vite), fixable with `npm audit fix`.

---

## To run

```bash
cd backend/
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
prisma generate && prisma db push      # needs `create extension vector;` in Supabase
uvicorn main:app --reload

cd ../frontend/ && npm install && npm run dev
```

Required: `DATABASE_URL`, `DIRECT_URL`, `GROQ_API_KEY`. `TELEGRAM_BOT_TOKEN` is
optional — without it the bot logs an error and the API still serves.
