from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
	message: str = Field(..., min_length=1)


class MessageState(BaseModel):
	extracted_params: Optional[Dict[str, Any]] = None
	missing_fields: Optional[List[str]] = None
	final_response: Optional[str] = None


class ChatMessageResponse(BaseModel):
	conversation_id: str
	intent: Literal["search", "details", "book", "escalate"]
	assistant_response: str
	escalate: bool
	tool_result: Any
	state: MessageState
	timestamp: datetime


class ConversationMessage(BaseModel):
	role: Literal["user", "assistant", "system"]
	content: str
	timestamp: datetime


class HistorySummary(BaseModel):
	total_messages: int
	last_intent: Optional[Literal["search", "details", "book", "escalate"]] = None
	escalate: bool


class ConversationHistoryResponse(BaseModel):
	conversation_id: str
	messages: List[ConversationMessage]
	summary: HistorySummary
