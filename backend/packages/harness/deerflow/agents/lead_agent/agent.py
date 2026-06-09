"""Lead agent factory.

INVARIANT — tracing callback placement
======================================

Tracing callbacks (Langfuse, LangSmith) are attached at the **graph
invocation root** in :func:`_make_lead_agent` (see the
``build_tracing_callbacks()`` block that appends to ``config["callbacks"]``).
Every ``create_chat_model(...)`` call inside this module — and inside any
middleware reachable from this graph (e.g. ``TitleMiddleware``) — MUST pass
``attach_tracing=False``.

Forgetting that flag emits duplicate spans (one rooted at the graph, one at
the model) AND prevents the Langfuse handler's ``propagate_attributes``
path from firing, so ``session_id`` / ``user_id`` never reach the trace.
The four current sites are: bootstrap agent, default agent, summarization
middleware, and the async path inside ``TitleMiddleware``. Any new in-graph
``create_chat_model`` call must add to this list and pass the flag.
"""

import json
import logging
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool

from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.agents.memory.summarization_hook import memory_flush_hook
from deerflow.agents.middlewares.clarification_middleware import ClarificationMiddleware
from deerflow.agents.middlewares.loop_detection_middleware import LoopDetectionMiddleware
from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware
from deerflow.agents.middlewares.safety_finish_reason_middleware import SafetyFinishReasonMiddleware
from deerflow.agents.middlewares.subagent_limit_middleware import SubagentLimitMiddleware
from deerflow.agents.middlewares.summarization_middleware import BeforeSummarizationHook, DeerFlowSummarizationMiddleware
from deerflow.agents.middlewares.title_middleware import TitleMiddleware
from deerflow.agents.middlewares.todo_middleware import TodoMiddleware
from deerflow.agents.middlewares.token_usage_middleware import TokenUsageMiddleware
from deerflow.agents.middlewares.tool_error_handling_middleware import build_lead_runtime_middlewares
from deerflow.agents.middlewares.view_image_middleware import ViewImageMiddleware
from deerflow.agents.thread_state import ThreadState
from deerflow.config.agents_config import load_agent_config, validate_agent_name
from deerflow.config.app_config import AppConfig, get_app_config
from deerflow.models import create_chat_model
from deerflow.skills.tool_policy import filter_tools_by_skill_allowed_tools
from deerflow.skills.types import Skill
from deerflow.tracing import build_tracing_callbacks

logger = logging.getLogger(__name__)

_HR_BOSS_AGENT_NAME = "hr-boss-agent"
_HR_BOSS_RECOMMENDATION_SLOW_TOOLS: frozenset[str] = frozenset(
    {
        "hr-graphrag-qa_query_basic",
        "hr-graphrag-qa_query_local",
        "hr-graphrag-qa_query_global",
        "hr-graphrag-qa_query_drift",
    }
)
_HR_BOSS_RECOMMENDATION_MAX_TOKENS = 700
_TEXT2CYPHER_ANSWER_TOOL_NAME = "text2cypher_answer_question"


def _get_runtime_config(config: RunnableConfig) -> dict:
    """Merge legacy configurable options with LangGraph runtime context."""
    cfg = dict(config.get("configurable", {}) or {})
    context = config.get("context", {}) or {}
    if isinstance(context, dict):
        cfg.update(context)
    return cfg


def _resolve_model_name(requested_model_name: str | None = None, *, app_config: AppConfig | None = None) -> str:
    """Resolve a runtime model name safely, falling back to default if invalid. Returns None if no models are configured."""
    app_config = app_config or get_app_config()
    default_model_name = app_config.models[0].name if app_config.models else None
    if default_model_name is None:
        raise ValueError("No chat models are configured. Please configure at least one model in config.yaml.")

    if requested_model_name and app_config.get_model_config(requested_model_name):
        return requested_model_name

    if requested_model_name and requested_model_name != default_model_name:
        logger.warning(f"Model '{requested_model_name}' not found in config; fallback to default model '{default_model_name}'.")
    return default_model_name


