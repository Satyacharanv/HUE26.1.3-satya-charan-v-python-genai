"""Documentation page – structured SDE/PM reports and diagrams."""
import html
import streamlit as st
import asyncio
import time
import base64
import streamlit.components.v1 as components
import markdown as md_lib
from streamlit_mermaid import st_mermaid
from utils.mermaid_renderer import render_mermaid_svg
from utils.api_client import api_client
from utils.auth import is_authenticated, load_session, is_token_expired, logout

st.set_page_config(
    page_title="Documentation – maCAD System",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_session()

if not is_authenticated():
    st.warning("Please log in to view documentation.")
    if st.button("Go to Login"):
        st.switch_page("pages/1_Login.py")
    st.stop()

token = st.session_state.get("access_token")
if token and is_token_expired(token):
    logout()
    st.error("Your session expired. Please log in again.")
    if st.button("Go to Login"):
        st.switch_page("pages/1_Login.py")
    st.stop()

st.title("📄 Documentation")
st.markdown("Structured reports and diagrams from completed analysis.")

# analysis_id from query params or session
query_params = st.query_params
analysis_id = query_params.get("analysis_id") or st.session_state.get("documentation_analysis_id")

if not analysis_id:
    st.info("No analysis selected. Open documentation from the **Analysis Console** (when analysis is completed) or enter an analysis ID below.")
    analysis_id_input = st.text_input("Analysis ID (UUID)", placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000", key="doc_analysis_id_input")
    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if st.button("📄 View Documentation", type="primary", key="doc_load_btn"):
            if (analysis_id_input or "").strip():
                st.session_state.documentation_analysis_id = analysis_id_input.strip()
                st.query_params["analysis_id"] = analysis_id_input.strip()
                st.rerun()
            else:
                st.warning("Enter an analysis ID first.")
    with btn_col2:
        if st.button("← Back to Dashboard", key="doc_back_no_id"):
            st.switch_page("pages/2_Dashboard.py")
    st.stop()

# We have analysis_id from query or session (or from input after Load)
analysis_id = analysis_id or (st.session_state.get("doc_analysis_id_input") or "").strip()
if not analysis_id:
    st.stop()

st.session_state.documentation_analysis_id = analysis_id

# Navigation: Analysis Console (left), Back to Dashboard (right)
col_console, _, col_back = st.columns([1, 2, 1])
with col_console:
    if st.button("⚙️ Analysis Console", key="doc_to_console"):
        st.query_params.update({"analysis_id": analysis_id})
        st.switch_page("pages/4_Analysis_Console.py")
with col_back:
    if st.button("← Back to Dashboard", key="doc_back"):
        st.switch_page("pages/2_Dashboard.py")

st.divider()

def _normalize_mermaid(code: str) -> str:
    lines = (code or "").replace("\r", "").split("\n")
    # Trim leading/trailing empty lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    # Replace tabs and remove common indentation
    lines = [line.replace("\t", "  ") for line in lines]
    if lines:
        indent = min((len(line) - len(line.lstrip())) for line in lines if line.strip())
        lines = [line[indent:] if len(line) >= indent else line for line in lines]
    return "\n".join(lines)


def _render_mermaid(code: str):
    normalized = _normalize_mermaid(code)
    svg_bytes, err = render_mermaid_svg(normalized)
    if svg_bytes:
        svg_text = svg_bytes.decode("utf-8", errors="ignore")
        components.html(svg_text, height=320, scrolling=True)
    else:
        st_mermaid(normalized)
        if err:
            st.caption(f"Mermaid render fallback: {err}")

try:
    artifacts_resp = asyncio.run(api_client.get_analysis_artifacts(analysis_id))
    artifacts = artifacts_resp.get("artifacts", [])
except Exception as e:
    st.error(f"Could not load artifacts: {e}")
    artifacts = []

if not artifacts:
    st.warning("No documentation artifacts found for this analysis. Run an analysis and complete it first.")
    st.stop()

# Group by type
def _artifact_type(a: dict) -> str:
    return a.get("type") or a.get("artifact_type") or ""


sde_reports = [a for a in artifacts if _artifact_type(a) == "sde_report"]
pm_reports = [a for a in artifacts if _artifact_type(a) == "pm_report"]
web_findings = [a for a in artifacts if _artifact_type(a) == "web_findings"]
diagrams = [a for a in artifacts if a.get("format") == "mermaid"]

# CSS: square box around each tab's report content (container)
st.markdown("""
<style>
/* Box around the main content block inside each tab */
.doc-report-content-box {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    margin: 0.5rem 0;
    background-color: var(--background-secondary, #fafafa);
}
</style>
""", unsafe_allow_html=True)

# Tabs: SDE Report | PM Report | Web Findings | Diagrams
tab1, tab2, tab3, tab4 = st.tabs([
    "👨‍💻 SDE Report",
    "📋 PM Report",
    "🌐 Web Findings",
    "📐 Diagrams",
])

def _mermaid_ink_url(code: str) -> str:
    """Return mermaid.ink URL for embedding diagram as image."""
    if not (code or "").strip():
        return ""
    payload = base64.urlsafe_b64encode((code or "").strip().encode("utf-8")).decode("ascii").rstrip("=")
    return f"https://mermaid.ink/svg/{payload}"

with tab1:
    with st.container():
        if sde_reports:
            for r in sde_reports:
                title = html.escape(r.get("title", "SDE Summary"))
                body_html = md_lib.markdown(r.get("content", ""))
                st.markdown(
                    f'<div class="doc-report-content-box"><h3>{title}</h3>{body_html}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No SDE report for this analysis.")

with tab2:
    with st.container():
        if pm_reports:
            for r in pm_reports:
                title = html.escape(r.get("title", "PM Summary"))
                body_html = md_lib.markdown(r.get("content", ""))
                st.markdown(
                    f'<div class="doc-report-content-box"><h3>{title}</h3>{body_html}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No PM report for this analysis.")

with tab3:
    with st.container():
        if web_findings:
            for r in web_findings:
                title = html.escape(r.get("title", "Web Research"))
                body_html = md_lib.markdown(r.get("content", ""))
                st.markdown(
                    f'<div class="doc-report-content-box"><h3>{title}</h3>{body_html}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No web findings for this analysis.")

with tab4:
    if diagrams:
        for d in diagrams:
            st.markdown(f"#### {d.get('title', 'Diagram')}")
            _render_mermaid(d.get("content", ""))
            with st.expander("Mermaid source", expanded=False):
                st.code(d.get("content", ""), language="mermaid")
    else:
        st.caption("No diagrams for this analysis.")

st.divider()
st.subheader("Export")
# Export buttons call API; download appears when data is ready
if "export_md_data" not in st.session_state:
    st.session_state.export_md_data = None
if "export_pdf_data" not in st.session_state:
    st.session_state.export_pdf_data = None

col_md, col_pdf = st.columns(2)
with col_md:
    if st.button("📥 Download Markdown", key="export_md"):
        with st.spinner("Preparing Markdown..."):
            try:
                data = asyncio.run(api_client.export_analysis_markdown(analysis_id))
                st.session_state.export_md_data = data
                st.rerun()
            except Exception as e:
                st.session_state.export_md_data = None
                st.error(str(e))
    if st.session_state.export_md_data:
        d = st.session_state.export_md_data
        st.download_button("Save .md file", data=d.get("content", ""), file_name=d.get("filename", "documentation.md"), mime="text/markdown", key="dl_md")
with col_pdf:
    if st.button("📥 Download PDF", key="export_pdf"):
        with st.spinner("Generating PDF..."):
            try:
                pdf_bytes = asyncio.run(api_client.export_analysis_pdf(analysis_id))
                st.session_state.export_pdf_data = pdf_bytes
                st.rerun()
            except Exception as e:
                st.session_state.export_pdf_data = None
                st.error(str(e))
    if st.session_state.export_pdf_data:
        if len(st.session_state.export_pdf_data) < 100:
            st.warning("PDF export returned an unexpectedly small file. Check server logs.")
        st.download_button("Save PDF", data=st.session_state.export_pdf_data, file_name="documentation.pdf", mime="application/pdf", key="dl_pdf")

# ---------- Q&A with code citations ----------
st.divider()
st.subheader("💬 Ask about this analysis")
if "doc_qa_history" not in st.session_state:
    st.session_state.doc_qa_history = []
if "doc_qa_inflight" not in st.session_state:
    st.session_state.doc_qa_inflight = False
if "doc_qa_last_question" not in st.session_state:
    st.session_state.doc_qa_last_question = None
if "doc_qa_last_request_ts" not in st.session_state:
    st.session_state.doc_qa_last_request_ts = 0.0
if "doc_qa_submit" not in st.session_state:
    st.session_state.doc_qa_submit = False

with st.form("doc_qa_form", clear_on_submit=False):
    doc_question = st.text_area(
        "Ask a question about the codebase (with code citations)",
        placeholder="e.g., Where is authentication handled? How does the API validate tokens?",
        height=80,
        label_visibility="collapsed",
        key="doc_analysis_question"
    )
    st.form_submit_button(
        "💬 Ask",
        use_container_width=True,
        disabled=st.session_state.doc_qa_inflight,
        on_click=lambda: st.session_state.update({"doc_qa_submit": True})
    )

if st.session_state.doc_qa_submit:
    st.session_state.doc_qa_submit = False
    if (doc_question or "").strip():
        try:
            now_ts = time.time()
            if st.session_state.doc_qa_inflight:
                st.warning("Q&A request already in progress.")
            elif (
                st.session_state.doc_qa_last_question == (doc_question or "").strip()
                and now_ts - st.session_state.doc_qa_last_request_ts < 3
            ):
                st.warning("Please wait a moment before asking again.")
            else:
                st.session_state.doc_qa_inflight = True
                st.session_state.doc_qa_last_question = (doc_question or "").strip()
                st.session_state.doc_qa_last_request_ts = now_ts
                with st.spinner("Asking..."):
                    answer_resp = api_client.ask_analysis_sync(analysis_id, (doc_question or "").strip())
                if (
                    not st.session_state.doc_qa_history
                    or st.session_state.doc_qa_history[0].get("answer") != answer_resp.get("answer")
                ):
                    st.session_state.doc_qa_history.insert(0, answer_resp)
        except Exception as e:
            st.error(f"Error asking question: {e!r}")
        finally:
            st.session_state.doc_qa_inflight = False
    else:
        st.warning("Please enter a question.")

if st.session_state.doc_qa_history:
    latest = st.session_state.doc_qa_history[0]
    st.info(f"**Answer:** {latest.get('answer', '')}")
    citations = latest.get("citations") or []
    if citations:
        st.write("**Citations:**")
        for idx, cite in enumerate(citations[:5], start=1):
            file_path = cite.get("file_path", "unknown")
            start_line = cite.get("start_line")
            end_line = cite.get("end_line")
            relevance = cite.get("relevance_score")
            lang = cite.get("language") or ""
            st.caption(
                f"{idx}. {file_path} "
                f"(lines {start_line}-{end_line}) "
                f"- relevance {relevance}"
            )
            snippet = cite.get("content", "")
            if snippet:
                st.code(snippet, language=lang if isinstance(lang, str) else None)
