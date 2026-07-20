from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Optional

from backend.core.models import SessionData


def build_session_id(channel: str, user_id: str) -> str:
    return f"{channel}:{user_id}"


@dataclass
class SessionStore:
    _sessions: dict[str, SessionData] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

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
