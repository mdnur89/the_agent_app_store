# The Hub: AI Agent Swarm Ecosystem 🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

A modular, highly scalable "App Store" for AI agents. This platform allows users to browse, switch between, and interact with various AI personas. It has evolved from a simple Telegram bot into a **Massive Multi-Agent Swarm Ecosystem** where agents can dynamically discover and collaborate with each other.

## 🧠 Core Features

- **Hierarchical Swarm Architecture**: Top-level "Supervisor" agents (like the Master Orchestrator) can break down complex user requests and delegate sub-tasks to specialist agents in the background, synthesizing their responses for the user.
- **Semantic Agent Discovery**: Utilizing Supabase `pgvector`, agents are embedded into a vector space based on their capabilities. Supervisors dynamically search the vector database to discover and recruit the exact experts they need on the fly.
- **Private-by-default Accounts**: Supabase Auth protects agent creation and chat history. User agents remain private until their owner explicitly publishes them.
- **Multi-Transport Interfaces**: 
  - **Web Dashboard & Chat**: A premium React dashboard to create agents and a dedicated web-chat UI to interact with them directly in the browser.
  - **Telegram Bot**: Native integration via webhooks/polling, maintaining conversation memory across transports.
- **Voice In and Out**: Send a Telegram voice note or tap the mic in the web chat and Groq Whisper
  transcribes it; the reply is spoken back with Groq Orpheus in the agent's configured voice.
  Uses the existing `GROQ_API_KEY` — no extra provider. Set `VOICE_ENABLED=false` for text-only.
- **Modular Domains**: Agents are structured logically by domain (`business`, `personal`, `system`), making it trivial to scale the ecosystem.

## 🏗 Architecture

