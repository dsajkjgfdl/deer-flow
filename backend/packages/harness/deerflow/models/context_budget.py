"""Final LLM request context-budget estimation and preflight checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import tiktoken
from pydantic import BaseModel, Field


class ContextPreflightConfig(BaseModel):
    """Configuration for final chat payload budget checks."""

    enabled: bool = Field(default=False, description="Whether to check final chat payloads before provider calls.")
    safety_margin_tokens: int = Field(default=512, ge=0, description="Extra reserve for tokenizer/provider differences.")
    template_overhead_tokens: int = Field(default=800, ge=0, description="Estimated provider chat-template overhead.")
    tokenizer: str = Field(default="cl100k_base", description="tiktoken encoding name used for local estimates.")
    on_overflow: Literal["raise", "trim"] = Field(default="raise", description="How to handle overflow before provider calls.")


@dataclass(frozen=True)
class MessageTokenDetail:
    index: int
    role: str
    name: str | None
    tokens: int


@dataclass(frozen=True)
class ContextBudgetEstimate:
    message_tokens: int
    tool_tokens: int
    template_overhead_tokens: int
    safety_margin_tokens: int
    reserved_output_tokens: int
    input_tokens: int
    total_tokens: int
    message_count: int
    largest_messages: tuple[MessageTokenDetail, ...]


class ContextBudgetExceeded(ValueError):
    """Raised before sending a chat payload that cannot fit the model window."""

    def __init__(
        self,
        *,
        model: str | None,
        max_context_tokens: int,
        estimate: ContextBudgetEstimate,
    ) -> None:
        self.model = model
        self.max_context_tokens = max_context_tokens
        self.estimate = estimate
        over_by = estimate.total_tokens - max_context_tokens
        largest = ", ".join(
            f"{detail.index}:{detail.role}{':' + detail.name if detail.name else ''}={detail.tokens}"
            for detail in estimate.largest_messages
        )
        super().__init__(
            "Context budget exceeded: "
            f"model={model or '<unknown>'} "
            f"max_context_tokens={max_context_tokens} "
            f"input_tokens={estimate.input_tokens} "
            f"reserved_output_tokens={estimate.reserved_output_tokens} "
            f"total_tokens={estimate.total_tokens} "
            f"over_by={over_by} "
            f"message_count={estimate.message_count} "
            f"largest_messages=[{largest}]"
        )


def _encoding(tokenizer: str):
    try:
        return tiktoken.get_encoding(tokenizer)
    except ValueError:
        return tiktoken.get_encoding("cl100k_base")


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _count(value: Any, tokenizer: str) -> int:
    encoding = _encoding(tokenizer)
    if isinstance(value, str):
        text = value
    else:
        text = _stable_json(value)
    return len(encoding.encode(text))


def _message_payload_for_count(message: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "role",
        "name",
        "content",
        "tool_calls",
        "tool_call_id",
        "function_call",
        "reasoning",
    )
    return {key: message[key] for key in keys if key in message and message[key] is not None}


def _reserved_output_tokens(payload: dict[str, Any], fallback_reserved_output_tokens: int | None) -> int:
    for key in ("max_completion_tokens", "max_tokens", "max_output_tokens"):
        value = payload.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return fallback_reserved_output_tokens or 0


def _is_protected_leading_message(message: dict[str, Any]) -> bool:
    return message.get("role") in {"system", "developer"} or message.get("name") == "summary"


def _tool_call_ids(message: dict[str, Any]) -> set[str]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return set()

    ids: set[str] = set()
    for tool_call in tool_calls:
        if isinstance(tool_call, dict) and isinstance(tool_call.get("id"), str):
            ids.add(tool_call["id"])
    return ids


def _oldest_removable_payload_group(messages: list[dict[str, Any]]) -> tuple[int, int] | None:
    index = 0
    while index < len(messages) and _is_protected_leading_message(messages[index]):
        index += 1
    if index >= len(messages):
        return None

    first = messages[index]
    if first.get("role") == "assistant":
        tool_call_ids = _tool_call_ids(first)
        if tool_call_ids:
            end = index + 1
            while end < len(messages) and messages[end].get("role") == "tool":
                if messages[end].get("tool_call_id") not in tool_call_ids:
                    break
                end += 1
            return index, end

    if first.get("role") == "tool":
        end = index + 1
        while end < len(messages) and messages[end].get("role") == "tool":
            end += 1
        return index, end

    return index, index + 1


def estimate_chat_payload_tokens(
    payload: dict[str, Any],
    *,
    template_overhead_tokens: int,
    safety_margin_tokens: int,
    tokenizer: str,
    fallback_reserved_output_tokens: int | None = None,
) -> ContextBudgetEstimate:
    """Estimate the final OpenAI-compatible chat payload budget."""

    messages = payload.get("messages")
    if not isinstance(messages, list):
        messages = []

    details: list[MessageTokenDetail] = []
    message_tokens = 0
    for index, raw_message in enumerate(messages):
        message = raw_message if isinstance(raw_message, dict) else {"content": raw_message}
        tokens = _count(_message_payload_for_count(message), tokenizer)
        message_tokens += tokens
        role = str(message.get("role") or "unknown")
        name = message.get("name") if isinstance(message.get("name"), str) else None
        details.append(MessageTokenDetail(index=index, role=role, name=name, tokens=tokens))

    tool_tokens = 0
    for key in ("tools", "functions", "response_format"):
        value = payload.get(key)
        if value is not None:
            tool_tokens += _count(value, tokenizer)

    reserved_output = _reserved_output_tokens(payload, fallback_reserved_output_tokens)
    input_tokens = message_tokens + tool_tokens + template_overhead_tokens + safety_margin_tokens
    total_tokens = input_tokens + reserved_output
    largest_messages = tuple(sorted(details, key=lambda detail: detail.tokens, reverse=True)[:5])

    return ContextBudgetEstimate(
        message_tokens=message_tokens,
        tool_tokens=tool_tokens,
        template_overhead_tokens=template_overhead_tokens,
        safety_margin_tokens=safety_margin_tokens,
        reserved_output_tokens=reserved_output,
        input_tokens=input_tokens,
        total_tokens=total_tokens,
        message_count=len(messages),
        largest_messages=largest_messages,
    )


def _estimate_for_preflight(
    payload: dict[str, Any],
    preflight: ContextPreflightConfig,
    fallback_reserved_output_tokens: int | None,
) -> ContextBudgetEstimate:
    return estimate_chat_payload_tokens(
        payload,
        template_overhead_tokens=preflight.template_overhead_tokens,
        safety_margin_tokens=preflight.safety_margin_tokens,
        tokenizer=preflight.tokenizer,
        fallback_reserved_output_tokens=fallback_reserved_output_tokens,
    )


def _trim_chat_payload_messages_to_budget(
    payload: dict[str, Any],
    *,
    max_context_tokens: int,
    preflight: ContextPreflightConfig,
    fallback_reserved_output_tokens: int | None,
) -> ContextBudgetEstimate:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return _estimate_for_preflight(payload, preflight, fallback_reserved_output_tokens)

    estimate = _estimate_for_preflight(payload, preflight, fallback_reserved_output_tokens)
    while estimate.total_tokens > max_context_tokens:
        group = _oldest_removable_payload_group(messages)
        if group is None:
            break

        start, end = group
        remaining_after_drop = [*messages[:start], *messages[end:]]
        if _oldest_removable_payload_group(remaining_after_drop) is None:
            break

        del messages[start:end]
        estimate = _estimate_for_preflight(payload, preflight, fallback_reserved_output_tokens)

    return estimate


def check_chat_payload_context_budget(
    payload: dict[str, Any],
    *,
    model: str | None,
    max_context_tokens: int | None,
    config: ContextPreflightConfig | dict[str, Any] | None,
    fallback_reserved_output_tokens: int | None = None,
) -> ContextBudgetEstimate | None:
    """Raise when the final chat payload cannot fit the configured context window."""

    preflight = config if isinstance(config, ContextPreflightConfig) else ContextPreflightConfig.model_validate(config or {})
    if not preflight.enabled or not max_context_tokens:
        return None

    estimate = _estimate_for_preflight(payload, preflight, fallback_reserved_output_tokens)
    if estimate.total_tokens > max_context_tokens and preflight.on_overflow == "trim":
        estimate = _trim_chat_payload_messages_to_budget(
            payload,
            max_context_tokens=max_context_tokens,
            preflight=preflight,
            fallback_reserved_output_tokens=fallback_reserved_output_tokens,
        )
    if estimate.total_tokens > max_context_tokens:
        raise ContextBudgetExceeded(model=model, max_context_tokens=max_context_tokens, estimate=estimate)
    return estimate
