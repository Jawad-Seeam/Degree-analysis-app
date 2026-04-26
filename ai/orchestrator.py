import uuid
import re
from typing import Any, Dict, List, Tuple

from ai.mcp_client import MCPClient, MCPClientError
from core.config import get_mcp_settings


SAFE_FALLBACK_REPLY = "I could not complete tool execution right now. Please retry, or continue with manual/CSV input."


class MCPGuardrailError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_DEFAULT_TOOL_SCHEMA: Dict[str, Dict[str, Any]] = {
    "transcript_lookup": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "user_id": {"type": "string"}},
        "required": ["query"],
    },
    "degree_audit_hint": {
        "type": "object",
        "properties": {"program": {"type": "string"}, "course_code": {"type": "string"}},
        "required": ["program", "course_code"],
    },
}


def _validate_args(tool: str, arguments: Dict[str, Any], schema_map: Dict[str, Dict[str, Any]]):
    if tool not in schema_map:
        raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"No schema configured for tool '{tool}'")

    schema = schema_map[tool] or {}
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    required = schema.get("required", []) if isinstance(schema, dict) else []
    if not isinstance(properties, dict):
        properties = {}
    if not isinstance(required, list):
        required = []

    for key in required:
        if key not in arguments:
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Missing argument '{key}'")

    for key, value in arguments.items():
        if key not in properties:
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Unexpected argument '{key}'")
        expected_type = str((properties.get(key) or {}).get("type", "")).strip().lower()
        if expected_type == "string" and not isinstance(value, str):
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Argument '{key}' must be string")
        if expected_type == "number" and not isinstance(value, (int, float)):
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Argument '{key}' must be number")
        if expected_type == "integer" and not isinstance(value, int):
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Argument '{key}' must be integer")
        if expected_type == "boolean" and not isinstance(value, bool):
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Argument '{key}' must be boolean")
        if expected_type == "object" and not isinstance(value, dict):
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Argument '{key}' must be object")
        if expected_type == "array" and not isinstance(value, list):
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", f"Argument '{key}' must be array")


def _should_use_tool(message: str) -> Tuple[str, Dict[str, Any]]:
    lowered = (message or "").lower()
    if "lookup" in lowered or "find" in lowered:
        hit = re.search(r"\b([A-Za-z]{2,4}\s?\d{3}[A-Za-z]?)\b", message or "")
        if hit:
            query = re.sub(r"\s+", "", hit.group(1)).upper()
        else:
            query = (message or "").strip()
        return "transcript_lookup", {"query": query}
    if "audit" in lowered and "course" in lowered:
        return "degree_audit_hint", {"program": "CSE", "course_code": "CSE115"}
    return "", {}


def _format_plain_reply(message: str) -> str:
    # TODO: Replace with real LLM provider call using MODEL_API_KEY / MODEL_NAME.
    return f"Assistant reply: {message.strip()}"


def _format_tool_reply(tool_name: str, payload: Dict[str, Any]) -> str:
    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    if not isinstance(result, dict):
        return f"Tool '{tool_name}' executed successfully."

    if tool_name == "transcript_lookup":
        query = str(result.get("query", "")).strip() or "(empty query)"
        matches = result.get("matches", [])
        rows = result.get("rows", [])
        from_transcript = bool(result.get("from_transcript", False))
        if isinstance(matches, list):
            cleaned = [str(item).strip() for item in matches if str(item).strip()]
        else:
            cleaned = []
        source_label = "your transcript" if from_transcript else "demo catalog"
        if cleaned:
            if isinstance(rows, list) and rows:
                detail_chunks = []
                for row in rows[:6]:
                    if not isinstance(row, dict):
                        continue
                    code = str(row.get("course_code", "")).strip() or "-"
                    grade = str(row.get("grade", "")).strip() or "-"
                    semester = str(row.get("semester", "")).strip() or "-"
                    detail_chunks.append(f"{code} ({grade}, {semester})")
                if detail_chunks:
                    return f"Transcript lookup in {source_label} for '{query}': " + "; ".join(detail_chunks)
            return f"Transcript lookup in {source_label} for '{query}': {', '.join(cleaned)}"
        return f"Transcript lookup in {source_label} for '{query}': no matching courses found."

    if tool_name == "degree_audit_hint":
        program = str(result.get("program", "")).strip() or "Unknown"
        course_code = str(result.get("course_code", "")).strip() or "Unknown"
        hint = str(result.get("hint", "")).strip()
        if hint:
            return f"Audit hint for {program} {course_code}: {hint}"
        return f"Audit hint generated for {program} {course_code}."

    return f"Tool '{tool_name}' executed successfully."