This project strictly adheres to a **Domain-Driven Design (DDD)** and Separation of Concerns:
- **Backend**: FastAPI (Python), serving as the core orchestration and API layer.
- **Frontend**: React + Vite + Vanilla CSS, providing a premium, ultra-modern dashboard for agent management.
- **Database**: PostgreSQL with `pgvector` (hosted on Supabase) accessed via `prisma-client-py` with asyncio support.
- **Routing**: A unified `MessageRouter` that handles cross-agent tool calling, memory management, and dynamic LLM (Groq) generation.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- A [Supabase](https://supabase.com) account (for PostgreSQL, **must support pgvector**)
- A Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- A [Groq API Key](https://console.groq.com/) for LLM inference

### 2. Environment Setup

Navigate to the `backend/` directory and create a `.env` file:
```env
# Supabase PostgreSQL connection strings
DATABASE_URL="postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?pgbouncer=true"
DIRECT_URL="postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

# API Keys
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
GROQ_API_KEY="your_groq_api_key"

# Supabase Auth and browser origin
SUPABASE_URL="https://YOUR-PROJECT-REF.supabase.co"
# Only needed for legacy HS256 projects; asymmetric projects use JWKS.
SUPABASE_JWT_SECRET="your_legacy_jwt_secret"
CORS_ORIGINS="http://localhost:5173"

# Local semantic search controls
EMBEDDINGS_ENABLED="true"
FASTEMBED_CACHE_DIR=".fastembed_cache"
EMBEDDING_THREADS="1"
OMP_NUM_THREADS="1"
```

### 3. Backend Installation

We use a Python Virtual Environment to keep dependencies clean.

```bash
cd backend/
# Create and activate virtual environment (Windows/MINGW64)
python -m venv venv
source venv/Scripts/activate

# Install requirements
pip install -r requirements.txt

# For an existing installation, back up the database and run the reviewed
# statements in prisma/PRE_DEPLOY.sql before pushing this schema, then run
# prisma/POST_DEPLOY.sql to classify preserved rows.
prisma generate
prisma db push
```

### 4. Frontend Installation

```bash
cd frontend/
npm install
```

Create `frontend/.env.local`:

```env
VITE_API_URL="http://localhost:8000"
VITE_SUPABASE_URL="https://YOUR-PROJECT-REF.supabase.co"
VITE_SUPABASE_PUBLISHABLE_KEY="your_publishable_key"
```

---

## 💻 Running Locally

You will need two terminals running simultaneously.

### Start the Backend (Terminal 1)
```bash
cd backend/
source venv/Scripts/activate
uvicorn main:app --reload
```
*The backend runs on `http://localhost:8000`. This will simultaneously start the FastAPI server and the Telegram bot polling.*

### Start the Frontend (Terminal 2)
```bash
cd frontend/
npm run dev
```
*The frontend runs on `http://localhost:5173`.*

---

## 🌍 Production Deployment

The project is architected to run across a split-deployment model for optimal performance: the Frontend on a static CDN, and the Backend on a robust containerized platform to support the always-on Telegram polling.

### 1. Deploying the Backend
The checked-in Render blueprint is a starting point, but local ONNX embeddings add roughly 300–400 MB RSS above FastAPI and Prisma. Use a host with adequate memory, or set `EMBEDDINGS_ENABLED=false` to retain keyword discovery without loading the model.
1. Create a new account on Render and connect your GitHub repository.
2. Go to **Blueprints** and create a New Blueprint Instance using the `render.yaml` file in this repo.
3. Render will automatically detect the configuration, run `prisma generate`, and start the `uvicorn` server.
4. **Environment Variables**: Add the database/API variables plus `SUPABASE_URL`, the production `CORS_ORIGINS`, and (legacy projects only) `SUPABASE_JWT_SECRET`.
5. Copy the generated Render URL (e.g., `https://your-app.onrender.com`).

### 2. Deploying the Frontend (Vercel - Free Tier)
Deploy the React application to [Vercel](https://vercel.com/) for lightning-fast, free static hosting.
1. Import your GitHub repository into Vercel.
2. Set the Root Directory to `frontend`.
3. Set the Build Command to `npm run build` and Output Directory to `dist`.
4. **Environment Variables**: Add `VITE_API_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY`.
5. Vercel will use the provided `vercel.json` to handle React Router SPA routing seamlessly.

---
## 📁 Project Structure

```text
/agents_store
 ├── /backend               # Python FastAPI application
 │   ├── /agents            # Modular JSON agent definitions
 │   │   ├── /business      # Business specialists (e.g. Sales, Tech Support)
 │   │   ├── /personal      # Personal specialists (e.g. Fitness, Therapy)
 │   │   └── /system        # Supervisor agents (e.g. Master Orchestrator)
 │   ├── /api               # REST API Routers & Schemas (Agents, Users)
 │   ├── /core              # Unified MessageRouter & Swarm Delegation
 │   ├── /db                # Prisma Client & Vector Search logic
 │   ├── /prisma            # Prisma schema definitions (Modularized)
 │   ├── /services          # External integrations (Groq, TTS, Embeddings)
 │   ├── /transports        # Protocol integrations (Telegram)
 │   └── main.py            # Entry point for Uvicorn
 │
 ├── /frontend              # React + Vite application
 │   ├── /src
 │   │   ├── /assets
 │   │   ├── /components
 │   │   ├── /pages         # Dashboard, Landing Page, and Web Chat UI
 │   │   ├── App.jsx
 │   │   └── index.css      # Premium Design System tokens
 │   ├── index.html
 │   └── package.json
 │
 ├── AGENTS.md              # System Architecture Rules & Guidelines
 └── .gitignore             # Global git ignores
```

## 🤝 Contributing

We welcome contributions from the community! Whether you are adding a new specialist agent to the swarm, fixing a bug, or improving the React dashboard, please check out our [Contributing Guidelines](CONTRIBUTING.md) for how to get started.

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

### Architectural Rules
When contributing, please refer to `AGENTS.md` for strict guidelines regarding anti-spaghetti code and maintaining absolute separation of concerns.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
