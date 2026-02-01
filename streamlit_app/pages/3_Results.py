"""M2 Results Page - Display analysis and preprocessing results"""
import streamlit as st
import asyncio
import pandas as pd
from utils.api_client import api_client
from utils.auth import is_authenticated, load_session

st.set_page_config(page_title="M2 Results - maCAD System", page_icon="📈", layout="wide")

# Load persisted session
load_session()

# Initialize session keys
if "access_token" not in st.session_state:
    st.session_state.access_token = None

# Check authentication
if not is_authenticated():
    st.warning("Please login to view results.")
    if st.button("Go to Login"):
        st.switch_page("pages/1_Login.py")
    st.stop()

# Page header
st.title("📈 M2 Analysis Results")
st.markdown("View preprocessing results, code intelligence, and embeddings")

# Get project ID from query params or sidebar selection
query_params = st.query_params
project_id = query_params.get("project_id", None)

# If no project_id in URL, show project selector
if not project_id:
    st.subheader("Select a Project")
    
    try:
        with st.spinner("Loading projects..."):
            result = asyncio.run(api_client.list_projects())
        
        projects = result.get("projects", [])
        
        if not projects:
            st.info("No projects found. Create a project first!")
            if st.button("Go to Dashboard"):
                st.switch_page("pages/2_Dashboard.py")
            st.stop()
        
        # Filter to completed/preprocessed projects (case-insensitive)
        completed_projects = [p for p in projects if p.get("status", "").upper() in ["COMPLETED", "PREPROCESSING"]]
        
        if not completed_projects:
            st.warning("No projects with analysis results. Please complete preprocessing first.")
            if st.button("Go to Dashboard"):
                st.switch_page("pages/2_Dashboard.py")
            st.stop()
        
        # Project selector
        project_names = {p["id"]: f"{p['name']} ({p['status']})" for p in completed_projects}
        selected_project_id = st.selectbox(
            "Choose a project:",
            options=list(project_names.keys()),
            format_func=lambda x: project_names[x]
        )
        
        if st.button("View Results", type="primary"):
            st.query_params.project_id = str(selected_project_id)
            st.rerun()
        st.stop()
        
    except Exception as e:
        st.error(f"Error loading projects: {e}")
        if st.button("Go to Dashboard"):
            st.switch_page("pages/2_Dashboard.py")
        st.stop()

# Cache data loading to prevent multiple API calls
@st.cache_data(ttl=300)
def load_project_data(project_id):
    """Load all project data with caching to prevent duplicate API calls"""
    try:
        project_data = asyncio.run(api_client.get_project(project_id))
        metadata = asyncio.run(api_client.get_project_metadata(project_id))
        files_data = asyncio.run(api_client.get_project_files(project_id))
        chunks_data = asyncio.run(api_client.get_project_chunks(project_id, limit=1000))
        return project_data, metadata, files_data, chunks_data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        if st.button("Back to Projects"):
            st.query_params.clear()
            st.rerun()
        st.stop()

# Load project data using cache
project_data, metadata, files_data, chunks_data = load_project_data(project_id)

# Project header with back button
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.header(f"📁 {project_data['name']}")
with col2:
    st.metric("Status", project_data.get("status", "UNKNOWN"))
with col3:
    if st.button("← Back"):
        st.query_params.clear()
        st.rerun()

st.markdown("---")

# Tabs for different views
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Files", "Code Chunks", "Intelligence", "Q&A Search"])

