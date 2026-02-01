"""Dashboard page - Project list and creation"""
import streamlit as st
import asyncio
import httpx
from utils.api_client import api_client
from utils.auth import is_authenticated, logout, load_session, is_admin
from utils.validation import validate_zip_file, validate_github_url, get_file_size_warning

st.set_page_config(
    page_title="Dashboard - maCAD System",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load persisted session FIRST
load_session()

# Initialize missing session keys ONLY if not set by load_session
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None

# Check authentication
if not is_authenticated():
    st.warning("Please login to access the dashboard.")
    if st.button("Go to Login"):
        st.switch_page("pages/1_Login.py")
    st.stop()

# Helper function to parse API errors
def parse_error_message(error: Exception) -> str:
    """Parse error messages from API responses"""
    error_str = str(error)
    
    # Common error patterns from backend
    if "not a valid ZIP archive" in error_str or "corrupted" in error_str.lower():
        return "⚠️ The file is corrupted or not a valid ZIP archive. Please try again with a different file."
    elif "exceeds maximum allowed size" in error_str or "exceeds" in error_str.lower():
        return "⚠️ File size exceeds the maximum limit (100MB). Please upload a smaller file."
    elif "no recognizable code files" in error_str or "no code files" in error_str.lower():
        return "⚠️ The ZIP file doesn't contain recognizable code files. Make sure to include source code (Python, JavaScript, Java, etc.)."
    elif "Invalid GitHub URL" in error_str:
        return "⚠️ The GitHub URL format is invalid. Please use: https://github.com/username/repository"
    elif "requires authentication" in error_str.lower():
        return "⚠️ This GitHub repository is private or doesn't exist. Please check the URL or ensure you have access."
    elif "404" in error_str.lower():
        return "⚠️ Repository not found. Please verify the GitHub URL is correct."
    else:
        return f"❌ Error: {error_str}"


def get_template_defaults(template_name: str) -> dict:
    """Return default analysis config for a template."""
    presets = {
        "Quick": {"analysis_depth": "quick", "verbosity_level": "low"},
        "Standard": {"analysis_depth": "standard", "verbosity_level": "normal"},
        "Deep": {"analysis_depth": "deep", "verbosity_level": "high"},
    }
    return presets.get(template_name, presets["Standard"])


def load_analysis_templates():
    if "analysis_templates" not in st.session_state:
        st.session_state.analysis_templates = {}
    if not st.session_state.analysis_templates:
        try:
            result = asyncio.run(api_client.list_analysis_templates())
            templates = result.get("templates", [])
            st.session_state.analysis_templates = {
                t["name"]: {"id": t["id"], "config": t["config"]} for t in templates
            }
        except Exception:
            pass


def build_analysis_config(depth: str, verbosity: str, personas: list, enable_web: bool,
                          enable_diagrams: bool, diagram_prefs: list,
                          initial_context: str) -> dict:
    config = {
        "analysis_depth": depth,
        "verbosity_level": verbosity,
        "target_personas": {
            "sde": "sde" in personas,
            "pm": "pm" in personas
        },
        "enable_web_search": enable_web,
        "enable_diagrams": enable_diagrams,
        "diagram_preferences": diagram_prefs
    }
    if initial_context and initial_context.strip():
        config["initial_context"] = initial_context.strip()
    return config



# Page header (same style as Admin Dashboard)
st.title("📊 Dashboard")
st.caption("Your projects and analysis at a glance")
st.markdown(f"Welcome, **{st.session_state.user_email}**!")

# Navigation and logout in one row
col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([2, 1, 1, 1])
with col_nav1:
    if st.button("📁 Browse All Projects", use_container_width=True):
        st.switch_page("pages/4_Projects.py")
with col_nav2:
    if is_admin():
        if st.button("🛡️ Admin Dashboard", use_container_width=True):
            st.switch_page("pages/6_Admin_Dashboard.py")
    else:
        st.write("")
with col_nav4:
    if st.button("🚪 Logout", use_container_width=True, type="secondary"):
        logout()
        st.switch_page("main.py")

st.divider()

# Tabs (same pattern as Admin Dashboard)
tab1, tab2 = st.tabs(["Overview", "Create Project"])

# Overview tab
with tab1:
    st.subheader("Quick Project Summary")
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    # ============= MINI-PLAYER SECTION =============
    # Check if there's an active analysis
    try:
        # Fetch the latest analysis
        latest_result = asyncio.run(api_client.get_latest_analysis())
        latest_analysis = latest_result.get("analysis") if latest_result else None
        
        if latest_analysis:
            st.markdown("**🎬 Active Analysis**")
            
            # Mini-player with real analysis data - full width
            mini_col1, mini_col2, mini_col3, mini_col4 = st.columns([4, 1.5, 1.5, 1.5], gap="medium")
            
            with mini_col1:
                # Get project name for display
                try:
                    projects_result = asyncio.run(api_client.list_projects())
                    projects = {p['id']: p['name'] for p in projects_result.get("projects", [])}
                    project_name = projects.get(latest_analysis['project_id'], 'Unknown Project')
                except:
                    project_name = 'Analysis'
                
                st.write(f"**{project_name}**")
                st.caption(f"Status: {latest_analysis['status']}")
            
            with mini_col2:
                # Progress
                st.metric("Progress", f"{latest_analysis['progress_percent']}%", label_visibility="visible")
            
            with mini_col3:
                # Token usage
                st.metric("Tokens", f"{latest_analysis['tokens_used']:,}", label_visibility="visible")
            
            with mini_col4:
                if st.button("Open Console", use_container_width=True, key="mini_view"):
                    st.query_params.update({"analysis_id": str(latest_analysis['id'])})
                    st.switch_page("pages/4_Analysis_Console.py")
    except Exception:
        pass

    st.divider()
    
    try:
        with st.spinner("Loading projects..."):
            result = asyncio.run(api_client.list_projects())
        
        projects = result.get("projects", [])
        total = result.get("total", 0)
        
        if total == 0:
            st.info("No projects yet. Create your first project in the 'Create Project' tab!")
        else:
            st.metric("Total Projects", total)
            
            # Group projects by status (handle both uppercase and lowercase)
            created = [p for p in projects if p['status'].upper() == 'CREATED']
            preprocessing = [p for p in projects if p['status'].upper() == 'PREPROCESSING']
            completed = [p for p in projects if p['status'].upper() == 'COMPLETED']
            failed = [p for p in projects if p['status'].upper() == 'FAILED']
            
            # Show status summary
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📝 Created", len(created))
            with col2:
                st.metric("⏳ Preprocessing", len(preprocessing))
            with col3:
                st.metric("✅ Completed", len(completed))
            with col4:
                st.metric("❌ Failed", len(failed))
            
            st.divider()

            SHOW_FIRST_N = 5

            def _render_completed_row(project, key_prefix):
                col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                with col1:
                    st.write(f"**📁 {project['name']}**")
                    st.caption(f"{project['source_type']} • {project['created_at'][:10]}")
                with col2:
                    if st.button("👁️ View", key=f"{key_prefix}_view_{project['id']}", use_container_width=True):
                        st.query_params.project_id = str(project['id'])
                        st.switch_page("pages/3_Results.py")
                with col3:
                    if st.button("📄 Docs", key=f"{key_prefix}_docs_{project['id']}", use_container_width=True):
                        latest = asyncio.run(api_client.get_latest_analysis(str(project['id'])))
                        aid = (latest or {}).get("analysis", {}).get("id")
                        if aid:
                            st.session_state.documentation_analysis_id = aid
                            st.query_params["analysis_id"] = aid
                            st.switch_page("pages/5_Documentation.py")
                        else:
                            st.warning("No analysis found for this project.")
                with col4:
                    if st.button("🔄 Re-analyze", key=f"{key_prefix}_reanalyze_{project['id']}", use_container_width=True):
                        try:
                            with st.spinner("Starting analysis..."):
                                analysis_config = build_analysis_config(
                                    "standard", "normal", project.get("personas", ["sde", "pm"]),
                                    True, True, ["architecture", "sequence"], ""
                                )
                                result = asyncio.run(api_client.create_analysis(project['id'], analysis_config))
                            analysis_id = result.get("analysis_id")
                            if analysis_id:
                                st.query_params.update({"analysis_id": analysis_id})
                                st.switch_page("pages/4_Analysis_Console.py")
                            else:
                                st.warning("Analysis created but no analysis ID returned.")
                        except Exception as e:
                            st.error(f"Error: {e}")
                with col5:
                    if st.button("🗑️", key=f"{key_prefix}_del_{project['id']}", help="Delete project"):
                        pass

            if completed:
                st.subheader("✅ Analysis Complete")
                for project in completed[:SHOW_FIRST_N]:
                    _render_completed_row(project, "comp")
                if len(completed) > SHOW_FIRST_N:
                    with st.expander(f"View all completed ({len(completed)})", expanded=False):
                        for project in completed[SHOW_FIRST_N:]:
                            _render_completed_row(project, "comp_all")

            if preprocessing:
                st.subheader("⏳ Preprocessing in Progress")
                for project in preprocessing[:SHOW_FIRST_N]:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"**📁 {project['name']}**")
                        st.caption(f"{project['source_type']} • Analysis in progress...")
                    with col2:
                        if st.button("👁️ View", key=f"view_prep_{project['id']}", use_container_width=True):
                            st.query_params.project_id = str(project['id'])
                            st.switch_page("pages/3_Results.py")
                    with col3:
                        if st.button("🔄", key=f"refresh_{project['id']}", help="Refresh status"):
                            st.rerun()
                if len(preprocessing) > SHOW_FIRST_N:
                    with st.expander(f"View all in progress ({len(preprocessing)})", expanded=False):
                        for project in preprocessing[SHOW_FIRST_N:]:
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.write(f"**📁 {project['name']}**")
                                st.caption(f"{project['source_type']} • Analysis in progress...")
                            with col2:
                                if st.button("👁️ View", key=f"view_prep_all_{project['id']}", use_container_width=True):
                                    st.query_params.project_id = str(project['id'])
                                    st.switch_page("pages/3_Results.py")
                            with col3:
                                if st.button("🔄", key=f"refresh_all_{project['id']}", help="Refresh"):
                                    st.rerun()
            
            if created:
                st.subheader("📝 Pending Analysis")
                for project in created[:SHOW_FIRST_N]:
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        st.write(f"**📁 {project['name']}**")
                        st.caption(f"{project['source_type']} • Waiting for analysis...")
                    with col2:
                        if st.button("👁️ View", key=f"view_created_{project['id']}", use_container_width=True):
                            st.query_params.project_id = str(project['id'])
                            st.switch_page("pages/3_Results.py")
                    with col3:
                        if st.button("▶️ Start", key=f"start_{project['id']}", use_container_width=True):
                            try:
                                with st.spinner("Starting analysis..."):
                                    analysis_config = build_analysis_config(
                                        "standard", "normal", project.get("personas", ["sde", "pm"]),
                                        True, True, ["architecture", "sequence"], ""
                                    )
                                    result = asyncio.run(api_client.create_analysis(project['id'], analysis_config))
                                analysis_id = result.get("analysis_id")
                                if analysis_id:
                                    st.query_params.update({"analysis_id": analysis_id})
                                    st.switch_page("pages/4_Analysis_Console.py")
                                else:
                                    st.warning("Analysis created but no analysis ID returned.")
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with col4:
                        if st.button("🗑️", key=f"delete_created_{project['id']}", help="Delete project"):
                            pass
                if len(created) > SHOW_FIRST_N:
                    with st.expander(f"View all pending ({len(created)})", expanded=False):
                        for project in created[SHOW_FIRST_N:]:
                            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                            with col1:
                                st.write(f"**📁 {project['name']}**")
                                st.caption(f"{project['source_type']} • Waiting for analysis...")
                            with col2:
                                if st.button("👁️ View", key=f"view_created_all_{project['id']}", use_container_width=True):
                                    st.query_params.project_id = str(project['id'])
                                    st.switch_page("pages/3_Results.py")
                            with col3:
                                if st.button("▶️ Start", key=f"start_all_{project['id']}", use_container_width=True):
                                    try:
                                        with st.spinner("Starting analysis..."):
                                            analysis_config = build_analysis_config(
                                                "standard", "normal", project.get("personas", ["sde", "pm"]),
                                                True, True, ["architecture", "sequence"], ""
                                            )
                                            result = asyncio.run(api_client.create_analysis(project['id'], analysis_config))
                                        analysis_id = result.get("analysis_id")
                                        if analysis_id:
                                            st.query_params.update({"analysis_id": analysis_id})
                                            st.switch_page("pages/4_Analysis_Console.py")
                                        else:
                                            st.warning("Analysis created but no analysis ID returned.")
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                            with col4:
                                if st.button("🗑️", key=f"delete_created_all_{project['id']}", help="Delete"):
                                    pass
            
            if failed:
                st.subheader("❌ Analysis Failed")
                for project in failed[:SHOW_FIRST_N]:
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        st.write(f"**📁 {project['name']}**")
                        st.caption(f"{project['source_type']} • Analysis failed")
                    with col2:
                        if st.button("👁️ View", key=f"view_failed_{project['id']}", use_container_width=True):
                            st.query_params.project_id = str(project['id'])
                            st.switch_page("pages/3_Results.py")
                    with col3:
                        if st.button("🔄 Retry", key=f"retry_{project['id']}", use_container_width=True):
                            try:
                                with st.spinner("Retrying analysis..."):
                                    analysis_config = build_analysis_config(
                                        "standard", "normal", project.get("personas", ["sde", "pm"]),
                                        True, True, ["architecture", "sequence"], ""
                                    )
                                    result = asyncio.run(api_client.create_analysis(project['id'], analysis_config))
                                analysis_id = result.get("analysis_id")
                                if analysis_id:
                                    st.query_params.update({"analysis_id": analysis_id})
                                    st.switch_page("pages/4_Analysis_Console.py")
                                else:
                                    st.warning("Analysis created but no analysis ID returned.")
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with col4:
                        if st.button("🗑️", key=f"delete_failed_{project['id']}", help="Delete project"):
                            pass
                if len(failed) > SHOW_FIRST_N:
                    with st.expander(f"View all failed ({len(failed)})", expanded=False):
                        for project in failed[SHOW_FIRST_N:]:
                            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                            with col1:
                                st.write(f"**📁 {project['name']}**")
                                st.caption(f"{project['source_type']} • Analysis failed")
                            with col2:
                                if st.button("👁️ View", key=f"view_failed_all_{project['id']}", use_container_width=True):
                                    st.query_params.project_id = str(project['id'])
                                    st.switch_page("pages/3_Results.py")
                            with col3:
                                if st.button("🔄 Retry", key=f"retry_all_{project['id']}", use_container_width=True):
                                    try:
                                        with st.spinner("Retrying analysis..."):
                                            analysis_config = build_analysis_config(
                                                "standard", "normal", project.get("personas", ["sde", "pm"]),
                                                True, True, ["architecture", "sequence"], ""
                                            )
                                            result = asyncio.run(api_client.create_analysis(project['id'], analysis_config))
                                        analysis_id = result.get("analysis_id")
                                        if analysis_id:
                                            st.query_params.update({"analysis_id": analysis_id})
                                            st.switch_page("pages/4_Analysis_Console.py")
                                        else:
                                            st.warning("Analysis created but no analysis ID returned.")
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                            with col4:
                                if st.button("🗑️", key=f"delete_failed_all_{project['id']}", help="Delete"):
                                    pass
    except Exception as e:
        st.error(f"Error loading projects: {str(e)}")

