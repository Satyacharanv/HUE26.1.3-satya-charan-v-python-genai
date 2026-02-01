"""Langfuse helper utilities for LLM tracing."""
from __future__ import annotations
from typing import Any, Dict, Optional
from src.core.config import settings


def _get_client():
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST_RESOLVED,
        )
    except Exception:
        return None


def log_generation(
    name: str,
    model: str,
    input_data: Any,
    output_data: Any,
    usage: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    client = _get_client()
    if not client:
        return
    try:
        trace = client.trace(name=name, metadata=metadata or {})
        generation = trace.generation(
            name=name,
            model=model,
            input=input_data,
            metadata=metadata or {},
        )
        generation.end(output=output_data, usage=usage or {})
    except Exception:
        pass
