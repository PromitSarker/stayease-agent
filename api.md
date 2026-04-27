# StayEase API Contract

## Purpose

This document defines the HTTP contract for chat-based guest interactions on top of the LangGraph workflow in the StayEase agent.

## Architecture Context

- State model: conversation state follows `AgentState` in `agent/state.py` with `messages`, `intent`, `extracted_params`, `missing_fields`, `tool_result`, `final_response`, and `escalate`.
- Orchestration: the graph in `agent/graph.py` routes from `classify_intent` to `execute_tool` or `escalate`, then `format_response`.
- Tool execution: data access happens through tools in `agent/tools.py`.

## Endpoint 1

### POST /api/chat/{conversation_id}/message

Send a guest message to the assistant and get a single assistant response for this turn.

### Path Params

- `conversation_id` (string, required): Stable identifier for one chat thread.

### Request Body Schema

```json
{
  "message": "string"
}
```

### Response Body Schema (200)

```json
{
  "conversation_id": "string",
  "intent": "search|details|book|escalate",
  "assistant_response": "string",
  "escalate": false,
  "tool_result": {},
  "state": {
    "extracted_params": {},
    "missing_fields": [],
    "final_response": "string"
  },
  "timestamp": "ISO-8601 string"
}
```

### Realistic Example (Bangladesh)

Request:

```json
{
  "message": "I need a stay in Cox's Bazar from 2026-12-10 to 2026-12-12 for 2 guests under 7000 BDT per night"
}
```

Response:

```json
{
  "conversation_id": "conv-bd-0001",
  "intent": "search",
  "assistant_response": "I found 2 options in Cox's Bazar within your plan. Sea View Cottage is 4,500 BDT/night and Laboni Beach House is 6,200 BDT/night.",
  "escalate": false,
  "tool_result": [
    {
      "id": 1,
      "name": "Sea View Cottage",
      "location": "Cox's Bazar",
      "price_per_night": 4500,
      "max_guests": 4,
      "amenities": ["WiFi", "AC", "Sea View"],
      "requested_check_in": "2026-12-10",
      "requested_check_out": "2026-12-12",
      "requested_guests": 2
    },
    {
      "id": 2,
      "name": "Laboni Beach House",
      "location": "Cox's Bazar",
      "price_per_night": 6200,
      "max_guests": 3,
      "amenities": ["Breakfast", "WiFi", "Balcony"],
      "requested_check_in": "2026-12-10",
      "requested_check_out": "2026-12-12",
      "requested_guests": 2
    }
  ],
  "state": {
    "extracted_params": {
      "location": "Cox's Bazar",
      "check_in": "2026-12-10",
      "check_out": "2026-12-12",
      "num_guests": 2
    },
    "missing_fields": [],
    "final_response": "I found 2 options in Cox's Bazar within your plan."
  },
  "timestamp": "2026-04-27T16:20:00Z"
}
```

### Possible Error Responses

- `400 Bad Request`

```json
{
  "error": "INVALID_INPUT",
  "message": "message is required and must be a non-empty string"
}
```

- `503 Service Unavailable`

```json
{
  "error": "DEPENDENCY_FAILURE",
  "message": "Could not process message right now"
}
```

## Endpoint 2

### GET /api/chat/{conversation_id}/history

Return full conversation history for the given chat thread in chronological order.

### Path Params

- `conversation_id` (string, required): Stable identifier for one chat thread.

### Response Body Schema (200)

```json
{
  "conversation_id": "string",
  "messages": [
    {
      "role": "user|assistant|system",
      "content": "string",
      "timestamp": "ISO-8601 string"
    }
  ],
  "summary": {
    "total_messages": 0,
    "last_intent": "search|details|book|escalate|null",
    "escalate": false
  }
}
```

### Realistic Example (Bangladesh)

Response:

```json
{
  "conversation_id": "conv-bd-0001",
  "messages": [
    {
      "role": "user",
      "content": "Need a room in Sylhet for 3 guests next weekend",
      "timestamp": "2026-04-27T16:00:00Z"
    },
    {
      "role": "assistant",
      "content": "Sure, please share your exact check-in and check-out dates so I can check availability and BDT pricing.",
      "timestamp": "2026-04-27T16:00:02Z"
    },
    {
      "role": "user",
      "content": "From 2026-05-08 to 2026-05-10, budget around 5000 BDT/night",
      "timestamp": "2026-04-27T16:00:20Z"
    },
    {
      "role": "assistant",
      "content": "I found a 4,800 BDT/night option in Sylhet for your dates.",
      "timestamp": "2026-04-27T16:00:23Z"
    }
  ],
  "summary": {
    "total_messages": 4,
    "last_intent": "search",
    "escalate": false
  }
}
```

### Possible Error Responses

- `404 Not Found`

```json
{
  "error": "CONVERSATION_NOT_FOUND",
  "message": "No history found for conversation_id conv-bd-0001"
}
```

- `500 Internal Server Error`

```json
{
  "error": "HISTORY_READ_FAILED",
  "message": "Could not load conversation history"
}
```

## HTTP Conventions

- `POST /message` is synchronous for one-turn processing.
- Client sends only one field in request body: `message`.
- `GET /history` is idempotent and read-only.
- Timestamps must be returned in UTC using ISO-8601.
- BDT amounts are represented as integer values (for example, 6200).

