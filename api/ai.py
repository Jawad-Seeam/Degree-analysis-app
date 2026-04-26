from flask import Blueprint, jsonify, request
from flask_login import current_user

from ai.mcp_client import MCPClientError
from ai.orchestrator import MCPGuardrailError, build_orchestrator


ai_bp = Blueprint("ai_api", __name__)


def _error_response(code: str, message: str, status: int):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


@ai_bp.route("/api/ai/chat", methods=["POST"])
def api_ai_chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if current_user.is_authenticated:
        user_id = str(current_user.id)
    else:
        user_id = str(payload.get("user_id", "")).strip() or "anonymous"
    context = payload.get("context", {})

    if not message:
        return _error_response("TOOL_VALIDATION_ERROR", "message is required", 400)
    if not isinstance(context, dict):
        return _error_response("TOOL_VALIDATION_ERROR", "context must be an object", 400)

    orchestrator = build_orchestrator()
    try:
        result = orchestrator.chat(message=message, user_id=user_id, context=context)
        return jsonify(
            {
                "reply": result["reply"],
                "tool_trace": result.get("tool_trace", []),
                "request_id": result["request_id"],
                "fallback_used": bool(result.get("fallback_used", False)),
            }
        )
    except MCPGuardrailError as exc:
        status = 403 if exc.code == "TOOL_NOT_ALLOWED" else 400
        return _error_response(exc.code, exc.message, status)
    except MCPClientError as exc:
        status = 504 if exc.code == "TOOL_TIMEOUT" else 502
        return _error_response(exc.code, exc.message, status)
    except Exception:
        return _error_response("TOOL_EXECUTION_ERROR", "Unexpected backend error", 500)


@ai_bp.route("/api/ai/tools/test", methods=["POST"])
def api_ai_tool_test():
    payload = request.get_json(silent=True) or {}
    tool = str(payload.get("tool", "")).strip()
    arguments = payload.get("arguments", {})

    if not tool:
        return _error_response("TOOL_VALIDATION_ERROR", "tool is required", 400)
    if not isinstance(arguments, dict):
        return _error_response("TOOL_VALIDATION_ERROR", "arguments must be an object", 400)

    orchestrator = build_orchestrator()
    try:
        result = orchestrator.test_tool(tool=tool, arguments=arguments)
        return jsonify(result)
    except MCPGuardrailError as exc:
        status = 403 if exc.code == "TOOL_NOT_ALLOWED" else 400
        return _error_response(exc.code, exc.message, status)
    except MCPClientError as exc:
        status = 504 if exc.code == "TOOL_TIMEOUT" else 502
        return _error_response(exc.code, exc.message, status)
    except Exception:
        return _error_response("TOOL_EXECUTION_ERROR", "Unexpected backend error", 500)
