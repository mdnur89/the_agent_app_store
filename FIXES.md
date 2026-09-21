# Engineering Record — Fork of `TadiwanasheZvidzaRodney/the_agent_app_store`

**Fork point:** `08a6f9a` · **Scope:** 60 files, +2463 / −541

Everything this fork changed, in one place. Two bodies of work:

1. **Correctness, security and deploy safety** — five defects in the inherited code.
2. **Finishing the three headline features** the README advertised but that were stubs:
   semantic discovery, open delegation, and accounts/ownership. Plus voice.

---

# Part 1 — Correctness, security & deploy safety

## 1.1 `process_web_message` violated its own return contract

**HTTP 500 on routine input.**

`MessageRouter.process_web_message` returns `(reply, session_id)` rather than a bare
reply, because `transfer_to_agent` retires the current session and opens a new one —
the caller cannot assume the session it passed in is the session that answered. One
exit path returned a bare string:

```python
if not session:
    return "Session not found."     # every other path returns a 2-tuple
```

The chat route unpacks two values, so any request carrying a `session_id` the database
no longer knows raised `ValueError` → **500**. Not exotic: a browser holds `session_id`
in React state across a DB reset or a `prisma db push` that dropped rows.

All exit paths now return a 2-tuple, annotated `-> tuple[str, str]` so a type checker
catches the next regression.

Fixing only the tuple would have turned the 500 into a **200 whose `reply` body was the
literal string `"Session not found."`** — rendered in the transcript as if the agent had
said it. So both ids are validated at the API boundary and return 404.

## 1.2 Two parallel CRUD layers, one edit from divergence

`db/crud.py` (62 lines) duplicated `db/{users,agents,sessions,messages}/crud.py`
verbatim — and the two halves of the codebase imported *different copies* (`core/` the
monolith, `api/` the modules). An edit to one would silently diverge on whichever call
path you did not happen to test.

Monolith deleted, per-domain modules canonical, all six importers repointed. Each module
carries a docstring recording why it is the single home.

## 1.3 TLS verification disabled in production

```python
# Disable SSL verification for local dev to bypass Windows cert/proxy issues
request = HTTPXRequest(httpx_kwargs={"verify": False})
```

The comment says "local dev", but this was the only code path — it also ran on Render.
Certificate verification was off for **every Telegram API call, including those carrying
`TELEGRAM_BOT_TOKEN`**.

Now verifies against certifi's CA bundle — the actual remedy for the Windows failures
the flag was working around. The escape hatch survives as opt-in `TELEGRAM_INSECURE_SSL`
and logs a warning; the old version failed open in silence, which is how it reached a
deployed service unnoticed. Same one-liner corrected in `test_bot.py`.

## 1.4 `.env` loading worked only by accident

`core/router.py` built its Groq client at module scope; `main.py` called `load_dotenv()`
**after** the import that reached it. It worked only because instantiating `Prisma()`
calls `load_dotenv()` as a side effect — from the *cwd*, so it resolved only when
launched from inside `backend/`.

New `backend/config.py` loads `backend/.env` anchored on `__file__`, imported first by
`main.py` and `db/client.py`. The Groq client is now built lazily, so a missing key is a
per-request error rather than an import-time crash that took down the health endpoint
and every CRUD route.

## 1.5 A dead database reported itself healthy

`/api/health` returned a hardcoded `{"status": "ok"}` while startup swallowed database
failures — so a wrong `DATABASE_URL` sailed past Render's health check and shipped green
while every data route 500d.

It now runs a live query and returns **503** with the diagnosis. Three deliberate calls:
a live query rather than a boot-time flag (pooler drops and paused free tiers happen
later); it touches the `Agent` table rather than `SELECT 1`, so a `prisma db push` that
failed leaves a connectable database with no tables and is still caught; and startup
stays non-fatal, because a restart loop is harder to diagnose than a process reporting
itself unhealthy. `render.yaml` gained `healthCheckPath`.

---

# Part 2 — Semantic agent discovery (was a stub)

The README advertised pgvector semantic discovery. In fact `db/search.py` had the query
entirely commented out, `search_agents_by_capability` returned `find_many(take=3)` —
the first three rows, **ignoring the query** — and `generate_mock_embedding` returned
`[0.01] * 1536`, making every agent equidistant. Nothing had ever written an embedding.

**Now real**, using local ONNX embeddings (`fastembed`, `BAAI/bge-small-en-v1.5`, 384-d).
No API key, no external embedding vendor.

- `services/embeddings/service.py` — lazy model load (never at import: a ~130MB ONNX
  graph between `import main` and FastAPI existing would take the health endpoint down),
  `asyncio.to_thread` plus a lock so two concurrent requests cannot each load a graph.
