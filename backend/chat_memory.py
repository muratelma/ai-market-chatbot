"""
Lightweight in-memory conversation session storage.

Keeps enough context per session to merge short follow-up messages with
the previous query so that the user does not have to repeat themselves
after a clarification question.

Design
------
* Plain ``dict`` — no database, no Redis.
* Sessions auto-expire after ``SESSION_TTL_SECONDS`` of inactivity.
* Lazy cleanup: stale sessions are purged on the next access.
* Thread-safe enough for a single-process uvicorn (GIL-protected dict ops).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 30 * 60  # 30 minutes
MAX_FOLLOW_UP_WORDS = 5
MAX_FOLLOW_UP_CHARS = 40


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    session_id: str
    last_user_query: str | None = None
    last_normalized_query: str | None = None
    last_parsed_query: dict | None = None
    pending_clarification: bool = False
    last_constraints: dict | None = None
    updated_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_sessions: dict[str, SessionState] = {}


def _cleanup_expired() -> None:
    """Remove sessions older than ``SESSION_TTL_SECONDS``."""
    now = time.time()
    expired_ids = [
        sid for sid, s in _sessions.items()
        if now - s.updated_at > SESSION_TTL_SECONDS
    ]
    for sid in expired_ids:
        del _sessions[sid]

    if expired_ids:
        logger.debug("Cleaned up %d expired sessions.", len(expired_ids))


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_or_create_session(session_id: str | None) -> SessionState:
    """
    Return an existing session or create a new one.

    If *session_id* is ``None`` or empty, a fresh UUID-based session is
    created so the system still works without frontend session support.
    """
    _cleanup_expired()

    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id in _sessions:
        session = _sessions[session_id]
        session.updated_at = time.time()
        return session

    session = SessionState(session_id=session_id)
    _sessions[session_id] = session
    return session


def _is_likely_follow_up(message: str) -> bool:
    """
    Heuristic: a message is probably a follow-up to a clarification
    question when it is short (few words / few chars).
    """
    words = message.strip().split()
    return (
        len(words) <= MAX_FOLLOW_UP_WORDS
        or len(message.strip()) <= MAX_FOLLOW_UP_CHARS
    )


def resolve_follow_up(
    user_message: str,
    session: SessionState,
) -> str:
    """
    If the session has a pending clarification and the new message looks
    like a short follow-up, combine it with the previous context.

    Returns the effective query to feed into the normalizer.
    """
    if not session.pending_clarification:
        return user_message

    if not session.last_user_query:
        return user_message

    if not _is_likely_follow_up(user_message):
        # Long / explicit message → treat as a new search, not a follow-up
        return user_message

    combined = f"{session.last_user_query} {user_message.strip()}"
    logger.info(
        "Follow-up detected. Merged: '%s' + '%s' → '%s'",
        session.last_user_query,
        user_message,
        combined,
    )
    return combined


def update_session(
    session: SessionState,
    *,
    user_query: str | None = None,
    normalized_query: str | None = None,
    parsed_query: dict | None = None,
    pending_clarification: bool = False,
    constraints: dict | None = None,
) -> None:
    """Persist state after a request completes."""
    if user_query is not None:
        session.last_user_query = user_query
    if normalized_query is not None:
        session.last_normalized_query = normalized_query
    if parsed_query is not None:
        session.last_parsed_query = parsed_query
    session.pending_clarification = pending_clarification
    if constraints is not None:
        session.last_constraints = constraints
    session.updated_at = time.time()
