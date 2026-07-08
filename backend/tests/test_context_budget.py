import pytest
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from deerflow.config.app_config import AppConfig, reset_app_config, set_app_config
from deerflow.models.context_budget import (
    ContextBudgetExceeded,
    ContextPreflightConfig,
    estimate_chat_payload_tokens,
)
from deerflow.models.factory import create_chat_model
from deerflow.models.vllm_provider import VllmChatModel


class StrictFakeChatModel(BaseChatModel):
    model: str
    model_config = ConfigDict(extra="forbid")

    @property
    def _llm_type(self) -> str:
        return "strict-fake"

    def _generate(
        self,
        messages,
        stop=None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=HumanMessage(content="ok"))])


def test_estimate_chat_payload_counts_tools_template_margin_and_reserved_output() -> None:
    payload = {
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup_employee",
                    "description": "Look up an employee profile",
                    "parameters": {
                        "type": "object",
                        "properties": {"employee_id": {"type": "string"}},
                    },
                },
            }
        ],
        "max_completion_tokens": 128,
    }

    budget = estimate_chat_payload_tokens(
        payload,
        template_overhead_tokens=32,
        safety_margin_tokens=64,
        tokenizer="cl100k_base",
    )

    assert budget.message_tokens > 0
    assert budget.tool_tokens > 0
    assert budget.reserved_output_tokens == 128
    assert budget.input_tokens == budget.message_tokens + budget.tool_tokens + 32 + 64
    assert budget.total_tokens == budget.input_tokens + 128


def test_vllm_context_preflight_raises_before_provider_request_when_budget_exceeded() -> None:
    model = VllmChatModel(
        model="Qwen3",
        api_key="test-key",
        base_url="http://example.test/v1",
        max_tokens=64,
        max_context_tokens=120,
        context_preflight=ContextPreflightConfig(
            enabled=True,
            safety_margin_tokens=0,
            template_overhead_tokens=0,
            tokenizer="cl100k_base",
        ),
    )

    with pytest.raises(ContextBudgetExceeded) as exc_info:
        model._get_request_payload(
            [
                HumanMessage(content="long employee context payload " * 80),
            ]
        )

    message = str(exc_info.value)
    assert "Context budget exceeded" in message
    assert "model=Qwen3" in message
    assert "max_context_tokens=120" in message
    assert "reserved_output_tokens=64" in message


def test_vllm_context_preflight_trims_oldest_messages_when_configured() -> None:
    model = VllmChatModel(
        model="Qwen3",
        api_key="test-key",
        base_url="http://example.test/v1",
        max_tokens=16,
        max_context_tokens=90,
        context_preflight=ContextPreflightConfig(
            enabled=True,
            safety_margin_tokens=0,
            template_overhead_tokens=0,
            tokenizer="cl100k_base",
            on_overflow="trim",
        ),
    )

    payload = model._get_request_payload(
        [
            HumanMessage(content="old context payload " * 80),
            HumanMessage(content="recent question"),
        ]
    )

    assert [message["content"] for message in payload["messages"]] == ["recent question"]
    budget = estimate_chat_payload_tokens(
        payload,
        template_overhead_tokens=0,
        safety_margin_tokens=0,
        tokenizer="cl100k_base",
        fallback_reserved_output_tokens=16,
    )
    assert budget.total_tokens <= 90


def test_vllm_context_preflight_trim_raises_when_only_message_is_too_large() -> None:
    model = VllmChatModel(
        model="Qwen3",
        api_key="test-key",
        base_url="http://example.test/v1",
        max_tokens=16,
        max_context_tokens=40,
        context_preflight=ContextPreflightConfig(
            enabled=True,
            safety_margin_tokens=0,
            template_overhead_tokens=0,
            tokenizer="cl100k_base",
            on_overflow="trim",
        ),
    )

    with pytest.raises(ContextBudgetExceeded):
        model._get_request_payload([HumanMessage(content="only oversized payload " * 80)])


def test_create_chat_model_does_not_pass_context_preflight_to_unsupported_providers() -> None:
    config = AppConfig.model_validate(
        {
            "models": [
                {
                    "name": "strict-fake",
                    "use": f"{__name__}:StrictFakeChatModel",
                    "model": "fake-model",
                }
            ],
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        }
    )

    try:
        set_app_config(config)
        model = create_chat_model("strict-fake", attach_tracing=False)
    finally:
        reset_app_config()

    assert isinstance(model, StrictFakeChatModel)
    assert model.model == "fake-model"