- `db/agents/embeddings.py` — the sole raw-SQL boundary, because prisma-client-py cannot
  see `Unsupported("vector")` columns. Parameterized throughout; vector and content hash
  always written in one statement.
- `db/search.py` — cosine `<=>` (not the original's L2 `<->`, which would silently
  bypass the index opclass), `isActive` filtered, self excluded, and a per-token ILIKE
  keyword fallback that tops up whenever semantic returns fewer than `limit`.
- Content-hash dirty check so unchanged agents are not re-embedded on every boot.
- HNSW index (`vector_cosine_ops`), not IVFFlat — no `lists` tuning, no retraining.
- `EMBEDDINGS_ENABLED=false` degrades to keyword search rather than failing.

**Verified working** — not just wired. Real embeddings, correct specialist ranked first:

| Query | Top hit | Score |
|---|---|---|
| "help me lose weight and build muscle" | `sys-fitness-coach` | 0.604 |
| "I feel anxious and overwhelmed" | `sys-therapist` | 0.493 |
| "my laptop will not boot" | `sys-tech-support` | 0.468 |

---

# Part 3 — Open delegation (was one hardcoded node)

`core/router.py` gated every tool on `agent.id == "sys-orchestrator"`, a string literal,
so no other agent could ever search or delegate.

Replaced with a per-tool grant driven by a new `capabilities String[]` column. Per-tool
rather than one boolean because `transfer_to_agent` permanently retires the user's
session — a much larger grant than `search_experts`.

Two traps closed in the same change:

- **`capabilities` is not settable through the API** — absent from `AgentCreate` /
  `AgentUpdate`, which are `extra="forbid"`. Grants come only from committed JSON.
- **Delegation recursion became reachable** the moment more than one agent could
  delegate. `run_agent_headless` gained a depth cap.

---

# Part 4 — Accounts & ownership (there was no auth at all)

Before: CORS `allow_origins=["*"]`, every browser visitor sharing one account
(`web_user_id` defaulting to the literal `"web-user-1"`, written into
`User.telegram_id`), every agent globally visible and deletable by anyone, and
`GET /api/users/` + `DELETE /api/users/{id}` exposing and deleting **any** user
unauthenticated.

**Supabase Auth**, verified locally against JWKS. Branches on the token's `alg` and
never puts HS256 and an asymmetric algorithm in one `algorithms=[]` list — the public
key is published, so sharing a decode call invites algorithm confusion. Supports both
asymmetric (RS256/ES256/EdDSA, default for projects since 2025-05-01) and the legacy
HS256 secret.

- `Agent` gained `owner_id`, `visibility`, `published_at`; private by default with
  explicit publish/unpublish. The 5 core agents stay platform-owned and public.
- `User` gained `supabase_user_id`, `email`, `is_admin`; `telegram_id` became nullable.
- Telegram accounts link via a one-time `/link CODE` — transactional, single-use via a
  conditional `used_at` write, rate limited, and it merges an existing anonymous
  Telegram row rather than stranding its history.
- `GET|DELETE /api/users/me` replace the open routes; listing is admin-gated.
- CORS restricted to an explicit origin list with `allow_credentials=False`.

### Security fixes in this part

| Issue | Before | Now |
|---|---|---|
| **IDOR on chat sessions** | Any caller could pass any `session_id`; the route only checked the row *existed*. The full history was then loaded into the model — so a stranger could read (*"summarise our conversation"*) and write to anyone's transcript. | `session.user_id != user.id` → 404 |
| **Private agents reachable via the orchestrator** | `core/router.py` interpolated *every* agent's name and id into the supervisor prompt, and `delegate_task`/`transfer_to_agent` ran an `agent_id` **chosen by the LLM** with no visibility check — a prompt-injected orchestrator could execute any user's private agent. | Visibility-scoped listing; LLM-supplied ids re-resolved through `get_visible_agent` |
| **System prompts leaked** | Routes returned raw Prisma models, so `GET /api/agents/` exposed every agent's `system_prompt` — the thing the author actually built. | `AgentOut`; `system_prompt` only for its owner |
| **Private agent existence oracle** | 403 on another user's private agent confirmed the id was real. | Resolved through the visibility filter first → 404 |

---

# Part 5 — Voice (was a stub)

`services/tts/service.py` returned hardcoded strings, `core/pipeline/runner.py` returned
`"This is a response generated by the modular Pipecat pipeline."`, and the Telegram voice
handler replied "please send text for now". Every agent carried a `voice_type` that did
nothing.

