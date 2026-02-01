"""Streamlit application main entry point"""
import streamlit as st
from utils.auth import is_authenticated, load_session

st.set_page_config(
    page_title="maCAD System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state for access_token if not exists
if "access_token" not in st.session_state:
    st.session_state.access_token = None

# Load persisted session on startup
load_session()

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 1rem;
    }
    .feature-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# Main header
st.markdown('<div class="main-header">🤖 maCAD System</div>', unsafe_allow_html=True)
st.markdown("### Multi-Agent Code Analysis & Documentation System")

st.markdown("---")


def _render_home_content():
    """What the app does and how it does it."""
    st.markdown("""
    ### What maCAD Does
    
    Transforms any codebase into **role-specific documentation**: SDE and PM reports, architecture and sequence diagrams, Q&A over your code with file and line citations, and PDF or Markdown export — all from a ZIP or GitHub repo.
    
    ### How It Works
    
    1. **Ingest & analyze** — Upload a ZIP or link a GitHub repo; maCAD chunks the code, detects frameworks and entry points, and builds semantic embeddings for search.
    2. **Multi-agent workflow** — A LangGraph pipeline runs Structure, Web Search (optional), SDE, and PM agents to produce structured reports and Mermaid diagrams.
    3. **Real-time control** — Watch progress live, pause or resume analysis, and ask questions during the run; answers include code citations.
    4. **Documentation hub** — View SDE/PM reports and diagrams on the Documentation page, then export as PDF or Markdown.
    """)


# Check if user is authenticated
if is_authenticated():
    st.success(f"✅ Logged in as **{st.session_state.user_email}**")
    
    # Redirect to dashboard
    if st.button("Go to Dashboard →", use_container_width=True, type="primary"):
        st.switch_page("pages/2_Dashboard.py")
    
    st.markdown("---")
    _render_home_content()
    
else:
    _render_home_content()
    
    st.markdown("---")
    st.markdown("### Get Started")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔐 Login →", use_container_width=True, type="primary"):
            st.switch_page("pages/1_Login.py")
    
    with col2:
        if st.button("📝 Sign Up →", use_container_width=True):
            st.switch_page("pages/1_Login.py")
