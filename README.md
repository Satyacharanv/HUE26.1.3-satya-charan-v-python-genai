# maCAD System — Multi-Agent Code Analysis & Documentation

Transform any codebase into role-specific documentation with SDE/PM reports, architecture diagrams, Q&A with code citations, and PDF/Markdown export. Built with LangGraph, FastAPI, and Streamlit.

## Overview

maCAD is a multi-agent system that:

- **Ingests** code (ZIP or GitHub), chunks and embeds it for semantic search
- **Orchestrates** agents (Structure, Web Search, SDE, PM) via LangGraph with optional pause/resume
- **Produces** structured SDE/PM reports, Mermaid diagrams, and exportable documentation
- **Supports** Q&A over the codebase with file/line citations and optional Langfuse tracing

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI (REST + WebSocket/SSE) |
| **Frontend** | Streamlit |
| **Database** | PostgreSQL + pgvector |
| **Orchestration** | LangGraph (async, SQLite checkpoints) |
| **LLM / Embeddings** | OpenAI (configurable model) |
| **Observability** | Langfuse (optional) |
| **Web Search** | FastMCP server + Serper API (optional) |
| **PDF Export** | Playwright → WeasyPrint → ReportLab fallback |

## Features

- **M1 — Foundation**: JWT auth, project CRUD, file upload (ZIP), storage
- **M2 — Preprocessing**: Repo type/framework detection, multi-language parsing (8 languages), semantic chunking, pgvector embeddings
- **M3 — Real-Time Progress**: SSE live updates, activity feed, stage-based progress
- **M4 — Multi-Agent Orchestra**: Structure agent, conditional web search (knowledge gaps), SDE and PM agents, LangGraph workflow
- **M5 — Interactive Control**: Pause/resume analysis, configurable pause timeout, human-in-the-loop ready
- **M6 — Rich Outputs**: Structured SDE/PM reports, Documentation page, Mermaid diagrams, Q&A with code citations, PDF/Markdown export
- **M7 — Observability**: Admin API & dashboard, Langfuse tracing, token/cost tracking per analysis

Optional: **MCP server** (FastMCP) for web search; **Playwright** for high-quality PDFs; **Langfuse** for LLM observability.

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for PostgreSQL)
- (Optional) OpenAI API key, Serper API key for web search, Langfuse keys for tracing

### Install & Run

```bash
# Clone and enter project
cd maCAD-System

# Virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # Linux/Mac

# Dependencies
pip install -r requirements.txt

# Environment (copy .env.example to .env and set DB_*, JWT_SECRET_KEY, etc.)
copy .env.example .env         # Windows
# cp .env.example .env         # Linux/Mac

# Database
docker-compose up -d
alembic upgrade head

# Backend
uvicorn src.main:app --reload --port 8000

# Frontend (separate terminal)
streamlit run streamlit_app/main.py --server.port 8501

# MCP Server (separate terminal)
python mcp_server/app.py
```

**Full setup** (env vars, optional Playwright/MCP/Langfuse, troubleshooting): see **[SETUP.md](SETUP.md)**.

## Access

| What | URL |
|------|-----|
| **API** | http://localhost:8000 |
| **API docs (Swagger)** | http://localhost:8000/docs |
| **Streamlit app** | http://localhost:8501 |

App pages: **Login** → **Dashboard** (create project, start analysis) → **Analysis Console** (progress, pause/resume, Q&A) → **Documentation** (reports, diagrams, export) → **Admin Dashboard** (admin users only).

## Project Structure

```
maCAD-System/
├── src/                    # Backend
│   ├── api/v1/             # Auth, projects, analysis, admin, semantic search
│   ├── core/               # Config, security, exceptions
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Agents, orchestration, export, QA, MCP client
│   ├── prompts/            # Externalized prompts (JSON)
│   └── main.py             # FastAPI app
├── streamlit_app/          # Frontend
│   ├── pages/              # Login, Dashboard, Analysis Console, Documentation, Admin
│   └── utils/              # API client, auth, mermaid renderer
├── mcp_server/             # FastMCP web search tool (optional)
├── alembic/                # Migrations
├── scripts/                # init_db, seed_admin
├── storage/                # Uploads & artifacts (created at runtime)
├── .env.example            # Env template
├── SETUP.md                # Full setup guide
└── requirements.txt
```

## Milestones Summary

| Milestone | Status | Description |
|-----------|--------|-------------|
| **M1** | ✅ | Auth, projects, file handling |
| **M2** | ✅ | Preprocessing, chunking, embeddings |
| **M3** | ✅ | Real-time progress (SSE), activity feed |
| **M4** | ✅ | Multi-agent orchestration (LangGraph) |
| **M5** | ✅ | Pause/resume, configurable timeout |
| **M6** | ✅ | Rich reports, docs page, Q&A citations, PDF/MD export |
| **M7** | ✅ | Admin API/dashboard, Langfuse, token/cost tracking |

## Documentation

- **[SETUP.md](SETUP.md)** — Full setup, environment variables, optional components (Playwright, MCP, Langfuse), troubleshooting
- **API docs** — http://localhost:8000/docs (when backend is running)

## License & Support

For assignment or usage details, refer to the project brief or repository owner.