def _create_summarization_middleware(*, app_config: AppConfig | None = None) -> DeerFlowSummarizationMiddleware | None:
    """Create and configure the summarization middleware from config."""
    resolved_app_config = app_config or get_app_config()
    config = resolved_app_config.summarization

    if not config.enabled:
        return None

    # Prepare trigger parameter
    trigger = None
    if config.trigger is not None:
        if isinstance(config.trigger, list):
            trigger = [t.to_tuple() for t in config.trigger]
        else:
            trigger = config.trigger.to_tuple()

    # Prepare keep parameter
    keep = config.keep.to_tuple()

    # Prepare model parameter.
    # Bind "middleware:summarize" tag so RunJournal identifies these LLM calls
    # as middleware rather than lead_agent (SummarizationMiddleware is a
    # LangChain built-in, so we tag the model at creation time).
    # attach_tracing=False because the graph-level RunnableConfig (set in
    # ``_make_lead_agent``) already carries tracing callbacks; binding them
    # again at the model level would emit duplicate spans and break
    # ``session_id`` / ``user_id`` propagation.
    if config.model_name:
        model = create_chat_model(name=config.model_name, thinking_enabled=False, app_config=resolved_app_config, attach_tracing=False)
    else:
        model = create_chat_model(thinking_enabled=False, app_config=resolved_app_config, attach_tracing=False)
    model = model.with_config(tags=["middleware:summarize"])

    # Prepare kwargs
    kwargs = {
        "model": model,
        "trigger": trigger,
        "keep": keep,
    }

    if config.trim_tokens_to_summarize is not None:
        kwargs["trim_tokens_to_summarize"] = config.trim_tokens_to_summarize

    if config.summary_prompt is not None:
        kwargs["summary_prompt"] = config.summary_prompt

    hooks: list[BeforeSummarizationHook] = []
    if resolved_app_config.memory.enabled:
        hooks.append(memory_flush_hook)

    # The logic below relies on two assumptions holding true: this factory is
    # the sole entry point for DeerFlowSummarizationMiddleware, and the runtime
    # config is not expected to change after startup.
    skills_container_path = resolved_app_config.skills.container_path or "/mnt/skills"

    return DeerFlowSummarizationMiddleware(
        **kwargs,
        skills_container_path=skills_container_path,
        skill_file_read_tool_names=config.skill_file_read_tool_names,
        before_summarization=hooks,
        preserve_recent_skill_count=config.preserve_recent_skill_count,
        preserve_recent_skill_tokens=config.preserve_recent_skill_tokens,
        preserve_recent_skill_tokens_per_skill=config.preserve_recent_skill_tokens_per_skill,
    )


