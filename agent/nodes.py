import re
from datetime import date
from typing import Any, Dict, List, Optional

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from agent.config import GROQ_API_KEY, GROQ_MODEL
from agent.state import AgentState
from agent.tools import create_booking, get_listing_details, search_available_properties


# Tool-calling LLM — used by call_model_node to decide which tool to invoke
_LLM_WITH_TOOLS: Optional[Any] = None
# Plain LLM (no tools) — used by format_response_node to produce friendly text
_LLM_PLAIN: Optional[Any] = None


def _get_llm_with_tools():
	"""Return the tool-bound LLM, initialising it once."""
	global _LLM_WITH_TOOLS
	if _LLM_WITH_TOOLS is not None:
		return _LLM_WITH_TOOLS

	if not GROQ_API_KEY:
		print("WARNING: GROQ_API_KEY is not set.")
		return None

	try:
		base = ChatGroq(
			model=GROQ_MODEL,
			api_key=GROQ_API_KEY,
			temperature=0,
			max_retries=3,
			timeout=60.0,
		)
		tools = [search_available_properties, get_listing_details, create_booking]
		_LLM_WITH_TOOLS = base.bind_tools(tools)
		return _LLM_WITH_TOOLS
	except Exception as e:
		print(f"ERROR: Failed to initialise tool-calling LLM: {str(e)}")
		return None


def _get_plain_llm():
	"""Return a plain LLM (no tools bound) used only to generate friendly text."""
	global _LLM_PLAIN
	if _LLM_PLAIN is not None:
		return _LLM_PLAIN

	if not GROQ_API_KEY:
		print("WARNING: GROQ_API_KEY is not set.")
		return None

	try:
		_LLM_PLAIN = ChatGroq(
			model=GROQ_MODEL,
			api_key=GROQ_API_KEY,
			temperature=0,
			max_retries=3,
			timeout=60.0,
		)
		return _LLM_PLAIN
	except Exception as e:
		print(f"ERROR: Failed to initialise plain LLM: {str(e)}")
		return None


# System prompt 


_SYSTEM_PROMPT_TEMPLATE = """You are StayEase's friendly booking assistant for Bangladesh.
Today's date is {today} ({weekday}).

PERSONALITY:
- Warm, natural, and conversational (like a local friend).
- Avoid sounding like a database; be empathetic if results aren't found.

CORE RULES:
- You NEVER answer questions about property availability or listings from your own knowledge.
- You ALWAYS call the appropriate tool first, then base your answer ONLY on the tool's output.
- If a tool returns zero results, be polite and suggest alternatives (e.g. different area or dates).
- Do NOT hallucinate properties or options that the tool didn't confirm.

You handle exactly 3 things:
1. Search properties  → call search_available_properties
2. Property details   → call get_listing_details (use the numeric Property ID from search results)
3. Make a booking     → call create_booking (use the numeric Property ID from search results)

══════════════════════════════════════════════════════
DATE RULES
══════════════════════════════════════════════════════
- Always convert relative terms ("tomorrow", "next Friday", "this weekend") into actual
  YYYY-MM-DD dates using today's date above BEFORE calling any tool.
- If the user does not provide a check-out date, ask for it — never assume a 1-night stay.
- All dates passed to tools MUST be in YYYY-MM-DD format.
══════════════════════════════════════════════════════

══════════════════════════════════════════════════════
SEARCH RULES
══════════════════════════════════════════════════════
Before calling search_available_properties you MUST have ALL of the following:
  • location    — where the user wants to stay
  • check_in    — check-in date (YYYY-MM-DD)
  • check_out   — check-out date (YYYY-MM-DD)
  • num_guests  — number of guests (integer)
If ANY of these are missing, ask the user for them before calling the tool.
══════════════════════════════════════════════════════

══════════════════════════════════════════════════════
BOOKING RULES — READ CAREFULLY
══════════════════════════════════════════════════════
Before calling create_booking you MUST have ALL of the following from the user:
  • listing_id   — the numeric ID from a previous search result (never guess or make one up)
  • guest_name   — the guest's real full name (never use placeholders like "Your Name")
  • guest_phone  — the guest's real phone number (never use placeholders)
  • check_in     — check-in date in YYYY-MM-DD format
  • check_out    — check-out date in YYYY-MM-DD format
  • num_guests   — number of guests as an integer

If ANY of these are missing, DO NOT call create_booking.
Instead, ask the user for the missing information naturally, one or two items at a time.
Example: "To complete your booking, could I get your full name and phone number?"

NEVER call create_booking with placeholder text, example values, or assumed data.
NEVER call create_booking unless every field above has been explicitly provided by the user.
""".strip()

# Regex to strip raw <function=...>...</function> markup that some models
# include in their content text alongside structured tool_calls.
_FUNCTION_TAG_RE = re.compile(r"<function=[^>]+>.*?</function>", re.DOTALL)


