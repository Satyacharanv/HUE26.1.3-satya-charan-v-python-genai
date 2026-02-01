"""WebSocket endpoints for real-time analysis progress streaming"""
import json
import logging
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.project import Project
from src.models.analysis import Analysis
from src.services.analysis_progress import AnalysisProgressService
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws/analysis", tags=["websocket"])


class ConnectionManager:
    """Manage WebSocket connections for analysis progress"""
    
    def __init__(self):
        # Store active connections: {analysis_id: [websocket1, websocket2, ...]}
        self.active_connections: dict[UUID, list[WebSocket]] = {}
    
    async def connect(self, analysis_id: UUID, websocket: WebSocket):
        """Register a new WebSocket connection"""
        await websocket.accept()
        if analysis_id not in self.active_connections:
            self.active_connections[analysis_id] = []
        self.active_connections[analysis_id].append(websocket)
        logger.info(f"Client connected to analysis {analysis_id}")
    
    async def disconnect(self, analysis_id: UUID, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if analysis_id in self.active_connections:
            self.active_connections[analysis_id].remove(websocket)
            if not self.active_connections[analysis_id]:
                del self.active_connections[analysis_id]
        logger.info(f"Client disconnected from analysis {analysis_id}")
    
    async def broadcast(self, analysis_id: UUID, message: dict):
        """Send message to all connected clients for an analysis"""
        if analysis_id in self.active_connections:
            disconnected = []
            for websocket in self.active_connections[analysis_id]:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to websocket: {e}")
                    disconnected.append(websocket)
            
            # Clean up disconnected clients
            for websocket in disconnected:
                await self.disconnect(analysis_id, websocket)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to a specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")


manager = ConnectionManager()


@router.websocket("/{analysis_id}")
async def websocket_analysis_progress(
    websocket: WebSocket,
    analysis_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time analysis progress
    
    Client can:
    - Receive progress updates
    - Send pause/resume commands
    - Send user context additions
    
    Message format:
    {
        "type": "progress" | "log" | "command_response" | "error",
        "data": {...}
    }
    """
    
    try:
        analysis_uuid = UUID(analysis_id)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Verify analysis exists
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_uuid)
    )
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    await manager.connect(analysis_uuid, websocket)
    progress_service = AnalysisProgressService(db)
    
    try:
        # Send current state to newly connected client
        await websocket.send_json({
            "type": "initial_state",
            "data": {
                "analysis_id": str(analysis.id),
                "status": analysis.status.value,
                "stage": analysis.current_stage.value if analysis.current_stage else None,
                "progress": {
                    "files": f"{analysis.processed_files}/{analysis.total_files}",
                    "chunks": f"{analysis.processed_chunks}/{analysis.total_chunks}",
                    "percentage": (analysis.processed_files / analysis.total_files * 100) if analysis.total_files > 0 else 0
                },
                "tokens": {
                    "used": analysis.total_tokens_used,
                    "estimated_cost": analysis.estimated_cost
                }
            }
        })
        
        # Listen for client commands
        while True:
            data = await websocket.receive_json()
            
            command_type = data.get("type")
            command_data = data.get("data", {})
            
            logger.info(f"Received command: {command_type} for analysis {analysis_id}")
            
            if command_type == "pause":
                await progress_service.pause_analysis(analysis_uuid)
                await manager.broadcast(analysis_uuid, {
                    "type": "command_response",
                    "data": {
                        "command": "pause",
                        "status": "success",
                        "message": "Analysis paused"
                    }
                })
            
            elif command_type == "resume":
                await progress_service.resume_analysis(analysis_uuid)
                await manager.broadcast(analysis_uuid, {
                    "type": "command_response",
                    "data": {
                        "command": "resume",
                        "status": "success",
                        "message": "Analysis resumed"
                    }
                })
            
            elif command_type == "add_context":
                context = command_data.get("context", {})
                await progress_service.add_user_context(analysis_uuid, context)
                text = context.get("text") or context.get("instruction")
                scope = context.get("scope") or "global"
                if text:
                    await progress_service.add_interaction(
                        analysis_id=analysis_uuid,
                        kind="context",
                        content=text,
                        scope=scope
                    )
                await manager.broadcast(analysis_uuid, {
                    "type": "command_response",
                    "data": {
                        "command": "add_context",
                        "status": "success",
                        "message": "Context added to analysis"
                    }
                })
            
            elif command_type == "heartbeat":
                # Keep connection alive
                await websocket.send_json({
                    "type": "heartbeat",
                    "data": {"status": "alive"}
                })
            
            else:
                logger.warning(f"Unknown command type: {command_type}")
    
    except WebSocketDisconnect:
        await manager.disconnect(analysis_uuid, websocket)
        logger.info(f"WebSocket disconnected for analysis {analysis_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(analysis_uuid, websocket)


# Public function to broadcast progress updates (called from analysis pipeline)
async def broadcast_progress(
    analysis_id: UUID,
    stage: str,
    message: str,
    current_file: str = None,
    file_index: int = None,
    total_files: int = None,
    processed_chunks: int = None,
    total_chunks: int = None,
    tokens_used: int = None,
    estimated_cost: float = None,
    level: str = "info"
):
    """Broadcast progress update to all connected clients"""
    
    progress_percentage = None
    if total_files and file_index is not None:
        progress_percentage = (file_index / total_files) * 100
    
    await manager.broadcast(analysis_id, {
        "type": "progress",
        "data": {
            "stage": stage,
            "message": message,
            "current_file": current_file,
            "file_index": file_index,
            "total_files": total_files,
            "progress_percentage": progress_percentage,
            "tokens_used": tokens_used,
            "estimated_cost": estimated_cost,
            "level": level
        }
    })


# Public function to broadcast log events
async def broadcast_log(
    analysis_id: UUID,
    level: str,
    message: str,
    **kwargs
):
    """Broadcast log event to all connected clients"""
    
    await manager.broadcast(analysis_id, {
        "type": "log",
        "data": {
            "level": level,
            "message": message,
            **kwargs
        }
    })