def _create_todo_list_middleware(is_plan_mode: bool) -> TodoMiddleware | None:
    """Create and configure the TodoList middleware.

    Args:
        is_plan_mode: Whether to enable plan mode with TodoList middleware.

    Returns:
        TodoMiddleware instance if plan mode is enabled, None otherwise.
    """
    if not is_plan_mode:
        return None

    # Custom prompts matching DeerFlow's style
    system_prompt = """
<todo_list_system>
You have access to the `write_todos` tool to help you manage and track complex multi-step objectives.

**CRITICAL RULES:**
- Mark todos as completed IMMEDIATELY after finishing each step - do NOT batch completions
- Keep EXACTLY ONE task as `in_progress` at any time (unless tasks can run in parallel)
- Update the todo list in REAL-TIME as you work - this gives users visibility into your progress
- DO NOT use this tool for simple tasks (< 3 steps) - just complete them directly

**When to Use:**
This tool is designed for complex objectives that require systematic tracking:
- Complex multi-step tasks requiring 3+ distinct steps
- Non-trivial tasks needing careful planning and execution
- User explicitly requests a todo list
- User provides multiple tasks (numbered or comma-separated list)
- The plan may need revisions based on intermediate results

**When NOT to Use:**
- Single, straightforward tasks
- Trivial tasks (< 3 steps)
- Purely conversational or informational requests
- Simple tool calls where the approach is obvious

**Best Practices:**
- Break down complex tasks into smaller, actionable steps
- Use clear, descriptive task names
- Remove tasks that become irrelevant
- Add new tasks discovered during implementation
- Don't be afraid to revise the todo list as you learn more

**Task Management:**
Writing todos takes time and tokens - use it when helpful for managing complex problems, not for simple requests.
</todo_list_system>
"""

    tool_description = """Use this tool to create and manage a structured task list for complex work sessions.

**IMPORTANT: Only use this tool for complex tasks (3+ steps). For simple requests, just do the work directly.**

## When to Use

Use this tool in these scenarios:
1. **Complex multi-step tasks**: When a task requires 3 or more distinct steps or actions
2. **Non-trivial tasks**: Tasks requiring careful planning or multiple operations
3. **User explicitly requests todo list**: When the user directly asks you to track tasks
4. **Multiple tasks**: When users provide a list of things to be done
5. **Dynamic planning**: When the plan may need updates based on intermediate results

## When NOT to Use

Skip this tool when:
1. The task is straightforward and takes less than 3 steps
2. The task is trivial and tracking provides no benefit
3. The task is purely conversational or informational
4. It's clear what needs to be done and you can just do it

## How to Use

1. **Starting a task**: Mark it as `in_progress` BEFORE beginning work
2. **Completing a task**: Mark it as `completed` IMMEDIATELY after finishing
3. **Updating the list**: Add new tasks, remove irrelevant ones, or update descriptions as needed
4. **Multiple updates**: You can make several updates at once (e.g., complete one task and start the next)

## Task States

- `pending`: Task not yet started
- `in_progress`: Currently working on (can have multiple if tasks run in parallel)
- `completed`: Task finished successfully

## Task Completion Requirements

**CRITICAL: Only mark a task as completed when you have FULLY accomplished it.**

Never mark a task as completed if:
- There are unresolved issues or errors
- Work is partial or incomplete
- You encountered blockers preventing completion
- You couldn't find necessary resources or dependencies
- Quality standards haven't been met

If blocked, keep the task as `in_progress` and create a new task describing what needs to be resolved.

## Best Practices

- Create specific, actionable items
- Break complex tasks into smaller, manageable steps
- Use clear, descriptive task names
- Update task status in real-time as you work
- Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
- Remove tasks that are no longer relevant
- **IMPORTANT**: When you write the todo list, mark your first task(s) as `in_progress` immediately
- **IMPORTANT**: Unless all tasks are completed, always have at least one task `in_progress` to show progress

Being proactive with task management demonstrates thoroughness and ensures all requirements are completed successfully.

**Remember**: If you only need a few tool calls to complete a task and it's clear what to do, it's better to just do the task directly and NOT use this tool at all.
"""

    return TodoMiddleware(system_prompt=system_prompt, tool_description=tool_description)


