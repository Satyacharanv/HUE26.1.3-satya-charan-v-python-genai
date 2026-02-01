"""Export analysis documentation to Markdown and PDF."""
import base64
import html
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import markdown as md_lib

logger = logging.getLogger(__name__)

# HTML template for PDF: title + body, basic styling
PDF_HTML_HEAD = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Documentation</title>
  <style>
    :root { color-scheme: light; }
    body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; line-height: 1.6; margin: 32px; color: #222; }
    h1 { font-size: 24px; margin: 0 0 8px; }
    h2 { font-size: 18px; margin: 28px 0 8px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }
    h3 { font-size: 15px; margin: 20px 0 6px; }
    p, li { font-size: 12.5px; }
    ul { padding-left: 18px; }
    .cover { display: flex; flex-direction: column; gap: 6px; margin-bottom: 24px; }
    .subtle { color: #6b7280; font-size: 12px; }
    .toc { margin-top: 14px; margin-bottom: 24px; }
    .toc li { margin: 4px 0; }
    pre, code { background: #f5f7fb; padding: 2px 4px; border-radius: 4px; font-size: 11px; }
    pre { padding: 10px; overflow-x: auto; border: 1px solid #e5e7eb; }
    .mermaid-code { margin-top: 8px; font-size: 11px; }
    img { max-width: 100%; border: 1px solid #e5e7eb; border-radius: 6px; }
    .page-break { page-break-before: always; }
  </style>
</head>
<body>
"""

PDF_HTML_TAIL = """
</body>
</html>
"""


def build_markdown(artifacts: List[Dict[str, Any]], analysis_id: str) -> Dict[str, Any]:
    """Combine all artifacts into a single Markdown string. Returns { content, filename }."""
    parts = [f"# Documentation (Analysis {analysis_id})\n"]
    for a in artifacts:
        atype = a.get("type", "")
        title = a.get("title") or atype
        content = a.get("content", "")
        fmt = a.get("format", "markdown")
        if fmt == "mermaid":
            parts.append(f"## {title}\n\n```mermaid\n{content}\n```\n")
        else:
            parts.append(f"## {title}\n\n{content}\n")
    return {
        "content": "\n".join(parts),
        "filename": f"documentation_{analysis_id[:8]}.md",
    }


def _mermaid_to_image_svg(mermaid_code: str) -> bytes | None:
    """Render Mermaid to SVG using mermaid-cli (mmdc) if available. Returns SVG bytes or None."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mmd", delete=False) as f:
            f.write(mermaid_code.encode("utf-8"))
            mmd_path = f.name
        out_path = mmd_path + ".svg"
        result = subprocess.run(
            ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", mmd_path, "-o", out_path],
            capture_output=True,
            timeout=30,
            text=True,
        )
        Path(mmd_path).unlink(missing_ok=True)
        if result.returncode == 0 and Path(out_path).exists():
            data = Path(out_path).read_bytes()
            Path(out_path).unlink(missing_ok=True)
            return data
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug("Mermaid CLI not available or failed: %s", e)
    return None


def _mermaid_to_image_png(mermaid_code: str) -> bytes | None:
    """Render Mermaid to PNG using mermaid-cli (mmdc) if available."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mmd", delete=False) as f:
            f.write(mermaid_code.encode("utf-8"))
            mmd_path = f.name
        out_path = mmd_path + ".png"
        result = subprocess.run(
            ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", mmd_path, "-o", out_path],
            capture_output=True,
            timeout=30,
            text=True,
        )
        Path(mmd_path).unlink(missing_ok=True)
        if result.returncode == 0 and Path(out_path).exists():
            data = Path(out_path).read_bytes()
            Path(out_path).unlink(missing_ok=True)
            return data
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug("Mermaid CLI not available or failed: %s", e)
    return None


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _markdown_to_text(content: str) -> str:
    """Convert markdown to plain text for reportlab fallback."""
    html_fragment = md_lib.markdown(content, extensions=["extra"])
    text = re.sub(r"<[^>]+>", "", html_fragment)
    return html.unescape(text)


def build_pdf_html(artifacts: List[Dict[str, Any]], analysis_id: str) -> str:
    """Build HTML string for WeasyPrint: markdown -> HTML, Mermaid as image (if possible) + code block."""
    parts = [PDF_HTML_HEAD]
    parts.append('<div class="cover">')
    parts.append(f"<h1>Documentation</h1>")
    parts.append(f"<div class='subtle'>Analysis ID: {analysis_id}</div>")
    parts.append("</div>\n")
    if artifacts:
        parts.append("<div class='toc'><h2>Table of Contents</h2><ul>")
        for a in artifacts:
            title = a.get("title") or a.get("type", "Artifact")
            anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.strip()).strip("-").lower()
            parts.append(f"<li><a href='#{_html_escape(anchor)}'>{_html_escape(title)}</a></li>")
        parts.append("</ul></div>")
    for a in artifacts:
        atype = a.get("type", "")
        title = a.get("title") or atype
        content = a.get("content", "")
        fmt = a.get("format", "markdown")
        anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.strip()).strip("-").lower()
        parts.append(f"<div class='page-break'></div>")
        parts.append(f"<h2 id='{_html_escape(anchor)}'>{_html_escape(title)}</h2>\n")
        if fmt == "mermaid":
            svg_bytes = _mermaid_to_image_svg(content)
            if svg_bytes:
                b64 = base64.b64encode(svg_bytes).decode("ascii")
                parts.append(f'<p><img src="data:image/svg+xml;base64,{b64}" alt="{_html_escape(title)}" /></p>\n')
            parts.append(f'<pre class="mermaid-code"><code>{_html_escape(content)}</code></pre>\n')
        else:
            html_fragment = md_lib.markdown(content, extensions=["extra"])
            parts.append(html_fragment)
            parts.append("\n")
    parts.append(PDF_HTML_TAIL)
    return "".join(parts)


def build_pdf(artifacts: List[Dict[str, Any]], analysis_id: str) -> bytes:
    """Generate PDF bytes from artifacts. Prefer Playwright, then WeasyPrint, then reportlab."""
    html_str = build_pdf_html(artifacts, analysis_id)
    try:
        # Preferred renderer: Playwright (HTML/CSS)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html_str, wait_until="networkidle")
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "20mm", "right": "18mm", "bottom": "20mm", "left": "18mm"},
            )
            browser.close()
            return pdf_bytes
    except Exception as exc:
        logger.warning("Playwright unavailable, falling back to WeasyPrint: %s", exc)
    try:
        from weasyprint import HTML
        html_obj = HTML(string=html_str)
        return html_obj.write_pdf()
    except (OSError, ImportError) as exc:
        logger.warning("WeasyPrint unavailable, falling back to reportlab: %s", exc)
        return _build_pdf_reportlab(artifacts, analysis_id)


def _build_pdf_reportlab(artifacts: List[Dict[str, Any]], analysis_id: str) -> bytes:
    """Fallback PDF generation using reportlab (plain text + optional Mermaid PNG)."""
    from io import BytesIO
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER
    margin = 50
    y = height - margin

    def draw_line(text: str, size: int = 10):
        nonlocal y
        c.setFont("Helvetica", size)
        for line in text.splitlines() or [""]:
            if y < margin:
                c.showPage()
                y = height - margin
                c.setFont("Helvetica", size)
            c.drawString(margin, y, line[:1200])
            y -= size + 2

    draw_line(f"Documentation (Analysis {analysis_id[:8]})", size=14)
    y -= 6

    for a in artifacts:
        title = a.get("title") or a.get("type", "Artifact")
        fmt = a.get("format", "markdown")
        content = a.get("content", "")
        draw_line(f"\n{title}", size=12)

        if fmt == "mermaid":
            png_bytes = _mermaid_to_image_png(content)
            if png_bytes:
                img = ImageReader(BytesIO(png_bytes))
                iw, ih = img.getSize()
                max_w = width - 2 * margin
                scale = min(max_w / iw, 1.0)
                img_w = iw * scale
                img_h = ih * scale
                if y - img_h < margin:
                    c.showPage()
                    y = height - margin
                c.drawImage(img, margin, y - img_h, width=img_w, height=img_h)
                y -= img_h + 8
            draw_line("Mermaid source:", size=10)
            draw_line(content, size=9)
        else:
            draw_line(_markdown_to_text(content), size=10)

    c.showPage()
    c.save()
    return buffer.getvalue()
