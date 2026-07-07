"""Run event storage configuration.

Controls where run events (messages + execution traces) are persisted.

Backends:
- memory: In-memory storage, data lost on restart. Suitable for
  development and testing.
- db: SQL database via SQLAlchemy ORM. Provides full query capability.
  Suitable for production deployments.
- jsonl: Append-only JSONL files. Lightweight alternative for
  single-node deployments that need persistence without a database.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RunEventsConfig(BaseModel):
    backend: Literal["memory", "db", "jsonl"] = Field(
        default="memory",
        description="Storage backend for run events. 'memory' for development (no persistence), 'db' for production (SQL queries), 'jsonl' for lightweight single-node persistence.",
    )
    max_trace_content: int = Field(
        default=10240,
        description="Maximum trace content size in bytes before truncation (db backend only).",
    )
    track_token_usage: bool = Field(
        default=True,
        description="Whether RunJournal should accumulate token counts to RunRow.",
    )
    capture_llm_requests: Literal["off", "summary", "full"] = Field(
        default="off",
        description="Whether RunJournal should record chat model request prompts: off, summary previews, or full serialized messages.",
    )
    max_llm_request_content: int = Field(
        default=200_000,
        ge=1,
        description="Maximum serialized llm.chat.request payload size in bytes before RunJournal stores a preview instead.",
    )

    @field_validator("capture_llm_requests", mode="before")
    @classmethod
    def _normalize_capture_llm_requests(cls, value):
        # YAML 1.1 parsers treat bare `off` as False. Accept that spelling as
        # the documented disabled mode instead of forcing every config to quote it.
        if value is False:
            return "off"
        return value
