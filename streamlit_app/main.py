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

# Check if user is authenticated
if is_authenticated():
    st.success(f"✅ Logged in as **{st.session_state.user_email}**")
    
    # Redirect to dashboard
    if st.button("Go to Dashboard →", use_container_width=True, type="primary"):
        st.switch_page("pages/2_Dashboard.py")
    
    st.markdown("---")
    st.markdown("""
    ### What's Built
    
    ✅ **User Authentication** - Secure signup and login system with role-based access  
    ✅ **Project Management** - Create and organize your code analysis projects  
    ✅ **Multi-Source Support** - Analyze code from ZIP uploads or GitHub repositories  
    ✅ **Persona Selection** - Choose documentation for Software Engineers (SDE) or Product Managers (PM)  
    ✅ **File Validation** - Smart handling of corrupted files and invalid formats  
    
    ### What's Next
    
    🔜 **Intelligent Preprocessing** - Automatic code structure analysis and file categorization  
    🔜 **Real-Time Progress** - Live updates as your code is being analyzed  
    🔜 **Multi-Agent System** - Specialized agents working together for comprehensive documentation  
    🔜 **Interactive Control** - Pause, resume, and ask questions during analysis  
    🔜 **Rich Documentation** - Visual diagrams, architecture maps, and role-specific reports  
    """)
    
else:
    st.markdown("""
    ### What's Built
    
    ✅ **User Authentication** - Secure signup and login system with role-based access  
    ✅ **Project Management** - Create and organize your code analysis projects  
    ✅ **Multi-Source Support** - Analyze code from ZIP uploads or GitHub repositories  
    ✅ **Persona Selection** - Choose documentation for Software Engineers (SDE) or Product Managers (PM)  
    ✅ **File Validation** - Smart handling of corrupted files and invalid formats  
    
    ### What's Next
    
    🔜 **Intelligent Preprocessing** - Automatic code structure analysis and file categorization  
    🔜 **Real-Time Progress** - Live updates as your code is being analyzed  
    🔜 **Multi-Agent System** - Specialized agents working together for comprehensive documentation  
    🔜 **Interactive Control** - Pause, resume, and ask questions during analysis  
    🔜 **Rich Documentation** - Visual diagrams, architecture maps, and role-specific reports  
    """)
    
    st.markdown("---")
    st.markdown("### Get Started")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔐 Login →", use_container_width=True, type="primary"):
            st.switch_page("pages/1_Login.py")
    
    with col2:
        if st.button("📝 Sign Up →", use_container_width=True):
            st.switch_page("pages/1_Login.py")
