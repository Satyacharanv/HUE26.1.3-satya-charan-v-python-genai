"""Semantic search and Q&A service for code analysis"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any, Optional
from uuid import UUID
import logging
import numpy as np

from src.models.code_chunk import CodeChunk
from src.services.code_parser import CodeParser
from src.services.langfuse_client import log_generation
from src.services.usage_tracker import record_llm_usage

logger = logging.getLogger(__name__)

class SemanticSearchService:
    """Service for semantic search over code using embeddings"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.parser = CodeParser()
    
    async def search_similar_code(
        self,
        project_id: str,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Find code chunks similar to a query using semantic search with pgvector.
        """
        try:
            logger.info(f"Starting semantic search for query: '{query}' in project: {project_id}")
            
            # Generate embedding for the query
            query_embedding = await self._generate_query_embedding(query)
            
            if not query_embedding:
                logger.warning(f"Failed to generate embedding for query: '{query}'")
                return []
            
            # NOTE: Do NOT wrap query_embedding in Vector(). Pass the list of floats directly.
            # max_inner_product correlates to the <#> operator.
            # In pgvector, <#> returns the negative inner product.
            # Sorting ASC (default) puts the most similar (most negative) at the top.
            stmt = (
                select(
                    CodeChunk,
                    CodeChunk.embedding.max_inner_product(query_embedding).label('distance')
                )
                .where(
                    CodeChunk.project_id == project_id,
                    CodeChunk.embedding.isnot(None)
                )
                .order_by(CodeChunk.embedding.max_inner_product(query_embedding))
                .limit(limit)
            )
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            results = []
            for chunk, distance in rows:
                # distance is -(a · b). Since OpenAI vectors are normalized, 
                # similarity (cosine) = (a · b). So similarity = -distance.
                similarity = -float(distance)
                
                # Only include results above similarity threshold
                if similarity >= similarity_threshold:
                    results.append({
                        "id": str(chunk.id),
                        "name": chunk.name,
                        "type": chunk.chunk_type,
                        "language": chunk.language,
                        "file_path": chunk.file_path,
                        "content": chunk.content,
                        "docstring": chunk.docstring,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "similarity_score": round(similarity, 4),
                        "confidence": "high" if similarity > 0.8 else "medium"
                    })
            
            logger.info(f"Found {len(results)} chunks above threshold {similarity_threshold}")
            return results
            
        except Exception as e:
            logger.error(f"Error during semantic search: {e}", exc_info=True)
            return []
    
    async def _generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding using OpenAI text-embedding-3-small"""
        try:
            from src.core.config import settings
            from openai import AsyncOpenAI
            
            if not settings.OPENAI_API_KEY:
                return None
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.embeddings.create(
                input=query,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            return None
    
    async def answer_question(
        self,
        project_id: str,
        question: str,
        use_llm: bool = True,
        progress: Optional[Any] = None,
        analysis_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Search for code relevant to the question and return structured data:
        - answer: LLM-generated answer text (when use_llm and API key set), else brief summary
        - citations: list of { file_path, start_line, end_line, content, relevance_score } for UI to render
        """
        try:
            relevant_chunks = await self.search_similar_code(
                project_id=project_id,
                query=question,
                limit=5,
                similarity_threshold=0.25,
            )

            citations = [
                {
                    "file_path": c.get("file_path", ""),
                    "start_line": c.get("start_line"),
                    "end_line": c.get("end_line"),
                    "content": c.get("content", ""),
                    "relevance_score": c.get("similarity_score", 0),
                    "language": c.get("language"),
                }
                for c in relevant_chunks
            ]

            if not relevant_chunks:
                return {
                    "question": question,
                    "answer": "No relevant code found for this question.",
                    "citations": [],
                    "results": [],
                    "total_results": 0,
                    "message": "No relevant code found",
                }
            answer_text = ""
            if use_llm:
                answer_text = await self._generate_answer_from_chunks(
                    question,
                    relevant_chunks,
                    project_id=project_id,
                    progress=progress,
                    analysis_id=analysis_id,
                )
            if not answer_text:
                answer_text = (
                    f"Found {len(relevant_chunks)} relevant code section(s). "
                    "See citations below for file locations and snippets."
                )
            return {
                "question": question,
                "answer": answer_text,
                "citations": citations,
                "results": relevant_chunks,
                "total_results": len(relevant_chunks),
                "message": f"Found {len(relevant_chunks)} relevant code sections",
            }
        except Exception as e:
            logger.error(f"Error searching for question: {e}")
            return {
                "question": question,
                "answer": "An error occurred while answering.",
                "citations": [],
                "results": [],
                "total_results": 0,
                "message": "Error processing search",
            }

    async def _generate_answer_from_chunks(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        project_id: str | None = None,
        progress: Optional[Any] = None,
        analysis_id: Optional[UUID] = None,
    ) -> str:
        """Generate a short answer from question and code chunks using LLM. Returns empty string if unavailable."""
        try:
            from src.core.config import settings
            from openai import AsyncOpenAI
            if not getattr(settings, "OPENAI_API_KEY", None):
                return ""
            context = self._prepare_context(chunks)
            system = (
                "You are a codebase assistant. Answer the user's question using ONLY the provided code snippets. "
                "Be concise. Do not invent code or file names not in the context. "
                "If the snippets do not contain enough information, say so briefly."
            )
            user = f"Question: {question}\n\nRelevant code:\n{context}"
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content.strip()
                usage = {}
                if getattr(response, "usage", None):
                    usage = {
                        "input": response.usage.prompt_tokens,
                        "output": response.usage.completion_tokens,
                        "total": response.usage.total_tokens,
                    }
                    if progress and analysis_id:
                        await record_llm_usage(
                            progress,
                            analysis_id,
                            response.usage.prompt_tokens,
                            response.usage.completion_tokens,
                            model,
                        )
                log_generation(
                    name="semantic_qa",
                    model=model,
                    input_data={"question": question, "context": context},
                    output_data=content,
                    usage=usage,
                    metadata={"project_id": project_id} if project_id else None,
                )
                return content
            return ""
        except Exception as e:
            logger.warning(f"LLM answer generation failed: {e}")
            return ""

    def _prepare_context(self, chunks: List[Dict[str, Any]]) -> str:
        ctx = ""
        for i, c in enumerate(chunks):
            ctx += f"\n--- Chunk {i+1} ({c['name']}) ---\n{c['content'][:500]}\n"
        return ctx

    def _calculate_confidence(self, chunks: List[Dict[str, Any]]) -> str:
        if not chunks: return "low"
        avg = sum(c['similarity_score'] for c in chunks) / len(chunks)
        if avg > 0.75: return "high"
        if avg > 0.5: return "medium"
        return "low"