# ============= TAB 1: OVERVIEW =============
with tab1:
    st.subheader("📊 Project Overview")
    
    # Project metadata
    repo_meta = metadata.get("repository_metadata", {})
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Repository Type", repo_meta.get("repo_type", "Unknown"))
    with col2:
        st.metric("Total Files", repo_meta.get("total_files", 0))
    with col3:
        st.metric("Total Code Chunks", chunks_data.get("total", 0))
    with col4:
        chunks_with_embeddings = chunks_data.get("total", 0)  # All chunks should have embeddings
        st.metric("Embeddings Generated", chunks_with_embeddings)
    
    st.markdown("---")
    
    # Frameworks detected
    st.subheader("🔧 Frameworks & Technologies Detected")
    col1, col2 = st.columns(2)
    
    with col1:
        primary_frameworks = repo_meta.get("primary_frameworks", [])
        if primary_frameworks:
            st.write("**Primary Frameworks:**")
            for fw in primary_frameworks:
                st.write(f"• {fw}")
        else:
            st.write("No primary frameworks detected")
    
    with col2:
        secondary_frameworks = repo_meta.get("secondary_frameworks", [])
        if secondary_frameworks:
            st.write("**Secondary Frameworks:**")
            for fw in secondary_frameworks:
                st.write(f"• {fw}")
        else:
            st.write("No secondary frameworks detected")
    
    st.markdown("---")
    
    # File statistics
    st.subheader("📈 File Statistics")
    
    files = files_data.get("files", [])
    
    if files:
        # Group by language
        lang_stats = {}
        for file in files:
            lang = file.get("language", "Unknown")
            if lang not in lang_stats:
                lang_stats[lang] = {"count": 0, "loc": 0, "files": []}
            lang_stats[lang]["count"] += 1
            lang_stats[lang]["loc"] += file.get("lines_of_code", 0)
            lang_stats[lang]["files"].append(file.get("file_name", "Unknown"))
        
        # Display stats
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Files by Language:**")
            for lang, stats in sorted(lang_stats.items(), key=lambda x: x[1]["count"], reverse=True):
                st.write(f"• {lang}: {stats['count']} files ({stats['loc']} LOC)")
        
        with col2:
            st.write("**Files by Type:**")
            type_stats = {}
            for file in files:
                file_type = file.get("file_type", "code")
                type_stats[file_type] = type_stats.get(file_type, 0) + 1
            for file_type, count in sorted(type_stats.items()):
                st.write(f"• {file_type}: {count} files")
    else:
        st.info("No files analyzed yet")

# ============= TAB 2: FILES =============
with tab2:
    st.subheader("📄 Analyzed Files")
    
    files = files_data.get("files", [])
    
    if files:
        # Create DataFrame
        df = pd.DataFrame([
            {
                "File": f.get("file_name", "Unknown"),
                "Language": f.get("language", "Unknown"),
                "Type": f.get("file_type", "code"),
                "LOC": f.get("lines_of_code", 0),
                "Functions": f.get("function_count", 0),
                "Classes": f.get("class_count", 0),
                "Test": "✓" if f.get("is_test_file") else "✗"
            }
            for f in files
        ])
        
        # Display as table
        st.dataframe(df, use_container_width=True, height=400)
        
        # Download option
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download Files CSV",
            data=csv,
            file_name=f"{project_data['name']}_files.csv",
            mime="text/csv"
        )
    else:
        st.info("No files analyzed yet")

# ============= TAB 3: CODE CHUNKS =============
with tab3:
    st.subheader("🔍 Code Chunks & Embeddings")
    
    chunks = chunks_data.get("chunks", [])
    
    if chunks:
        # Chunk statistics
        chunk_types = {}
        for chunk in chunks:
            chunk_type = chunk.get("chunk_type", "function")
            chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
        
        # Display stats
        st.write("**Chunks by Type:**")
        col1, col2, col3 = st.columns(3)
        for chunk_type, count in sorted(chunk_types.items()):
            with col1 if chunk_type == "function" else (col2 if chunk_type == "class" else col3):
                st.metric(chunk_type.title(), count)
        
        st.markdown("---")
        
        # Search/filter chunks
        st.write("**Search Chunks:**")
        search_col, lang_col = st.columns(2)
        
        with search_col:
            search_query = st.text_input("Search by name or content:", placeholder="e.g., 'authenticate'")
        
        with lang_col:
            languages = sorted(set(c.get("language", "Unknown") for c in chunks))
            selected_lang = st.selectbox("Filter by language:", ["All"] + languages)
        
        # Filter chunks
        filtered_chunks = chunks
        if search_query:
            filtered_chunks = [
                c for c in filtered_chunks
                if search_query.lower() in c.get("name", "").lower() or 
                   search_query.lower() in c.get("content", "").lower()
            ]
        
        if selected_lang != "All":
            filtered_chunks = [c for c in filtered_chunks if c.get("language") == selected_lang]
        
        st.markdown(f"**Found {len(filtered_chunks)} chunks**")
        
        # Display chunks
        for idx, chunk in enumerate(filtered_chunks[:50]):  # Show first 50
            with st.expander(f"📌 {chunk.get('name', 'Unknown')} ({chunk.get('chunk_type', 'unknown')}) - {chunk.get('language', 'unknown')}"):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.write("**Metadata:**")
                    st.write(f"• **Type:** {chunk.get('chunk_type')}")
                    st.write(f"• **Language:** {chunk.get('language')}")
                    st.write(f"• **Lines:** {chunk.get('start_line')} - {chunk.get('end_line')}")
                    st.write(f"• **Has Embedding:** {'✓' if chunk.get('embedding') else '✗'}")
                
                with col2:
                    if chunk.get("docstring"):
                        st.write("**Docstring:**")
                        st.write(chunk.get("docstring"))
                    
                    if chunk.get("parameters"):
                        st.write("**Parameters:**")
                        st.write(chunk.get("parameters"))
                
                st.write("**Code:**")
                st.code(chunk.get("content", ""), language=chunk.get("language", "text"))
        
        # Download chunks
        chunks_df = pd.DataFrame([
            {
                "Name": c.get("name"),
                "Type": c.get("chunk_type"),
                "Language": c.get("language"),
                "Start Line": c.get("start_line"),
                "End Line": c.get("end_line"),
                "Has Embedding": "Yes" if c.get("embedding") else "No",
                "Docstring": (c.get("docstring") or "")[:100]
            }
            for c in chunks
        ])
        
        csv = chunks_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Chunks CSV",
            data=csv,
            file_name=f"{project_data['name']}_chunks.csv",
            mime="text/csv"
        )
    else:
        st.info("No code chunks found. Run preprocessing to analyze the code.")