# ThreadDataMiddleware must be before SandboxMiddleware to ensure thread_id is available
# UploadsMiddleware should be after ThreadDataMiddleware to access thread_id
# DanglingToolCallMiddleware patches missing ToolMessages before model sees the history
# SummarizationMiddleware should be early to reduce context before other processing
# TodoListMiddleware should be before ClarificationMiddleware to allow todo management
# TitleMiddleware generates title after first exchange
# MemoryMiddleware queues conversation for memory update (after TitleMiddleware)
# ViewImageMiddleware should be before ClarificationMiddleware to inject image details before LLM
# ToolErrorHandlingMiddleware should be before ClarificationMiddleware to convert tool exceptions to ToolMessages
# ClarificationMiddleware should be last to intercept clarification requests after model calls
def _build_middlewares(
    config: RunnableConfig,
    model_name: str | None,
    agent_name: str | None = None,
    custom_middlewares: list[AgentMiddleware] | None = None,
    *,
    app_config: AppConfig | None = None,
):
    """Build middleware chain based on runtime configuration.

    Args:
        config: Runtime configuration containing configurable options like is_plan_mode.
        agent_name: If provided, MemoryMiddleware will use per-agent memory storage.
        custom_middlewares: Optional list of custom middlewares to inject into the chain.

    Returns:
        List of middleware instances.
    """
    resolved_app_config = app_config or get_app_config()
    middlewares = build_lead_runtime_middlewares(app_config=resolved_app_config, lazy_init=True)

    # Always inject current date (and optionally memory) as <system-reminder> into the
    # first HumanMessage to keep the system prompt fully static for prefix-cache reuse.
    from deerflow.agents.middlewares.dynamic_context_middleware import DynamicContextMiddleware

    middlewares.append(DynamicContextMiddleware(agent_name=agent_name, app_config=resolved_app_config))

    # Add summarization middleware if enabled
    summarization_middleware = _create_summarization_middleware(app_config=resolved_app_config)
    if summarization_middleware is not None:
        middlewares.append(summarization_middleware)

    # Add TodoList middleware if plan mode is enabled
    cfg = _get_runtime_config(config)
    is_plan_mode = cfg.get("is_plan_mode", False)
    todo_list_middleware = _create_todo_list_middleware(is_plan_mode)
    if todo_list_middleware is not None:
        middlewares.append(todo_list_middleware)

    # Add TokenUsageMiddleware when token_usage tracking is enabled
    if resolved_app_config.token_usage.enabled:
        middlewares.append(TokenUsageMiddleware())

    # Add TitleMiddleware
    if not _should_skip_title_middleware(agent_name=agent_name, runtime_config=cfg):
        middlewares.append(TitleMiddleware(app_config=resolved_app_config))

    # Add MemoryMiddleware (after TitleMiddleware)
    middlewares.append(MemoryMiddleware(agent_name=agent_name, memory_config=resolved_app_config.memory))

    # Add ViewImageMiddleware only if the current model supports vision.
    # Use the resolved runtime model_name from make_lead_agent to avoid stale config values.
    model_config = resolved_app_config.get_model_config(model_name) if model_name else None
    if model_config is not None and model_config.supports_vision:
        middlewares.append(ViewImageMiddleware())

    # Add DeferredToolFilterMiddleware to hide deferred tool schemas from model binding
    if resolved_app_config.tool_search.enabled:
        from deerflow.agents.middlewares.deferred_tool_filter_middleware import DeferredToolFilterMiddleware

        middlewares.append(DeferredToolFilterMiddleware())

    # Add SubagentLimitMiddleware to truncate excess parallel task calls
    subagent_enabled = cfg.get("subagent_enabled", False)
    if subagent_enabled:
        max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)
        middlewares.append(SubagentLimitMiddleware(max_concurrent=max_concurrent_subagents))

    # LoopDetectionMiddleware — detect and break repetitive tool call loops
    loop_detection_config = resolved_app_config.loop_detection
    if loop_detection_config.enabled:
        middlewares.append(LoopDetectionMiddleware.from_config(loop_detection_config))

    # Inject custom middlewares before ClarificationMiddleware
    if custom_middlewares:
        middlewares.extend(custom_middlewares)

    # SafetyFinishReasonMiddleware — suppress tool execution when the provider
    # safety-terminated the response. Registered after custom middlewares so
    # that LangChain's reverse-order after_model dispatch runs Safety first;
    # cleared tool_calls then flow through Loop/Subagent accounting without
    # firing extra alarms. See safety_finish_reason_middleware.py docstring.
    safety_config = resolved_app_config.safety_finish_reason
    if safety_config.enabled:
        middlewares.append(SafetyFinishReasonMiddleware.from_config(safety_config))

    # ClarificationMiddleware should always be last
    middlewares.append(ClarificationMiddleware())
    return middlewares


def _available_skill_names(agent_config, is_bootstrap: bool) -> set[str] | None:
    if is_bootstrap:
        return {"bootstrap"}
    if agent_config and agent_config.skills is not None:
        return set(agent_config.skills)
    return None


def _load_enabled_skills_for_tool_policy(available_skills: set[str] | None, *, app_config: AppConfig) -> list[Skill]:
    try:
        from deerflow.agents.lead_agent.prompt import get_enabled_skills_for_config

        skills = get_enabled_skills_for_config(app_config)
    except Exception:
        logger.exception("Failed to load skills for allowed-tools policy")
        raise

    if available_skills is None:
        return skills
    return [skill for skill in skills if skill.name in available_skills]


def _filter_hr_boss_recommendation_tools(tools: list, *, agent_name: str | None, runtime_config: dict) -> list:
    if agent_name != _HR_BOSS_AGENT_NAME:
        return tools
    if runtime_config.get("hr_boss_recommendation_fast_path") is not True:
        return tools
    return [tool for tool in tools if getattr(tool, "name", "") not in _HR_BOSS_RECOMMENDATION_SLOW_TOOLS]


