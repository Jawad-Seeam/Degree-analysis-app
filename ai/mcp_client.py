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
        self._local_mode = False
        self._tools_cache = None

    def connect(self):
        if not self.server_url:
            self._local_mode = True
            self._connected = True
            return True
        self._connected = True
        return True

    def list_tools(self) -> List[Dict[str, Any]]:
        self._ensure_connected()
        if self._local_mode:
            if self._tools_cache is None:
                self._tools_cache = self._local_tools()
            return self._tools_cache
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
            logger.warning("mcp_list_tools timeout; switching to local fallback tools")
            self._local_mode = True
            self._tools_cache = self._local_tools()
            return self._tools_cache
        except requests.RequestException as exc:
            logger.warning("mcp_list_tools remote error; switching to local fallback tools")
            self._local_mode = True
            self._tools_cache = self._local_tools()
            return self._tools_cache

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
        if self._local_mode:
            start = time.perf_counter()
            try:
                result = self._call_local_tool(tool_name, arguments or {})
                latency_ms = int((time.perf_counter() - start) * 1000)
                return {"ok": True, "result": result, "latency_ms": latency_ms}
            except MCPClientError:
                raise
            except Exception as exc:
                raise MCPClientError("TOOL_EXECUTION_ERROR", f"Local tool '{tool_name}' failed") from exc

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
            logger.warning("mcp_call timeout; switching to local fallback tool execution")
            self._local_mode = True
            result = self._call_local_tool(tool_name, arguments or {})
            fallback_latency = int((time.perf_counter() - start) * 1000)
            return {"ok": True, "result": result, "latency_ms": fallback_latency}
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "mcp_call_end request_id=%s tool=%s status=error latency_ms=%s",
                request_id,
                tool_name,
                latency_ms,
            )
            logger.warning("mcp_call remote error; switching to local fallback tool execution")
            self._local_mode = True
            result = self._call_local_tool(tool_name, arguments or {})
            fallback_latency = int((time.perf_counter() - start) * 1000)
            return {"ok": True, "result": result, "latency_ms": fallback_latency}

    def _ensure_connected(self):
        if not self._connected:
            self.connect()

    def _local_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "transcript_lookup",
                "description": "Lookup transcript-like course matches",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "degree_audit_hint",
                "description": "Return a lightweight audit hint",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "program": {"type": "string"},
                        "course_code": {"type": "string"},
                    },
                    "required": ["program", "course_code"],
                },
            },
        ]

    def _call_local_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "transcript_lookup":
            query = str(arguments.get("query", "") or "").strip()
            needle = query.upper().replace(" ", "")
            catalog = [
                "ACT201", "ACT202", "BEN205", "BIO103", "BUS101", "BUS112", "BUS134", "CSE115", "CSE173",
                "CSE215", "CSE225", "CSE231", "CSE311", "CSE323", "CSE327", "CSE331", "CSE332", "CSE425",
                "EEE141", "ENG102", "ENG103", "ENV203", "FIN254", "HIS103", "MAT116", "MAT120", "MAT250",
                "MAT350", "MAT361", "MGT210", "MGT314", "MGT368", "MIS205", "MKT202", "PHI101", "QM212",
            ]
            matches = [code for code in catalog if needle and needle in code]
            if not needle:
                matches = catalog[:8]
            return {
                "query": query,
                "matches": matches[:15],
                "rows": [],
                "source": "local-fallback",
                "from_transcript": False,
                "pool_size": len(catalog),
            }

        if tool_name == "degree_audit_hint":
            program = str(arguments.get("program", "") or "CSE").upper().strip() or "CSE"
            course_code = str(arguments.get("course_code", "") or "").upper().strip() or "UNKNOWN"
            return {
                "program": program,
                "course_code": course_code,
                "hint": f"For {program}, verify prerequisite chain and minimum grade policy for {course_code}.",
                "source": "local-fallback",
            }

        raise MCPClientError("TOOL_NOT_FOUND", f"Unknown tool '{tool_name}'")


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
