"""Code chunking and embedding service for semantic search"""
import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from uuid import UUID
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.core.logging_config import get_logger
from src.models.code_chunk import CodeChunk as CodeChunkModel
from src.models.repository_metadata import RepositoryMetadata, FileMetadata
from src.models.project import Project, ProjectStatus
from src.services.repository_analyzer import RepositoryAnalyzer
from src.services.code_parser import CodeParser, CodeChunk
from src.services.storage import storage_service
from src.services.usage_tracker import record_embedding_usage
from src.core.config import settings

logger = get_logger(__name__)


class CodeChunker:
    """Handles code chunking and semantic preparation for vector embedding"""
    EMBED_FILES_PER_WINDOW = 2
    EMBED_BATCH_SIZE = 20
    EMBED_MAX_CHUNKS_PER_WINDOW = 80
    MAX_CHUNK_CHARS = 3000
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.parser = CodeParser()
        self.analyzer = RepositoryAnalyzer("")  # Will be set per project
        self.progress_callback: Optional[Callable] = None  # For real-time updates
        self.pause_checker: Optional[Callable[[], Any]] = None  # Pause gate
        self.embedding_failures = 0
        self._progress = None  # AnalysisProgressService when running under analysis
        self._analysis_id: Optional[UUID] = None
    
    def set_analysis_context(self, progress: Any, analysis_id: UUID) -> None:
        """Set progress and analysis_id so embedding usage can be recorded."""
        self._progress = progress
        self._analysis_id = analysis_id
    
    async def _emit_progress(self, event: Dict[str, Any]):
        """Emit progress event if callback is set"""
        if self.progress_callback:
            try:
                await self.progress_callback(event)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")

    async def _maybe_pause(self):
        """Pause gate hook for long-running loops."""
        if self.pause_checker:
            await self.pause_checker()

    async def _register_embedding_failure(self, message: str) -> None:
        """Track embedding failures and fail after threshold."""
        self.embedding_failures += 1
        await self._emit_progress({
            "type": "log",
            "level": "warning",
            "message": message
        })
        if self.embedding_failures > 2:
            await self._emit_progress({
                "type": "log",
                "level": "error",
                "message": "❌ Embedding failed more than 2 batches; aborting analysis"
            })
            raise RuntimeError("Embedding failed more than 2 batches; aborting analysis")
    
    def _split_large_chunks(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        """Split oversized chunks by character length."""
        split_chunks: List[CodeChunk] = []
        for chunk in chunks:
            if len(chunk.content) <= self.MAX_CHUNK_CHARS:
                split_chunks.append(chunk)
                continue
            
            lines = chunk.content.splitlines()
            if not lines:
                split_chunks.append(chunk)
                continue
            
            part_index = 1
            current_lines: List[str] = []
            current_len = 0
            start_offset = 0
            
            for idx, line in enumerate(lines):
                line_len = len(line) + 1
                if current_lines and current_len + line_len > self.MAX_CHUNK_CHARS:
                    part_content = "\n".join(current_lines)
                    part = CodeChunk(
                        name=f"{chunk.name}__part{part_index}",
                        chunk_type=chunk.chunk_type,
                        content=part_content,
                        start_line=chunk.start_line + start_offset,
                        end_line=chunk.start_line + idx - 1,
                        language=chunk.language,
                        docstring=chunk.docstring if part_index == 1 else None,
                        dependencies=chunk.dependencies,
                        parameters=chunk.parameters,
                        return_type=chunk.return_type,
                        parent=chunk.parent
                    )
                    split_chunks.append(part)
                    part_index += 1
                    current_lines = []
                    current_len = 0
                    start_offset = idx
                
                current_lines.append(line)
                current_len += line_len
            
            if current_lines:
                part_content = "\n".join(current_lines)
                part = CodeChunk(
                    name=f"{chunk.name}__part{part_index}",
                    chunk_type=chunk.chunk_type,
                    content=part_content,
                    start_line=chunk.start_line + start_offset,
                    end_line=chunk.start_line + len(lines) - 1,
                    language=chunk.language,
                    docstring=chunk.docstring if part_index == 1 else None,
                    dependencies=chunk.dependencies,
                    parameters=chunk.parameters,
                    return_type=chunk.return_type,
                    parent=chunk.parent
                )
                split_chunks.append(part)
        
        return split_chunks
    
    async def preprocess_project(self, project_id: str, extracted_path: str) -> Dict[str, Any]:
        """Main preprocessing pipeline"""
        logger.debug(f"Starting preprocessing for project: {project_id}")
        self.embedding_failures = 0
        
        try:
            # Get project
            result = await self.db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            
            if not project:
                raise ValueError(f"Project not found: {project_id}")
            
            # Update project status
            project.status = ProjectStatus.PREPROCESSING
            await self.db.commit()
            
            # Get full extracted path
            repo_path = storage_service.get_file_path(extracted_path)
            
            if not repo_path.exists():
                raise ValueError(f"Extracted repository not found: {extracted_path}")
            
            # Step 1: Analyze repository
            await self._maybe_pause()
            await self._emit_progress({
                "type": "log",
                "level": "info",
                "message": "Step 1: Analyzing repository structure",
                "stage": "repo_scan"
            })
            logger.debug("Step 1: Analyzing repository structure")
            self.analyzer = RepositoryAnalyzer(str(repo_path))
            repo_metadata = self.analyzer.analyze()
            
            # Create repository metadata record
            repo_meta_record = RepositoryMetadata(
                project_id=project_id,
                repository_type=repo_metadata["repository_type"],
                primary_framework=repo_metadata.get("primary_framework"),
                secondary_frameworks=repo_metadata.get("secondary_frameworks", []),
                total_files=repo_metadata["total_files"],
                code_files=repo_metadata["code_files"],
                test_files=repo_metadata["test_files"],
                config_files=repo_metadata["config_files"],
                documentation_files=repo_metadata["documentation_files"],
                entry_points=repo_metadata.get("entry_points", {}),
                config_files_list=repo_metadata.get("config_files_list", []),
                dependencies=repo_metadata.get("dependencies", {}),
                preprocessing_status="processing",
            )
            
            self.db.add(repo_meta_record)
            await self.db.commit()
            await self.db.refresh(repo_meta_record)
            
            logger.debug(f"Repository metadata created: {repo_meta_record.id}")
            
            # Step 2: Process files and extract code chunks
            await self._maybe_pause()
            await self._emit_progress({
                "type": "log",
                "level": "info",
                "message": "Step 2: Processing files and extracting code chunks",
                "stage": "code_chunking"
            })
            logger.debug("Step 2: Processing files and extracting code chunks")
            
            # Count total files first
            total_files = 0
            for root, dirs, files in os.walk(repo_path):
                skip_patterns = self.analyzer.skip_patterns
                dirs[:] = [d for d in dirs if d not in skip_patterns]
                total_files += len([f for f in files if self.parser.detect_language(f)])
            
            total_chunks = 0
            file_count = 0
            window_files = 0
            window_chunks: List[CodeChunkModel] = []
            embedding_started = False
            
            for root, dirs, files in os.walk(repo_path):
                # Filter skip directories
                skip_patterns = self.analyzer.skip_patterns
                dirs[:] = [d for d in dirs if d not in skip_patterns]
                
                for file in files:
                    await self._maybe_pause()
                    file_path = Path(root) / file
                    relative_path = str(file_path.relative_to(repo_path))
                    
                    # Detect language
                    language = self.parser.detect_language(file)
                    if not language:
                        continue
                    
                    file_count += 1
                    progress_percent = min(int((file_count / max(total_files, 1)) * 100), 99)  # Cap at 99% until complete
                    
                    # Emit progress with file info
                    await self._emit_progress({
                        "type": "progress",
                        "percent": progress_percent,
                        "stage": "code_chunking",
                        "current_file": relative_path,
                        "file_index": file_count,
                        "total_files": total_files
                    })
                    
                    # Emit detailed log about file processing
                    await self._emit_progress({
                        "type": "log",
                        "level": "info",
                        "message": f"Processing: {relative_path} ({language})"
                    })
                    
                    logger.debug(f"Processing file ({file_count}/{total_files}): {relative_path}")
                    
                    try:
                        await self._maybe_pause()
                        # Parse file and extract chunks
                        raw_chunks = self.parser.parse_file(str(file_path), language)
                        chunks = self._split_large_chunks(raw_chunks)
                        
                        if not chunks:
                            continue
                        
                        # Emit log about chunks found
                        await self._emit_progress({
                            "type": "log",
                            "level": "info",
                            "message": f"✓ Extracted {len(chunks)} code chunks from {relative_path}"
                        })
                        
                        # Check if file is important
                        is_important = self._is_important_file(relative_path, repo_metadata)
                        
                        # Create file metadata record
                        file_meta = FileMetadata(
                            project_id=project_id,
                            repository_id=repo_meta_record.id,
                            file_path=relative_path,
                            file_name=file,
                            file_type=self._get_file_type(relative_path),
                            language=language,
                            lines_of_code=self._count_lines(str(file_path)),
                            is_test_file=self._is_test_file(file),
                            is_important=is_important,
                            has_docstring=self._has_docstring(chunks),
                            function_count=sum(1 for c in raw_chunks if c.chunk_type == "function"),
                            class_count=sum(1 for c in raw_chunks if c.chunk_type == "class"),
                            chunks_created=len(chunks),
                            is_processed=True,
                        )
                        
                        self.db.add(file_meta)
                        await self.db.commit()
                        
                        # Create code chunk records
                        for chunk in chunks:
                            chunk_record = CodeChunkModel(
                                project_id=project_id,
                                file_path=relative_path,
                                chunk_type=chunk.chunk_type,
                                name=chunk.name,
                                content=chunk.content,
                                start_line=chunk.start_line,
                                end_line=chunk.end_line,
                                language=language,
                                is_important=is_important,
                                docstring=chunk.docstring,
                                dependencies={"external": chunk.dependencies},
                                parameters=chunk.parameters,
                                return_type=chunk.return_type,
                            )
                            
                            self.db.add(chunk_record)
                            total_chunks += 1
                            window_chunks.append(chunk_record)
                        
                        await self.db.commit()
                        window_files += 1
                        logger.debug(f"Extracted {len(chunks)} chunks from {relative_path}")
                        
                        if settings.OPENAI_API_KEY and window_chunks:
                            if (window_files >= self.EMBED_FILES_PER_WINDOW or
                                len(window_chunks) >= self.EMBED_MAX_CHUNKS_PER_WINDOW):
                                await self._maybe_pause()
                                if not embedding_started:
                                    embedding_started = True
                                    await self._emit_progress({
                                        "type": "progress",
                                        "stage": "embedding_generation",
                                        "file_index": file_count,
                                        "total_files": total_files
                                    })
                                    await self._emit_progress({
                                        "type": "log",
                                        "level": "info",
                                        "message": "🔄 Starting embeddings generation"
                                    })
                                
                                try:
                                    embedding_count = await asyncio.wait_for(
                                        self._generate_embeddings(
                                            window_chunks,
                                            batch_size=self.EMBED_BATCH_SIZE
                                        ),
                                        timeout=120.0
                                    )
                                except asyncio.TimeoutError:
                                    await self._register_embedding_failure(
                                        "⚠️ Embedding generation timed out; skipping this window."
                                    )
                                    embedding_count = 0
                                await self._emit_progress({
                                    "type": "log",
                                    "level": "info",
                                    "message": f"✓ Embedded window - {embedding_count} embeddings created"
                                })
                                window_chunks = []
                                window_files = 0
                    
                    except Exception as e:
                        logger.warning(f"Error processing {relative_path}: {e}")
                        continue
            
            # Commit all code chunks
            await self.db.commit()
            
            logger.debug(f"Preprocessing complete: {file_count} files, {total_chunks} chunks")
            
            # Step 3: Generate embeddings for remaining chunks
            if settings.OPENAI_API_KEY:
                if window_chunks:
                    await self._maybe_pause()
                    if not embedding_started:
                        embedding_started = True
                        await self._emit_progress({
                            "type": "progress",
                            "stage": "embedding_generation",
                            "file_index": file_count,
                            "total_files": total_files
                        })
                        await self._emit_progress({
                            "type": "log",
                            "level": "info",
                            "message": "🔄 Starting embeddings generation"
                        })
                    try:
                        embedding_count = await asyncio.wait_for(
                            self._generate_embeddings(
                                window_chunks,
                                batch_size=self.EMBED_BATCH_SIZE
                            ),
                            timeout=120.0
                        )
                    except asyncio.TimeoutError:
                        await self._register_embedding_failure(
                            "⚠️ Embedding generation timed out; skipping final window."
                        )
                        embedding_count = 0
                    await self._emit_progress({
                        "type": "log",
                        "level": "info",
                        "message": f"✓ Embedded final window - {embedding_count} embeddings created"
                    })
                
                chunks_to_embed = await self.db.execute(
                    select(CodeChunkModel).where(
                        CodeChunkModel.project_id == project_id,
                        CodeChunkModel.embedding == None
                    )
                )
                remaining = chunks_to_embed.scalars().all()
                if remaining:
                    await self._maybe_pause()
                    if not embedding_started:
                        embedding_started = True
                        await self._emit_progress({
                            "type": "progress",
                            "stage": "embedding_generation",
                            "file_index": file_count,
                            "total_files": total_files
                        })
                        await self._emit_progress({
                            "type": "log",
                            "level": "info",
                            "message": "🔄 Starting embeddings generation"
                        })
                    try:
                        embedding_count = await asyncio.wait_for(
                            self._generate_embeddings(
                                remaining,
                                batch_size=self.EMBED_BATCH_SIZE
                            ),
                            timeout=120.0
                        )
                    except asyncio.TimeoutError:
                        await self._register_embedding_failure(
                            "⚠️ Embedding generation timed out; skipping remaining chunks."
                        )
                        embedding_count = 0
                    logger.debug(f"Generated embeddings for {embedding_count} chunks")
                else:
                    await self._emit_progress({
                        "type": "log",
                        "level": "info",
                        "message": "✓ All chunks already have embeddings"
                    })
            else:
                await self._emit_progress({
                    "type": "log",
                    "level": "warning",
                    "message": "⚠️ OpenAI API key not configured - skipping embeddings"
                })
                logger.warning("OpenAI API key not configured, skipping embeddings")
            
            # Update repository metadata
            repo_meta_record.is_preprocessed = True
            repo_meta_record.preprocessing_status = "completed"
            repo_meta_record.file_count_processed = file_count
            repo_meta_record.total_chunks_created = total_chunks
            await self.db.commit()
            
            # Update project status
            project.status = ProjectStatus.COMPLETED
            await self.db.commit()
            
            logger.info(f"Preprocessing finished for project: {project_id}")
            
            # Emit completion event
            await self._emit_progress({
                "type": "completed",
                "status": "success",
                "files_processed": file_count,
                "chunks_created": total_chunks,
                "repository_type": repo_metadata["repository_type"]
            })
            
            return {
                "project_id": str(project_id),
                "files_processed": file_count,
                "chunks_created": total_chunks,
                "repository_type": repo_metadata["repository_type"],
                "status": "completed"
            }
        
        except Exception as e:
            logger.error(f"Error preprocessing project: {e}", exc_info=True)
            
            # Update project status to FAILED
            project.status = ProjectStatus.FAILED
            await self.db.commit()
            
            # Emit error event
            await self._emit_progress({
                "type": "error",
                "error": str(e)
            })
            
            raise
    
    async def _generate_embeddings(self, chunks: List[CodeChunkModel], batch_size: int = 20) -> int:
        """Generate embeddings for code chunks using OpenAI"""
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=60.0)
            count = 0
            await self._maybe_pause()
            
            # Emit progress: starting embeddings
            await self._emit_progress({
                "type": "log",
                "level": "info",
                "message": f"🔄 Starting embeddings generation for {len(chunks)} chunks using OpenAI API..."
            })
            
            # Process chunks in batches
            total_batches = (len(chunks) + batch_size - 1) // batch_size
            
            for batch_idx, i in enumerate(range(0, len(chunks), batch_size), 1):
                await self._maybe_pause()
                batch = chunks[i:i + batch_size]
                
                # Emit progress for this batch
                await self._emit_progress({
                    "type": "log",
                    "level": "info",
                    "message": f"⏳ Processing embedding batch {batch_idx}/{total_batches} ({len(batch)} chunks)..."
                })
                
                # Prepare texts for embedding
                texts = [
                    f"{chunk.name}\n{chunk.chunk_type}\n{chunk.docstring or ''}\n{chunk.content[:500]}"
                    for chunk in batch
                ]
                
                try:
                    # Get embeddings from OpenAI with timeout
                    await self._maybe_pause()
                    await self._emit_progress({
                        "type": "log",
                        "level": "info",
                        "message": f"📡 Calling OpenAI API for batch {batch_idx}..."
                    })
                    
                    try:
                        response = await asyncio.wait_for(
                            client.embeddings.create(
                                input=texts,
                                model="text-embedding-3-small"
                            ),
                            timeout=60.0  # 60 second timeout per batch
                        )
                    except asyncio.TimeoutError:
                        await self._emit_progress({
                            "type": "log",
                            "level": "warning",
                            "message": f"⚠️ Timeout waiting for OpenAI API response for batch {batch_idx}. Retrying..."
                        })
                        await self._maybe_pause()
                        # Retry once with timeout
                        response = await asyncio.wait_for(
                            client.embeddings.create(
                                input=texts,
                                model="text-embedding-3-small"
                            ),
                            timeout=60.0
                        )
                    
                    await self._maybe_pause()
                    
                    # Store embeddings
                    for idx, chunk in enumerate(batch):
                        if idx < len(response.data):
                            embedding = response.data[idx].embedding
                            chunk.embedding = embedding
                            chunk.embedding_model = "text-embedding-3-small"
                            count += 1
                    
                    await self.db.commit()
                    
                    # Record embedding usage for analysis (tokens + cost)
                    if self._progress and self._analysis_id and getattr(response, "usage", None):
                        total_tokens = getattr(response.usage, "total_tokens", 0) or 0
                        if total_tokens > 0:
                            await record_embedding_usage(
                                self._progress,
                                self._analysis_id,
                                total_tokens,
                                "text-embedding-3-small",
                            )
                    
                    # Emit progress for successful batch
                    await self._emit_progress({
                        "type": "log",
                        "level": "info",
                        "message": f"✓ Embedded batch {batch_idx}/{total_batches} - {count} embeddings created so far"
                    })
                    
                except asyncio.TimeoutError as e:
                    await self._register_embedding_failure(
                        f"⚠️ Timeout on batch {batch_idx}: {str(e)[:100]}. Skipping this batch."
                    )
                    logger.warning(f"Timeout generating embeddings for batch {batch_idx}: {e}")
                    continue
                except Exception as e:
                    await self._register_embedding_failure(
                        f"⚠️ Error on batch {batch_idx}: {str(e)[:100]}. Skipping this batch."
                    )
                    logger.warning(f"Error generating embeddings for batch {batch_idx}: {e}")
                    continue
            
            # Emit completion
            await self._emit_progress({
                "type": "log",
                "level": "info",
                "message": f"✅ Embeddings generation complete - {count} chunks embedded"
            })
            
            return count
        
        except ImportError:
            await self._emit_progress({
                "type": "log",
                "level": "warning",
                "message": "⚠️ OpenAI library not available - skipping embeddings"
            })
            logger.warning("OpenAI library not available")
            return 0
        except Exception as e:
            await self._emit_progress({
                "type": "log",
                "level": "error",
                "message": f"❌ Error in embedding generation: {str(e)[:200]}"
            })
            logger.error(f"Error in embedding generation: {e}", exc_info=True)
            return 0
    
    def _is_important_file(self, file_path: str, repo_metadata: Dict[str, Any]) -> bool:
        """Check if file is important"""
        entry_points = repo_metadata.get("entry_points", {})
        config_files = repo_metadata.get("config_files_list", [])
        
        return any(
            entry_point in file_path for entry_point in entry_points.values()
        ) or any(
            config_file in file_path for config_file in config_files
        )
    
    def _is_test_file(self, file_name: str) -> bool:
        """Check if file is a test file"""
        test_patterns = ["test_", "_test.", ".test.", ".spec."]
        return any(pattern in file_name for pattern in test_patterns)
    
    def _get_file_type(self, file_path: str) -> str:
        """Determine file type"""
        if self._is_test_file(file_path):
            return "test"
        
        name = file_path.lower()
        if any(config in name for config in ["package.json", "requirements.txt", "pom.xml", "setup.py"]):
            return "config"
        
        if name.endswith((".md", ".txt", ".rst")):
            return "documentation"
        
        return "code"
    
    def _count_lines(self, file_path: str) -> int:
        """Count lines in file"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return len(f.readlines())
        except Exception:
            return 0
    
    def _has_docstring(self, chunks: List[CodeChunk]) -> bool:
        """Check if any chunk has docstring"""
        return any(chunk.docstring for chunk in chunks)
