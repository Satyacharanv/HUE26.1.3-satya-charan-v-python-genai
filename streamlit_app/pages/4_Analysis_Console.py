"""Analysis Console - Real-time progress monitoring"""
import streamlit as st
import asyncio
import time
import threading
import queue
import json
import httpx
import streamlit.components.v1 as components
from streamlit_mermaid import st_mermaid
from utils.mermaid_renderer import render_mermaid_svg
from datetime import datetime
from utils.api_client import api_client
from utils.auth import is_authenticated, load_session, is_token_expired, logout


def _run_async(coro):
    """Run async coroutine from Streamlit safely."""
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro)
        finally:
            asyncio.set_event_loop(current_loop)
            new_loop.close()
    return asyncio.run(coro)

st.set_page_config(
    page_title="Analysis Console",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load session
load_session()

if not is_authenticated():
    st.warning("Please login to view analysis")
    if st.button("Go to Login"):
        st.switch_page("pages/1_Login.py")
    st.stop()

# If token is expired, force logout and prompt
token = st.session_state.get("access_token")
if token and is_token_expired(token):
    logout()
    st.error("Your session expired. Please log in again.")
    if st.button("Go to Login"):
        st.switch_page("pages/1_Login.py")
    st.stop()

st.title("⚙️ Analysis Console")
st.markdown("Real-time analysis progress and control panel")

# Get analysis ID from URL params with debugging
query_params = st.query_params
analysis_id = query_params.get("analysis_id", None)
if not analysis_id:
    analysis_id = st.session_state.get("latest_analysis_id")

if not analysis_id:
    import sys
    # Clear SSE state to avoid stale errors
    st.session_state.sse_thread_started = False
    st.session_state.sse_connected = False
    st.session_state.sse_last_error = None
    st.session_state.sse_error_at = None

    if "auto_redirected" not in st.session_state:
        st.session_state.auto_redirected = False

    if not st.session_state.auto_redirected:
        try:
            latest = _run_async(api_client.get_latest_analysis())
            latest_analysis = latest.get("analysis") if latest else None
            if latest_analysis and latest_analysis.get("id"):
                st.session_state.auto_redirected = True
                st.session_state.latest_analysis_id = latest_analysis["id"]
                st.query_params.update({"analysis_id": latest_analysis["id"]})
                st.rerun()
        except Exception:
            pass

    st.warning("⚠️ No analysis ID provided in URL")
    st.info("Try navigating from the Dashboard mini-player or use a URL like: `?analysis_id=<uuid>`")
    
    if st.button("↩️ Go back to Dashboard"):
        st.switch_page("pages/2_Dashboard.py")
    st.stop()

# Initialize session state
if "logs" not in st.session_state:
    st.session_state.logs = []
if "current_status" not in st.session_state:
    st.session_state.current_status = None
if "sse_connected" not in st.session_state:
    st.session_state.sse_connected = False
if "sse_queue" not in st.session_state:
    st.session_state.sse_queue = queue.Queue()
if "sse_thread_started" not in st.session_state:
    st.session_state.sse_thread_started = False
if "sse_last_error" not in st.session_state:
    st.session_state.sse_last_error = None
if "sse_key" not in st.session_state:
    st.session_state.sse_key = None
if "sse_last_event_at" not in st.session_state:
    st.session_state.sse_last_event_at = None
if "force_refresh_analysis" not in st.session_state:
    st.session_state.force_refresh_analysis = False
if "sse_error_at" not in st.session_state:
    st.session_state.sse_error_at = None
if "analysis_load_started_at" not in st.session_state:
    st.session_state.analysis_load_started_at = None
if "analysis_load_failures" not in st.session_state:
    st.session_state.analysis_load_failures = 0
if "is_paused" not in st.session_state:
    st.session_state.is_paused = False
if "artifacts" not in st.session_state:
    st.session_state.artifacts = []
if "qa_history" not in st.session_state:
    st.session_state.qa_history = []
if "qa_inflight" not in st.session_state:
    st.session_state.qa_inflight = False
if "qa_last_question" not in st.session_state:
    st.session_state.qa_last_question = None
if "qa_last_request_ts" not in st.session_state:
    st.session_state.qa_last_request_ts = 0.0
if "qa_submit" not in st.session_state:
    st.session_state.qa_submit = False

# Start SSE listener once for realtime updates
def _start_sse_listener(url: str, headers: dict, out_queue: queue.Queue):
    try:
        with httpx.Client(timeout=None) as client:
            with client.stream("GET", url, headers=headers) as response:
                out_queue.put({"event": "__connected__", "data": "{}"})
                event_type = None
                data_lines = []
                for line in response.iter_lines():
                    if line is None:
                        continue
                    if line == "":
                        if data_lines:
                            payload = "\n".join(data_lines)
                            out_queue.put({
                                "event": event_type or "message",
                                "data": payload
                            })
                        event_type = None
                        data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].lstrip())
    except Exception as exc:
        out_queue.put({"event": "__error__", "data": json.dumps({"error": str(exc)})})