# Create Project tab
with tab2:
    st.subheader("Create New Project")
    
    # Project source selection
    source_type = st.radio(
        "Project Source",
        ["Upload ZIP File", "GitHub Repository"],
        horizontal=True
    )
    
    st.divider()
    
    if source_type == "Upload ZIP File":
        st.write("**Upload ZIP File**")
        
        # Info box about file requirements
        st.info("📋 **File Requirements:**\n"
                "- Must be a ZIP file (.zip)\n"
                "- Maximum size: 100 MB\n"
                "- Must contain source code files (Python, JavaScript, Java, etc.)\n"
                "- Avoid large dependencies folders (node_modules, venv, etc.)")
        
        with st.form("upload_zip_form"):
            project_name = st.text_input("Project Name", placeholder="My Awesome Project")
            uploaded_file = st.file_uploader(
                "Choose ZIP file",
                type=["zip"],
                help="Upload a ZIP file containing your codebase"
            )
            
            # Validate file before form submission
            file_error = ""
            if uploaded_file:
                is_valid, message = validate_zip_file(uploaded_file.size, uploaded_file.name)
                if not is_valid:
                    file_error = message
                    st.error(f"❌ {file_error}")
                else:
                    size_warning = get_file_size_warning(uploaded_file.size)
                    if size_warning:
                        st.warning(size_warning)
            
            personas = st.multiselect(
                "Select Personas",
                ["sde", "pm"],
                default=["sde", "pm"],
                help="Choose which documentation types to generate"
            )

            st.divider()
            st.write("**Analysis Configuration**")

            load_analysis_templates()
            saved_templates = st.session_state.get("analysis_templates", {})
            template_options = ["Standard", "Quick", "Deep"] + list(saved_templates.keys())
            template_choice = st.selectbox(
                "Configuration Template",
                template_options,
                index=0
            )
            template_defaults = saved_templates.get(template_choice, {}).get("config") or get_template_defaults(template_choice)

            analysis_depth = st.selectbox(
                "Analysis Depth",
                ["quick", "standard", "deep"],
                index=["quick", "standard", "deep"].index(template_defaults["analysis_depth"])
            )
            verbosity_level = st.selectbox(
                "Verbosity Level",
                ["low", "normal", "high"],
                index=["low", "normal", "high"].index(template_defaults["verbosity_level"])
            )

            enable_web_search = st.checkbox("Enable Web-Augmented Analysis", value=True)
            enable_diagrams = st.checkbox("Enable Diagram Generation", value=True)
            diagram_preferences = st.multiselect(
                "Diagram Preferences",
                ["architecture", "sequence", "flowchart", "entity_relationship"],
                default=["architecture", "sequence"]
            )
            initial_context = st.text_area(
                "Suggestions for analysis (optional)",
                placeholder="e.g., Focus on the payment module, highlight security risks",
                height=80
            )

            save_template = st.checkbox("Save as template for reuse", value=False)
            template_name = st.text_input("Template name (optional)", placeholder="e.g., Team Standard")
            
            submit = st.form_submit_button("Create Project", use_container_width=True, type="primary", disabled=bool(file_error))
            
            if submit:
                if not project_name:
                    st.error("Please enter a project name")
                elif not uploaded_file:
                    st.error("Please upload a ZIP file")
                elif not personas:
                    st.error("Please select at least one persona")
                else:
                    try:
                        with st.spinner("Creating project... This may take a moment"):
                            file_content = uploaded_file.read()
                            result = asyncio.run(
                                api_client.create_project_from_zip(
                                    name=project_name,
                                    file_content=file_content,
                                    filename=uploaded_file.name,
                                    personas=personas
                                )
                            )
                        
                        st.success(f"✅ Project '{result['name']}' created successfully!")

                        if save_template and template_name.strip():
                            try:
                                template_payload = build_analysis_config(
                                    analysis_depth,
                                    verbosity_level,
                                    personas,
                                    enable_web_search,
                                    enable_diagrams,
                                    diagram_preferences,
                                    initial_context
                                )
                                created = asyncio.run(
                                    api_client.create_analysis_template(
                                        name=template_name.strip(),
                                        description=None,
                                        config=template_payload
                                    )
                                )
                                st.session_state.analysis_templates[created["name"]] = {
                                    "id": created["id"],
                                    "config": created["config"]
                                }
                            except Exception as e:
                                st.warning(f"Template save failed: {e}")

                        analysis_config = build_analysis_config(
                            analysis_depth,
                            verbosity_level,
                            personas,
                            enable_web_search,
                            enable_diagrams,
                            diagram_preferences,
                            initial_context
                        )

                        analysis_result = asyncio.run(
                            api_client.create_analysis(result['id'], analysis_config)
                        )
                        analysis_id = analysis_result.get("analysis_id")

                        if analysis_id:
                            st.success("🚀 Analysis started. Opening Analysis Console...")
                            st.session_state.latest_analysis_id = analysis_id
                            st.query_params.update({"analysis_id": analysis_id})
                            st.switch_page("pages/4_Analysis_Console.py")
                        else:
                            st.warning("Analysis created but no analysis ID returned.")
                    except httpx.HTTPStatusError as e:
                        # Try to get error detail from response
                        try:
                            error_detail = e.response.json().get("detail", str(e))
                        except:
                            error_detail = str(e)
                        st.error(parse_error_message(error_detail))
                    except Exception as e:
                        st.error(parse_error_message(e))
    
    else:  # GitHub Repository
        st.write("**GitHub Repository**")
        
        # Info box about GitHub requirements
        st.info("📋 **GitHub Requirements:**\n"
                "- Public repository (private repos not yet supported)\n"
                "- Must contain source code\n"
                "- Valid GitHub URL format required")
        
        with st.form("github_form"):
            project_name = st.text_input("Project Name", placeholder="My Awesome Project", key="github_name")
            github_url = st.text_input(
                "GitHub URL",
                placeholder="https://github.com/username/repository",
                key="github_url"
            )
            
            # Validate GitHub URL
            url_error = ""
            if github_url:
                is_valid, message = validate_github_url(github_url)
                if not is_valid:
                    url_error = message
                    st.error(f"❌ {url_error}")
            
            personas = st.multiselect(
                "Select Personas",
                ["sde", "pm"],
                default=["sde", "pm"],
                help="Choose which documentation types to generate",
                key="github_personas"
            )

            st.divider()
            st.write("**Analysis Configuration**")

            load_analysis_templates()
            saved_templates = st.session_state.get("analysis_templates", {})
            template_options = ["Standard", "Quick", "Deep"] + list(saved_templates.keys())
            template_choice = st.selectbox(
                "Configuration Template",
                template_options,
                index=0,
                key="github_template"
            )
            template_defaults = saved_templates.get(template_choice, {}).get("config") or get_template_defaults(template_choice)

            analysis_depth = st.selectbox(
                "Analysis Depth",
                ["quick", "standard", "deep"],
                index=["quick", "standard", "deep"].index(template_defaults["analysis_depth"]),
                key="github_depth"
            )
            verbosity_level = st.selectbox(
                "Verbosity Level",
                ["low", "normal", "high"],
                index=["low", "normal", "high"].index(template_defaults["verbosity_level"]),
                key="github_verbosity"
            )

            enable_web_search = st.checkbox("Enable Web-Augmented Analysis", value=True, key="github_web")
            enable_diagrams = st.checkbox("Enable Diagram Generation", value=True, key="github_diagrams")
            diagram_preferences = st.multiselect(
                "Diagram Preferences",
                ["architecture", "sequence", "flowchart", "entity_relationship"],
                default=["architecture", "sequence"],
                key="github_diagram_prefs"
            )
            initial_context = st.text_area(
                "Suggestions for analysis (optional)",
                placeholder="e.g., Emphasize architecture and integration points",
                height=80,
                key="github_initial_context"
            )

            save_template = st.checkbox("Save as template for reuse", value=False, key="github_save_template")
            template_name = st.text_input("Template name (optional)", placeholder="e.g., Team Standard", key="github_template_name")
            
            submit = st.form_submit_button("Create Project", use_container_width=True, type="primary", disabled=bool(url_error))
            
            if submit:
                if not project_name:
                    st.error("Please enter a project name")
                elif not github_url:
                    st.error("Please enter a GitHub URL")
                elif not personas:
                    st.error("Please select at least one persona")
                else:
                    try:
                        with st.spinner("Creating project from GitHub..."):
                            result = asyncio.run(
                                api_client.create_project_from_github(
                                    name=project_name,
                                    github_url=github_url,
                                    personas=personas
                                )
                            )

                        st.success(f"✅ Project '{result['name']}' created successfully!")

                        if save_template and template_name.strip():
                            try:
                                template_payload = build_analysis_config(
                                    analysis_depth,
                                    verbosity_level,
                                    personas,
                                    enable_web_search,
                                    enable_diagrams,
                                    diagram_preferences,
                                    initial_context
                                )
                                created = asyncio.run(
                                    api_client.create_analysis_template(
                                        name=template_name.strip(),
                                        description=None,
                                        config=template_payload
                                    )
                                )
                                st.session_state.analysis_templates[created["name"]] = {
                                    "id": created["id"],
                                    "config": created["config"]
                                }
                            except Exception as e:
                                st.warning(f"Template save failed: {e}")

                        analysis_config = build_analysis_config(
                            analysis_depth,
                            verbosity_level,
                            personas,
                            enable_web_search,
                            enable_diagrams,
                            diagram_preferences,
                            initial_context
                        )

                        analysis_result = asyncio.run(
                            api_client.create_analysis(result["id"], analysis_config)
                        )
                        analysis_id = analysis_result.get("analysis_id")

                        if analysis_id:
                            st.success("🚀 Analysis started. Opening Analysis Console...")
                            st.query_params.update({"analysis_id": analysis_id})
                            st.switch_page("pages/4_Analysis_Console.py")
                        else:
                            st.warning("Analysis created but no analysis ID returned.")

                    except Exception as e:
                        st.error(parse_error_message(e))


# Footer
st.divider()
