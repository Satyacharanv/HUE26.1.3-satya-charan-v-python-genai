"""Server-side Mermaid rendering using mermaid-cli when available."""
from __future__ import annotations

import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

import httpx


def render_mermaid_svg(code: str) -> Tuple[bytes | None, str | None]:
    """
    Render Mermaid to SVG via mermaid-cli (npx @mermaid-js/mermaid-cli).
    Returns (svg_bytes, error_message).
    """
    try:
        cleaned = (code or "").strip()
        if not cleaned:
            return None, "Empty Mermaid code"
        with tempfile.NamedTemporaryFile(suffix=".mmd", delete=False) as f:
            f.write(cleaned.encode("utf-8"))
            mmd_path = f.name
        out_path = mmd_path + ".svg"
        result = subprocess.run(
            ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", mmd_path, "-o", out_path],
            capture_output=True,
            timeout=30,
            text=True,
        )
        Path(mmd_path).unlink(missing_ok=True)
        if result.returncode != 0:
            return None, (result.stderr or result.stdout or "Mermaid CLI error").strip()
        svg_path = Path(out_path)
        if not svg_path.exists():
            return None, "Mermaid CLI did not produce SVG"
        data = svg_path.read_bytes()
        svg_path.unlink(missing_ok=True)
        return data, None
    except FileNotFoundError:
        # Fallback to mermaid.ink (no Node required)
        return _render_mermaid_svg_via_http(code)
    except Exception as exc:
        return None, str(exc)


def _render_mermaid_svg_via_http(code: str) -> Tuple[bytes | None, str | None]:
    """Render Mermaid to SVG using mermaid.ink (no Node required)."""
    try:
        cleaned = (code or "").strip()
        if not cleaned:
            return None, "Empty Mermaid code"
        payload = base64.urlsafe_b64encode(cleaned.encode("utf-8")).decode("ascii").rstrip("=")
        url = f"https://mermaid.ink/svg/{payload}"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None, f"mermaid.ink error: {resp.status_code}"
            return resp.content, None
    except Exception as exc:
        return None, str(exc)
