"""Structure analysis agent."""
from typing import Dict, Any, List
import ast
import re
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from src.services.analysis_progress import AnalysisProgressService
from src.services.agents.base_agent import BaseAgent
from src.models.repository_metadata import RepositoryMetadata, FileMetadata
from src.models.code_chunk import CodeChunk as CodeChunkModel
from src.services.storage import storage_service


class StructureAgent(BaseAgent):
    """Summarizes repository structure and basic API footprint."""

    name = "structure"
    description = "Analyze repository structure and entry points"

    async def run(
        self,
        state: Dict[str, Any],
        db: AsyncSession,
        progress: AnalysisProgressService
    ) -> Dict[str, Any]:
        project_id = state["project_id"]

        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message="StructureAgent: analyzing repository metadata",
            stage="agent_orchestration"
        )

        repo_result = await db.execute(
            select(RepositoryMetadata).where(RepositoryMetadata.project_id == project_id)
        )
        repo = repo_result.scalar_one_or_none()

        # Basic API footprint: chunks with route decorators or router mounting
        api_count_result = await db.execute(
            select(func.count(CodeChunkModel.id)).where(
                CodeChunkModel.project_id == project_id,
                or_(
                    CodeChunkModel.content.ilike("%@router.%"),
                    CodeChunkModel.content.ilike("%@app.%"),
                    CodeChunkModel.content.ilike("%@blueprint.%"),
                    CodeChunkModel.content.ilike("%include_router%"),
                    CodeChunkModel.content.ilike("%APIRouter%"),
                )
            )
        )
        api_chunks = api_count_result.scalar_one()

        # Python-specific structure extraction (routes, entrypoints, models)
        patterns = [
            "@router.", "@app.", "@blueprint.",
            "include_router", "APIRouter(",
            "FastAPI(", "Flask(", "uvicorn.run", "__name__ == \"__main__\"",
            "urlpatterns", "path(", "re_path(",
            "BaseModel", "models.Model", "declarative_base", "SQLAlchemy("
        ]
        stmt = select(CodeChunkModel.file_path, CodeChunkModel.content).where(
            CodeChunkModel.project_id == project_id,
            CodeChunkModel.language.ilike("python%"),
            or_(*[CodeChunkModel.content.ilike(f"%{p}%") for p in patterns])
        )
        result = await db.execute(stmt)
        rows = result.all()

        # Fallback entrypoint detection by filename (main.py/app.py)
        entrypoint_stmt = select(CodeChunkModel.file_path).where(
            CodeChunkModel.project_id == project_id,
            CodeChunkModel.language.ilike("python%"),
            or_(
                CodeChunkModel.file_path.ilike("%/main.py"),
                CodeChunkModel.file_path.ilike("%\\main.py"),
                CodeChunkModel.file_path.ilike("%/app.py"),
                CodeChunkModel.file_path.ilike("%\\app.py"),
            )
        ).distinct()
        entrypoint_result = await db.execute(entrypoint_stmt)
        entrypoint_rows = [r[0] for r in entrypoint_result.all() if r and r[0]]

        api_routes: List[Dict[str, Any]] = []
        entrypoint_files: List[str] = []
        model_hints: List[str] = []
        framework_hints: List[str] = []

        # Match @router.get("/path") or @router.get(\n  "/path") (re.DOTALL so \s matches newlines)
        fastapi_rx = re.compile(
            r"@(?:app|router)\.(get|post|put|delete|patch|options|head)\s*\(\s*['\"]([^'\"]+)['\"]",
            re.DOTALL,
        )
        apirouter_prefix_rx = re.compile(
            r"APIRouter\([^)]*prefix\s*=\s*['\"]([^'\"]+)['\"]",
            re.DOTALL,
        )
        include_router_prefix_rx = re.compile(
            r"include_router\([^)]*prefix\s*=\s*['\"]([^'\"]+)['\"]",
            re.DOTALL,
        )
        flask_rx = re.compile(r"@(?:app|blueprint)\.route\s*\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?")
        django_path_rx = re.compile(r"\bpath\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z0-9_\.]+)")
        django_re_path_rx = re.compile(r"\bre_path\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z0-9_\.]+)")
        pydantic_rx = re.compile(r"class\s+([A-Za-z0-9_]+)\s*\(.*BaseModel.*\)\s*:")
        sqlalchemy_rx = re.compile(r"class\s+([A-Za-z0-9_]+)\s*\(.*Base.*\)\s*:")
        django_model_rx = re.compile(r"class\s+([A-Za-z0-9_]+)\s*\(.*models\.Model.*\)\s*:")

        seen_fastapi: set = set()
        for file_path, content in rows:
            text = content or ""
            if "FastAPI(" in text:
                framework_hints.append("FastAPI")
                entrypoint_files.append(file_path)
            if "Flask(" in text:
                framework_hints.append("Flask")
            if "django" in text or "urlpatterns" in text:
                framework_hints.append("Django")

            if "__name__ == \"__main__\"" in text or "uvicorn.run" in text:
                entrypoint_files.append(file_path)

            for match in fastapi_rx.findall(text):
                method, path = match
                key = (file_path, method.upper().strip(), path.strip())
                if key in seen_fastapi:
                    continue
                seen_fastapi.add(key)
                api_routes.append({
                    "framework": "fastapi",
                    "method": method.upper().strip(),
                    "path": path.strip(),
                    "file_path": file_path,
                })

            # Capture router prefixes to avoid empty API list when only prefixes are present
            for prefix in apirouter_prefix_rx.findall(text):
                api_routes.append({
                    "framework": "fastapi",
                    "method": "N/A",
                    "path": prefix.strip(),
                    "file_path": file_path,
                })
            for prefix in include_router_prefix_rx.findall(text):
                api_routes.append({
                    "framework": "fastapi",
                    "method": "N/A",
                    "path": prefix.strip(),
                    "file_path": file_path,
                })

        # AST-based extraction (framework-agnostic and more robust than regex)
        ast_routes: List[Dict[str, Any]] = []
        ast_entrypoints: List[str] = []
        ast_models: List[str] = []
        ast_frameworks: List[str] = []

        def _is_main_guard(node: ast.AST) -> bool:
            if not isinstance(node, ast.If):
                return False
            test = node.test
            return (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            )

        def _string_arg(call: ast.Call) -> str | None:
            if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                return call.args[0].value
            return None

        def _keyword_str(call: ast.Call, name: str) -> str | None:
            for kw in call.keywords or []:
                if kw.arg == name and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    return kw.value.value
            return None

        def _keyword_list(call: ast.Call, name: str) -> List[str]:
            for kw in call.keywords or []:
                if kw.arg == name and isinstance(kw.value, (ast.List, ast.Tuple)):
                    out = []
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            out.append(elt.value)
                    return out
            return []

        verb_set = {"get", "post", "put", "delete", "patch", "options", "head"}
        django_func_set = {"path", "re_path", "include"}

        file_stmt = await db.execute(
            select(FileMetadata.file_path).where(
                FileMetadata.project_id == project_id,
                FileMetadata.language.ilike("python%")
            )
        )
        python_files = [r[0] for r in file_stmt.all() if r and r[0]]
        project_root = storage_service.projects_path / str(project_id) / "extracted"

        for rel_path in python_files[:300]:
            abs_path = project_root / Path(rel_path)
            if not abs_path.exists():
                continue
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue

            for node in ast.walk(tree):
                # Framework hints via imports
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("django"):
                        ast_frameworks.append("Django")
                    if node.module and node.module.startswith("pyspark"):
                        ast_frameworks.append("PySpark")
                if isinstance(node, ast.Import):
                    for alias in node.names or []:
                        if alias.name.startswith("django"):
                            ast_frameworks.append("Django")
                        if alias.name.startswith("pyspark"):
                            ast_frameworks.append("PySpark")

                # Entry points
                if _is_main_guard(node):
                    ast_entrypoints.append(rel_path)
                if isinstance(node, ast.Call):
                    # Framework instantiation
                    if isinstance(node.func, ast.Name):
                        if node.func.id == "FastAPI":
                            ast_frameworks.append("FastAPI")
                            ast_entrypoints.append(rel_path)
                        if node.func.id == "Flask":
                            ast_frameworks.append("Flask")
                            ast_entrypoints.append(rel_path)
                        if node.func.id == "APIRouter":
                            ast_frameworks.append("FastAPI")
                            prefix = _keyword_str(node, "prefix")
                            if prefix:
                                ast_routes.append({
                                    "framework": "fastapi",
                                    "method": "N/A",
                                    "path": prefix,
                                    "file_path": rel_path,
                                })
                        if node.func.id == "Blueprint":
                            ast_frameworks.append("Flask")
                        if node.func.id == "SparkSession":
                            ast_frameworks.append("PySpark")
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr == "include_router":
                            prefix = _keyword_str(node, "prefix")
                            if prefix:
                                ast_routes.append({
                                    "framework": "fastapi",
                                    "method": "N/A",
                                    "path": prefix,
                                    "file_path": rel_path,
                                })
                        if node.func.attr == "getOrCreate":
                            # SparkSession.builder.getOrCreate()
                            ast_frameworks.append("PySpark")

                # Decorated route handlers
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in node.decorator_list or []:
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                            verb = dec.func.attr.lower()
                            if verb in verb_set:
                                path = _string_arg(dec) or ""
                                ast_routes.append({
                                    "framework": "fastapi",
                                    "method": verb.upper(),
                                    "path": path,
                                    "file_path": rel_path,
                                })
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "route":
                            path = _string_arg(dec) or ""
                            methods_list = _keyword_list(dec, "methods")
                            ast_routes.append({
                                "framework": "flask",
                                "method": (methods_list[0].upper() if methods_list else "GET"),
                                "path": path,
                                "file_path": rel_path,
                            })

                # Model hints (AST)
                if isinstance(node, ast.ClassDef):
                    for base in node.bases or []:
                        if isinstance(base, ast.Name) and base.id == "BaseModel":
                            ast_models.append(node.name)
                        if isinstance(base, ast.Attribute) and base.attr in {"Base", "Model"}:
                            ast_models.append(node.name)

                # Django urlpatterns extraction
                if isinstance(node, ast.Assign):
                    targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                    if "urlpatterns" in targets and isinstance(node.value, (ast.List, ast.Tuple)):
                        ast_frameworks.append("Django")
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Call):
                                call_func = elt.func
                                func_name = None
                                if isinstance(call_func, ast.Name):
                                    func_name = call_func.id
                                elif isinstance(call_func, ast.Attribute):
                                    func_name = call_func.attr
                                if func_name in django_func_set:
                                    path = _string_arg(elt) or ""
                                    ast_routes.append({
                                        "framework": "django",
                                        "method": "N/A",
                                        "path": path,
                                        "file_path": rel_path,
                                    })

            for match in flask_rx.findall(text):
                path, methods = match
                method_list = [m.strip().strip("'\"") for m in methods.split(",")] if methods else ["GET"]
                for m in method_list:
                    api_routes.append({
                        "framework": "flask",
                        "method": m.upper(),
                        "path": path,
                        "file_path": file_path,
                    })

            for match in django_path_rx.findall(text):
                path, handler = match
                api_routes.append({
                    "framework": "django",
                    "method": "N/A",
                    "path": path,
                    "handler": handler,
                    "file_path": file_path,
                })
            for match in django_re_path_rx.findall(text):
                path, handler = match
                api_routes.append({
                    "framework": "django",
                    "method": "N/A",
                    "path": path,
                    "handler": handler,
                    "file_path": file_path,
                })

            for match in pydantic_rx.findall(text):
                model_hints.append(match)
            for match in sqlalchemy_rx.findall(text):
                model_hints.append(match)
            for match in django_model_rx.findall(text):
                model_hints.append(match)

        # de-duplicate
        framework_hints = sorted(set(framework_hints + ast_frameworks))
        entrypoint_files = sorted(set(entrypoint_files + entrypoint_rows + ast_entrypoints))
        model_hints = sorted(set(model_hints + ast_models))

        # de-duplicate routes (framework, method, path, file)
        if api_routes or ast_routes:
            seen_routes = set()
            deduped = []
            for r in (api_routes + ast_routes):
                key = (
                    r.get("framework"),
                    r.get("method"),
                    r.get("path"),
                    r.get("file_path"),
                )
                if key in seen_routes:
                    continue
                seen_routes.add(key)
                deduped.append(r)
            api_routes = deduped

        summary = {
            "repository_type": repo.repository_type if repo else "unknown",
            "primary_framework": repo.primary_framework if repo else None,
            "total_files": repo.total_files if repo else 0,
            "code_files": repo.code_files if repo else 0,
            "entry_points": repo.entry_points if repo else {},
            "config_files": repo.config_files_list if repo else [],
            "api_chunk_hits": int(api_chunks or 0),
            "api_routes": api_routes[:200],
            "entrypoint_files": entrypoint_files[:50],
            "model_hints": model_hints[:200],
            "framework_hints": framework_hints
        }

        await progress.log_event(
            analysis_id=state["analysis_id"],
            level="info",
            message=f"StructureAgent: detected {summary['repository_type']} repo with "
                    f"{summary['code_files']} code files and {summary['api_chunk_hits']} API hints",
            stage="agent_orchestration"
        )

        gaps = list(state.get("knowledge_gaps", []) or [])
        if not api_routes:
            gaps.append("no_api_routes_detected")
        if not entrypoint_files and not (repo.entry_points if repo else None):
            gaps.append("no_entrypoints_detected")
        if not model_hints:
            gaps.append("no_models_detected")
        gaps = sorted(set(gaps))

        return {
            "repo_summary": summary,
            "knowledge_gaps": gaps,
            "web_search_requester": "structure"
        }