current_token = st.session_state.get("access_token")
current_sse_key = f"{analysis_id}:{current_token}" if analysis_id and current_token else None
if current_sse_key and st.session_state.sse_key != current_sse_key:
    st.session_state.sse_thread_started = False
    st.session_state.sse_connected = False
    st.session_state.sse_last_error = None
    st.session_state.sse_error_at = None
    st.session_state.sse_key = current_sse_key
    st.session_state.sse_queue = queue.Queue()
    st.session_state.logs = []
    st.session_state.current_status = None
    st.session_state.sse_last_event_at = None
    st.session_state.analysis_load_started_at = datetime.utcnow()
    st.session_state.analysis_load_failures = 0

# Auto-reconnect SSE on error while analysis is active
terminal_statuses = {"completed", "failed", "cancelled"}
live_status = (st.session_state.get("current_status") or {}).get("status")
current_status = live_status or (st.session_state.get("analysis_data") or {}).get("status")
if (
    st.session_state.sse_last_error
    and not st.session_state.sse_thread_started
    and current_status not in terminal_statuses
    and analysis_id
    and current_token
):
    st.session_state.sse_last_error = None
    st.session_state.sse_error_at = None


def _within_load_grace(seconds: int = 5) -> bool:
    started = st.session_state.get("analysis_load_started_at")
    if not started:
        return False
    return (datetime.utcnow() - started).total_seconds() <= seconds

if analysis_id and current_token and not st.session_state.sse_thread_started:
    sse_url = f"{api_client.base_url}{api_client.api_prefix}/analysis/{analysis_id}/events"
    sse_headers = api_client._get_headers()
    thread = threading.Thread(
        target=_start_sse_listener,
        args=(sse_url, sse_headers, st.session_state.sse_queue),
        daemon=True
    )
    thread.start()
    st.session_state.sse_thread_started = True

if analysis_id and st.session_state.analysis_load_started_at is None:
    st.session_state.analysis_load_started_at = datetime.utcnow()

# Drain SSE queue into session logs/status
should_rerun = False
while not st.session_state.sse_queue.empty():
    try:
        item = st.session_state.sse_queue.get_nowait()
        event_type = item.get("event")
        try:
            payload = json.loads(item.get("data") or "{}")
        except json.JSONDecodeError:
            payload = {"raw": item.get("data")}
        if event_type == "__connected__":
            st.session_state.sse_connected = True
            st.session_state.sse_last_error = None
            st.session_state.sse_error_at = None
            continue
        if event_type == "__error__":
            st.session_state.sse_connected = False
            st.session_state.sse_last_error = payload.get("error")
            st.session_state.sse_error_at = datetime.utcnow().isoformat()
            st.session_state.sse_thread_started = False
            continue
        if event_type == "end":
            st.session_state.sse_connected = False
            st.session_state.sse_last_error = None
            st.session_state.sse_thread_started = False
            st.session_state.force_refresh_analysis = True
            should_rerun = True
            continue
        if event_type == "log":
            st.session_state.logs.append({
                "timestamp": payload.get("timestamp", ""),
                "level": payload.get("level", "info"),
                "message": payload.get("message", ""),
                "file": payload.get("file", ""),
                "progress": payload.get("progress")
            })
            st.session_state.sse_last_event_at = datetime.utcnow().isoformat()
        elif event_type == "progress":
            st.session_state.current_status = payload
            st.session_state.sse_last_event_at = datetime.utcnow().isoformat()
    except Exception:
        break

