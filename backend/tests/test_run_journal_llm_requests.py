from __future__ import annotations

import asyncio
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage


def _flush_and_list(journal, store):
    async def _run():
        await journal.flush()
        return await store.list_events("thread-1", "run-1", limit=50)

    return asyncio.run(_run())


def _make_journal(*, capture_llm_requests: str = "off", max_llm_request_content: int = 200_000):
    from deerflow.runtime.events.store.memory import MemoryRunEventStore
    from deerflow.runtime.journal import RunJournal

    store = MemoryRunEventStore()
    journal = RunJournal(
        run_id="run-1",
        thread_id="thread-1",
        event_store=store,
        capture_llm_requests=capture_llm_requests,
        max_llm_request_content=max_llm_request_content,
    )
    return journal, store


def test_llm_request_capture_off_keeps_existing_human_input_only():
    journal, store = _make_journal(capture_llm_requests="off")

    journal.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[SystemMessage(content="system prompt"), HumanMessage(content="hello")]],
        run_id=uuid4(),
        tags=["lead_agent"],
    )

    events = _flush_and_list(journal, store)
    event_types = [event["event_type"] for event in events]

    assert "llm.human.input" in event_types
    assert "llm.chat.request" not in event_types


def test_llm_request_capture_summary_records_message_previews():
    journal, store = _make_journal(capture_llm_requests="summary")
    lc_run_id = uuid4()

    journal.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[SystemMessage(content="system prompt"), HumanMessage(content="hello from user")]],
        run_id=lc_run_id,
        tags=["lead_agent"],
        invocation_params={"model": "qwen3"},
    )

    events = _flush_and_list(journal, store)
    request_event = next(event for event in events if event["event_type"] == "llm.chat.request")

    assert request_event["category"] == "trace"
    assert request_event["metadata"]["capture_mode"] == "summary"
    assert request_event["metadata"]["llm_call_index"] == 1
    assert request_event["metadata"]["langchain_run_id"] == str(lc_run_id)
    assert request_event["content"]["mode"] == "summary"
    assert request_event["content"]["message_count"] == 2
    assert request_event["content"]["batches"][0]["messages"] == [
        {
            "type": "system",
            "name": None,
            "id": None,
            "content_preview": "system prompt",
            "content_length": len("system prompt"),
            "additional_kwargs_keys": [],
        },
        {
            "type": "human",
            "name": None,
            "id": None,
            "content_preview": "hello from user",
            "content_length": len("hello from user"),
            "additional_kwargs_keys": [],
        },
    ]


def test_llm_request_capture_full_records_messages_and_truncates_large_payloads():
    journal, store = _make_journal(capture_llm_requests="full", max_llm_request_content=350)

    journal.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[SystemMessage(content="system prompt"), HumanMessage(content="x" * 1000)]],
        run_id=uuid4(),
        tags=["lead_agent"],
        invocation_params={"model": "qwen3"},
    )

    events = _flush_and_list(journal, store)
    request_event = next(event for event in events if event["event_type"] == "llm.chat.request")

    assert request_event["metadata"]["capture_mode"] == "full"
    assert request_event["metadata"]["content_truncated"] is True
    assert request_event["metadata"]["original_byte_length"] > 350
    assert request_event["metadata"]["trace_content_limit"] == 350
    assert request_event["content"]["mode"] == "full"
    assert request_event["content"]["truncated"] is True
    assert "payload_json_preview" in request_event["content"]


def test_run_events_config_treats_yaml_false_as_capture_off():
    from deerflow.config.run_events_config import RunEventsConfig

    config = RunEventsConfig(capture_llm_requests=False)

    assert config.capture_llm_requests == "off"