# ============= TAB 4: INTELLIGENCE =============
with tab4:
    st.subheader("🧠 Code Intelligence & Insights")
    
    repo_meta = metadata.get("repository_metadata", {})
    
    # Architecture overview
    st.write("**📐 Architecture Overview:**")
    if repo_meta.get("entry_points"):
        st.write("**Entry Points:**")
        for ep_type, ep_path in repo_meta.get("entry_points", {}).items():
            st.write(f"• {ep_type}: `{ep_path}`")
    
    # Dependencies
    if repo_meta.get("dependencies"):
        st.write("**Dependencies:**")
        deps = repo_meta.get("dependencies", {})
        for dep_type, dep_list in deps.items():
            if dep_list:
                st.write(f"• {dep_type}: {', '.join(dep_list[:10])}")
                if len(dep_list) > 10:
                    st.write(f"  ... and {len(dep_list) - 10} more")
    
    # Code quality insights
    st.write("**📊 Code Quality Metrics:**")
    
    if files_data.get("files"):
        files = files_data.get("files", [])
        
        # Calculate metrics
        total_loc = sum(f.get("lines_of_code", 0) for f in files)
        avg_loc = total_loc // len(files) if files else 0
        total_functions = sum(f.get("function_count", 0) for f in files)
        total_classes = sum(f.get("class_count", 0) for f in files)
        test_files = sum(1 for f in files if f.get("is_test_file"))
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total LOC", total_loc)
        with col2:
            st.metric("Avg LOC/File", avg_loc)
        with col3:
            st.metric("Total Functions", total_functions)
        with col4:
            st.metric("Total Classes", total_classes)
        with col5:
            st.metric("Test Files", test_files)
    
    # Embedding statistics
    st.write("**🔗 Embedding Intelligence:**")
    chunks = chunks_data.get("chunks", [])
    
    if chunks:
        chunks_with_embeddings = sum(1 for c in chunks if c.get("embedding"))
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Chunks", len(chunks))
        with col2:
            st.metric("Chunks with Embeddings", chunks_with_embeddings)
        with col3:
            embedding_pct = (chunks_with_embeddings / len(chunks) * 100) if chunks else 0
            st.metric("Coverage %", f"{embedding_pct:.1f}%")
        
        st.info("✅ Embeddings are generated using OpenAI's text-embedding-3-small model (1536 dimensions). "
                "These embeddings enable semantic search and code similarity analysis.")
    
    # Recommended next steps
    st.markdown("---")
    st.write("**💡 Next Steps:**")
    st.write("""
    1. **Semantic Search**: Use embeddings to find similar code patterns
    2. **Code Navigation**: Jump to related functions and classes
    3. **Quality Analysis**: Identify code duplicates and refactoring opportunities
    4. **Documentation**: Generate documentation from analyzed code
    5. **Team Insights**: Share analysis with team members
    """)