if should_rerun:
    st.rerun()


def _simplify_log_message(level: str, message: str) -> str | None:
    """Return simplified message or None to skip."""
    if not message:
        return None

    # Drop noisy or duplicate messages
    if message.startswith("code_chunking:"):
        return None
    if message.startswith("📡 Calling OpenAI API for batch"):
        return None
    if message.startswith("SDE Summary") or message.startswith("PM Summary"):
        return None

    if message.startswith("Processing:"):
        # "Processing: path (language)" -> "Processing file: path"
        cleaned = message.replace("Processing:", "", 1).strip()
        if "(" in cleaned:
            cleaned = cleaned.split("(")[0].strip()
        return f"Processing file: {cleaned}"

    if "Extracted" in message and "code chunks" in message:
        return message.replace("✓ ", "").strip()

    if message.startswith("📊 Step 3:"):
        return "Preparing embeddings"
    if message.startswith("📊 Found"):
        return message.replace("📊 ", "").strip()
    if message.startswith("🔄 Starting embeddings generation"):
        return "Starting embeddings generation"
    if message.startswith("⏳ Processing embedding batch"):
        return message.replace("⏳ ", "").strip()
    if message.startswith("✓ Embedded batch"):
        return message.replace("✓ ", "").strip()
    if message.startswith("✅ Embeddings generation complete"):
        return message.replace("✅ ", "").strip()

    if message == "Preprocessing completed":
        return "Preprocessing completed"
    if message == "Starting LangGraph agent orchestration":
        return "Agents started"
    if message == "Agent orchestration completed":
        return "Agents completed"

    # Shorten agent messages
    if message.startswith("Coordinator:"):
        return "Coordinator: routing agents"
    if message.startswith("StructureAgent:"):
        return "StructureAgent: repository summary"
    if message.startswith("WebSearchAgent:"):
        return "WebSearchAgent: research complete" if "completed" in message else "WebSearchAgent: research started"
    if message.startswith("SDEAgent:"):
        return "SDEAgent: summary generated" if "generated" in message else "SDEAgent: generating summary"
    if message.startswith("PMAgent:"):
        return "PMAgent: summary generated" if "generated" in message else "PMAgent: generating summary"

    return message

# Create three columns: Control Panel | Live Feed | Status
col1, col2, col3 = st.columns([1, 2, 1], gap="large")

