"""Login and Signup page"""
import streamlit as st
import asyncio
from utils.api_client import api_client
from utils.auth import logout, save_session, load_session, _decode_jwt_payload

st.set_page_config(page_title="Login - maCAD System", page_icon="🔐")

# Load persisted session
load_session()

# Initialize session state
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "login_mode" not in st.session_state:
    st.session_state.login_mode = "login"  # "login" or "signup"

# Page title
st.title("🔐 maCAD System")
st.markdown("### Multi-Agent Code Analysis & Documentation System")

st.markdown("---")

# Back to home button
if st.button("← Back to Home"):
    st.switch_page("main.py")

st.markdown("---")

# Mode selection buttons
col1, col2 = st.columns(2)
with col1:
    if st.button("🔐 Login", use_container_width=True, type="primary" if st.session_state.login_mode == "login" else "secondary"):
        st.session_state.login_mode = "login"
        st.rerun()

with col2:
    if st.button("📝 Sign Up", use_container_width=True, type="primary" if st.session_state.login_mode == "signup" else "secondary"):
        st.session_state.login_mode = "signup"
        st.rerun()

st.markdown("---")

# Login Mode
if st.session_state.login_mode == "login":
    st.header("Login")
    
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="your.email@example.com")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login", use_container_width=True, type="primary")
        
        if submit:
            if not email or not password:
                st.error("Please fill in all fields")
            else:
                try:
                    with st.spinner("Logging in..."):
                        result = asyncio.run(api_client.login(email, password))
                    
                    # Set session state from token (role is in JWT payload)
                    token = result["access_token"]
                    st.session_state.access_token = token
                    st.session_state.user_email = email
                    payload = _decode_jwt_payload(token)
                    st.session_state.user_role = (payload.get("role") or "user").strip()
                    
                    # Then save to file
                    save_session()
                    
                    st.success("Login successful! Redirecting...")
                    
                    # Small delay to ensure session is saved
                    import time
                    time.sleep(0.5)
                    
                    st.switch_page("pages/2_Dashboard.py")
                except Exception as e:
                    st.error(f"Login failed: {str(e)}")
    
    st.markdown("---")
    st.markdown("**Don't have an account?** Click the 'Sign Up' button above to create one.")

# Signup Mode
else:
    st.header("Sign Up")
    
    with st.form("signup_form"):
        email = st.text_input("Email", placeholder="your.email@example.com", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
        role = st.selectbox("Role", ["user", "admin"], key="signup_role")
        submit = st.form_submit_button("Sign Up", use_container_width=True, type="primary")
        
        if submit:
            if not email or not password or not confirm_password:
                st.error("Please fill in all fields")
            elif password != confirm_password:
                st.error("Passwords do not match")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters")
            else:
                try:
                    with st.spinner("Creating account..."):
                        result = asyncio.run(api_client.signup(email, password, role))
                    
                    st.success("Account created successfully! Please login.")
                    st.info("Switch to the Login tab to sign in.")
                    st.session_state.login_mode = "login"
                    st.rerun()
                except Exception as e:
                    st.error(f"Signup failed: {str(e)}")
    
    st.markdown("---")
    st.markdown("**Already have an account?** Click the 'Login' button above to sign in.")
