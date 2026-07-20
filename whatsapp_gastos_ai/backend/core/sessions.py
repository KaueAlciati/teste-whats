from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from backend.core.models import SessionData


def build_session_id(channel: str, user_id: str) -> str:
    return f"{channel}:{user_id}"


@dataclass
class SessionStore:
    _sessions: dict[str, SessionData] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)
    _max_history_items: int = 20

    def get(self, channel: str, user_id: str) -> SessionData:
        session_id = build_session_id(channel, user_id)
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = SessionData(session_id=session_id, channel=channel, user_id=user_id)
                self._sessions[session_id] = session
            return session

    def update_state(self, channel: str, user_id: str, **kwargs: Any) -> SessionData:
        session = self.get(channel, user_id)
        session.state.update(kwargs)
        return session

    def reset(self, channel: str, user_id: str) -> None:
        session_id = build_session_id(channel, user_id)
        with self._lock:
            self._sessions.pop(session_id, None)

    def remove(self, channel: str, user_id: str) -> None:
        self.reset(channel, user_id)

    def clear_history(self, channel: str, user_id: str) -> None:
        session = self.get(channel, user_id)
        session.state["history"] = []
        session.state["current_intent"] = None
        session.state["collected_data"] = {}
        session.state["history_loaded"] = False

    def set_current_intent(self, channel: str, user_id: str, intent: str | None) -> None:
        session = self.get(channel, user_id)
        session.state["current_intent"] = intent

    def append_history(
        self,
        channel: str,
        user_id: str,
        *,
        role: str,
        content: str,
        message_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        session = self.get(channel, user_id)
        history = session.state.setdefault("history", [])
        history.append(
            {
                "role": role,
                "content": content,
                "message_type": message_type,
                "metadata": metadata or {},
            }
        )
        if len(history) > self._max_history_items:
            del history[:-self._max_history_items]

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                session_id: {
                    "channel": session.channel,
                    "user_id": session.user_id,
                    "state": dict(session.state),
                }
                for session_id, session in self._sessions.items()
            }


session_store = SessionStore()