Now real, via **Groq Whisper (STT) and Groq Orpheus (TTS)** — the same `GROQ_API_KEY` the
chat completions already use, so voice added **no vendor, no key and no dependency**
beyond `python-multipart` for the upload.

- Telegram: voice note → transcript echoed back (so a misrecognition is obvious) → agent
  reply → spoken reply in that agent's voice.
- Web: mic button in the chat, plus a 🔈 on each reply. `POST /{id}/chat/voice`
  (multipart) and `POST /{id}/speak` (→ `audio/wav`). Speech is a separate call so
  callers don't pay for synthesis they never play.
- `voice_type` finally means something: `male-1`→troy, `female-1`→hannah, etc. The map
  lives in one dict so the agent JSON stays provider-agnostic.
- `VOICE_ENABLED=false` runs text-only.
- `services/groq/service.py` — was a second dead stub, now the shared lazy Groq client
  (a service importing from `core/` would invert the layering).

---

# Part 6 — Repo hygiene

- **`.gitignore` was silently swallowing `frontend/src/lib/`.** An unanchored `lib/`
  from the Python template matched any directory of that name at any depth, so
  `api.js`, `supabase.js` and `voice.js` were untracked — and every page imports from
  them, so a fresh clone would not have built. Anchored to `/lib/`.
- Deleted the dead `core/pipeline/runner.py`; both `services/*` stubs are now real code.
- `.env.example` for backend and frontend; README updated.

---

# Deploying this

**Order matters — getting it wrong takes the service down, not just the feature.**
`prisma db push` runs in the Render *start* command, so a destructive diff fails the
boot rather than the deploy.

1. Back up: `pg_dump "$DIRECT_URL" -n public -Fc -f pre.dump`
2. Run `backend/prisma/PRE_DEPLOY.sql` — confirms pgvector is reachable and performs the
   `vector(1536)` → `vector(384)` change by hand while the column is still all-NULL.
3. `prisma generate && prisma db push`
4. Run `backend/prisma/POST_DEPLOY.sql` — publishes the core agents, quarantines
   pre-auth custom agents (they were created anonymously; there is no signal tying them
   to a person, so they are preserved but invisible until claimed), retires `web-user-1`.
5. Set `SUPABASE_URL`, `CORS_ORIGINS`, `GROQ_API_KEY`, `DATABASE_URL`, `DIRECT_URL`, and
   `VITE_SUPABASE_URL` / `VITE_SUPABASE_PUBLISHABLE_KEY` on the frontend.

### Breaking changes

- `ChatRequest.web_user_id` is gone; all agent write routes and chat now require a bearer
  token.
- `GET /api/users/` and `DELETE /api/users/{id}` are admin-only; `/me` variants added.
- New agents default to **private**.

---

# Verification

Run against a throwaway Python 3.14 venv and a disposable PostgreSQL 18.6 cluster.

| Area | Result |
|---|---|
| Semantic ranking | Correct specialist first on all three probe queries (table above) |
| Auth | No token / garbage token / expired → 401; anon `POST /api/agents/` → 401 |
| Prompt leakage | `system_prompt` absent from anonymous `GET /api/agents/` |
| IDOR | User B resuming A's `session_id` → 404, through both the text and voice routes |
| Ownership ladder | Another user's private → 404; their public → 403; system → 403; own → allowed |
| Voice guards | Empty / oversized audio, empty text, `VOICE_ENABLED=false` all degrade cleanly |
| Degradation | pgvector absent → logged, swallowed, keyword search still serves |
| Build | Backend compiles and imports; frontend builds (85 modules), lints clean, 0 npm vulnerabilities |

### Not verified — read before merging

- **The pgvector SQL path has never executed.** The test database had no pgvector, so
  `<=>`, the `::vector` casts and the HNSW index have never run once. Embedding *quality*
  is proven; the *query* is not.
- **No valid Supabase token has ever been accepted.** Rejection is tested; the
  authenticated happy path is not.
- **No real Groq call.** No LLM reply, no Whisper transcription, no Orpheus synthesis has
  actually round-tripped — request shapes match the SDK signatures, nothing more.
- **Telegram `/link` has never been redeemed** against a live bot.
- Migrations in `PRE_DEPLOY.sql` / `POST_DEPLOY.sql` have not been run anywhere.

---

# Known gaps (unchanged, out of scope)

- No test suite and no CI. `test_db.py` / `test_bot.py` are manual scripts.
- `pipecat-ai` remains an unused dependency (deliberately kept).
- `switch_user_agent` deactivates *all* of a user's sessions, so two browser tabs on two
  agents clobber each other.
- The `deployment` file documents a stale Railway setup superseded by `render.yaml`.
- "Millions of agents" is five.