def _build_system_prompt() -> str:
	"""Return the system prompt with today's real date injected."""
	today = date.today()
	return _SYSTEM_PROMPT_TEMPLATE.format(
		today=today.strftime("%Y-%m-%d"),
		weekday=today.strftime("%A"),
	)


def _clean_response(text: str) -> str:
	"""Strip any raw <function=...> markup the model may have leaked into content text."""
	return _FUNCTION_TAG_RE.sub("", text).strip()



# Graph nodes


def call_model_node(state: AgentState) -> Dict[str, Any]:
	"""Calls the LLM to decide on the next action (tool call or final response)."""
	llm = _get_llm_with_tools()

	if llm is None:
		return {
			"final_response": "The assistant is not available right now. Please try again later.",
			"escalate": True,
		}

	system_prompt = _build_system_prompt()
	messages = [SystemMessage(content=system_prompt)] + state.get("messages", [])

	try:
		response = llm.invoke(messages)

		# Strip any raw <function=...> markup the model may include in content text
		raw_content = str(getattr(response, "content", "")).strip()
		updates: Dict[str, Any] = {
			"messages": [response],
			"final_response": _clean_response(raw_content),
		}

		# Detect explicit escalation request
		lowered = updates["final_response"].lower()
		if any(phrase in lowered for phrase in ["human agent", "talk to a person", "connect you with a human"]):
			updates["escalate"] = True

		# Update intent metadata from tool calls
		if hasattr(response, "tool_calls") and response.tool_calls:
			tool_name = response.tool_calls[0]["name"]
			if "search" in tool_name:
				updates["intent"] = "search"
			elif "details" in tool_name:
				updates["intent"] = "details"
			elif "booking" in tool_name:
				updates["intent"] = "book"

		return updates

	except Exception as e:
		print(f"ERROR in call_model_node: {e}")
		return {
			"final_response": "I had trouble processing that. Can you try again?",
		}


def execute_tool_node(state: AgentState) -> Dict[str, Any]:
	"""Executes tool calls generated by the LLM and appends ToolMessages to state."""
	messages = state.get("messages", [])
	if not messages:
		return {}

	last_message = messages[-1]

	if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
		return {}

	tools_map = {
		"search_available_properties": search_available_properties,
		"get_listing_details": get_listing_details,
		"create_booking": create_booking,
	}

	new_messages: List[ToolMessage] = []
	# Keep only the first tool's result as the primary tool_result for the API
	primary_tool_result: Optional[str] = None

	for tool_call in last_message.tool_calls:
		tool_name = tool_call["name"]
		tool_args = tool_call["args"]
		tool_func = tools_map.get(tool_name)

		if tool_func:
			try:
				result = tool_func.invoke(tool_args)
				if primary_tool_result is None:
					primary_tool_result = result
				new_messages.append(
					ToolMessage(
						content=str(result),
						tool_call_id=tool_call["id"],
					)
				)
			except Exception as e:
				new_messages.append(
					ToolMessage(
						content=f"ERROR: Tool execution failed: {str(e)}",
						tool_call_id=tool_call["id"],
					)
				)

	updates: Dict[str, Any] = {"messages": new_messages}
	if primary_tool_result is not None:
		updates["tool_result"] = primary_tool_result

	return updates


def format_response_node(state: AgentState) -> Dict[str, Any]:
	"""Called after tool execution — uses a plain LLM to convert raw tool output into a friendly reply.

	Using a plain (non-tool-bound) LLM here is intentional: it cannot make further tool
	calls, so it is forced to produce a natural-language summary of the results.
	"""
	messages = state.get("messages", [])
	if not messages:
		return {}

	last_message = messages[-1]

	# Only proceed if the last message is a ToolMessage (i.e., a tool just ran)
	if not isinstance(last_message, ToolMessage):
		return {}

	# Use the plain LLM — no tools bound, so it can only output text
	llm = _get_plain_llm()
	if llm is None:
		return {"final_response": str(last_message.content)}

	all_messages = [SystemMessage(content=_build_system_prompt())] + messages

	try:
		response = llm.invoke(all_messages)
		final_text = str(getattr(response, "content", "")).strip()
		if not final_text:
			# Edge case: model returned empty content — fall back to raw tool output
			return {"final_response": str(last_message.content)}
		return {
			"messages": [response],
			"final_response": final_text,
		}
	except Exception as e:
		print(f"ERROR in format_response_node: {e}")
		return {"final_response": str(last_message.content)}


def escalate_to_human_node(state: AgentState) -> Dict[str, Any]:
	"""Hard handoff node — signals that a human agent should take over."""
	return {
		"escalate": True,
		"final_response": "I am connecting you to a human agent who can assist with this request.",
	}
