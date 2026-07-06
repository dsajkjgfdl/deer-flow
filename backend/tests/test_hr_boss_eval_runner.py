from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.mcp import cache as mcp_cache
from deerflow import client as deerflow_client
from scripts import run_hr_boss_eval
from scripts.run_hr_boss_eval import XIYAN_TEXT2SQL_ANSWER_TOOL, XiYanSqlMcpRunner


def test_run_turn_accumulates_streamed_ai_chunks():
    class FakeClient:
        def stream(self, _message, *, thread_id):
            assert thread_id == "thread-1"
            return iter(
                [
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "content": "福建"}),
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "content": "火炬"}),
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "content": "1人"}),
                ]
            )

    turn = run_hr_boss_eval.run_turn(
        record={"id": "case-1"},
        client=FakeClient(),
        message="q",
        thread_id="thread-1",
        rnd=1,
        turn_num=1,
    )

    assert turn["answer"] == "福建火炬1人"


def test_run_turn_reports_latest_displayable_ai_message():
    class FakeClient:
        def stream(self, _message, *, thread_id):
            assert thread_id == "thread-1"
            return iter(
                [
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "plan", "content": "先查询"}),
                    SimpleNamespace(
                        type="messages-tuple",
                        data={
                            "type": "ai",
                            "id": "plan",
                            "content": "",
                            "tool_calls": [{"name": "text2cypher_answer_question", "args": {}}],
                        },
                    ),
                    SimpleNamespace(
                        type="messages-tuple",
                        data={"type": "tool", "id": "tool-1", "name": "text2cypher_answer_question", "content": "{}"},
                    ),
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "summary", "content": "## SESSION INTENT\n内部摘要"}),
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "final", "content": "福建火炬"}),
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "final", "content": "1人"}),
                ]
            )

    turn = run_hr_boss_eval.run_turn(
        record={"id": "case-1"},
        client=FakeClient(),
        message="q",
        thread_id="thread-1",
        rnd=1,
        turn_num=1,
    )

    assert turn["answer"] == "福建火炬1人"


def test_run_turn_ignores_replayed_message_ids_between_turns():
    seen_message_ids = {"old-ai", "old-tool"}

    class FakeClient:
        def stream(self, _message, *, thread_id):
            assert thread_id == "thread-1"
            return iter(
                [
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "old-ai", "content": "旧答案"}),
                    SimpleNamespace(
                        type="messages-tuple",
                        data={
                            "type": "ai",
                            "id": "old-ai",
                            "content": "",
                            "tool_calls": [{"name": "old_tool", "args": {}}],
                        },
                    ),
                    SimpleNamespace(type="messages-tuple", data={"type": "tool", "id": "old-tool", "name": "old_tool", "content": "{}"}),
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "new-ai", "content": "新答案"}),
                ]
            )

    turn = run_hr_boss_eval.run_turn(
        record={"id": "case-1"},
        client=FakeClient(),
        message="q",
        thread_id="thread-1",
        rnd=1,
        turn_num=2,
        seen_message_ids=seen_message_ids,
    )

    assert turn["answer"] == "新答案"
    assert turn["tool_calls"] == []
    assert seen_message_ids == {"old-ai", "old-tool", "new-ai"}


def test_run_turn_fetches_text2cypher_debug_cypher_when_fast_result_is_slim():
    class FakeClient:
        def stream(self, _message, *, thread_id):
            assert thread_id == "thread-1"
            slim_result = {
                "status": "success",
                "answerable": True,
                "term_resolution": {
                    "question": "福建火炬电子科技股份有限公司IT部有多少人?",
                    "needs_clarification": False,
                    "mappings": [],
                },
                "execution": {"columns": ["employee_count"], "records": [{"employee_count": 1}]},
            }
            return iter(
                [
                    SimpleNamespace(
                        type="messages-tuple",
                        data={
                            "type": "ai",
                            "id": "tool-ai",
                            "content": "",
                            "tool_calls": [{"name": "text2cypher_answer_question", "args": {"question": "q"}}],
                        },
                    ),
                    SimpleNamespace(
                        type="messages-tuple",
                        data={
                            "type": "tool",
                            "id": "tool-1",
                            "name": "text2cypher_answer_question",
                            "content": slim_result,
                        },
                    ),
                    SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "final", "content": "1人"}),
                ]
            )

    class FakeDebugRunner:
        def __init__(self):
            self.questions = []

        def answer_question(self, question):
            self.questions.append(question)
            return {
                "generation": {"generated_cypher": "MATCH (e:Employee) RETURN count(e)"},
                "execution": {"normalized_cypher": "MATCH (e:Employee) RETURN count(e)"},
            }

    debug_runner = FakeDebugRunner()

    turn = run_hr_boss_eval.run_turn(
        record={"id": "case-1"},
        client=FakeClient(),
        message="福建的那家",
        thread_id="thread-1",
        rnd=1,
        turn_num=2,
        text2cypher_debug_runner=debug_runner,
    )

    assert turn["answer"] == "1人"
    assert turn["generated_cypher"] == "MATCH (e:Employee) RETURN count(e)"
    assert debug_runner.questions == ["福建火炬电子科技股份有限公司IT部有多少人?"]


