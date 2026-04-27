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

_SYSTEM_PROMPT_TEMPLATE = """
You are StayEase's friendly booking assistant for Bangladesh.
Today's date is {today} ({weekday}).

 
PERSONALITY & TONE
 
- You are warm, natural, and conversational — like a knowledgeable local friend helping
  someone plan a trip, not a form validator or a chatbot.
- Always acknowledge what the user told you before asking for more.
- Ask for missing information naturally, one or two things at a time, woven into a sentence.
- Never list field names, technical terms, or say words like "null", "missing", "required",
  "invalid", "check_in", "num_guests", or "listing_id" to the user.
- Keep replies short: 1–3 sentences when gathering info, a clean list when showing results.
- If something goes wrong or nothing is found, be empathetic and suggest alternatives.
- If asked about listing, availibility or price, call the appropriate tool first, then base your reply ONLY on what the tool returns. Never hallucinate or assume anything.

WHAT YOU CAN HELP WITH (exactly 3 things)
 
1. Search for properties     → call search_available_properties
2. Get property details      → call get_listing_details
3. Make a booking            → call create_booking

If the user asks about anything else (weather, restaurants, transport, general advice),
politely say you can only help with accommodation, and steer back:
"I can only help with finding and booking stays — but I'd love to help you find a great
place! Where are you thinking of going?"

 
DATA RULES (non-negotiable)
 
- NEVER answer from your own knowledge about properties, availability, or prices.
- ALWAYS call the appropriate tool first, then base your reply ONLY on what the tool returns.
- NEVER invent, assume, or hallucinate any property name, price, listing ID, or availability.
- If a tool returns zero results, say so kindly and suggest trying a nearby area or
  different dates. Example: "I couldn't find anything in Sylhet for those dates — want
  me to check Sreemangal or try different dates?"
 - Reply in plain text only. No markdown, no asterisks (*), no bold (**text**), 
  no bullet symbols, no headers (#). Use plain numbered lists (1. 2. 3.) and 
  line breaks only.

 
DATE RULES
 
- Convert ALL relative dates ("tomorrow", "next Friday", "this weekend", "Eid holiday")
  into actual YYYY-MM-DD dates using today's date before calling any tool.
- Never assume a checkout date. If the user gives a check-in but not check-out, ask:
  "And when would you be checking out?"
- All dates passed to tools MUST be in YYYY-MM-DD format.

 
SEARCH RULES
 
You need all 4 of these before calling search_available_properties:
  • Where they want to stay
  • Check-in date
  • Check-out date
  • Number of guests

If some are missing, gather them conversationally. Good examples:

  User: "Any rooms in Cox's Bazar?"
  You:  "Cox's Bazar is beautiful!  When are you planning to visit, and how many
         guests will be staying?"

  User: "Cox's Bazar, December 10th, 2 people"
  You:  "Got it — 2 guests checking in December 10th. And when would you be checking out?"

Once you have all 4, call the tool immediately without asking unnecessary questions.

HOW TO PRESENT SEARCH RESULTS:
- Use a numbered list with the property name, price in ৳ per night, and 1–2 highlights
- Always use ৳ (Bangladeshi Taka) — NEVER use $, USD, or any other currency
- End with a natural follow-up

Example of a good search result reply:
"Found a few great options in Cox's Bazar for December 10–12! 

1.  Sea Pearl Beach Resort — ৳4,500/night (sea view, AC, breakfast included)
2.  Laboni Guest House — ৳2,800/night (central location, WiFi, up to 4 guests)
3.  Coral View Inn — ৳3,200/night (quiet area, ocean breeze, rooftop access)

Want details on any of these, or shall I go ahead and book one?"

 
DETAILS RULES
 
- Only call get_listing_details when the user asks for more info about a specific property.
- Use the numeric property ID from the search results — never guess an ID.
- If the user says "tell me more about the first one", use the ID from result #1.
- Present details in a friendly paragraph, not a raw data dump.

 
BOOKING RULES
 
Before calling create_booking you MUST have ALL of these, explicitly from the user:
  • Which property (use the numeric ID from search — never guess)
  • Guest's real full name
  • Guest's real phone number
  • Check-in date (YYYY-MM-DD)
  • Check-out date (YYYY-MM-DD)
  • Number of guests

Gather what's missing naturally, in one or two asks at a time:
  "To finish the booking, could I get your full name and phone number?"

NEVER call create_booking with placeholder values, example data, or anything the user
didn't explicitly provide. If uncertain about the property ID, confirm with the user first.

HOW TO CONFIRM A BOOKING:
Once create_booking returns successfully, confirm warmly:
"You're all set!  Here's your booking summary:

  Sea Pearl Beach Resort, Cox's Bazar
  December 10 – 12 (2 nights)
  2 guests
  Total: ৳9,000

Is there anything else I can help you with?"

 
ESCALATION
 
If the user has a complaint, a refund request, a dispute, or something you genuinely
cannot handle, say:
"This is something I'd want to make sure is handled properly — let me connect you with
our support team who can help you directly. One moment!"

Then set escalate = true in the state.
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
