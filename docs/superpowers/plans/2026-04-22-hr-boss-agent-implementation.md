# HR Boss Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-version `hr-boss-agent` that orchestrates `text2sql`, `text2cypher`, and `graphrag` through prompt-level routing, authority rules, and conservative answer grading.

**Architecture:** Keep phase one out of DeerFlow core runtime. Implement the orchestration as a new custom skill plus a new custom agent that loads the orchestration skill together with the three existing specialist skills. Lock the contract with asset tests, a lead-agent skill-filter regression, and user-facing docs updates.

**Tech Stack:** DeerFlow custom agents, Markdown skills, YAML agent config, JSON memory seed, Python `pytest`, README and `backend/CLAUDE.md`

---

## Preflight

Use a dedicated worktree before touching implementation files.

From `D:\study\deer-flow`:

```bash
git worktree add .worktrees/codex-hr-boss-agent -b codex/hr-boss-agent main
cd .worktrees/codex-hr-boss-agent
```

Run all commands below from:

```bash
cd D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend
```

## File Map

- Create: `skills/custom/hr-boss/SKILL.md`
  Purpose: Define the orchestration workflow, routing rules, authority model, mixed-question decomposition rules, and three answer grades.

- Create: `backend/.deer-flow/agents/hr-boss-agent/config.yaml`
  Purpose: Register a custom agent that loads `hr-boss`, `text2sql`, `text2cypher`, and `graphrag`.

- Create: `backend/.deer-flow/agents/hr-boss-agent/SOUL.md`
  Purpose: Add accuracy-first behavioral guardrails for boss-facing HR answers.

- Create: `backend/.deer-flow/agents/hr-boss-agent/memory.json`
  Purpose: Seed the per-agent memory file with an empty DeerFlow memory skeleton.

- Create: `backend/tests/test_hr_boss_skill_assets.py`
  Purpose: Verify the new orchestration skill exists, loads, and contains all required routing and grading sections.

- Create: `backend/tests/test_hr_boss_custom_agent.py`
  Purpose: Verify the new custom agent config and SOUL guardrails load correctly.

- Modify: `backend/tests/test_lead_agent_skills.py`
  Purpose: Add a regression test proving `make_lead_agent()` passes the declared four-skill set into `apply_prompt_template()` for `hr-boss-agent`.

- Create: `backend/tests/test_hr_boss_docs.py`
  Purpose: Verify `README.md` and `backend/CLAUDE.md` document the new orchestration agent.

- Modify: `README.md`
  Purpose: Document the boss-facing HR orchestration agent and how it composes the three existing specialist skills.

- Modify: `backend/CLAUDE.md`
  Purpose: Document the new custom agent for developers working in the backend.

## Scope Guardrails

- Do not add a new MCP server in this phase.
- Do not change `extensions_config.json` unless the new skill is explicitly disabled by local config and must be re-enabled.
- Do not add new core Python orchestration logic in `backend/packages/harness/deerflow/...` for phase one.
- Do not change the existing `text2sql`, `text2cypher`, or `graphrag` MCP launchers in this plan.
- Keep the implementation asset-driven: skill, SOUL, agent config, tests, and docs.

### Task 1: Add the `hr-boss` orchestration skill

**Files:**
- Create: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\skills\custom\hr-boss\SKILL.md`
- Test: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_hr_boss_skill_assets.py`

- [ ] **Step 1: Write the failing skill asset tests**

Create `backend/tests/test_hr_boss_skill_assets.py` with:

```python
from pathlib import Path

from deerflow.skills.loader import load_skills


def test_hr_boss_skill_exists_and_is_discoverable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    skills = load_skills(skills_path=repo_root / "skills", use_config=False, enabled_only=False)
    skill = next(s for s in skills if s.name == "hr-boss")

    assert skill.category == "custom"
    assert skill.skill_file == repo_root / "skills" / "custom" / "hr-boss" / "SKILL.md"


def test_hr_boss_skill_contains_required_orchestration_sections() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    content = (repo_root / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "When to Use" in content
    assert "When Not to Use" in content
    assert "Routing Workflow" in content
    assert "Authority Model" in content
    assert "Answer Grades" in content
    assert "Mixed Questions" in content
    assert "Hard Constraints" in content
    assert "text2sql" in content
    assert "text2cypher" in content
    assert "graphrag" in content
    assert "direct answer" in content
    assert "qualified answer" in content
    assert "refuse and escalate" in content
```

