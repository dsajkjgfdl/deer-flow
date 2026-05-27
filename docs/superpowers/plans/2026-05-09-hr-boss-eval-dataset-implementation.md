# HR Boss Evaluation Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reviewable HR boss evaluation dataset with separate exact-answer and logic-only tracks.

**Architecture:** Store the dataset under `docs/evaluation/hr-boss/` as two JSONL files plus README/rubric docs. Add one pytest validator in `backend/tests` that checks schema, counts, and coverage. Keep the two scorecards separate and do not compute a weighted total.

**Tech Stack:** Markdown, JSONL, Python 3.12, `pytest`, standard library `json` and `pathlib`.

---

## File Structure

Planned files and responsibilities:

- Create: `docs/evaluation/hr-boss/README.md`
  - Explains scope, source of truth, how to extend the dataset, and how to run validation.
- Create: `docs/evaluation/hr-boss/rubric.md`
  - Defines the two scoring tracks and the pass/fail rules.
- Create: `docs/evaluation/hr-boss/text2cypher.strict.jsonl`
  - Holds exact-answer items with strict gold labels.
- Create: `docs/evaluation/hr-boss/graphrag.logic.jsonl`
  - Holds logic-and-evidence items with uncertainty rules.
- Create: `backend/tests/test_hr_boss_eval_dataset.py`
  - Validates file existence, schema shape, sample counts, and category coverage.

The approved design spec is the source of truth for the schema:

- `docs/superpowers/specs/2026-05-09-hr-boss-eval-dataset-design.md`

---

### Task 1: Scaffold The Dataset Docs And Validator

**Files:**
- Create: `docs/evaluation/hr-boss/README.md`
- Create: `docs/evaluation/hr-boss/rubric.md`
- Create: `backend/tests/test_hr_boss_eval_dataset.py`

- [ ] **Step 1: Write the failing validator test**

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "docs" / "evaluation" / "hr-boss"


def test_hr_boss_eval_docs_exist() -> None:
    assert (DATA_DIR / "README.md").exists()
    assert (DATA_DIR / "rubric.md").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_eval_dataset.py::test_hr_boss_eval_docs_exist -v
```

Expected: FAIL because the evaluation docs directory does not exist yet.

- [ ] **Step 3: Write the dataset README and rubric**

`docs/evaluation/hr-boss/README.md`:

```markdown
# HR Boss Evaluation Dataset

This directory contains two separate evaluation tracks:

- `text2cypher.strict` for exact-answer evaluation
- `graphrag.logic` for logic-and-evidence evaluation

Source of truth:

- `docs/superpowers/specs/2026-05-09-hr-boss-eval-dataset-design.md`
- `docs/hr-agent-wecom-demo-script.md`
- reviewed HR graph snapshot identified by `snapshot_id`

Rules:

- Do not compute a composite weighted total score.
- Keep strict-answer and logic-only scoring separate.
- Use a frozen snapshot id for all gold answers in the first release.
```

`docs/evaluation/hr-boss/rubric.md`:

```markdown
# HR Boss Evaluation Rubric

## text2cypher.strict

- Exact numbers must match exactly.
- Sets must match after normalization.
- Ordered lists must preserve order.
- Boolean answers must be true or false only.
- A refusal is correct only when `allow_refusal` is true and the question is under-specified.

## graphrag.logic

- The answer must stay on topic.
- The answer must be consistent with the evidence.
- The answer must not invent exact statistics.
- The answer must state uncertainty when evidence is weak.
- The answer must not turn a qualitative summary into a false quantitative claim.
```

- [ ] **Step 4: Run the validator again**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_eval_dataset.py::test_hr_boss_eval_docs_exist -v
```

Expected: PASS.

- [ ] **Step 5: Commit the scaffold**

```powershell
cd D:\study\deer-flow
git add docs/evaluation/hr-boss/README.md docs/evaluation/hr-boss/rubric.md backend/tests/test_hr_boss_eval_dataset.py
git commit -m "docs: scaffold hr boss eval dataset"
```

