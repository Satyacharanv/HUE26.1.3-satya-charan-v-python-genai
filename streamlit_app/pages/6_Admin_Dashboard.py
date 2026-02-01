"""Admin Dashboard - System observability and management."""
import streamlit as st
import asyncio
from datetime import datetime
from utils.api_client import api_client
from utils.auth import is_authenticated, load_session, is_token_expired, logout, is_admin

st.set_page_config(
    page_title="Admin Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

load_session()

if not is_authenticated():
    st.warning("Please login to view admin dashboard")
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

if not is_admin():
    st.error("Admin access required.")
    st.stop()

st.title("🛡️ Admin Dashboard")
st.caption("System observability and admin controls")


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    return asyncio.run(coro)


tab_overview, tab_users, tab_projects, tab_analyses, tab_errors = st.tabs(
    ["Overview", "Users", "Projects", "Analyses", "Errors"]
)

with tab_overview:
    try:
        health = _run_async(api_client.admin_health())
        st.subheader("System Health")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Users", health.get("users", 0))
        with col2:
            st.metric("Projects", health.get("projects", 0))
        with col3:
            st.metric("Analyses", health.get("analyses", 0))
        with col4:
            st.metric("Success Rate", f"{health.get('success_rate', 0) * 100:.1f}%")

        st.write("**Analysis Status Breakdown**")
        st.json(health.get("analysis_status", {}))
    except Exception as e:
        st.error(f"Failed to load health stats: {e}")

with tab_users:
    st.subheader("Users")
    try:
        users_resp = _run_async(api_client.admin_list_users())
        users = users_resp.get("users", [])
        st.dataframe(users, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load users: {e}")

    st.divider()
    st.write("**Create User**")
    with st.form("admin_create_user"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["user", "admin"], index=0)
        submitted = st.form_submit_button("Create")
    if submitted:
        try:
            _run_async(api_client.admin_create_user({"email": email, "password": password, "role": role}))
            st.success("User created")
        except Exception as e:
            st.error(f"Create failed: {e}")

    st.write("**Update User**")
    with st.form("admin_update_user"):
        user_id = st.text_input("User ID")
        new_email = st.text_input("New Email (optional)")
        new_password = st.text_input("New Password (optional)", type="password")
        new_role = st.selectbox("New Role (optional)", ["", "user", "admin"], index=0)
        submitted_update = st.form_submit_button("Update")
    if submitted_update:
        payload = {}
        if new_email:
            payload["email"] = new_email
        if new_password:
            payload["password"] = new_password
        if new_role:
            payload["role"] = new_role
        try:
            _run_async(api_client.admin_update_user(user_id, payload))
            st.success("User updated")
        except Exception as e:
            st.error(f"Update failed: {e}")

    st.write("**Delete User**")
    with st.form("admin_delete_user"):
        delete_user_id = st.text_input("User ID to delete")
        submitted_delete = st.form_submit_button("Delete")
    if submitted_delete:
        try:
            _run_async(api_client.admin_delete_user(delete_user_id))
            st.success("User deleted")
        except Exception as e:
            st.error(f"Delete failed: {e}")

with tab_projects:
    st.subheader("Projects")
    status_filter = st.selectbox(
        "Filter by status",
        ["", "created", "preprocessing", "analyzing", "paused", "completed", "failed"],
        index=0
    )
    try:
        projects_resp = _run_async(api_client.admin_list_projects(status_filter=status_filter or None))
        raw = projects_resp.get("projects", [])
        # Show Owner (email) instead of owner_id UUID
        projects = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "Owner": p.get("owner_email") or p.get("owner_id"),
                "status": p.get("status"),
                "source_type": p.get("source_type"),
                "created_at": p.get("created_at"),
            }
            for p in raw
        ]
        st.dataframe(projects, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load projects: {e}")

    st.divider()
    st.write("**Update Project Status**")
    with st.form("admin_update_project"):
        project_id = st.text_input("Project ID")
        new_status = st.selectbox(
            "Status",
            ["created", "preprocessing", "analyzing", "paused", "completed", "failed"],
            index=0
        )
        submitted_proj = st.form_submit_button("Update Status")
    if submitted_proj:
        try:
            _run_async(api_client.admin_update_project(project_id, {"status": new_status}))
            st.success("Project updated")
        except Exception as e:
            st.error(f"Update failed: {e}")

    st.write("**Delete Project**")
    with st.form("admin_delete_project"):
        delete_project_id = st.text_input("Project ID to delete")
        submitted_delete_proj = st.form_submit_button("Delete")
    if submitted_delete_proj:
        try:
            _run_async(api_client.admin_delete_project(delete_project_id))
            st.success("Project deleted")
        except Exception as e:
            st.error(f"Delete failed: {e}")

with tab_analyses:
    st.subheader("Running Analyses")
    try:
        running = _run_async(api_client.admin_running_analyses())
        st.write(f"Active: {running.get('count', 0)}")
        st.dataframe(running.get("analyses", []), use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load running analyses: {e}")

with tab_errors:
    st.subheader("Recent Errors")
    try:
        errors = _run_async(api_client.admin_error_logs(limit=50))
        st.dataframe(errors.get("logs", []), use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load error logs: {e}")
