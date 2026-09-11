from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy.orm import Session

from models.database import Conversation, Message
from services.llm_service import llm

_SYSTEM_PROMPT = SystemMessage(
    content="You are a helpful AI assistant. Answer clearly and concisely."
)


def create_conversation(db: Session, user_id: int, title: str) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation | None:
    return (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )


def list_conversations(db: Session, user_id: int) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


def _save_message(db: Session, conversation_id: int, role: str, content: str) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def delete_conversation(db: Session, conversation: Conversation) -> None:
    db.delete(conversation)
    db.commit()


def chat(db: Session, conversation: Conversation, user_text: str) -> tuple[str, Message]:
    """
    Append the user turn to history, call the LLM with full context,
    persist the assistant reply, and return (reply_text, saved_message).
    """
    # Build LangChain message list from stored history
    history = [_SYSTEM_PROMPT]
    for msg in conversation.messages:
        if msg.role == "user":
            history.append(HumanMessage(content=msg.content))
        else:
            history.append(AIMessage(content=msg.content))
    history.append(HumanMessage(content=user_text))

    # Save user message before calling the LLM
    _save_message(db, conversation.id, "user", user_text)

    response = llm.invoke(history)
    reply = response.content

    saved = _save_message(db, conversation.id, "assistant", reply)

    # Bump conversation.updated_at
    db.query(Conversation).filter(Conversation.id == conversation.id).update(
        {"updated_at": saved.created_at}
    )
    db.commit()

    return reply, saved
