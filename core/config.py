import os


class MCPConfigError(Exception):
    pass


class MCPSettings:
    def __init__(self):
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "").strip()
        self.mcp_timeout_seconds = int(os.getenv("MCP_TIMEOUT_SECONDS", "10") or "10")
        self.mcp_max_tool_calls = int(os.getenv("MCP_MAX_TOOL_CALLS", "3") or "3")
        allowlist_raw = os.getenv("MCP_TOOL_ALLOWLIST", "")
        self.mcp_tool_allowlist = [item.strip() for item in allowlist_raw.split(",") if item.strip()]

        self.model_api_key = os.getenv("MODEL_API_KEY", "").strip()
        self.model_name = os.getenv("MODEL_NAME", "mock-model").strip()
        self.log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    def validate(self):
        if self.mcp_timeout_seconds <= 0:
            raise MCPConfigError("MCP_TIMEOUT_SECONDS must be > 0")
        if self.mcp_max_tool_calls <= 0:
            raise MCPConfigError("MCP_MAX_TOOL_CALLS must be > 0")

    def masked(self):
        return {
            "MCP_SERVER_URL": self.mcp_server_url,
            "MCP_TIMEOUT_SECONDS": self.mcp_timeout_seconds,
            "MCP_MAX_TOOL_CALLS": self.mcp_max_tool_calls,
            "MCP_TOOL_ALLOWLIST": self.mcp_tool_allowlist,
            "MODEL_NAME": self.model_name,
            "MODEL_API_KEY": mask_secret(self.model_api_key),
            "LOG_LEVEL": self.log_level,
        }


def mask_secret(value):
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


_settings_cache = None


def get_mcp_settings():
    global _settings_cache
    if _settings_cache is None:
        cfg = MCPSettings()
        cfg.validate()
        _settings_cache = cfg
    return _settings_cache
