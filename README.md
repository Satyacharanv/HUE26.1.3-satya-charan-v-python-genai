# maCAD System - Multi-Agent Code Analysis & Documentation System

A sophisticated multi-agent system that transforms any codebase into comprehensive, role-specific documentation with visual diagrams and real-time analysis.

## Tech Stack

- **Backend**: FastAPI (REST + WebSocket)
- **Frontend**: Streamlit
- **Database**: PostgreSQL + pgvector
- **Orchestration**: LangGraph (for future milestones)
- **Observability**: Langfuse (for future milestones)

## Setup

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- PostgreSQL 16+ with pgvector extension

### Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy environment file:
   ```bash
   cp .env.example .env
   ```

5. Start PostgreSQL:
   ```bash
   docker-compose up -d
   ```

6. Run database migrations:
   ```bash
   alembic upgrade head
   ```

7. Start the FastAPI backend:
   ```bash
   uvicorn src.main:app --reload --port 8000
   ```

8. Start the Streamlit frontend (in another terminal):
   ```bash
   streamlit run streamlit_app/main.py --server.port 8501
   ```

## Access

- **API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **Streamlit UI**: http://localhost:8501

## Project Structure

```
maCAD-System/
├── src/              # Backend source code
├── streamlit_app/    # Frontend Streamlit app
├── alembic/          # Database migrations
├── storage/          # File storage (created automatically)
└── tests/            # Tests
```

## Milestones

- **M1**: Foundation - Authentication, Project Creation, File Handling ✅
- **M2**: Intelligent Preprocessing - Code Analysis, Semantic Chunks, Embeddings ✅
- **M3**: Real-Time Progress (upcoming)
- **M4**: Multi-Agent Orchestra (upcoming)
- **M5**: Interactive Control (upcoming)
- **M6**: Rich Outputs (upcoming)
- **M7**: Observability & Admin (upcoming)

## Current Status: Milestone 2 Complete ✅

### What M2 Provides

**Intelligent Code Preprocessing Pipeline**:
- ✅ Repository type detection (Python, JavaScript, Java, etc.)
- ✅ Framework identification (50+ frameworks supported)
- ✅ Multi-language code parsing (8 languages with AST/regex)
- ✅ Semantic code chunking (functions, classes, methods)
- ✅ OpenAI embeddings for semantic search (pgvector)
- ✅ 7 REST APIs for code intelligence queries
- ✅ Real-time preprocessing job tracking

### Supported Languages
Python (AST), JavaScript/TypeScript, Java, C#, Go, Rust, PHP

### Key Features
- Framework Detection: FastAPI, Django, Flask, React, Next.js, Spring, and 45+ more
- Code Metadata: Functions, classes, methods, docstrings, parameters, return types
- Repository Intelligence: Entry points, dependencies, file statistics
- Semantic Storage: pgvector embeddings for similarity search (M3+)

### Documentation
- [M2_COMPLETE.md](M2_COMPLETE.md) - Completion summary
- [M2_IMPLEMENTATION.md](M2_IMPLEMENTATION.md) - Technical documentation  
- [M2_SETUP.md](M2_SETUP.md) - Setup and testing guide
