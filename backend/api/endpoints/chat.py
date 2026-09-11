from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from api.endpoints.auth import get_current_user
from core.database import get_db
from core.rate_limit import limiter
from models.database import User
from models.schemas import (
    ChatMessageRequest,
    ChatReply,
    ConversationResponse,
    ConversationSummary,
)
from services.chat_service import chat, create_conversation, delete_conversation, get_conversation, list_conversations

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/", response_model=ChatReply, summary="Start a new conversation")
@limiter.limit("20/minute")
def start_conversation(
    request: Request,
    body: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    title = body.title or body.message[:60]
    conv = create_conversation(db, current_user.id, title)
    reply, saved = chat(db, conv, body.message)
    return ChatReply(conversation_id=conv.id, message_id=saved.id, reply=reply)


@router.post("/{conversation_id}", response_model=ChatReply, summary="Continue a conversation")
@limiter.limit("20/minute")
def continue_conversation(
    request: Request,
    conversation_id: int,
    body: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = get_conversation(db, current_user.id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    reply, saved = chat(db, conv, body.message)
    return ChatReply(conversation_id=conv.id, message_id=saved.id, reply=reply)


@router.get("/", response_model=List[ConversationSummary], summary="List all conversations")
def get_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_conversations(db, current_user.id)


@router.delete("/{conversation_id}", status_code=204, summary="Delete a conversation and its messages")
def delete_conversation_endpoint(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = get_conversation(db, current_user.id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    delete_conversation(db, conv)


@router.get("/{conversation_id}", response_model=ConversationResponse, summary="Get full conversation with messages")
def get_conversation_detail(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = get_conversation(db, current_user.id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv
