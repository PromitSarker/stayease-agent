from typing import Any, Dict, List, Optional
from typing_extensions import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
	conversation_id: str
	# add_messages reducer: new messages are appended, not overwritten
	messages: Annotated[List[BaseMessage], add_messages]
	intent: Optional[str]
	extracted_params: Optional[Dict[str, Any]]
	missing_fields: Optional[List[str]]
	tool_result: Optional[Any]
	final_response: Optional[str]
	escalate: bool