# ============= TAB 5: Q&A SEARCH =============
with tab5:
    st.subheader("🤖 AI-Powered Code Assistant")
    st.write("Ask questions about this project's code. AI will search the codebase and provide intelligent summaries.")
    
    # Initialize session state for Q&A
    if "qa_history" not in st.session_state:
        st.session_state.qa_history = []
    if "current_question" not in st.session_state:
        st.session_state.current_question = ""
    
    st.markdown("---")
    
    # Question input with send button
    col1, col2 = st.columns([4, 1])
    
    with col1:
        question = st.text_input(
            "What would you like to know about this project?",
            placeholder="e.g., 'What is the authentication method used?', 'How does the database work?', 'What are the main API endpoints?'",
            key="qa_input",
            label_visibility="collapsed"
        )
    
    with col2:
        send_button = st.button("🚀 Ask", use_container_width=True, key="qa_search_btn")
    
    # Process question when send button is clicked
    if send_button:
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            try:
                with st.spinner("🔍 Searching your project's code..."):
                    # Call semantic search API
                    result = asyncio.run(api_client.ask_question(
                        project_id=project_id,
                        question=question
                    ))
                    
                    # Add to history
                    st.session_state.qa_history.append({
                        "question": question,
                        "result": result
                    })
                    
                    # Clear input after successful query
                    st.session_state.current_question = ""
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.write(f"Details: {e}")
    
    # Display conversation history (most recent first)
    if st.session_state.qa_history:
        st.markdown("---")
        
        # Display in reverse order (most recent on top)
        for idx, item in enumerate(reversed(st.session_state.qa_history)):
            conversation_idx = len(st.session_state.qa_history) - idx
            result = item.get("result", {})
            
            # Display question
            st.markdown(f"### ❓ Question {conversation_idx}")
            st.write(f"**{item['question']}**")
            
            # Display message and result count
            st.markdown("#### 🔍 Search Results")
            st.info(result.get("message", "No results"))
            
            # Display relevant code chunks
            if result.get("results"):
                results = result.get("results", [])
                st.write(f"Found **{result.get('total_results', 0)}** relevant code section{'s' if result.get('total_results', 0) != 1 else ''}:")
                
                for src_idx, chunk in enumerate(results, 1):
                    # File header with relevance
                    file_path = chunk.get('file_path', 'Unknown')
                    start_line = chunk.get('start_line', '?')
                    end_line = chunk.get('end_line', '?')
                    similarity = chunk.get("similarity_score")
                    relevance_pct = int(similarity * 100) if similarity is not None else 0
                    
                    # Color code relevance
                    if relevance_pct >= 85:
                        relevance_emoji = "🟢"
                    elif relevance_pct >= 70:
                        relevance_emoji = "🟡"
                    else:
                        relevance_emoji = "🔵"
                    
                    with st.expander(
                        f"{relevance_emoji} **Result {src_idx}:** {file_path} (Lines {start_line}-{end_line}) • {relevance_pct}% match",
                        expanded=(src_idx == 1)  # Expand first one by default
                    ):
                        # Metadata columns
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.caption(f"📄 File")
                            st.code(file_path, language="text")
                        
                        with col2:
                            st.caption(f"🔤 Language")
                            st.write(chunk.get('language', 'Unknown'))
                        
                        with col3:
                            st.caption(f"📍 Lines")
                            st.write(f"{start_line} - {end_line}")
                        
                        with col4:
                            st.caption(f"🎯 Relevance")
                            st.write(f"{relevance_pct}%")
                            st.progress(min(similarity, 1.0) if similarity else 0)
                        
                        # Function/Class name
                        if chunk.get('name'):
                            st.markdown(f"**{chunk.get('chunk_type', 'Code')}:** `{chunk.get('name')}`")
                        
                        # Docstring if available
                        if chunk.get('docstring'):
                            st.markdown("**Documentation:**")
                            st.write(chunk.get('docstring'))
                        
                        # Code content
                        st.markdown("**Code:**")
                        code_content = chunk.get("content", "")
                        language = chunk.get("language", "text").lower()
                        st.code(code_content, language=language)
            else:
                st.warning("No relevant code found for your search.")
            
            st.markdown("---")
    
    # If no history, show welcome message
    if not st.session_state.qa_history:
        st.info("""
        ### 👋 Welcome to Code Search
        
        Search your entire codebase using natural language! I'll find all relevant code sections.
        
        **Example questions:**
        - "What is the authentication method used in this application?"
        - "How does the database connection work?"
        - "What are the main API endpoints?"
        - "Where is the configuration stored?"
        - "How are errors handled?"
        """)
    
    # Help section
    st.markdown("---")
    st.subheader("💡 How This Works")
    st.write("""
    **Step 1: You Ask** → Type a natural language question about your code
    
    **Step 2: Semantic Search** → System searches through all code using vector embeddings
    
    **Step 3: View Results** → Expand any result to see the code and metadata
    
    **Smart Ranking** → Results are ranked by relevance (similarity score)
    
    **Project-Specific:** All searches are limited to this project's code only.
    """)
    
    st.markdown("---")
    st.subheader("🎯 Tips for Best Results")
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("""
        ✅ **DO:**
        - Be specific in your questions
        - Ask about features or functionality
        - Ask about architecture or design
        - Ask how things are implemented
        """)
    
    with col2:
        st.write("""
        ❌ **DON'T:**
        - Ask vague questions
        - Ask for code not in this project
        - Ask for unrelated advice
        - Ask about tools not used here
        """)
