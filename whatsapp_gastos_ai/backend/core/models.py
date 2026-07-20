from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class IncomingMessage:
    user_id: str
    channel: str
    message_type: str
    text: Optional[str] = None
    media_id: Optional[str] = None
    media_url: Optional[str] = None
    file_name: Optional[str] = None
    raw_payload: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResponse:
    text: Optional[str] = None
    response_type: str = "text"
    options: Optional[list[dict[str, Any]]] = None
    image_path: Optional[str] = None
    document_path: Optional[str] = None
    document_name: Optional[str] = None
    transfer_to_human: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionData:
    session_id: str
    channel: str
    user_id: str
    state: dict[str, Any] = field(default_factory=dict)
