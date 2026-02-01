"""LLM-backed Q&A for in-progress analysis."""
from typing import Any, Dict, List
from src.core.config import settings


async def generate_analysis_answer(
    question: str,
    analysis_summary: Dict[str, Any],
    recent_logs: List[Dict[str, Any]],
    repo_summary: Dict[str, Any] | None,
    user_context: Dict[str, Any] | None
) -> str:
    """Generate an LLM answer grounded in current analysis state."""
    if not settings.OPENAI_API_KEY:
        return "LLM is not configured yet. Please set OPENAI_API_KEY to answer questions."

    instructions = (user_context or {}).get("instructions", []) or []
    instruction_text = "\n".join(
        f"- ({item.get('scope', 'global')}) {item.get('text')}"
        for item in instructions
        if isinstance(item, dict) and item.get("text")
    ) or "none"

    context_payload = {
        "analysis": analysis_summary,
        "repo_summary": repo_summary or {},
        "recent_logs": recent_logs[:10],
        "user_context": instruction_text
    }

    system_prompt = (
        "You are an analysis assistant for a codebase documentation system. "
        "Answer questions using ONLY the provided analysis state, logs, and repo summary. "
        "If the information is not available yet, say so clearly and suggest waiting for more progress. "
        "Keep the response concise and factual."
    )

    user_prompt = (
        f"Question: {question}\n\n"
        f"Context:\n{context_payload}"
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        return "No answer returned yet. Please try again."
    except Exception as exc:
        return f"Q&A failed: {str(exc)[:200]}"
