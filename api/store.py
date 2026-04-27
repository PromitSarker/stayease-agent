from typing import List, Optional

from psycopg2.extras import RealDictCursor

from agent.db import get_connection
from api.schemas import ConversationMessage


class ConversationStore:
	"""PostgreSQL-backed store for chat history and conversation metadata."""

	_EXISTS_QUERY = """
		SELECT 1
		FROM conversations
		WHERE conversation_id = %s
		LIMIT 1
	"""

	_MESSAGES_QUERY = """
		SELECT role, content, created_at
		FROM conversations
		WHERE conversation_id = %s
		ORDER BY created_at ASC, id ASC
	"""

	_INSERT_QUERY = """
		INSERT INTO conversations (
			conversation_id,
			role,
			content,
			intent,
			escalate,
			created_at
		)
		VALUES (%s, %s, %s, %s, %s, %s)
	"""

	_LAST_INTENT_QUERY = """
		SELECT intent
		FROM conversations
		WHERE conversation_id = %s
			AND intent IS NOT NULL
		ORDER BY created_at DESC, id DESC
		LIMIT 1
	"""

	_LAST_ESCALATE_QUERY = """
		SELECT escalate
		FROM conversations
		WHERE conversation_id = %s
		ORDER BY created_at DESC, id DESC
		LIMIT 1
	"""

	def exists(self, conversation_id: str) -> bool:
		with get_connection() as conn:
			with conn.cursor() as cur:
				cur.execute(self._EXISTS_QUERY, (conversation_id,))
				return cur.fetchone() is not None

	def get_messages(self, conversation_id: str) -> List[ConversationMessage]:
		with get_connection() as conn:
			with conn.cursor(cursor_factory=RealDictCursor) as cur:
				cur.execute(self._MESSAGES_QUERY, (conversation_id,))
				rows = cur.fetchall()

		return [
			ConversationMessage(
				role=row["role"],
				content=row["content"],
				timestamp=row["created_at"],
			)
			for row in rows
		]

	def append(
		self,
		conversation_id: str,
		message: ConversationMessage,
		intent: Optional[str] = None,
		escalate: bool = False,
	) -> None:
		with get_connection() as conn:
			with conn.cursor() as cur:
				cur.execute(
					self._INSERT_QUERY,
					(
						conversation_id,
						message.role,
						message.content,
						intent,
						escalate,
						message.timestamp,
					),
				)
			conn.commit()

	def get_last_intent(self, conversation_id: str) -> Optional[str]:
		with get_connection() as conn:
			with conn.cursor(cursor_factory=RealDictCursor) as cur:
				cur.execute(self._LAST_INTENT_QUERY, (conversation_id,))
				row = cur.fetchone()

		if not row:
			return None

		intent = row.get("intent")
		return str(intent) if intent is not None else None

	def get_escalate(self, conversation_id: str) -> bool:
		with get_connection() as conn:
			with conn.cursor(cursor_factory=RealDictCursor) as cur:
				cur.execute(self._LAST_ESCALATE_QUERY, (conversation_id,))
				row = cur.fetchone()

		if not row:
			return False

		return bool(row.get("escalate", False))


conversation_store = ConversationStore()