def build_orchestrator() -> "AIOrchestrator":
    cfg = get_mcp_settings()
    client = MCPClient(cfg.mcp_server_url, timeout_seconds=cfg.mcp_timeout_seconds)
    return AIOrchestrator(client=client, settings=cfg)


class AIOrchestrator:
    def __init__(self, client: MCPClient, settings):
        self.client = client
        self.settings = settings
        self.tool_schemas = self._load_tool_schemas()

    def _load_tool_schemas(self) -> Dict[str, Dict[str, Any]]:
        try:
            if not hasattr(self.client, "get_tool_schemas"):
                return dict(_DEFAULT_TOOL_SCHEMA)
            discovered = self.client.get_tool_schemas()
            if isinstance(discovered, dict) and discovered:
                return discovered
        except Exception:
            pass
        return dict(_DEFAULT_TOOL_SCHEMA)

    def chat(self, message: str, user_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        trace: List[Dict[str, Any]] = []
        tool_calls = 0

        tool_name, tool_args = _should_use_tool(message)
        if not tool_name:
            return {
                "reply": _format_plain_reply(message),
                "tool_trace": trace,
                "request_id": request_id,
                "fallback_used": False,
            }

        if tool_name == "transcript_lookup" and isinstance(user_id, str) and user_id.strip():
            tool_args = {**tool_args, "user_id": user_id.strip()}

        self._assert_tool_allowed(tool_name)
        _validate_args(tool_name, tool_args, self.tool_schemas)

        if tool_calls >= self.settings.mcp_max_tool_calls:
            raise MCPGuardrailError("TOOL_VALIDATION_ERROR", "Max tool calls exceeded")

        retries = 1
        last_error = None
        for attempt in range(retries + 1):
            try:
                tool_calls += 1
                result = self.client.call_tool(tool_name, tool_args, request_id=request_id)
                trace.append({"tool": tool_name, "status": "ok", "latency_ms": result.get("latency_ms", 0)})
                reply = _format_tool_reply(tool_name, result)
                return {"reply": reply, "tool_trace": trace, "request_id": request_id, "fallback_used": False}
            except MCPClientError as exc:
                last_error = exc
                trace.append({"tool": tool_name, "status": "error", "latency_ms": 0})
                if exc.code in {"TOOL_TIMEOUT", "TOOL_EXECUTION_ERROR"} and attempt < retries:
                    continue
                break

        return {
            "reply": SAFE_FALLBACK_REPLY,
            "tool_trace": trace,
            "request_id": request_id,
            "fallback_used": True,
            "error_code": (last_error.code if last_error else "TOOL_EXECUTION_ERROR"),
        }

    def test_tool(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        self._assert_tool_allowed(tool)
        _validate_args(tool, arguments, self.tool_schemas)
        result = self.client.call_tool(tool, arguments, request_id=request_id)
        return {
            "ok": True,
            "tool": tool,
            "latency_ms": result.get("latency_ms", 0),
            "result": result.get("result", {}),
            "request_id": request_id,
        }

    def _assert_tool_allowed(self, tool_name: str):
        if self.settings.mcp_tool_allowlist and tool_name not in self.settings.mcp_tool_allowlist:
            raise MCPGuardrailError("TOOL_NOT_ALLOWED", f"Tool '{tool_name}' is not allowlisted")