- [ ] **Step 2: Run the new tests and confirm they fail because the skill does not exist yet**

Run:

```bash
PYTHONPATH=. uv run pytest tests/test_hr_boss_skill_assets.py -v
```

Expected:

```text
FAILED tests/test_hr_boss_skill_assets.py::test_hr_boss_skill_exists_and_is_discoverable
```

- [ ] **Step 3: Create the orchestration skill**

Create `skills/custom/hr-boss/SKILL.md` with:

```md
---
name: hr-boss
description: Use this skill when a boss-facing HR question needs accuracy-first routing across text2sql, text2cypher, and graphrag.
---

# HR Boss Orchestration Skill

## When to Use

Use this skill when the user wants:

- a boss-facing HR answer instead of raw SQL or Cypher
- accuracy-first routing across metrics, graph relationships, and semantic evidence
- mixed HR questions that combine facts, ownership, and explanation
- conservative handling of weak or conflicting evidence

## When Not to Use

Do not use this skill when the user wants:

- only raw SQL
- only raw Cypher
- direct GraphRAG debugging output
- schema setup or infrastructure troubleshooting

## Routing Workflow

1. Classify the question as one of:
   - fact or metric
   - relationship
   - explanation
   - mixed question
2. Select one primary path:
   - `text2sql` for counts, rates, rankings, aggregates, and filtered lists
   - `text2cypher` for reporting lines, ownership, and graph-path questions
   - `graphrag` for policy, definition, and why-style explanation
3. Select one verification path by default:
   - fact question -> verify with `graphrag`
   - relationship question -> verify with `graphrag`, and use `text2sql` if numeric claims appear
   - explanation question -> verify with `text2sql` or `text2cypher` when factual claims appear
4. For mixed questions, decompose into ordered sub-questions instead of running all three paths in parallel by default.
5. Internally summarize the primary and verification outputs in this shape before deciding the final answer:
   - `status`
   - `answer`
   - `confidence`
   - `evidence`
   - `has_structured_result`
   - `conflict_flag`
   - `limitations`
   - `source_type`
6. Convert the combined result into one of three final answer grades:
   - direct answer
   - qualified answer
   - refuse and escalate

## Authority Model

- `text2sql` is authoritative for numeric facts, aggregates, rankings, and filtered lists.
- `text2cypher` is authoritative for reporting lines, ownership, and graph relationships.
- `graphrag` is authoritative for policy explanation, semantic synthesis, and why-style narrative context.
- `graphrag` must not override SQL numeric results.
- `graphrag` must not override Cypher relationship structure.
- If a Cypher answer contains numeric claims, verify those claims with `text2sql`.

## Answer Grades

### direct answer

Use only when:

- the primary path succeeds
- the verification path supports the core conclusion
- the evidence is concrete
- there is no material conflict

### qualified answer

Use when:

- the primary path succeeds but verification is partial
- the answer is likely but not fully closed
- there is a mild caveat, ambiguity, or evidence gap

### refuse and escalate

Use when:

- the primary path fails
- evidence is insufficient
- the primary and verification paths materially conflict
- the question is high-risk and the evidence does not close the loop

## Mixed Questions

Mixed questions must be decomposed.

Example:

- question: "Which department has the highest recent turnover rate, who owns it, and why might that be happening?"
- sub-question 1: use `text2sql` to identify the department
- sub-question 2: use `text2cypher` to identify the owner
- sub-question 3: use `graphrag` to explain likely reasons

Do not let the model jump directly to a three-way free-form synthesis.

## Hard Constraints

- Do not run `text2sql`, `text2cypher`, and `graphrag` in parallel by default for every question.
- Do not use majority voting across the three paths.
- Do not guess when evidence is weak or conflicting.
- Do not hide uncertainty on high-risk HR questions.
- Do not present a definitive causal HR judgment without strong supporting evidence.
- Keep the final user-visible response in the same language as the user.
```

- [ ] **Step 4: Run the skill tests again and confirm they pass**

