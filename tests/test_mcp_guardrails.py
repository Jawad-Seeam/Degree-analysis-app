import unittest
from unittest.mock import patch

from ai.mcp_client import MCPClientError
from ai.orchestrator import AIOrchestrator, MCPGuardrailError


class _DummySettings:
    def __init__(self):
        self.mcp_tool_allowlist = ["transcript_lookup"]
        self.mcp_max_tool_calls = 3


class _DummyClient:
    def __init__(self, behavior="ok"):
        self.behavior = behavior

    def call_tool(self, tool_name, arguments, request_id="-"):
        if self.behavior == "timeout":
            raise MCPClientError("TOOL_TIMEOUT", "timeout")
        if self.behavior == "error":
            raise MCPClientError("TOOL_EXECUTION_ERROR", "error")
        return {"ok": True, "result": {"echo": arguments}, "latency_ms": 5}


class MCPGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.settings = _DummySettings()

    def test_tool_not_allowed(self):
        orch = AIOrchestrator(client=_DummyClient(), settings=self.settings)
        with self.assertRaises(MCPGuardrailError) as ctx:
            orch.test_tool("degree_audit_hint", {"program": "CSE", "course_code": "CSE115"})
        self.assertEqual(ctx.exception.code, "TOOL_NOT_ALLOWED")

    @patch("ai.orchestrator._should_use_tool", return_value=("transcript_lookup", {"query": 123}))
    def test_tool_argument_validation_error(self, _mock_router):
        orch = AIOrchestrator(client=_DummyClient(), settings=self.settings)
        with self.assertRaises(MCPGuardrailError) as ctx:
            orch.chat("lookup", "u1", {})
        self.assertEqual(ctx.exception.code, "TOOL_VALIDATION_ERROR")

    def test_tool_timeout_handling(self):
        orch = AIOrchestrator(client=_DummyClient("timeout"), settings=self.settings)
        with patch("ai.orchestrator._should_use_tool", return_value=("transcript_lookup", {"query": "cse"})):
            out = orch.chat("lookup cse", "u1", {})
        self.assertTrue(out.get("fallback_used"))
        self.assertEqual(out.get("error_code"), "TOOL_TIMEOUT")

    def test_fallback_reply_on_tool_failure(self):
        orch = AIOrchestrator(client=_DummyClient("error"), settings=self.settings)
        with patch("ai.orchestrator._should_use_tool", return_value=("transcript_lookup", {"query": "cse"})):
            out = orch.chat("lookup cse", "u1", {})
        self.assertTrue(out.get("fallback_used"))
        self.assertIn("could not complete", out.get("reply", "").lower())

    def test_max_tool_calls_enforced(self):
        orch = AIOrchestrator(client=_DummyClient(), settings=self.settings)
        orch.settings.mcp_max_tool_calls = 0
        with patch("ai.orchestrator._should_use_tool", return_value=("transcript_lookup", {"query": "cse"})):
            with self.assertRaises(MCPGuardrailError) as ctx:
                orch.chat("lookup cse", "u1", {})
        self.assertEqual(ctx.exception.code, "TOOL_VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