### Task 2: Build The Strict Text2Cypher Track

**Files:**
- Create: `docs/evaluation/hr-boss/text2cypher.strict.jsonl`
- Modify: `backend/tests/test_hr_boss_eval_dataset.py`

- [ ] **Step 1: Extend the validator with strict-dataset checks**

```python
import json


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_text2cypher_strict_dataset_shape() -> None:
    records = _load_jsonl(DATA_DIR / "text2cypher.strict.jsonl")
    questions = {record["question"] for record in records}

    assert len(records) == 30
    assert len({record["id"] for record in records}) == 30
    assert {"count", "average", "ranking", "filter", "list", "set_intersection", "relationship_chain", "boolean_existence", "group_compare", "ambiguous_but_resolvable"} <= {
        record["category"] for record in records
    }
    assert {
        "福建火炬电子科技股份有限公司平均年龄是多少？",
        "福建火炬电子科技股份有限公司的高级工程师有哪些？",
        "福建火炬电子各部门员工数排名前十是什么？",
    } <= questions

    required_keys = {
        "id",
        "question",
        "category",
        "difficulty",
        "snapshot_id",
        "source",
        "expected_behavior",
        "review_status",
        "answer_type",
        "expected_answer",
        "normalization",
        "acceptable_aliases",
        "allow_refusal",
    }

    for record in records:
        assert required_keys <= set(record)
        assert record["review_status"] == "gold_reviewed"
        assert record["answer_type"] in {"number", "set", "ordered_list", "boolean"}
```

- [ ] **Step 2: Run the strict-track test to verify it fails**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_eval_dataset.py::test_text2cypher_strict_dataset_shape -v
```

Expected: FAIL because `text2cypher.strict.jsonl` does not exist yet.

- [ ] **Step 3: Populate the 30 exact-answer records**

Use the approved seed families from the design spec and keep the gold answers frozen to one snapshot:

- `count`
- `average`
- `ranking`
- `filter`
- `list`
- `set_intersection`
- `relationship_chain`
- `boolean_existence`
- `group_compare`
- `ambiguous_but_resolvable`

The strict track should include edge cases where a refusal is the correct outcome because the data is incomplete, but only when `allow_refusal` is explicitly true.

Required schema details for each record:

- `id`, `question`, `category`, `difficulty`, `snapshot_id`, `source`, `expected_behavior`, `review_status`
- `answer_type` must be one of `number`, `set`, `ordered_list`, or `boolean`
- `expected_answer` must be the reviewed gold answer from the frozen snapshot
- `normalization` must define the comparison rule for that record
- `acceptable_aliases` must stay empty unless the question truly allows aliases
- `allow_refusal` must be true only for under-specified questions
- [ ] **Step 4: Run the strict-track validator**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_eval_dataset.py::test_text2cypher_strict_dataset_shape -v
```

Expected: PASS.

- [ ] **Step 5: Commit the strict track**

```powershell
cd D:\study\deer-flow
git add docs/evaluation/hr-boss/text2cypher.strict.jsonl backend/tests/test_hr_boss_eval_dataset.py
git commit -m "data: add hr boss strict text2cypher set"
```

### Task 3: Build The GraphRAG Logic Track

**Files:**
- Create: `docs/evaluation/hr-boss/graphrag.logic.jsonl`
- Modify: `backend/tests/test_hr_boss_eval_dataset.py`

- [ ] **Step 1: Extend the validator with logic-track checks**

