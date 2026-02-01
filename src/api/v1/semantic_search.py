"""Semantic search API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from pydantic import BaseModel

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project
from src.services.semantic_search import SemanticSearchService
from sqlalchemy import select

router = APIRouter()


class SearchQuery(BaseModel):
    """Semantic search query"""
    query: str
    limit: int = 5
    similarity_threshold: float = 0.3


class QuestionQuery(BaseModel):
    """Q&A question query"""
    question: str
    use_llm: bool = True


@router.post("/{project_id}/search")
async def semantic_search(
    project_id: str,
    search_query: SearchQuery,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Perform semantic search on code chunks in a project.
    
    Finds code sections similar to the query using embeddings.
    
    Args:
        project_id: Project ID to search in
        search_query: Query text and parameters
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        List of similar code chunks with similarity scores
    """
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied"
        )
    
    # Perform search
    search_service = SemanticSearchService(db)
    results = await search_service.search_similar_code(
        project_id=str(project.id),
        query=search_query.query,
        limit=search_query.limit,
        similarity_threshold=search_query.similarity_threshold
    )
    
    return {
        "query": search_query.query,
        "results": results,
        "count": len(results),
        "project_id": str(project.id)
    }


@router.post("/{project_id}/ask")
async def ask_question(
    project_id: str,
    question_query: QuestionQuery,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Ask a natural language question about the codebase.
    
    Uses semantic search to find relevant code sections and optionally
    uses LLM to generate a contextual answer.
    
    Args:
        project_id: Project ID to query
        question_query: Question and parameters
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        Answer with relevant code sources and confidence
    """
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied"
        )
    
    # Answer question; returns structured { answer, citations } for UI to render separately
    search_service = SemanticSearchService(db)
    answer = await search_service.answer_question(
        project_id=str(project.id),
        question=question_query.question,
        use_llm=question_query.use_llm,
    )
    return {**answer, "project_id": str(project.id)}
