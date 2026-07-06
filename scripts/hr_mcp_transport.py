from __future__ import annotations

import os
from typing import Any

NETWORK_TRANSPORTS = {"sse", "streamable-http"}
TRANSPORT_ALIASES = {
    "http": "streamable-http",
    "sse": "sse",
    "stdio": "stdio",
    "streamable-http": "streamable-http",
}


def server_run_kwargs() -> dict[str, Any]:
    raw_transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    transport = TRANSPORT_ALIASES.get(raw_transport)
    if transport is None:
        raise RuntimeError(
            f"Unsupported MCP transport: {raw_transport!r}. "
            "Expected one of: stdio, http, streamable-http, sse."
        )

    kwargs: dict[str, Any] = {
        "transport": transport,
        "show_banner": False,
        "log_level": os.getenv("MCP_LOG_LEVEL", "error").strip().lower() or "error",
    }
    if transport not in NETWORK_TRANSPORTS:
        return kwargs

    raw_port = os.getenv("MCP_PORT", "8000").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeError(f"MCP_PORT must be an integer, got {raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError(f"MCP_PORT must be between 1 and 65535, got {port}")

    kwargs["host"] = os.getenv("MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    kwargs["port"] = port
    return kwargs


def run_server(server: Any) -> None:
    server.run(**server_run_kwargs())
