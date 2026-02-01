"""API client for FastAPI backend"""
import httpx
import streamlit as st
import asyncio
from typing import Optional, Dict, Any


class APIClient:
    """Client for communicating with FastAPI backend"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_prefix = "/api/v1"
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth token"""
        headers = {"Content-Type": "application/json"}
        token = st.session_state.get("access_token")
        # Only attach Authorization header when we actually have a token
        if token:
            headers["Authorization"] = f"Bearer {token}"
            print(f"DEBUG: API headers with token: {token[:20]}...")
        else:
            print(f"DEBUG: API headers WITHOUT token. Session state keys: {list(st.session_state.keys())}")
        return headers
    
    async def signup(self, email: str, password: str, role: str = "user") -> Dict[str, Any]:
        """Sign up a new user"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/auth/signup",
                json={"email": email, "password": password, "role": role},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """Login user"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/auth/login",
                json={"email": email, "password": password},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def create_project_from_zip(
        self,
        name: str,
        file_content: bytes,
        filename: str,
        personas: list
    ) -> Dict[str, Any]:
        """Create project from ZIP file"""
        async with httpx.AsyncClient() as client:
            files = {"file": (filename, file_content, "application/zip")}
            data = {
                "name": name,
                "personas": ",".join(personas)
            }
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/projects/upload",
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {st.session_state.access_token}"}
            )
            response.raise_for_status()
            return response.json()
    
    async def create_project_from_github(
        self,
        name: str,
        github_url: str,
        personas: list
    ) -> Dict[str, Any]:
        """Create project from GitHub URL"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/projects",
                json={
                    "name": name,
                    "source_type": "github",
                    "source_path": github_url,
                    "personas": personas
                },
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def list_projects(self) -> Dict[str, Any]:
        """List user's projects"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/projects",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def get_project(self, project_id: str) -> Dict[str, Any]:
        """Get project by ID"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/projects/{project_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def preprocess_project(self, project_id: str) -> Dict[str, Any]:
        """Trigger preprocessing for a project"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/projects/{project_id}/preprocess",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def get_project_metadata(self, project_id: str) -> Dict[str, Any]:
        """Get project metadata (frameworks, files, analysis)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/projects/{project_id}/metadata",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def get_project_files(self, project_id: str) -> Dict[str, Any]:
        """Get project files with metadata"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/projects/{project_id}/files",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def get_project_chunks(self, project_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get code chunks for a project"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/projects/{project_id}/chunks",
                params={"limit": limit, "offset": offset},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def semantic_search(self, project_id: str, query: str, limit: int = 5) -> Dict[str, Any]:
        """Perform semantic search on code chunks"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/projects/{project_id}/search",
                json={"query": query, "limit": limit, "similarity_threshold": 0.3},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def ask_question(self, project_id: str, question: str, use_llm: bool = True) -> Dict[str, Any]:
        """Ask a question about the codebase"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/projects/{project_id}/ask",
                json={"question": question, "use_llm": use_llm},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def create_analysis(self, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create and start a new analysis job"""
        async with httpx.AsyncClient() as client:
            payload = {
                "project_id": project_id,
                **config
            }
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/analysis/create",
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def get_analysis(self, analysis_id: str) -> Dict[str, Any]:
        """Get analysis status and progress"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def control_analysis(self, analysis_id: str, control: Dict[str, Any]) -> Dict[str, Any]:
        """Control analysis (pause/resume/add context)"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}/control",
                json=control,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
    
    async def get_analysis_logs(self, analysis_id: str, limit: int = 100) -> Dict[str, Any]:
        """Get analysis activity logs"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}/logs",
                params={"limit": limit},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def ask_analysis(self, analysis_id: str, question: str) -> Dict[str, Any]:
        """Ask a question during analysis"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}/ask",
                json={"question": question},
                headers=self._get_headers()
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                detail = e.response.text
                raise Exception(f"{e.response.status_code} {detail}") from e
            return response.json()

    def ask_analysis_sync(self, analysis_id: str, question: str) -> Dict[str, Any]:
        """Sync ask during analysis (avoids event loop issues in Streamlit)."""
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}/ask",
                json={"question": question},
                headers=self._get_headers()
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                detail = e.response.text
                raise Exception(f"{e.response.status_code} {detail}") from e
            return response.json()
    
    async def get_latest_analysis(self, project_id: str | None = None) -> Optional[Dict[str, Any]]:
        """Get the latest analysis (optionally for a project) for display in mini-player or Docs link."""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}{self.api_prefix}/analysis/latest"
                params = {}
                if project_id:
                    params["project_id"] = project_id
                response = await client.get(url, params=params or None, headers=self._get_headers())
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"Error fetching latest analysis: {e}")
            return None

    async def list_analysis_templates(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/analysis/templates",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def create_analysis_template(self, name: str, description: str | None, config: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/analysis/templates",
                json={
                    "name": name,
                    "description": description,
                    "config": config
                },
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def delete_analysis_template(self, template_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}{self.api_prefix}/analysis/templates/{template_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def get_analysis_artifacts(self, analysis_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}/artifacts",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def export_analysis_markdown(self, analysis_id: str) -> Dict[str, Any]:
        """Export analysis documentation as a single Markdown file."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}/export/markdown",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def export_analysis_pdf(self, analysis_id: str) -> bytes | None:
        """Export analysis documentation as PDF. Returns raw bytes or None on error."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/analysis/{analysis_id}/export/pdf",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.content

    async def admin_health(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/admin/health",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_running_analyses(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/admin/analyses/running",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_error_logs(self, limit: int = 50) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/admin/logs/errors",
                params={"limit": limit},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_list_users(self, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/admin/users",
                params={"skip": skip, "limit": limit},
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_create_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{self.api_prefix}/admin/users",
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_update_user(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}{self.api_prefix}/admin/users/{user_id}",
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_delete_user(self, user_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}{self.api_prefix}/admin/users/{user_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_list_projects(
        self,
        skip: int = 0,
        limit: int = 100,
        status_filter: str | None = None
    ) -> Dict[str, Any]:
        params = {"skip": skip, "limit": limit}
        if status_filter:
            params["status_filter"] = status_filter
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}{self.api_prefix}/admin/projects",
                params=params,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_update_project(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}{self.api_prefix}/admin/projects/{project_id}",
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def admin_delete_project(self, project_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}{self.api_prefix}/admin/projects/{project_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    

# Global API client instance
api_client = APIClient()