```python
def test_graphrag_logic_dataset_shape() -> None:
    records = _load_jsonl(DATA_DIR / "graphrag.logic.jsonl")
    questions = {record["question"] for record in records}

    assert len(records) == 15
    assert len({record["id"] for record in records}) == 15
    assert {"employee_profile", "org_portrait", "talent_structure", "trend_summary", "evidence_lookup", "cross_group_exploration", "reason_explanation", "risk_hint", "uncertain_but_honest"} <= {
        record["category"] for record in records
    }
    assert {
        "老王1366的教育和项目经历是什么？",
        "福建火炬电子科技股份有限公司的人才结构有什么特点？",
        "制造车间哪些群体可能存在经验断层？",
    } <= questions

    required_keys = {
        "id",
        "question",
        "category",
        "difficulty",
        "snapshot_id",
        "source",
        "expected_behavior",
        "review_status",
        "must_include",
        "must_not_include",
        "evidence_requirements",
        "allow_uncertainty",
        "allowed_answer_shape",
    }

    for record in records:
        assert required_keys <= set(record)
        assert record["review_status"] == "logic_reviewed"
        assert isinstance(record["must_include"], list) and record["must_include"]
        assert isinstance(record["must_not_include"], list)
        assert isinstance(record["evidence_requirements"], dict)
```

- [ ] **Step 2: Run the logic-track test to verify it fails**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_eval_dataset.py::test_graphrag_logic_dataset_shape -v
```

Expected: FAIL because `graphrag.logic.jsonl` does not exist yet.

- [ ] **Step 3: Populate the 15 logic-only records**

Use the approved seed families from the design spec and keep the logic-only contract strict:

- `employee_profile`
- `org_portrait`
- `talent_structure`
- `trend_summary`
- `evidence_lookup`
- `cross_group_exploration`
- `reason_explanation`
- `risk_hint`
- `uncertain_but_honest`

The logic track must never be scored as if it were an exact-statistics dataset.

Required schema details for each record:

- `id`, `question`, `category`, `difficulty`, `snapshot_id`, `source`, `expected_behavior`, `review_status`
- `must_include` must name the concepts the answer should surface
- `must_not_include` must list claims that would invalidate the answer
- `evidence_requirements` must specify evidence and uncertainty constraints
- `allow_uncertainty` must reflect whether a qualified answer is acceptable
- `allowed_answer_shape` must match the intended response form
- [ ] **Step 4: Run the logic-track validator**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_eval_dataset.py::test_graphrag_logic_dataset_shape -v
```

Expected: PASS.

- [ ] **Step 5: Commit the logic track**

```powershell
cd D:\study\deer-flow
git add docs/evaluation/hr-boss/graphrag.logic.jsonl backend/tests/test_hr_boss_eval_dataset.py
git commit -m "data: add hr boss graphrag logic set"
```

### Task 4: Final Dataset Verification

**Files:**
- Read: `docs/evaluation/hr-boss/README.md`
- Read: `docs/evaluation/hr-boss/rubric.md`
- Read: `docs/evaluation/hr-boss/text2cypher.strict.jsonl`
- Read: `docs/evaluation/hr-boss/graphrag.logic.jsonl`

- [ ] **Step 1: Run the full dataset validator**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_eval_dataset.py -v
```

Expected: all dataset checks pass.

- [ ] **Step 2: Spot-check the seed coverage**

Verify that the approved seed questions from `docs/hr-agent-wecom-demo-script.md` are represented in one of the two files and that no sample introduces a weighted total score or route-score field.

- [ ] **Step 3: Commit any final doc-only adjustments**

```powershell
cd D:\study\deer-flow
git status --short
git add docs/evaluation/hr-boss
git commit -m "docs: finalize hr boss eval dataset"
```

## Self-Review

Checked against the approved spec:

- Separate scorecards are preserved.
- No composite weighted total score appears in the plan.
- `text2cypher` is planned as strict exact-answer evaluation.
- `graphrag` is planned as logic-and-evidence evaluation only.
- The seed coverage plan includes the approved question families and edge cases.
- The plan uses file-based JSONL data plus one pytest validator, which keeps the implementation small and reviewable.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-09-hr-boss-eval-dataset-implementation.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