def _text2cypher_payload_from_tool_result(value) -> dict | None:
    if isinstance(value, tuple) and value:
        value = value[0]
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                try:
                    parsed = json.loads(item["text"])
                except json.JSONDecodeError:
                    continue
                return parsed if isinstance(parsed, dict) else None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    if isinstance(value, dict):
        return value
    return None


def _first_text(values) -> str:
    if not isinstance(values, list):
        return ""
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _format_hr_boss_recommendation_record(record: dict, *, label: str) -> list[str]:
    employee_name = str(record.get("employee_name") or "候选人").strip()
    employee_id = str(record.get("employee_id") or "").strip()
    title = f"{label}：{employee_name}"
    if employee_id:
        title += f"（{employee_id}）"

    lines = [title]
    department = str(record.get("current_department") or "").strip()
    position = str(record.get("current_position") or "").strip()
    tenure = record.get("tenure_years")
    role_parts = [part for part in (department, position) if part]
    if role_parts:
        role_line = "，".join(role_parts)
        if tenure is not None:
            role_line += f"，司龄约{tenure:g}年" if isinstance(tenure, (int, float)) else f"，司龄{tenure}"
        lines.append(f"- {role_line}")

    school = _first_text(record.get("schools"))
    major = _first_text(record.get("majors"))
    degree = _first_text(record.get("degrees"))
    education = "".join(part for part in (school, major, degree) if part)
    if education:
        lines.append(f"- {education}背景")

    title_name = _first_text(record.get("title_names"))
    project = _first_text(record.get("related_project_experiences"))
    if project:
        project = project.replace(" as  ()", "").replace(" ()", "").strip()
        lines.append(f"- 相关项目：{project}")
    elif title_name:
        lines.append(f"- 职称：{title_name}")

    return lines[:4]


def _format_hr_boss_recommendation_answer(value) -> str:
    payload = _text2cypher_payload_from_tool_result(value)
    if not payload:
        return "已完成查询，但结果格式无法直接转写，请稍后重试或缩小推荐条件。"
    if payload.get("status") != "success" or payload.get("answerable") is False:
        return str(payload.get("limitation") or "当前条件下没有形成可靠推荐结果，需要先补充岗位范围或筛选条件。")

    execution = payload.get("execution")
    records = execution.get("records") if isinstance(execution, dict) else None
    if not isinstance(records, list) or not records:
        return "当前条件下没有查到可推荐的瓷粉研发候选人。"

    lines: list[str] = []
    lines.extend(_format_hr_boss_recommendation_record(records[0], label="首推"))
    for record in records[1:3]:
        lines.append("")
        lines.extend(_format_hr_boss_recommendation_record(record, label="备选"))
    lines.append("")
    lines.append("说明：按集团当前在职员工中瓷粉、陶瓷、材料研发相关证据排序；正式任用前建议再核实带团队经历。")
    return "\n".join(lines)


def _hr_boss_recommendation_direct_message(answer: str, runtime: ToolRuntime) -> ToolMessage:
    return ToolMessage(
        content=answer,
        tool_call_id=runtime.tool_call_id,
        additional_kwargs={
            "display_as_assistant": True,
            "hr_boss_recommendation_fast_path": True,
        },
    )


def _wrap_hr_boss_recommendation_direct_tool(tool: BaseTool) -> BaseTool:
    def _run(runtime: ToolRuntime, **kwargs):
        answer = _format_hr_boss_recommendation_answer(tool.invoke(kwargs))
        return _hr_boss_recommendation_direct_message(answer, runtime)

    async def _arun(runtime: ToolRuntime, **kwargs):
        answer = _format_hr_boss_recommendation_answer(await tool.ainvoke(kwargs))
        return _hr_boss_recommendation_direct_message(answer, runtime)

    return StructuredTool.from_function(
        func=_run,
        coroutine=_arun,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        return_direct=True,
    )


def _apply_hr_boss_recommendation_direct_tools(tools: list, *, agent_name: str | None, runtime_config: dict) -> list:
    if agent_name != _HR_BOSS_AGENT_NAME:
        return tools
    if runtime_config.get("hr_boss_recommendation_fast_path") is not True:
        return tools
    return [
        _wrap_hr_boss_recommendation_direct_tool(tool)
        if getattr(tool, "name", "") == _TEXT2CYPHER_ANSWER_TOOL_NAME
        else tool
        for tool in tools
    ]


