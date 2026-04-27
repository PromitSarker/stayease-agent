from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
	conversation_id: str
	messages: List[BaseMessage]
	intent: Optional[str]
	extracted_params: Optional[Dict[str, Any]]
	missing_fields: Optional[List[str]]
	tool_result: Optional[Any]
	final_response: Optional[str]
	escalate: bool