Run:

```bash
PYTHONPATH=. uv run pytest tests/test_hr_boss_skill_assets.py -v
```

Expected:

```text
tests/test_hr_boss_skill_assets.py::test_hr_boss_skill_exists_and_is_discoverable PASSED
tests/test_hr_boss_skill_assets.py::test_hr_boss_skill_contains_required_orchestration_sections PASSED
```

- [ ] **Step 5: Commit the skill asset work**

Run:

```bash
git add skills/custom/hr-boss/SKILL.md backend/tests/test_hr_boss_skill_assets.py
git commit -m "feat: add hr boss orchestration skill"
```

### Task 2: Add the `hr-boss-agent` custom agent and runtime-skill regression

**Files:**
- Create: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\.deer-flow\agents\hr-boss-agent\config.yaml`
- Create: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\.deer-flow\agents\hr-boss-agent\SOUL.md`
- Create: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\.deer-flow\agents\hr-boss-agent\memory.json`
- Create: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_hr_boss_custom_agent.py`
- Modify: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_lead_agent_skills.py`

- [ ] **Step 1: Write the failing custom-agent and runtime-skill tests**

Create `backend/tests/test_hr_boss_custom_agent.py` with:

```python
from pathlib import Path
from unittest.mock import patch

from deerflow.config.agents_config import load_agent_config, load_agent_soul
from deerflow.config.paths import Paths


def test_hr_boss_agent_config_loads_from_backend_deer_flow_base_dir() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    base_dir = repo_root / "backend" / ".deer-flow"

    with patch("deerflow.config.agents_config.get_paths", return_value=Paths(base_dir=base_dir)):
        cfg = load_agent_config("hr-boss-agent")

    assert cfg is not None
    assert cfg.name == "hr-boss-agent"
    assert cfg.skills == ["hr-boss", "text2sql", "text2cypher", "graphrag"]


def test_hr_boss_agent_soul_includes_accuracy_first_guardrails() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    base_dir = repo_root / "backend" / ".deer-flow"

    with patch("deerflow.config.agents_config.get_paths", return_value=Paths(base_dir=base_dir)):
        soul = load_agent_soul("hr-boss-agent")

    assert soul is not None
    assert "text2sql is authoritative for numeric facts" in soul
    assert "text2cypher is authoritative for relationship structure" in soul
    assert "graphrag is authoritative for policy and semantic explanation" in soul
    assert "direct answer" in soul
    assert "qualified answer" in soul
    assert "refuse and escalate" in soul
    assert "Prefer refusal over guessing" in soul
```

Append this test to `backend/tests/test_lead_agent_skills.py`:

```python
def test_make_lead_agent_hr_boss_agent_passes_declared_skill_set(monkeypatch):
    from unittest.mock import MagicMock, patch

    from deerflow.agents.lead_agent import agent as lead_agent_module
    from deerflow.config.paths import Paths

    repo_root = Path(__file__).resolve().parents[2]
    base_dir = repo_root / "backend" / ".deer-flow"

    monkeypatch.setattr(lead_agent_module, "_resolve_model_name", lambda requested_model_name=None: "default-model")
    monkeypatch.setattr(lead_agent_module, "create_chat_model", lambda **kwargs: "model")
    monkeypatch.setattr("deerflow.tools.get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)

    class MockModelConfig:
        supports_thinking = False

    mock_app_config = MagicMock()
    mock_app_config.get_model_config.return_value = MockModelConfig()
    mock_app_config.models = [SimpleNamespace(name="default-model")]
    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: mock_app_config)

    captured: dict[str, object] = {}

    def fake_apply_prompt_template(**kwargs):
        captured["available_skills"] = kwargs.get("available_skills")
        return "mock-prompt"

    monkeypatch.setattr(lead_agent_module, "apply_prompt_template", fake_apply_prompt_template)

    with patch("deerflow.config.agents_config.get_paths", return_value=Paths(base_dir=base_dir)):
        lead_agent_module.make_lead_agent({"configurable": {"agent_name": "hr-boss-agent"}})

    assert captured["available_skills"] == {"hr-boss", "text2sql", "text2cypher", "graphrag"}