# ============= LEFT COLUMN: CONTROL PANEL =============
with col1:
    st.subheader("🎮 Control Panel")
    
    try:
        # Fetch current analysis status (avoid polling when SSE is active)
        analysis_data = st.session_state.get("analysis_data")
        if not analysis_data or not st.session_state.sse_connected or st.session_state.force_refresh_analysis:
            analysis_data = _run_async(api_client.get_analysis(analysis_id))
            st.session_state.analysis_data = analysis_data
            st.session_state.force_refresh_analysis = False
        
        status = analysis_data.get("status", "unknown")
        stage = analysis_data.get("current_stage", "N/A")
        progress = analysis_data.get("progress", {})
        tokens = analysis_data.get("tokens_used", 0)
        cost = analysis_data.get("estimated_cost", 0.0)

        live = st.session_state.get("current_status") or {}
        if live:
            status = live.get("status", status)
            stage = live.get("current_stage", stage)
            total_files = live.get("total_files", 0) or 0
            processed_files = live.get("processed_files", 0) or 0
            total_chunks = live.get("total_chunks", 0) or 0
            processed_chunks = live.get("processed_chunks", 0) or 0
            percentage = (processed_files / total_files * 100) if total_files > 0 else 0
            progress = {
                "files": f"{processed_files}/{total_files}",
                "chunks": f"{processed_chunks}/{total_chunks}",
                "percentage": percentage
            }
            tokens = live.get("tokens_used", tokens)
            cost = live.get("estimated_cost", cost)
        
        # Status indicator
        if status == "completed":
            st.success(f"✅ Status: {status.upper()}")
        elif status == "failed":
            st.error(f"❌ Status: {status.upper()}")
        elif status == "paused":
            st.warning(f"⏸️ Status: {status.upper()}")
        else:
            st.info(f"▶️ Status: {status.upper()}")
        
        if st.session_state.sse_last_error:
            st.caption(f"SSE error: {st.session_state.sse_last_error}")
        elif not st.session_state.sse_connected:
            st.caption("SSE not connected yet; using API fallback.")
        else:
            last_evt = st.session_state.sse_last_event_at or "just now"
            st.caption(f"SSE connected (last event: {last_evt})")
        
        # Stage display
        st.metric("Current Stage", stage.replace("_", " ").title() if stage else "N/A")
        
        # Progress metrics
        st.metric(
            "Files Analyzed",
            progress.get("files", "0/0")
        )
        
        st.metric(
            "Progress",
            f"{progress.get('percentage', 0):.1f}%"
        )
        
        # Tokens and cost
        col_token1, col_token2 = st.columns(2)
        with col_token1:
            st.metric("Tokens Used", f"{tokens:,}")
        with col_token2:
            st.metric("Est. Cost", f"${cost:.4f}")
        
        st.divider()
        
        # Control buttons
        st.write("**Control Actions:**")
        
        button_col1, button_col2 = st.columns(2)
        pause_allowed_stages = {"repo_scan", "code_chunking", "embedding_generation", "agent_orchestration"}
        pause_allowed = stage in pause_allowed_stages
        
        with button_col1:
            if status != "paused":
                if st.button(
                    "⏸️ Pause",
                    use_container_width=True,
                    key="pause_btn",
                    disabled=not pause_allowed
                ):
                    try:
                        with st.spinner("Pausing..."):
                            result = _run_async(api_client.control_analysis(
                                analysis_id,
                                {"action": "pause"}
                            ))
                        st.session_state.is_paused = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error pausing: {e}")
            else:
                st.button("⏸️ Pause", use_container_width=True, disabled=True)
        
        if not pause_allowed and status != "paused":
            st.caption("Pause is available during preprocessing and agent analysis.")
        
        with button_col2:
            if status == "paused":
                if st.button("▶️ Resume", use_container_width=True, key="resume_btn"):
                    try:
                        with st.spinner("Resuming..."):
                            result = _run_async(api_client.control_analysis(
                                analysis_id,
                                {"action": "resume"}
                            ))
                        st.session_state.is_paused = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error resuming: {e}")
            else:
                st.button("▶️ Resume", use_container_width=True, disabled=True)
        
        st.divider()
        
        # User context addition
        st.write("**Add Context:**")
        if status != "paused":
            st.caption("Pause the analysis to add suggestions.")
        scope_mode = st.selectbox(
            "Context Scope",
            options=["global", "module"],
            index=0,
            help="Global applies to the whole analysis. Module scope targets a specific area."
        )
        scope_value = "global"
        if scope_mode == "module":
            scope_value = st.text_input(
                "Module or path",
                placeholder="e.g., src/services/auth or payment module"
            ).strip() or "module"
        user_input = st.text_area(
            "Add instructions or context for the analysis",
            placeholder="e.g., 'Focus on the payment module', 'Skip deprecated APIs'",
            height=100,
            label_visibility="collapsed"
        )
        
        if st.button("📝 Add Context", use_container_width=True, disabled=(status != "paused")):
            if user_input.strip():
                try:
                    with st.spinner("Sending context..."):
                        result = _run_async(api_client.control_analysis(
                            analysis_id,
                            {
                                "action": "add_context",
                                "context": {"text": user_input, "scope": scope_value}
                            }
                        ))
                    st.success("✓ Context added!")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter some context")

        st.divider()

        # Ask questions during analysis
        st.write("**Ask During Analysis:**")
        qa_allowed_statuses = {"paused", "completed"}
        if status not in qa_allowed_statuses:
            st.caption("Pause the analysis to ask questions.")
        qa_container = st.container()
        with qa_container:
            with st.form("analysis_qa_form", clear_on_submit=False):
                question = st.text_area(
                    "Ask a question about the current analysis",
                    placeholder="e.g., What are you analyzing right now?",
                    height=80,
                    label_visibility="collapsed",
                    key="analysis_question"
                )
                st.form_submit_button(
                    "💬 Ask",
                    use_container_width=True,
                    disabled=(status not in qa_allowed_statuses or st.session_state.qa_inflight),
                    on_click=lambda: st.session_state.update({"qa_submit": True})
                )
        if st.session_state.qa_submit:
            st.session_state.qa_submit = False
            if question.strip():
                try:
                    now_ts = time.time()
                    if st.session_state.qa_inflight:
                        st.warning("Q&A request already in progress.")
                        raise RuntimeError("Q&A already in progress")
                    if (
                        st.session_state.qa_last_question == question.strip()
                        and now_ts - st.session_state.qa_last_request_ts < 3
                    ):
                        st.warning("Please wait a moment before asking again.")
                        raise RuntimeError("Duplicate Q&A request blocked")
                    token = st.session_state.get("access_token")
                    if not token:
                        st.error("You are not authenticated. Please log in again.")
                    else:
                        st.session_state.qa_inflight = True
                        st.session_state.qa_last_question = question.strip()
                        st.session_state.qa_last_request_ts = now_ts
                        with st.spinner("Asking..."):
                            answer_resp = api_client.ask_analysis_sync(analysis_id, question.strip())
                        if (
                            not st.session_state.qa_history
                            or st.session_state.qa_history[0].get("answer") != answer_resp.get("answer")
                        ):
                            st.session_state.qa_history.insert(0, answer_resp)
                except Exception as e:
                    if "Duplicate Q&A request blocked" not in str(e) and "Q&A already in progress" not in str(e):
                        st.error(f"Error asking question: {e!r}")
                finally:
                    st.session_state.qa_inflight = False
            else:
                st.warning("Please enter a question")

        if st.session_state.qa_history:
            latest = st.session_state.qa_history[0]
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
    
    except Exception as e:
        st.session_state.analysis_load_failures += 1
        if _within_load_grace() or st.session_state.analysis_load_failures < 3:
            st.caption("Loading analysis...")
        else:
            st.error(f"Error loading analysis: {e}")

