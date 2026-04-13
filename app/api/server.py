from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from app.analytics.db import engine
from app.chat.store import append_message, create_session, get_session, list_sessions
from app.llm.agent_orchestrator import answer_question
from app.preferences.store import load_preferences, save_preferences


HOST = "127.0.0.1"
PORT = 8000
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _overall_confidence(tool_outputs: list[dict[str, Any]]) -> str:
    confidences = [str(t.get("confidence", "")).lower() for t in tool_outputs]
    if not confidences:
        return "unknown"
    if "low" in confidences:
        return "low"
    if "medium" in confidences:
        return "medium"
    if all(c == "high" for c in confidences):
        return "high"
    return "unknown"


def _collect_quality_flags(tool_outputs: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for tool_output in tool_outputs:
        for flag in tool_output.get("quality_flags", []):
            if isinstance(flag, str) and flag not in seen:
                seen.add(flag)
                ordered.append(flag)
    return ordered


def _public_response(result: dict[str, Any], debug: bool) -> dict[str, Any]:
    tool_outputs = result.get("tool_outputs", [])
    response = {
        "answer": result.get("answer"),
        "confidence": _overall_confidence(tool_outputs),
        "selected_tools": result.get("selected_tools", []),
        "quality_flags": _collect_quality_flags(tool_outputs),
        "session_id": result.get("session_id"),
    }

    if result.get("answer") is None:
        response["message"] = (
            "LLM answer not generated. Send `call_llm: true` to return a final natural-language answer."
        )

    if debug:
        response["debug"] = {
            "user_query": result.get("user_query"),
            "available_tools": result.get("available_tools", []),
            "tool_outputs": tool_outputs,
            "prompt": result.get("prompt"),
            "preferences": result.get("preferences", {}),
            "conversation_history": result.get("conversation_history", []),
        }

    return response


def _value_or_none(df: pd.DataFrame, column: str) -> Any:
    if df.empty:
        return None
    value = df.iloc[0][column]
    return None if pd.isna(value) else value


def _format_date(value: Any) -> str | None:
    if value is None:
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return str(ts.date())


def _load_data_status() -> dict[str, Any]:
    workouts = pd.read_sql(text("SELECT COUNT(*) AS total_workouts FROM workouts"), engine)
    recovery_days = pd.read_sql(text("SELECT COUNT(*) AS total_recovery_days FROM apple_daily_recovery"), engine)
    strength_range = pd.read_sql(
        text("SELECT MIN(date) AS strength_start, MAX(date) AS strength_end FROM exercise_progress"),
        engine,
    )
    recovery_range = pd.read_sql(
        text("SELECT MIN(date) AS recovery_start, MAX(date) AS recovery_end FROM apple_daily_recovery"),
        engine,
    )
    latest_feature = pd.read_sql(
        text("SELECT MAX(date) AS latest_feature_date FROM daily_features"),
        engine,
    )

    return {
        "total_workouts": int(_value_or_none(workouts, "total_workouts") or 0),
        "total_recovery_days": int(_value_or_none(recovery_days, "total_recovery_days") or 0),
        "strength_data_date_range": {
            "start": _format_date(_value_or_none(strength_range, "strength_start")),
            "end": _format_date(_value_or_none(strength_range, "strength_end")),
        },
        "recovery_data_date_range": {
            "start": _format_date(_value_or_none(recovery_range, "recovery_start")),
            "end": _format_date(_value_or_none(recovery_range, "recovery_end")),
        },
        "latest_available_feature_date": _format_date(_value_or_none(latest_feature, "latest_feature_date")),
    }


class AgentAPIHandler(BaseHTTPRequestHandler):
    server_version = "HaiAgentAPI/0.1"

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}

        raw = self.rfile.read(content_length)
        if not raw:
            return {}

        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON") from exc

        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")

        return payload

    def _send_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self._send_json(
                {"error": "Not found", "path": str(file_path)},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        body = file_path.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html")
            return

        if self.path.startswith("/static/"):
            relative = self.path.removeprefix("/static/")
            self._send_file(STATIC_DIR / relative)
            return

        if self.path == "/health":
            self._send_json({"ok": True, "service": "agent-api"})
            return

        if self.path == "/preferences":
            self._send_json(load_preferences())
            return

        if self.path == "/data/status":
            try:
                self._send_json(_load_data_status())
            except Exception as exc:  # pragma: no cover
                self._send_json(
                    {"error": "Could not load data status", "detail": str(exc)},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if self.path == "/sessions":
            self._send_json({"sessions": list_sessions()})
            return

        if self.path.startswith("/sessions/"):
            session_id = self.path.removeprefix("/sessions/").strip()
            session = get_session(session_id)
            if session is None:
                self._send_json(
                    {"error": "Session not found", "session_id": session_id},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            self._send_json(session)
            return

        self._send_json(
            {"error": "Not found", "path": self.path},
            status=HTTPStatus.NOT_FOUND,
        )

    def do_POST(self) -> None:
        if self.path == "/preferences":
            try:
                payload = self._read_json_body()
                self._send_json(save_preferences(payload))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if self.path == "/sessions":
            try:
                payload = self._read_json_body()
                title = payload.get("title")
                if title is not None and not isinstance(title, str):
                    raise ValueError("`title` must be a string if provided")
                self._send_json(create_session(title=title.strip() if isinstance(title, str) else None))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if self.path != "/agent/query":
            self._send_json(
                {"error": "Not found", "path": self.path},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        try:
            payload = self._read_json_body()
            user_query = payload.get("user_query")
            if not isinstance(user_query, str) or not user_query.strip():
                raise ValueError("`user_query` must be a non-empty string")

            tool_params = payload.get("tool_params")
            if tool_params is not None and not isinstance(tool_params, dict):
                raise ValueError("`tool_params` must be an object if provided")

            metrics_context = payload.get("metrics_context", "")
            research_context = payload.get("research_context", "")
            call_llm = bool(payload.get("call_llm", False))
            debug = bool(payload.get("debug", False))
            session_id = payload.get("session_id")
            if session_id is not None and not isinstance(session_id, str):
                raise ValueError("`session_id` must be a string if provided")
            preferences = payload.get("preferences")
            if preferences is None:
                preferences = load_preferences()
            elif not isinstance(preferences, dict):
                raise ValueError("`preferences` must be an object if provided")

            if session_id:
                session = get_session(session_id)
                if session is None:
                    raise ValueError(f"Session '{session_id}' was not found")
            else:
                session = create_session()
                session_id = str(session["session_id"])

            conversation_history = session.get("messages", [])

            result = answer_question(
                user_query=user_query,
                tool_params=tool_params,
                metrics_context=metrics_context if isinstance(metrics_context, str) else "",
                research_context=research_context if isinstance(research_context, str) else "",
                preferences=preferences,
                conversation_history=conversation_history,
                call_llm=call_llm,
            )
            append_message(session_id, "user", user_query)
            assistant_message = str(result.get("answer") or result.get("message") or "").strip()
            if assistant_message:
                append_message(session_id, "assistant", assistant_message)
            result["session_id"] = session_id
            self._send_json(_public_response(result, debug=debug))
        except ValueError as exc:
            self._send_json(
                {"error": str(exc)},
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as exc:  # pragma: no cover
            self._send_json(
                {"error": "Internal server error", "detail": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(host: str = HOST, port: int = PORT) -> None:
    server = ThreadingHTTPServer((host, port), AgentAPIHandler)
    print(f"Serving agent API on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
