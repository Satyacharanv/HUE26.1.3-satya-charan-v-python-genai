# Setup Guide for maCAD System

## Prerequisites

- **Python 3.10 or higher**
- **Docker & Docker Compose** (for PostgreSQL)
- **Git** (optional)

## Step-by-Step Setup

### 1. Install Python Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example environment file
# Windows:
copy .env.example .env
# Linux/Mac:
cp .env.example .env

# Edit .env and set at least:
# - Database: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# - Security: JWT_SECRET_KEY (min 32 characters)
```

**Environment variables reference:**

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | Yes | PostgreSQL connection |
| `JWT_SECRET_KEY` | Yes | Min 32 chars; used for auth tokens |
| `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Auth defaults (HS256, 30 min) |
| `API_V1_PREFIX`, `PROJECT_NAME`, `DEBUG` | No | App settings |
| `STORAGE_PATH`, `MAX_ZIP_SIZE_MB` | No | File storage (default: `./storage`, 100 MB) |
| `GITHUB_TOKEN` | No | For GitHub repo ingestion (future) |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | No | LLM for reports and Q&A (e.g. gpt-4o) |
| `ANTHROPIC_API_KEY` | No | Alternative LLM provider |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | No | Optional tracing (Langfuse) |
| `MCP_SERVER_URL` | No | MCP server URL for web search (e.g. `http://127.0.0.1:8001/sse`) |
| `PAUSE_TIMEOUT_MINUTES` | No | Minutes before paused analyses auto-cancel (default: 5) |
| `SERPER_API_KEY` | No | For MCP web search tool (Serper API) |

### 3. Start PostgreSQL Database

```bash
# Start PostgreSQL with Docker Compose
docker-compose up -d

# Verify it's running
docker ps
```

### 4. Initialize Database

```bash
# Run Alembic migrations (preferred)
alembic upgrade head

# Or create tables manually
python scripts/init_db.py
```

### 5. (Optional) Create Admin User

```bash
python scripts/seed_admin.py admin@example.com your_password
```

Admin users can access the **Admin Dashboard** (Streamlit page 6) for system health, users, projects, analyses, and error logs.

### 6. (Optional) Playwright for PDF Export

For best-quality PDF export of documentation, install Playwright browsers once:

```bash
playwright install chromium
```

If Playwright is not installed or fails (e.g. in asyncio contexts), the app falls back to **WeasyPrint**, then **ReportLab**. On some systems WeasyPrint may need GTK; ReportLab works without extra system libs.

### 7. (Optional) MCP Server for Web Search

To enable **conditional web search** during analysis (filling knowledge gaps):

