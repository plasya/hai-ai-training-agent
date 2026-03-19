from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.llm.agent_orchestrator import answer_question


HOST = "127.0.0.1"
PORT = 8000


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
        }

    return response


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

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"ok": True, "service": "agent-api"})
            return

        self._send_json(
            {"error": "Not found", "path": self.path},
            status=HTTPStatus.NOT_FOUND,
        )

    def do_POST(self) -> None:
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

            result = answer_question(
                user_query=user_query,
                tool_params=tool_params,
                metrics_context=metrics_context if isinstance(metrics_context, str) else "",
                research_context=research_context if isinstance(research_context, str) else "",
                call_llm=call_llm,
            )
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
