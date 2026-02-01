"""Accumulate LLM token usage and cost per analysis; update Analysis record and UI."""
from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.services.analysis_progress import AnalysisProgressService

# USD per 1M tokens (input, output). Approximate OpenAI list pricing; adjust as needed.
MODEL_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}

# USD per 1M tokens for embedding models.
EMBEDDING_PRICING = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}


def compute_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Compute estimated cost in USD from token counts and model name."""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0
    pricing = MODEL_PRICING.get(model) or MODEL_PRICING.get("gpt-4o-mini", (0.15, 0.60))
    input_per_1m, output_per_1m = pricing
    return (prompt_tokens / 1_000_000 * input_per_1m) + (
        completion_tokens / 1_000_000 * output_per_1m
    )


def compute_embedding_cost(total_tokens: int, model: str) -> float:
    """Compute estimated cost in USD for embedding API (single price per 1M tokens)."""
    if total_tokens <= 0:
        return 0.0
    per_1m = EMBEDDING_PRICING.get(model) or EMBEDDING_PRICING.get(
        "text-embedding-3-small", 0.02
    )
    return total_tokens / 1_000_000 * per_1m


async def record_llm_usage(
    progress: "AnalysisProgressService",
    analysis_id: UUID,
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
) -> None:
    """Accumulate tokens and cost for this analysis and call progress.update_progress."""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return
    analysis = await progress.get_analysis(analysis_id)
    if not analysis:
        return
    current_tokens = getattr(analysis, "total_tokens_used", None) or 0
    current_cost = float(getattr(analysis, "estimated_cost", None) or 0.0)
    new_tokens = prompt_tokens + completion_tokens
    cost_delta = compute_cost(prompt_tokens, completion_tokens, model)
    await progress.update_progress(
        analysis_id,
        tokens_used=current_tokens + new_tokens,
        estimated_cost=round(current_cost + cost_delta, 6),
    )


async def record_embedding_usage(
    progress: "AnalysisProgressService",
    analysis_id: UUID,
    total_tokens: int,
    model: str,
) -> None:
    """Accumulate embedding tokens and cost for this analysis and call progress.update_progress."""
    if total_tokens <= 0:
        return
    analysis = await progress.get_analysis(analysis_id)
    if not analysis:
        return
    current_tokens = getattr(analysis, "total_tokens_used", None) or 0
    current_cost = float(getattr(analysis, "estimated_cost", None) or 0.0)
    cost_delta = compute_embedding_cost(total_tokens, model)
    await progress.update_progress(
        analysis_id,
        tokens_used=current_tokens + total_tokens,
        estimated_cost=round(current_cost + cost_delta, 6),
    )