def _should_skip_title_middleware(*, agent_name: str | None, runtime_config: dict) -> bool:
    return agent_name == _HR_BOSS_AGENT_NAME and runtime_config.get("hr_boss_recommendation_fast_path") is True


def _model_kwargs_for_runtime(*, agent_name: str | None, runtime_config: dict, reasoning_effort: str | None) -> dict:
    kwargs = {}
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    if agent_name == _HR_BOSS_AGENT_NAME and runtime_config.get("hr_boss_recommendation_fast_path") is True:
        kwargs["max_tokens"] = _HR_BOSS_RECOMMENDATION_MAX_TOKENS
    return kwargs


def make_lead_agent(config: RunnableConfig):
    """LangGraph graph factory; keep the signature compatible with LangGraph Server."""
    runtime_config = _get_runtime_config(config)
    runtime_app_config = runtime_config.get("app_config")
    return _make_lead_agent(config, app_config=runtime_app_config or get_app_config())


def _make_lead_agent(config: RunnableConfig, *, app_config: AppConfig):
    # Lazy import to avoid circular dependency
    from deerflow.tools import get_available_tools
    from deerflow.tools.builtins import setup_agent, update_agent

    cfg = _get_runtime_config(config)
    resolved_app_config = app_config

    thinking_enabled = cfg.get("thinking_enabled", True)
    reasoning_effort = cfg.get("reasoning_effort", None)
    requested_model_name: str | None = cfg.get("model_name") or cfg.get("model")
    is_plan_mode = cfg.get("is_plan_mode", False)
    subagent_enabled = cfg.get("subagent_enabled", False)
    max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)
    is_bootstrap = cfg.get("is_bootstrap", False)
    agent_name = validate_agent_name(cfg.get("agent_name"))

    agent_config = load_agent_config(agent_name) if not is_bootstrap else None
    available_skills = _available_skill_names(agent_config, is_bootstrap)
    effective_mcp_servers = cfg.get("effective_mcp_servers")
    if effective_mcp_servers is None and agent_config and agent_config.mcp_servers is not None:
        effective_mcp_servers = agent_config.mcp_servers
    effective_allowed_tools = cfg.get("effective_allowed_tools")
    if effective_allowed_tools is None and agent_config and agent_config.allowed_tools is not None:
        effective_allowed_tools = agent_config.allowed_tools
    # Custom agent model from agent config (if any), or None to let _resolve_model_name pick the default
    agent_model_name = agent_config.model if agent_config and agent_config.model else None

    # Final model name resolution: request → agent config → global default, with fallback for unknown names
    model_name = _resolve_model_name(requested_model_name or agent_model_name, app_config=resolved_app_config)

    model_config = resolved_app_config.get_model_config(model_name)

    if model_config is None:
        raise ValueError("No chat model could be resolved. Please configure at least one model in config.yaml or provide a valid 'model_name'/'model' in the request.")
    if thinking_enabled and not model_config.supports_thinking:
        logger.warning(f"Thinking mode is enabled but model '{model_name}' does not support it; fallback to non-thinking mode.")
        thinking_enabled = False

    logger.info(
        "Create Agent(%s) -> thinking_enabled: %s, reasoning_effort: %s, model_name: %s, is_plan_mode: %s, subagent_enabled: %s, max_concurrent_subagents: %s",
        agent_name or "default",
        thinking_enabled,
        reasoning_effort,
        model_name,
        is_plan_mode,
        subagent_enabled,
        max_concurrent_subagents,
    )

    # Inject run metadata for LangSmith trace tagging
    if "metadata" not in config:
        config["metadata"] = {}

    config["metadata"].update(
        {
            "agent_name": agent_name or "default",
            "model_name": model_name or "default",
            "thinking_enabled": thinking_enabled,
            "reasoning_effort": reasoning_effort,
            "is_plan_mode": is_plan_mode,
            "subagent_enabled": subagent_enabled,
            "tool_groups": agent_config.tool_groups if agent_config else None,
            "allowed_tools": effective_allowed_tools,
            "available_skills": sorted(available_skills) if available_skills is not None else None,
        }
    )

    # Inject tracing callbacks at the graph invocation root so a single LangGraph
    # run produces one trace with all node / LLM / tool calls as child spans,
    # AND so the Langfuse handler sees ``on_chain_start(parent_run_id=None)`` and
    # actually propagates ``langfuse_session_id`` / ``langfuse_user_id`` from
    # ``config["metadata"]`` onto the trace. Without root-level attachment the
    # model is a nested observation and the handler strips ``langfuse_*`` keys.
    tracing_callbacks = build_tracing_callbacks()
    if tracing_callbacks:
        existing = config.get("callbacks") or []
        if not isinstance(existing, list):
            existing = list(existing)
        config["callbacks"] = [*existing, *tracing_callbacks]

    skills_for_tool_policy = _load_enabled_skills_for_tool_policy(available_skills, app_config=resolved_app_config)

    if is_bootstrap:
        # Special bootstrap agent with minimal prompt for initial custom agent creation flow
        bootstrap_tool_kwargs = {
            "model_name": model_name,
            "subagent_enabled": subagent_enabled,
            "app_config": resolved_app_config,
        }
        if effective_mcp_servers is not None:
            bootstrap_tool_kwargs["mcp_servers"] = effective_mcp_servers
        if effective_allowed_tools is not None:
            bootstrap_tool_kwargs["allowed_tools"] = effective_allowed_tools
        tools = get_available_tools(**bootstrap_tool_kwargs) + [setup_agent]
        return create_agent(
            model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled, app_config=resolved_app_config, attach_tracing=False),
            tools=filter_tools_by_skill_allowed_tools(tools, skills_for_tool_policy),
            middleware=_build_middlewares(config, model_name=model_name, app_config=resolved_app_config),
            system_prompt=apply_prompt_template(
                subagent_enabled=subagent_enabled,
                max_concurrent_subagents=max_concurrent_subagents,
                available_skills=set(["bootstrap"]),
                app_config=resolved_app_config,
            ),
            state_schema=ThreadState,
        )

    # Custom agents can update their own SOUL.md / config via update_agent.
    # The default agent (no agent_name) does not see this tool.
    extra_tools = []
    if agent_name and (effective_allowed_tools is None or "update_agent" in effective_allowed_tools):
        extra_tools.append(update_agent)
    # Default lead agent (unchanged behavior)
    tool_kwargs = {
        "model_name": model_name,
        "groups": agent_config.tool_groups if agent_config else None,
        "subagent_enabled": subagent_enabled,
        "app_config": resolved_app_config,
    }
    if effective_mcp_servers is not None:
        tool_kwargs["mcp_servers"] = effective_mcp_servers
    if effective_allowed_tools is not None:
        tool_kwargs["allowed_tools"] = effective_allowed_tools
    tools = get_available_tools(**tool_kwargs)
    tools = _filter_hr_boss_recommendation_tools(tools, agent_name=agent_name, runtime_config=cfg)
    extra_tools = _filter_hr_boss_recommendation_tools(extra_tools, agent_name=agent_name, runtime_config=cfg)
    tools = _apply_hr_boss_recommendation_direct_tools(tools, agent_name=agent_name, runtime_config=cfg)
    model_kwargs = _model_kwargs_for_runtime(agent_name=agent_name, runtime_config=cfg, reasoning_effort=reasoning_effort)
    return create_agent(
        model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled, app_config=resolved_app_config, attach_tracing=False, **model_kwargs),
        tools=filter_tools_by_skill_allowed_tools(tools + extra_tools, skills_for_tool_policy),
        middleware=_build_middlewares(config, model_name=model_name, agent_name=agent_name, app_config=resolved_app_config),
            system_prompt=apply_prompt_template(
                subagent_enabled=subagent_enabled,
                max_concurrent_subagents=max_concurrent_subagents,
                agent_name=agent_name,
                available_skills=set(agent_config.skills) if agent_config and agent_config.skills is not None else None,
                app_config=resolved_app_config,
                hr_boss_recommendation_fast_path=agent_name == _HR_BOSS_AGENT_NAME and cfg.get("hr_boss_recommendation_fast_path") is True,
            ),
            state_schema=ThreadState,
        )