# ============= MIDDLE COLUMN: LIVE FEED =============
with col2:
    st.subheader("📋 Activity Feed")
    
    # Create a placeholder for logs
    log_container = st.container()
    logs = []
    
    # Fetch and display logs
    try:
        sse_logs = st.session_state.logs[-50:] if st.session_state.logs else []
        logs = sse_logs
        if not st.session_state.sse_connected and not logs:
            logs_response = _run_async(api_client.get_analysis_logs(analysis_id, limit=50))
            logs = logs_response.get("logs", [])
        
        if logs:
            ordered_logs = sorted(
                logs,
                key=lambda item: item.get("timestamp") or "",
                reverse=True
            )
            latest_logs = ordered_logs[:10]
            with log_container:
                for log in latest_logs:
                    timestamp = log.get("timestamp", "")
                    level = log.get("level", "info").upper()
                    message = log.get("message", "")
                    progress = log.get("progress", None)
                    simplified = _simplify_log_message(level, message)
                    if not simplified:
                        continue
                    
                    # Color code by level
                    if level == "ERROR":
                        st.error(f"🔴 [{timestamp}] {simplified}")
                    elif level == "WARNING":
                        st.warning(f"🟡 [{timestamp}] {simplified}")
                    elif level == "MILESTONE":
                        st.success(f"🟢 ✓ {simplified}")
                    else:
                        st.info(f"🔵 [{timestamp}] {simplified}")
                    
                    if progress is not None:
                        st.progress(min(progress / 100, 1.0))

            with st.expander("Show all activity", expanded=False):
                for log in ordered_logs:
                    timestamp = log.get("timestamp", "")
                    level = log.get("level", "info").upper()
                    message = log.get("message", "")
                    progress = log.get("progress", None)
                    simplified = _simplify_log_message(level, message)
                    if not simplified:
                        continue

                    if level == "ERROR":
                        st.error(f"🔴 [{timestamp}] {simplified}")
                    elif level == "WARNING":
                        st.warning(f"🟡 [{timestamp}] {simplified}")
                    elif level == "MILESTONE":
                        st.success(f"🟢 ✓ {simplified}")
                    else:
                        st.info(f"🔵 [{timestamp}] {simplified}")

                    if progress is not None:
                        st.progress(min(progress / 100, 1.0))
        else:
            if not st.session_state.sse_connected:
                st.caption("Connecting to live updates...")
            else:
                st.info("📭 No activity yet. Analysis will start soon...")
    
    except Exception as e:
        st.session_state.analysis_load_failures += 1
        if _within_load_grace() or not st.session_state.sse_connected:
            st.caption("Connecting to live updates...")
        else:
            st.warning(f"Could not fetch logs: {e}")

    # Agent timeline view
    def _agent_status_from_logs(log_items: list) -> dict:
        agents = {
            "Coordinator": {"status": "pending", "started": ["Coordinator:"], "done": []},
            "StructureAgent": {"status": "pending", "started": ["StructureAgent:"], "done": ["StructureAgent: detected"]},
            "WebSearchAgent": {"status": "pending", "started": ["WebSearchAgent: searching"], "done": ["WebSearchAgent: web research completed"]},
            "SDEAgent": {"status": "pending", "started": ["SDEAgent: compiling"], "done": ["SDEAgent: technical summary generated"]},
            "PMAgent": {"status": "pending", "started": ["PMAgent: compiling"], "done": ["PMAgent: business summary generated"]},
        }

        for log in log_items:
            msg = log.get("message", "")
            for name, rules in agents.items():
                if any(token in msg for token in rules["done"]):
                    rules["status"] = "done"
                elif any(token in msg for token in rules["started"]) and rules["status"] == "pending":
                    rules["status"] = "running"

        return {name: rules["status"] for name, rules in agents.items()}

    with st.expander("🧭 Agent Timeline", expanded=False):
        agent_statuses = _agent_status_from_logs(logs if logs else [])
        for agent, status in agent_statuses.items():
            if status == "done":
                st.success(f"{agent}: completed")
            elif status == "running":
                st.info(f"{agent}: running")
            else:
                st.caption(f"{agent}: pending")

