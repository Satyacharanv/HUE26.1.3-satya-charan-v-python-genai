"""Projects Browser - View and manage all projects with search and filters"""
import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime
from utils.api_client import api_client
from utils.auth import is_authenticated, load_session

st.set_page_config(page_title="Projects - maCAD System", page_icon="📁", layout="wide")

# Load persisted session
load_session()

# Initialize session keys
if "access_token" not in st.session_state:
    st.session_state.access_token = None

# Check authentication
if not is_authenticated():
    st.warning("Please login to view projects.")
    if st.button("Go to Login"):
        st.switch_page("pages/1_Login.py")
    st.stop()

# Page header
st.title("📁 Projects")
st.markdown("Browse, search, and manage your codebase analysis projects")

# Load projects
try:
    with st.spinner("Loading projects..."):
        result = asyncio.run(api_client.list_projects())
    
    projects = result.get("projects", [])
    total = result.get("total", 0)
    
    if total == 0:
        st.info("No projects yet. Go to Dashboard and create your first project!")
        if st.button("Create Project"):
            st.switch_page("pages/2_Dashboard.py")
        st.stop()
    
    # ============= SEARCH & FILTERS =============
    st.subheader("🔍 Search & Filter")
    
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    
    with col1:
        search_query = st.text_input(
            "Search by project name:",
            placeholder="e.g., 'My Project', 'API Server'...",
            key="search_query"
        )
    
    with col2:
        status_filter = st.selectbox(
            "Filter by status:",
            ["All"] + ["CREATED", "PREPROCESSING", "COMPLETED", "FAILED"],
            key="status_filter"
        )
    
    with col3:
        source_filter = st.selectbox(
            "Filter by source:",
            ["All"] + ["ZIP", "github"],
            key="source_filter"
        )
    
    with col4:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # ============= APPLY FILTERS =============
    filtered_projects = projects
    
    # Search filter
    if search_query:
        filtered_projects = [
            p for p in filtered_projects
            if search_query.lower() in p.get("name", "").lower()
        ]
    
    # Status filter (case-insensitive)
    if status_filter != "All":
        filtered_projects = [
            p for p in filtered_projects
            if p.get("status", "").upper() == status_filter.upper()
        ]
    
    # Source filter (case-insensitive)
    if source_filter != "All":
        filtered_projects = [
            p for p in filtered_projects
            if p.get("source_type", "").upper() == source_filter.upper()
        ]
    
    # ============= STATISTICS =============
    st.markdown("---")
    st.subheader("📊 Statistics")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Projects", total)
    
    with col2:
        created_count = sum(1 for p in projects if p.get("status", "").upper() == "CREATED")
        st.metric("📝 Created", created_count)
    
    with col3:
        processing_count = sum(1 for p in projects if p.get("status", "").upper() == "PREPROCESSING")
        st.metric("⏳ Processing", processing_count)
    
    with col4:
        completed_count = sum(1 for p in projects if p.get("status", "").upper() == "COMPLETED")
        st.metric("✅ Completed", completed_count)
    
    with col5:
        failed_count = sum(1 for p in projects if p.get("status", "").upper() == "FAILED")
        st.metric("❌ Failed", failed_count)
    
    # ============= RESULTS COUNT =============
    st.markdown("---")
    
    if len(filtered_projects) == 0:
        st.warning(f"No projects match your search criteria.")
    else:
        st.success(f"Found {len(filtered_projects)} of {total} projects")
    
    # ============= PROJECT TABLE VIEW =============
    st.markdown("---")
    st.subheader("📋 Projects List")
    
    if filtered_projects:
        # Create DataFrame for table view
        df_data = []
        for p in filtered_projects:
            created_date = p.get("created_at", "")
            if created_date:
                created_date = created_date[:10]  # YYYY-MM-DD
            
            df_data.append({
                "Name": p.get("name", "Unknown"),
                "Status": p.get("status", "UNKNOWN"),
                "Source": p.get("source_type", "unknown").upper(),
                "Personas": ", ".join(p.get("personas", [])),
                "Created": created_date,
                "ID": p.get("id", "")
            })
        
        df = pd.DataFrame(df_data)
        
        # Remove ID column from display (we'll use it for actions)
        display_df = df.drop(columns=["ID"])
        
        st.dataframe(display_df, use_container_width=True, height=300)
    
    # ============= DETAILED PROJECT CARDS =============
    st.markdown("---")
    st.subheader("📌 Project Details")
    
    if not filtered_projects:
        st.info("No projects to display")
    else:
        for idx, project in enumerate(filtered_projects):
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                # Project name and info
                with col1:
                    st.write(f"### 📁 {project['name']}")
                    
                    # Details in columns
                    detail_col1, detail_col2, detail_col3 = st.columns(3)
                    
                    with detail_col1:
                        st.write(f"**ID:** `{project['id'][:8]}...`")
                        st.write(f"**Source:** {project['source_type'].upper()}")
                    
                    with detail_col2:
                        st.write(f"**Status:** {project['status']}")
                        st.write(f"**Created:** {project['created_at'][:10]}")
                    
                    with detail_col3:
                        personas = ", ".join(project.get("personas", []))
                        st.write(f"**Personas:** {personas if personas else 'None'}")
                
                # Status badge
                with col2:
                    status = project.get("status", "UNKNOWN").upper()
                    if status == "COMPLETED":
                        st.success("✅ Complete")
                    elif status == "PREPROCESSING":
                        st.warning("⏳ Processing")
                    elif status == "CREATED":
                        st.info("📝 Pending")
                    else:
                        st.error("❌ Failed")
                
                # Action buttons
                with col3:
                    if st.button(
                        "📊 View",
                        key=f"view_{project['id']}",
                        use_container_width=True,
                        help="View detailed analysis"
                    ):
                        st.session_state.selected_project_id = project['id']
                        if project['status'].upper() == "COMPLETED":
                            st.query_params.project_id = str(project['id'])
                            st.switch_page("pages/3_Results.py")
                        else:
                            st.warning("Project analysis is not complete yet")
                
                with col4:
                    if st.button(
                        "⚙️ Manage",
                        key=f"manage_{project['id']}",
                        use_container_width=True,
                        help="Manage project"
                    ):
                        st.session_state.selected_project_id = project['id']
                        st.rerun()
                
                # Expandable details
                with st.expander("📊 More Details"):
                    detail_col1, detail_col2 = st.columns(2)
                    
                    with detail_col1:
                        st.write("**Project Information**")
                        st.write(f"- Full ID: `{project['id']}`")
                        st.write(f"- Created: {project['created_at']}")
                        st.write(f"- Source Type: {project['source_type']}")
                        if project.get('source_path'):
                            st.write(f"- Source Path: `{project['source_path']}`")
                    
                    with detail_col2:
                        st.write("**Analysis Configuration**")
                        personas = project.get("personas", [])
                        st.write(f"- Personas: {', '.join(personas) if personas else 'None'}")
                        st.write(f"- Status: {project['status']}")
                        
                        # Calculate processing time if preprocessing
                        if project['status'].upper() == 'PREPROCESSING':
                            st.write("- Currently being analyzed...")
                    
                    # Quick actions
                    st.write("**Quick Actions**")
                    action_col1, action_col2, action_col3 = st.columns(3)
                    
                    with action_col1:
                        if project['status'].upper() == "CREATED":
                            if st.button(
                                "▶️ Start Analysis",
                                key=f"start_{project['id']}",
                                use_container_width=True
                            ):
                                try:
                                    with st.spinner("Starting analysis..."):
                                        asyncio.run(api_client.preprocess_project(project['id']))
                                    st.success("Analysis started!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        elif project['status'].upper() == "FAILED":
                            if st.button(
                                "🔄 Retry",
                                key=f"retry_{project['id']}",
                                use_container_width=True
                            ):
                                try:
                                    with st.spinner("Retrying analysis..."):
                                        asyncio.run(api_client.preprocess_project(project['id']))
                                    st.success("Analysis restarted!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        elif project['status'].upper() == "COMPLETED":
                            if st.button(
                                "🔄 Re-analyze",
                                key=f"reanalyze_{project['id']}",
                                use_container_width=True
                            ):
                                try:
                                    with st.spinner("Restarting analysis..."):
                                        asyncio.run(api_client.preprocess_project(project['id']))
                                    st.success("Analysis restarted!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                    
                    with action_col2:
                        if st.button(
                            "📋 Copy ID",
                            key=f"copy_{project['id']}",
                            use_container_width=True
                        ):
                            st.success(f"Copied: {project['id']}")
                    
                    with action_col3:
                        if st.button(
                            "🗑️ Delete",
                            key=f"delete_{project['id']}",
                            use_container_width=True,
                            type="secondary"
                        ):
                            st.info("Delete functionality coming soon")
    
    # ============= EXPORT DATA =============
    if filtered_projects:
        st.markdown("---")
        st.subheader("📥 Export")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Export as CSV
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download Projects CSV",
                data=csv,
                file_name="projects.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Export as JSON
            import json
            json_data = json.dumps(filtered_projects, indent=2, default=str)
            st.download_button(
                label="📥 Download Projects JSON",
                data=json_data,
                file_name="projects.json",
                mime="application/json",
                use_container_width=True
            )

except Exception as e:
    st.error(f"Error loading projects: {str(e)}")
    if st.button("Retry"):
        st.rerun()

# Footer
st.markdown("---")
st.caption("💡 Tip: Use search and filters to find specific projects quickly")