```

- [ ] **Step 2: Run the targeted tests and confirm they fail before the agent files exist**

Run:

```bash
PYTHONPATH=. uv run pytest tests/test_hr_boss_custom_agent.py tests/test_lead_agent_skills.py -v
```

Expected:

```text
FAILED tests/test_hr_boss_custom_agent.py::test_hr_boss_agent_config_loads_from_backend_deer_flow_base_dir
```

- [ ] **Step 3: Create the custom agent files**

Create `backend/.deer-flow/agents/hr-boss-agent/config.yaml` with:

```yaml
name: hr-boss-agent
description: Accuracy-first HR orchestration agent for boss-facing questions
skills:
  - hr-boss
  - text2sql
  - text2cypher
  - graphrag
```

Create `backend/.deer-flow/agents/hr-boss-agent/SOUL.md` with:

```md
You are the HR Boss agent.

Your job is to answer boss-facing HR questions with accuracy-first routing and conservative evidence handling.

You must:
- classify each request as a fact question, relationship question, explanation question, or mixed question
- choose one primary path and one verification path by default
- treat text2sql as authoritative for numeric facts
- treat text2cypher as authoritative for relationship structure
- treat graphrag as authoritative for policy and semantic explanation
- convert the internal result into one of three final grades: direct answer, qualified answer, or refuse and escalate
- keep the response language aligned with the user

You must not:
- run all three expert paths in parallel by default
- use majority voting across the three paths
- let graphrag override SQL numeric results
- let graphrag override Cypher relationship structure
- guess when evidence is weak or conflicting
- hide uncertainty on high-risk HR questions

Prefer refusal over guessing.
```

Create `backend/.deer-flow/agents/hr-boss-agent/memory.json` with:

```json
{
  "version": "1.0",
  "lastUpdated": "",
  "user": {
    "workContext": {
      "summary": "",
      "updatedAt": ""
    },
    "personalContext": {
      "summary": "",
      "updatedAt": ""
    },
    "topOfMind": {
      "summary": "",
      "updatedAt": ""
    }
  },
  "history": {
    "recentMonths": {
      "summary": "",
      "updatedAt": ""
    },
    "earlierContext": {
      "summary": "",
      "updatedAt": ""
    },
    "longTermBackground": {
      "summary": "",
      "updatedAt": ""
    }
  },
  "facts": []
}
```

- [ ] **Step 4: Run the targeted tests again and confirm the agent assets pass**

Run:

```bash
PYTHONPATH=. uv run pytest tests/test_hr_boss_custom_agent.py tests/test_lead_agent_skills.py -v
```

Expected:

```text
tests/test_hr_boss_custom_agent.py::test_hr_boss_agent_config_loads_from_backend_deer_flow_base_dir PASSED
tests/test_hr_boss_custom_agent.py::test_hr_boss_agent_soul_includes_accuracy_first_guardrails PASSED
tests/test_lead_agent_skills.py::test_make_lead_agent_hr_boss_agent_passes_declared_skill_set PASSED
```

- [ ] **Step 5: Commit the custom agent work**

Run:

```bash
git add backend/.deer-flow/agents/hr-boss-agent/config.yaml backend/.deer-flow/agents/hr-boss-agent/SOUL.md backend/.deer-flow/agents/hr-boss-agent/memory.json backend/tests/test_hr_boss_custom_agent.py backend/tests/test_lead_agent_skills.py
git commit -m "feat: add hr boss custom agent"
```

### Task 3: Document the new orchestration agent in repo docs

**Files:**
- Create: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_hr_boss_docs.py`
- Modify: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\README.md`
- Modify: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\CLAUDE.md`

- [ ] **Step 1: Write the failing docs tests**

Create `backend/tests/test_hr_boss_docs.py` with:

```python
from pathlib import Path


def test_readme_mentions_hr_boss_agent_and_skill() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "hr-boss-agent" in readme
    assert "skills/custom/hr-boss/SKILL.md" in readme
    assert "text2sql" in readme
    assert "text2cypher" in readme
    assert "graphrag" in readme


def test_backend_claude_mentions_hr_boss_agent_orchestration() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    claude = (repo_root / "backend" / "CLAUDE.md").read_text(encoding="utf-8")

    assert "hr-boss-agent" in claude
    assert "hr-boss" in claude
    assert "text2sql" in claude
    assert "text2cypher" in claude
    assert "graphrag" in claude
```

