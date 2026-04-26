"""Chat REST endpoint — wires the LLM orchestrator into FastAPI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.db.connection import DEFAULT_USER_ID
from app.llm import handle_chat_message


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


def create_chat_router() -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])

    @router.post("")
    async def post_chat(payload: ChatRequest) -> dict:
        result = await handle_chat_message(
            payload.message, user_id=DEFAULT_USER_ID
        )
        return result.model_dump()

    return router
