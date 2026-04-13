from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parents[2]
CHAT_STORE_PATH = BASE_DIR / "data" / "chat_sessions.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict[str, Any]:
    return {"sessions": []}


def _load_store() -> dict[str, Any]:
    if not CHAT_STORE_PATH.exists():
        return _empty_store()

    with CHAT_STORE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return _empty_store()
    if not isinstance(data.get("sessions"), list):
        data["sessions"] = []
    return data


def _save_store(store: dict[str, Any]) -> None:
    CHAT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHAT_STORE_PATH.open("w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def list_sessions() -> list[dict[str, Any]]:
    store = _load_store()
    sessions = store.get("sessions", [])
    ordered = sorted(
        sessions,
        key=lambda s: s.get("updated_at", ""),
        reverse=True,
    )
    return [
        {
            "session_id": session.get("session_id"),
            "title": session.get("title", "New Chat"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "message_count": len(session.get("messages", [])),
        }
        for session in ordered
    ]


def create_session(title: str | None = None) -> dict[str, Any]:
    store = _load_store()
    now = _now_iso()
    session = {
        "session_id": str(uuid4()),
        "title": title or "New Chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    store["sessions"].append(session)
    _save_store(store)
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    store = _load_store()
    for session in store.get("sessions", []):
        if session.get("session_id") == session_id:
            return session
    return None


def append_message(session_id: str, role: str, message_text: str) -> dict[str, Any]:
    store = _load_store()
    now = _now_iso()

    for session in store.get("sessions", []):
        if session.get("session_id") == session_id:
            session.setdefault("messages", []).append(
                {
                    "role": role,
                    "message_text": message_text,
                    "created_at": now,
                }
            )
            if session.get("title") in {None, "", "New Chat"} and role == "user":
                session["title"] = message_text[:60].strip() or "New Chat"
            session["updated_at"] = now
            _save_store(store)
            return session

    raise ValueError(f"Session '{session_id}' not found")
