from fastapi import APIRouter

from api.schemas import (
	ChatMessageRequest,
	ChatMessageResponse,
	ConversationHistoryResponse,
)
from api.service import get_history, send_message

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/{conversation_id}/message", response_model=ChatMessageResponse)
def send_guest_message(
	conversation_id: str,
	payload: ChatMessageRequest,
) -> ChatMessageResponse:
	return send_message(conversation_id, payload)


@router.get("/{conversation_id}/history", response_model=ConversationHistoryResponse)
def get_conversation_history(conversation_id: str) -> ConversationHistoryResponse:
	return get_history(conversation_id)
