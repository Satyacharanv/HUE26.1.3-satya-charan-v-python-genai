"""LLM-backed structured report generation for SDE and PM agents."""
from typing import Dict, Any, Optional
from pathlib import Path
from uuid import UUID
import json
import re
from src.core.config import settings
from src.services.langfuse_client import log_generation
from src.services.usage_tracker import record_llm_usage


PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _load_prompt(name: str, fallback: str) -> str:
    path = PROMPT_DIR / name
    try:
        if path.exists():
            if path.suffix.lower() == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                # Accept either {"text": "..."} or {"system": "...", "user": "..."}
                if isinstance(data, dict):
                    if "text" in data and isinstance(data["text"], str):
                        return data["text"]
                return json.dumps(data)
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return fallback


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


async def generate_sde_report_structured(
    repo_summary: Dict[str, Any],
    web_findings: str,
    instruction_block: str,
    analysis_depth: str,
    progress: Optional[Any] = None,
    analysis_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Generate structured SDE report JSON via LLM. Returns empty dict if LLM unavailable."""
    if not getattr(settings, "OPENAI_API_KEY", None):
        return {}

    system_prompt = _load_prompt(
        "sde_system.json",
        "You are a technical writer producing SDE documentation from structured repo data. "
        "Output ONLY valid JSON with the required keys."
    )
    user_template = _load_prompt(
        "sde_user.json",
        "Generate an SDE report as JSON only.\n"
        "Context:\n{context_json}\n"
    )
    context_payload = {
        "repo_summary": repo_summary,
        "web_findings": web_findings or "none",
        "instruction_block": instruction_block or "none",
        "analysis_depth": analysis_depth,
    }
    user_content = user_template.format_map(_SafeDict({
        "context_json": json.dumps(context_payload, ensure_ascii=True)
    }))

    return await _call_llm_json(
        system_prompt=system_prompt,
        user_content=user_content,
        progress=progress,
        analysis_id=analysis_id,
    )


async def generate_pm_report(
    repo_summary: Dict[str, Any],
    instruction_block: str,
    analysis_depth: str,
    progress: Optional[Any] = None,
    analysis_id: Optional[UUID] = None,
) -> str:
    """Generate structured PM report markdown via LLM. Returns empty string if LLM unavailable."""
    if not getattr(settings, "OPENAI_API_KEY", None):
        return ""

    system_prompt = _load_prompt(
        "pm_system.json",
        "You are a product manager documenting features and flows from repo metadata. "
        "Output only valid Markdown."
    )
    user_template = _load_prompt(
        "pm_user.json",
        "Generate a PM report in Markdown.\nContext:\n{context_json}\n"
    )
    context_payload = {
        "repo_summary": repo_summary,
        "instruction_block": instruction_block or "none",
        "analysis_depth": analysis_depth,
    }
    user_content = user_template.format_map(_SafeDict({
        "context_json": json.dumps(context_payload, ensure_ascii=True)
    }))

    return await _call_llm(
        system_prompt=system_prompt,
        user_content=user_content,
        progress=progress,
        analysis_id=analysis_id,
    )


async def _call_llm(
    system_prompt: str,
    user_content: str,
    progress: Optional[Any] = None,
    analysis_id: Optional[UUID] = None,
) -> str:
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        if response.choices and response.choices[0].message.content:
            content = response.choices[0].message.content.strip()
            usage = {}
            if getattr(response, "usage", None):
                usage = {
                    "input": response.usage.prompt_tokens,
                    "output": response.usage.completion_tokens,
                    "total": response.usage.total_tokens,
                }
                if progress and analysis_id:
                    await record_llm_usage(
                        progress,
                        analysis_id,
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                        model,
                    )
            log_generation(
                name="pm_report",
                model=model,
                input_data=user_content,
                output_data=content,
                usage=usage,
            )
            return content
        return ""
    except Exception:
        return ""


async def _call_llm_json(
    system_prompt: str,
    user_content: str,
    progress: Optional[Any] = None,
    analysis_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )
        except Exception:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
        content = response.choices[0].message.content if response.choices else ""
        if not content:
            return {}
        content = content.strip()
        usage = {}
        if getattr(response, "usage", None):
            usage = {
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
                "total": response.usage.total_tokens,
            }
            if progress and analysis_id:
                await record_llm_usage(
                    progress,
                    analysis_id,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    model,
                )
        log_generation(
            name="sde_report_structured",
            model=model,
            input_data=user_content,
            output_data=content,
            usage=usage,
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # try to extract JSON object from the response
            match = re.search(r"\{.*\}", content, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return {}
        return {}
    except Exception:
        return {}


def sde_structured_to_markdown(data: Dict[str, Any]) -> str:
    if not data:
        return ""
    def _section(title: str, body: str, sources: Optional[list] = None) -> str:
        body_str = (body.strip() if body else "Not detected in the data.")
        out = "## " + title + "\n" + body_str + "\n"
        if sources:
            out += "\n**Sources:** " + ", ".join(str(s) for s in sources) + "\n"
        return out
    summary = data.get("summary", "").strip()
    architecture = data.get("architecture", "")
    api = data.get("api_endpoints", [])
    data_models = data.get("data_models", [])
    code_structure = data.get("code_structure", "")
    setup = data.get("setup", "")
    security = data.get("security", "")
    notes = data.get("notes", "")
    sources = data.get("sources")  # optional: {"architecture": [...], "api": [...], ...}

    def _src(key: str) -> Optional[list]:
        if not sources or not isinstance(sources, dict):
            return None
        v = sources.get(key)
        return v if isinstance(v, list) else ([v] if v else None)

    parts = []
    if summary:
        parts.append("# SDE Summary\n" + summary + "\n")
    parts.append(_section("Architecture", architecture, _src("architecture")))
    if api:
        api_lines = []
        for item in api:
            if isinstance(item, dict):
                method = item.get("method", "")
                path = item.get("path", "")
                desc = item.get("description", "")
                source = item.get("file_path", "")
                api_lines.append(f"- {method} {path} {('- ' + desc) if desc else ''}{(' (' + source + ')') if source else ''}".strip())
            else:
                api_lines.append(f"- {item}")
        parts.append(_section("API / Endpoints", "\n".join(api_lines), _src("api")))
    else:
        parts.append(_section("API / Endpoints", "No API routes/handlers detected in the provided analysis.", _src("api")))
    if data_models:
        model_lines = []
        for m in data_models:
            if isinstance(m, dict):
                name = m.get("name", "")
                purpose = m.get("purpose", "")
                model_lines.append(f"- {name} – {purpose}" if purpose else f"- {name}")
            else:
                model_lines.append(f"- {m}")
        parts.append(_section("Database / Data Models", "\n".join(model_lines), _src("data_models")))
    else:
        parts.append(_section("Database / Data Models", "No data models detected in the provided analysis.", _src("data_models")))
    parts.append(_section("Code Structure", code_structure, _src("code_structure")))
    parts.append(_section("Setup & Run", setup, _src("setup")))
    parts.append(_section("Security & Authentication", security, _src("security")))
    if notes:
        parts.append(_section("Notes", notes))
    return "\n".join(parts)