# ============= RIGHT COLUMN: STATUS =============
with col3:
    st.subheader("📊 Quick Stats")
    
    try:
        # Analysis metadata
        analysis_data = st.session_state.get("analysis_data")
        if not analysis_data or not st.session_state.sse_connected or st.session_state.force_refresh_analysis:
            analysis_data = _run_async(api_client.get_analysis(analysis_id))
            st.session_state.analysis_data = analysis_data
            st.session_state.force_refresh_analysis = False
        
        # Display as expandable cards
        with st.expander("📈 Progress", expanded=True):
            progress = analysis_data.get("progress", {})
            
            # Overall progress bar
            percentage = progress.get("percentage", 0)
            st.progress(min(percentage / 100, 1.0))
            st.caption(f"{percentage:.1f}% Complete")
            
            # Breakdown
            st.write("**Breakdown:**")
            files = progress.get("files", "0/0")
            chunks = progress.get("chunks", "0/0")
            st.write(f"- Files: {files}")
            st.write(f"- Chunks: {chunks}")
        
        with st.expander("💰 Token Usage", expanded=True):
            tokens = analysis_data.get("tokens_used", 0)
            cost = analysis_data.get("estimated_cost", 0.0)
            
            st.metric("Total Tokens", f"{tokens:,}")
            st.metric("Est. Cost (USD)", f"${cost:.4f}")
            
            st.caption("*Cost estimates based on OpenAI pricing*")
        
        with st.expander("⚙️ Configuration", expanded=False):
            config = analysis_data.get("configuration", {}) or {}
            options = config.get("analysis_options", {}) or {}
            st.write("Analysis Configuration:")
            st.write(f"- Depth: {config.get('analysis_depth', 'standard')}")
            st.write(f"- Personas: {', '.join([p.upper() for p, v in (config.get('target_personas') or {}).items() if v])}")
            st.write(f"- Verbosity: {config.get('verbosity_level', 'normal')}")
            st.write(f"- Web Search: {'enabled' if options.get('enable_web_search', True) else 'disabled'}")
            st.write(f"- Diagrams: {'enabled' if options.get('enable_diagrams', True) else 'disabled'}")
            prefs = options.get("diagram_preferences", [])
            if prefs:
                st.write(f"- Diagram prefs: {', '.join(prefs)}")

        with st.expander("🧩 Diagrams & Artifacts", expanded=False):
            def _normalize_mermaid(code: str) -> str:
                lines = (code or "").replace("\r", "").split("\n")
                while lines and not lines[0].strip():
                    lines.pop(0)
                while lines and not lines[-1].strip():
                    lines.pop()
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
                    components.html(svg_text, height=300, scrolling=True)
                else:
                    st_mermaid(normalized)
                    if err:
                        st.caption(f"Mermaid render fallback: {err}")

            try:
                if not st.session_state.artifacts:
                    artifacts_resp = _run_async(api_client.get_analysis_artifacts(analysis_id))
                    st.session_state.artifacts = artifacts_resp.get("artifacts", [])

                diagrams = [a for a in st.session_state.artifacts if a.get("format") == "mermaid"]
                if diagrams:
                    for diagram in diagrams:
                        st.write(f"**{diagram.get('title', 'Diagram')}**")
                        _render_mermaid(diagram.get("content", ""))
                        with st.expander("View Mermaid source", expanded=False):
                            st.code(diagram.get("content", ""), language="mermaid")
                else:
                    st.caption("No diagrams generated yet.")
            except Exception as e:
                st.caption(f"Artifacts unavailable: {e}")
        
        with st.expander("📍 Timeline", expanded=False):
            started = analysis_data.get("started_at")
            completed = analysis_data.get("completed_at")
            if started:
                started_dt = datetime.fromisoformat(started)
                end_dt = datetime.fromisoformat(completed) if completed else datetime.utcnow()
                elapsed = end_dt - started_dt
                elapsed_minutes = int(elapsed.total_seconds() // 60)
                elapsed_seconds = int(elapsed.total_seconds() % 60)
                st.write(f"**Started:** {started_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                st.write(f"**Elapsed:** {elapsed_minutes}m {elapsed_seconds}s")
                if completed:
                    st.write("**Est. Remaining:** 0m 0s")
                else:
                    st.write("**Est. Remaining:** calculating...")
            else:
                st.write("**Started:** not available")
                st.write("**Elapsed:** not available")
                st.write("**Est. Remaining:** not available")
    
    except Exception as e:
        st.session_state.analysis_load_failures += 1
        if _within_load_grace():
            st.caption("Loading stats...")
        else:
            st.warning(f"Error loading stats: {e}")

# ============= AUTO-REFRESH =============
st.divider()

# Add auto-refresh capability
col_refresh1, col_refresh2 = st.columns([3, 1])

with col_refresh1:
    status = st.session_state.get("analysis_data", {}).get("status", "unknown")
    live_status = (st.session_state.get("current_status") or {}).get("status")
    if live_status:
        status = live_status
    auto_refresh = status not in ["completed", "failed", "cancelled"]
    if auto_refresh:
        refresh_note = "every 1 second (SSE active)" if st.session_state.sse_thread_started else "every 3 seconds"
        st.caption(f"💡 Tip: This page auto-refreshes {refresh_note}")
    else:
        st.caption("✅ Analysis completed — auto-refresh stopped")

if "nav_to_docs" not in st.session_state:
    st.session_state.nav_to_docs = False

with col_refresh2:
    # Ensure documentation page can read analysis_id from session state
    if analysis_id:
        st.session_state.documentation_analysis_id = analysis_id
    # Use page_link for reliable navigation across Streamlit page modes
    st.page_link(
        "pages/5_Documentation.py",
        label=" View Documentation",
        icon="📄",
        use_container_width=True
    )
    if st.button("🔄 Refresh Now", use_container_width=True, key="refresh_btn"):
        st.rerun()

# Auto-refresh to render SSE updates (no API polling)
if auto_refresh and not st.session_state.get("nav_to_docs"):
    refresh_interval = 1 if st.session_state.sse_thread_started else 3
    time.sleep(refresh_interval)
    st.rerun()
