# maCAD System — Setup Guide

## Prerequisites

- **Python 3.10+**
- **Docker & Docker Compose** (for PostgreSQL)
- (Optional) Git

---

## Required Setup

### 1. Python and dependencies

From the project root:

```bash
python -m venv venv
```

Activate the virtual environment:

- **Windows:** `venv\Scripts\activate`
- **Linux/Mac:** `source venv/bin/activate`

Install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Environment variables

Copy the example env file and edit `.env`:

- **Windows:** `copy .env.example .env`
- **Linux/Mac:** `cp .env.example .env`

Set these **required** values in `.env`:

| Variable | Description |
|----------|-------------|
| `DB_HOST` | PostgreSQL host (e.g. `localhost`) |
| `DB_PORT` | PostgreSQL port (e.g. `5432`) |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
| `DB_NAME` | Database name (e.g. `macad_db`) |
| `JWT_SECRET_KEY` | Secret for auth tokens (min 32 characters) |

Leave other variables as in `.env.example` unless you need them.

### 3. Start PostgreSQL(Optional)

```bash
docker-compose up -d
```

Check that the container is running: `docker ps`.

### 4. Initialize the database

```bash
alembic upgrade head
```

Or, if you prefer to create tables without migrations:

```bash
python scripts/init_db.py
```

### 5. Start the backend

**Option A — Command line**

```bash
uvicorn src.main:app --reload --port 8000
```

**Option B — Windows batch file**

```bash
run_backend.bat
```

Backend: **http://localhost:8000**  
API docs: **http://localhost:8000/docs**

### 6. Start the frontend

Open a **second** terminal, activate the same venv, then:

**Option A — Command line**

```bash
streamlit run streamlit_app/main.py --server.port 8501
```

**Option B — Windows batch file**

```bash
run_frontend.bat
```

Frontend: **http://localhost:8501**

---

## Verify setup

1. Open **http://localhost:8000/docs** — Swagger UI should load.
2. Open **http://localhost:8501** — Streamlit app should load.
3. Sign up and log in, then create a project and run an analysis.

**Optional:** Create an admin user to use the Admin Dashboard:

```bash
python scripts/seed_admin.py admin@example.com your_password
```

---

## Optional setup

Use these only if you need the extra features.

### MCP server (web search during analysis)

1. Get a [Serper](https://serper.dev) API key and add to `.env`:  
   `SERPER_API_KEY=your_key`
2. In `.env`, set:  
   `MCP_SERVER_URL=http://127.0.0.1:8001/sse`
3. Start the MCP server (from project root, with venv activated):

   **Command line:** `python -m mcp_server.app`  
   **Windows:** `run_mcpserver.bat`

The server runs at **http://127.0.0.1:8001**. Without it, analysis still runs; web search is skipped.

### Playwright (better PDF export)

For higher-quality PDF export from the Documentation page:

```bash
playwright install chromium
```

If Playwright is not used or fails, the app uses WeasyPrint, then ReportLab.

### Langfuse (LLM tracing)

1. Create a project at [Langfuse](https://cloud.langfuse.com).
2. In `.env`, set:  
   `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`

The app works without Langfuse; token usage and cost are still stored in the database.

### Other environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY`, `OPENAI_MODEL` | LLM for reports and Q&A |
| `STORAGE_PATH`, `MAX_ZIP_SIZE_MB` | File storage (defaults: `./storage`, 100) |
| `PAUSE_TIMEOUT_MINUTES` | Auto-cancel paused analysis after N minutes (default: 5) |

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| **Database connection** | PostgreSQL running (`docker ps`), correct `DB_*` in `.env`, `docker logs macad_postgres` |
| **Port in use** | Backend: 8000, Frontend: 8501, PostgreSQL: 5432, MCP: 8001. Change in `.env` or command line if needed. |
| **Import / Python errors** | Venv activated, Python 3.10+, `pip install -r requirements.txt` |
| **Upload / storage** | `STORAGE_PATH` in `.env` exists and is writable; check `MAX_ZIP_SIZE_MB` |
| **PDF export** | Try `playwright install chromium`; otherwise WeasyPrint/ReportLab are used. |
| **Web search / MCP** | MCP server running, `MCP_SERVER_URL` and `SERPER_API_KEY` set in `.env` |

---

For more detail, see **README.md** and **http://localhost:8000/docs** when the backend is running.