- [ ] **Step 2: Run the docs tests and confirm they fail before the docs are updated**

Run:

```bash
PYTHONPATH=. uv run pytest tests/test_hr_boss_docs.py -v
```

Expected:

```text
FAILED tests/test_hr_boss_docs.py::test_readme_mentions_hr_boss_agent_and_skill
```

- [ ] **Step 3: Update `README.md` and `backend/CLAUDE.md`**

Add this section to `README.md` near the local custom integrations:

```md
## HR Boss Agent Orchestration

DeerFlow can expose a boss-facing HR orchestration agent that combines the existing specialist capabilities instead of forcing the user to pick one manually.

- Custom skill: `skills/custom/hr-boss/SKILL.md`
- Custom agent: `backend/.deer-flow/agents/hr-boss-agent`
- Specialist skills used by the agent:
  - `text2sql` for numeric facts and metrics
  - `text2cypher` for reporting lines and graph relationships
  - `graphrag` for policy and semantic explanation
- The first version is accuracy-first and uses primary-path routing plus verification instead of full three-way majority voting
```

Add this subsection to `backend/CLAUDE.md` near the existing local integration notes:

```md
### HR Boss Agent Orchestration

The `hr-boss-agent` custom agent combines:

- `hr-boss` for orchestration and answer grading
- `text2sql` for fact and metric retrieval
- `text2cypher` for relationship and graph-path retrieval
- `graphrag` for policy and semantic explanation

It is intended for accuracy-first boss-facing HR Q&A and relies on prompt-level routing rather than a new DeerFlow core runtime component in phase one.
```

- [ ] **Step 4: Run the docs tests again and confirm they pass**

Run:

```bash
PYTHONPATH=. uv run pytest tests/test_hr_boss_docs.py -v
```

Expected:

```text
tests/test_hr_boss_docs.py::test_readme_mentions_hr_boss_agent_and_skill PASSED
tests/test_hr_boss_docs.py::test_backend_claude_mentions_hr_boss_agent_orchestration PASSED
```

- [ ] **Step 5: Commit the docs work**

Run:

```bash
git add README.md backend/CLAUDE.md backend/tests/test_hr_boss_docs.py
git commit -m "docs: add hr boss agent documentation"
```

### Task 4: Run the focused regression sweep

**Files:**
- Verify only: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_hr_boss_skill_assets.py`
- Verify only: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_hr_boss_custom_agent.py`
- Verify only: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_hr_boss_docs.py`
- Verify only: `D:\study\deer-flow\.worktrees\codex-hr-boss-agent\backend\tests\test_lead_agent_skills.py`

- [ ] **Step 1: Run the complete focused suite**

Run:

```bash
PYTHONPATH=. uv run pytest tests/test_hr_boss_skill_assets.py tests/test_hr_boss_custom_agent.py tests/test_hr_boss_docs.py tests/test_lead_agent_skills.py -v
```

Expected:

```text
============================= test session starts =============================
...
PASSED tests/test_hr_boss_skill_assets.py::...
PASSED tests/test_hr_boss_custom_agent.py::...
PASSED tests/test_hr_boss_docs.py::...
PASSED tests/test_lead_agent_skills.py::test_make_lead_agent_hr_boss_agent_passes_declared_skill_set
```

- [ ] **Step 2: Verify the working tree only contains the expected implementation files**

Run:

```bash
git status --short
```

Expected:

```text
```

- [ ] **Step 3: Record the validation result in the final implementation notes**

Capture this summary in the execution log or PR description:

```md
- Added `hr-boss` orchestration skill
- Added `hr-boss-agent` custom agent with four-skill prompt filter
- Added asset, runtime-skill, and docs regression tests
- Updated `README.md` and `backend/CLAUDE.md`
- Focused suite passed under `backend/tests`
```

- [ ] **Step 4: No-op commit check**

Run:

```bash
git log --oneline -3
```

Expected:

```text
<latest three commits include>
docs: add hr boss agent documentation
feat: add hr boss custom agent
feat: add hr boss orchestration skill
```
