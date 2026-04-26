import logging
import time
from typing import Any, Dict, List

import requests


logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class MCPClient:
    def __init__(self, server_url: str, timeout_seconds: int = 10):
        self.server_url = (server_url or "").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._connected = False
        self._tools_cache = None

    def connect(self):
        if not self.server_url:
            raise MCPClientError("MCP_CONFIG_ERROR", "MCP_SERVER_URL is not configured")
        self._connected = True
        return True

    def list_tools(self) -> List[Dict[str, Any]]:
        self._ensure_connected()
        if self._tools_cache is not None:
            return self._tools_cache
        try:
            response = self._session.get(f"{self.server_url}/tools", timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json() or {}
            tools = payload.get("tools", [])
            if isinstance(tools, list):
                self._tools_cache = tools
                return tools
            self._tools_cache = []
            return self._tools_cache
        except requests.Timeout as exc:
            raise MCPClientError("TOOL_TIMEOUT", "Tool listing timed out") from exc
        except requests.RequestException as exc:
            raise MCPClientError("TOOL_EXECUTION_ERROR", "Failed to list MCP tools") from exc

    def get_tool_schemas(self) -> Dict[str, Dict[str, Any]]:
        schemas: Dict[str, Dict[str, Any]] = {}
        for tool in self.list_tools():
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            schema = tool.get("input_schema")
            if isinstance(schema, dict):
                schemas[name] = schema
            else:
                schemas[name] = {"type": "object", "properties": {}, "required": []}
        return schemas

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], request_id: str = "-") -> Dict[str, Any]:
        self._ensure_connected()
        start = time.perf_counter()
        safe_args = redact_secrets(arguments)
        logger.info(
            "mcp_call_start request_id=%s tool=%s args=%s",
            request_id,
            tool_name,
            safe_args,
        )
        try:
            response = self._session.post(
                f"{self.server_url}/tools/{tool_name}/call",
                json={"arguments": arguments or {}},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json() or {}
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "mcp_call_end request_id=%s tool=%s status=ok latency_ms=%s",
                request_id,
                tool_name,
                latency_ms,
            )
            return {"ok": True, "result": payload.get("result", payload), "latency_ms": latency_ms}
        except requests.Timeout as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "mcp_call_end request_id=%s tool=%s status=timeout latency_ms=%s",
                request_id,
                tool_name,
                latency_ms,
            )
            raise MCPClientError("TOOL_TIMEOUT", "MCP tool request timed out") from exc
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "mcp_call_end request_id=%s tool=%s status=error latency_ms=%s",
                request_id,
                tool_name,
                latency_ms,
            )
            raise MCPClientError("TOOL_EXECUTION_ERROR", "MCP tool execution failed") from exc

    def _ensure_connected(self):
        if not self._connected:
            self.connect()


def redact_secrets(value: Any):
    secret_terms = {"token", "api_key", "secret", "password", "authorization"}
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in secret_terms:
                out[k] = "***"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(value, list):
        return [redact_secrets(x) for x in value]
    return value