def test_xiyan_runner_supports_legacy_mcp_cache_signature(monkeypatch):
    tool = SimpleNamespace(name=XIYAN_TEXT2SQL_ANSWER_TOOL)

    def get_cached_mcp_tools():
        return [tool]

    monkeypatch.setattr(mcp_cache, "get_cached_mcp_tools", get_cached_mcp_tools)

    runner = XiYanSqlMcpRunner()

    assert runner._get_tool() is tool


def test_boss_e2e_accepts_employee_query_route_but_strict_tracks_do_not():
    employee_route = ["text2cypher_query_employees"]

    assert employee_route in run_hr_boss_eval.expected_routes_for("boss.e2e")
    assert employee_route not in run_hr_boss_eval.expected_routes_for("text2cypher.strict")
    assert employee_route not in run_hr_boss_eval.expected_routes_for("term_resolution.strict")


def test_boss_e2e_accepts_employee_profile_route_but_strict_tracks_do_not():
    profile_route = ["text2cypher_get_employee_profile"]

    assert profile_route in run_hr_boss_eval.expected_routes_for("boss.e2e")
    assert profile_route not in run_hr_boss_eval.expected_routes_for("text2cypher.strict")
    assert profile_route not in run_hr_boss_eval.expected_routes_for("term_resolution.strict")


def test_eval_runner_defaults_deerflow_project_root_to_backend():
    assert Path(run_hr_boss_eval.os.environ["DEER_FLOW_PROJECT_ROOT"]) == run_hr_boss_eval.REPO_ROOT / "backend"


def test_main_cleans_up_mcp_resources_when_run_records_raises(monkeypatch, tmp_path):
    cleanup_events = []

    class FakeTempDir:
        def cleanup(self):
            cleanup_events.append("tempdir")

    class FakeDeerFlowClient:
        def __init__(self, **_kwargs):
            pass

    args = SimpleNamespace(
        data_dir=tmp_path,
        track=["test"],
        ids=None,
        limit=None,
        output_jsonl=tmp_path / "run-results.jsonl",
        output_md=tmp_path / "run-results.md",
        thread_prefix="thread",
        rounds=1,
        conversation_mode="single",
        max_turns=3,
        simulator_model_name=None,
        model_name=None,
        thinking_enabled=False,
        run_xiyan_sql=False,
    )

    monkeypatch.setattr(run_hr_boss_eval, "parse_args", lambda: args)
    monkeypatch.setattr(
        run_hr_boss_eval,
        "load_records",
        lambda _data_dir, _tracks: [{"id": "case-1", "track": "test", "category": "query", "question": "q"}],
    )
    monkeypatch.setattr(run_hr_boss_eval, "configure_restricted_mcp", lambda *_args, **_kwargs: FakeTempDir())
    monkeypatch.setattr(deerflow_client, "DeerFlowClient", FakeDeerFlowClient)
    monkeypatch.setattr(mcp_cache, "get_cached_mcp_tools", lambda: cleanup_events.append("preload") or [])
    monkeypatch.setattr(mcp_cache, "reset_mcp_tools_cache", lambda: cleanup_events.append("mcp"))

    def raise_run_records(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(run_hr_boss_eval, "run_records", raise_run_records)

    with pytest.raises(RuntimeError, match="boom"):
        run_hr_boss_eval.main()

    assert cleanup_events == ["preload", "mcp", "tempdir"]