1. **Get a Serper API key** from [serper.dev](https://serper.dev) and set `SERPER_API_KEY` in `.env`.
2. **Start the MCP server** (loads `.env` from project root):

   ```bash
   # From project root, with venv activated
   python -m mcp_server.app
   ```

   Server runs by default at `http://127.0.0.1:8001` (SSE transport).

3. **Set backend config**: In `.env`, set  
   `MCP_SERVER_URL=http://127.0.0.1:8001/sse`  
   (or the SSE URL your FastMCP version exposes).

If `MCP_SERVER_URL` or `SERPER_API_KEY` is not set, analysis still runs; web search steps are skipped or return a friendly “not configured” message.

### 8. (Optional) Langfuse for Observability

For LLM tracing and cost tracking:

1. Create a project at [Langfuse](https://cloud.langfuse.com) (or self-host).
2. Set in `.env`:
   - `LANGFUSE_PUBLIC_KEY`
   - `LANGFUSE_SECRET_KEY`
   - `LANGFUSE_HOST` (e.g. `https://cloud.langfuse.com`)

If these are not set, the app runs without Langfuse; token usage and cost are still accumulated in the database per analysis.

### 9. Start Backend Server

```bash
# Option 1: Using uvicorn directly
uvicorn src.main:app --reload --port 8000

# Option 2: Using the batch script (Windows)
run_backend.bat

# Option 3: Using Python
python -m src.main
```

- **Backend:** http://localhost:8000  
- **API docs (Swagger):** http://localhost:8000/docs  

### 10. Start Frontend (Streamlit)

```bash
# Option 1: Using streamlit directly
streamlit run streamlit_app/main.py --server.port 8501

# Option 2: Using the batch script (Windows)
run_frontend.bat
```

- **Frontend:** http://localhost:8501  

## Testing the Setup

### 1. API and Auth

- Open http://localhost:8000/docs and try the health or auth endpoints.
- In the app (http://localhost:8501), sign up and log in.

### 2. Project and Analysis

1. **Dashboard** → Create Project (upload ZIP or GitHub URL).
2. Select personas (SDE, PM, or both) and start analysis.
3. **Analysis Console** (page 4): monitor progress, pause/resume, and use Q&A with code citations.
4. **Documentation** (page 5): view SDE/PM reports, diagrams, and export PDF/Markdown.

### 3. Admin (if admin user exists)

- Log in as admin and open **Admin Dashboard** (page 6) for overview, users, projects, analyses, and errors.

## Troubleshooting

### Database

- Ensure PostgreSQL is running: `docker ps`
- Check `DB_*` and `.env`; inspect logs: `docker logs macad_postgres`

### Ports

- Backend: 8000 | Frontend: 8501 | PostgreSQL: 5432 | MCP (optional): 8001
- Change via `.env` or command-line arguments if needed.

### Import / Python

- Activate the venv and ensure Python 3.10+: `python --version`
- Reinstall: `pip install -r requirements.txt`

### Storage and Uploads

- Set `STORAGE_PATH` in `.env`; ensure the path exists and is writable.
- Respect `MAX_ZIP_SIZE_MB` for uploads.

### PDF Export

- **Playwright:** Run `playwright install chromium`. If you see “Playwright Sync API inside asyncio loop”, PDF may still be generated via WeasyPrint/ReportLab fallback.
- **WeasyPrint:** On Windows/Linux, GTK may be required; if it fails, ReportLab is used automatically.
- **ReportLab:** No extra install; works everywhere but with simpler layout.

### MCP / Web Search

- Confirm MCP server is running and `MCP_SERVER_URL` in `.env` matches the server’s SSE URL.
- Ensure `SERPER_API_KEY` is set for real search results; otherwise the tool returns “not configured”.

### Langfuse

- Verify `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` (or `LANGFUSE_BASE_URL`).
- App works without Langfuse; tracing is optional.

## Project Structure

```
maCAD-System/
├── src/                    # Backend
│   ├── api/v1/             # API routes (auth, projects, analysis, admin)
│   ├── core/               # Config, security, exceptions
│   ├── models/             # Database models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Agents, orchestration, export, QA, MCP client
│   ├── prompts/           # Externalized prompts (JSON)
│   └── main.py             # FastAPI app
├── streamlit_app/          # Frontend
│   ├── pages/              # Dashboard, Projects, Analysis Console, Documentation, Admin
│   └── utils/              # API client, helpers
├── mcp_server/             # FastMCP server (web search tool)
├── alembic/                # Migrations
├── scripts/                # init_db, seed_admin
├── storage/                # Uploads (created at runtime)
└── tests/                 # Tests
```

## Features Included

- **Milestone 1:** Auth, projects, storage  
- **M2:** Intelligent preprocessing, chunking, embeddings  
- **M3:** Real-time progress (SSE), activity feed  
- **M4:** Multi-agent orchestration (structure, web search, SDE, PM)  
- **M5:** Pause/resume with timeout, interactive control  
- **M6:** Rich outputs — structured reports, documentation page, Q&A with code citations, PDF/Markdown export, Mermaid diagrams  
- **M7:** Observability — Admin API & dashboard, Langfuse tracing, token/cost tracking  

## Support

For more detail, see the main **README.md** and the API documentation at http://localhost:8000/docs .
