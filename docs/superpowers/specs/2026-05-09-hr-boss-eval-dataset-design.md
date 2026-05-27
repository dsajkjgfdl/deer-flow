# HR Boss Evaluation Dataset Design

## Summary

This design defines a small, reviewable evaluation dataset for `hr-boss-agent` with two separate scorecards:

- `text2cypher.strict` for exact-answer evaluation
- `graphrag.logic` for logic-and-evidence evaluation

The goal is to improve answer accuracy for boss-facing HR questions without forcing GraphRAG to satisfy statistical precision it is not designed to provide.

## Goals

- Measure `text2cypher` answer correctness with strict, checkable gold answers.
- Measure `graphrag` for logical consistency, evidence use, and uncertainty handling.
- Keep the two evaluation tracks separate.
- Avoid a single weighted total score.
- Start with a small seed set that can be expanded later.

## Non-Goals

- Building a full evaluation service or UI in this phase.
- Producing one composite score across `text2cypher` and `graphrag`.
- Forcing GraphRAG to answer exact statistics such as counts, averages, or ranked lists.
- Covering every HR question type in the first release.

## Dataset Layout

Recommended file layout:

```text
docs/evaluation/hr-boss/
  README.md
  rubric.md
  text2cypher.strict.jsonl
  graphrag.logic.jsonl
```

### File Roles

- `README.md`: dataset purpose, scope, and usage notes
- `rubric.md`: human-readable scoring rules
- `text2cypher.strict.jsonl`: exact-answer examples with gold labels
- `graphrag.logic.jsonl`: logic-only examples with evidence constraints

## Shared Record Fields

Each record should include:

- `id`: stable sample identifier
- `question`: user-facing natural-language question
- `category`: task family such as `count`, `list`, `ranking`, `org_portrait`
- `difficulty`: `basic`, `medium`, or `hard`
- `snapshot_id`: data snapshot or corpus version used to define the gold answer
- `source`: provenance such as Neo4j, GraphRAG corpus, or human review
- `expected_behavior`: what the agent should do
- `review_status`: `draft`, `gold_reviewed`, or `logic_reviewed`

## `text2cypher.strict` Schema

This file is for questions where the answer must be exact.

Additional fields:

- `answer_type`: `number`, `set`, `ordered_list`, or `boolean`
- `expected_answer`: the gold answer
- `normalization`: rules for comparison
- `acceptable_aliases`: optional name aliases
- `allow_refusal`: whether a correct refusal is acceptable when data is incomplete

### Minimal Example

```json
{
  "id": "t2c_count_001",
  "question": "福建火炬电子科技股份有限公司有多少名高级工程师？",
  "category": "count",
  "difficulty": "basic",
  "snapshot_id": "hr-graph-2026-05-09",
  "source": "Neo4j",
  "expected_behavior": "answer_exact_value",
  "review_status": "gold_reviewed",
  "answer_type": "number",
  "expected_answer": 12,
  "normalization": {
    "number_tolerance": 0,
    "ignore_explanation": true
  },
  "acceptable_aliases": {},
  "allow_refusal": false
}
```

### Matching Rules

- Numbers must match exactly unless a question explicitly allows tolerance.
- Sets should be normalized by trimming, deduplicating, and ignoring order.
- Ordered lists must preserve rank order.
- Boolean answers must resolve to true or false only.
- If the corpus lacks the precision needed for the question, a clear refusal can be marked correct only when `allow_refusal` is true.

## `graphrag.logic` Schema

This file is for questions where the answer should be logically sound, evidence-aware, and honest about uncertainty.

Additional fields:

- `must_include`: key concepts or claims that should appear
- `must_not_include`: claims that would make the answer invalid
- `evidence_requirements`: evidence and uncertainty constraints
- `allow_uncertainty`: whether the answer may stay qualified
- `allowed_answer_shape`: expected response shape such as `summary_with_caveats`

### Minimal Example

```json
{
  "id": "gr_logic_001",
  "question": "福建火炬电子科技股份有限公司的人才结构有什么特点？",
  "category": "talent_structure",
  "difficulty": "medium",
  "snapshot_id": "hr-graph-2026-05-09",
  "source": "GraphRAG corpus",
  "expected_behavior": "logic_and_evidence",
  "review_status": "logic_reviewed",
  "must_include": ["人才结构", "部门或群体差异", "证据来源或依据"],
  "must_not_include": ["精确平均年龄", "未经证据支持的具体人数"],
  "evidence_requirements": {
    "requires_evidence_summary": true,
    "requires_uncertainty_when_weak": true
  },
  "allow_uncertainty": true,
  "allowed_answer_shape": "summary_with_caveats"
}
```

### Matching Rules

- The answer should address the main question directly.
- The answer should stay consistent with the available evidence.
- The answer should not invent precise statistics if the corpus does not support them.
- The answer should clearly state uncertainty when evidence is weak.

## Coverage Plan

### `text2cypher.strict`

Cover these families:

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

Recommended seed size: 30 questions.

### `graphrag.logic`

Cover these families:

- `employee_profile`
- `org_portrait`
- `talent_structure`
- `trend_summary`
- `evidence_lookup`
- `cross_group_exploration`
- `reason_explanation`
- `risk_hint`
- `uncertain_but_honest`

Recommended seed size: 15 questions.

## Seed Question Sources

The first seed set should reuse existing demo and routing content where possible, especially questions already present in:

- `docs/hr-agent-wecom-demo-script.md`
- `backend/.deer-flow/agents/hr-boss-agent/SOUL.md`
- existing HR routing documentation

Seed questions should then be expanded with edge cases such as:

- exact averages
- incomplete age data
- full-name list retrieval
- ranking with ties
- relationship-chain questions
- evidence-only questions

## Scoring Model

The two scorecards must stay separate.

### `text2cypher.strict`

Score by exact correctness:

- exact numbers
- exact sets after normalization
- exact order for ranked lists
- exact boolean outcomes
- correct refusal when marked acceptable

### `graphrag.logic`

Score by logic quality:

- whether the answer stays on topic
- whether it uses evidence responsibly
- whether it avoids fabricated precision
- whether it is explicit about uncertainty when needed

## Acceptance Criteria

This design is successful when:

1. The dataset is split into `text2cypher.strict.jsonl` and `graphrag.logic.jsonl`.
2. `text2cypher` questions have exact gold answers.
3. `graphrag` questions are judged on logic and evidence, not numeric precision.
4. No composite weighted total score is used.
5. Seed questions cover the main HR question families and edge cases.
6. The dataset is small enough to review by hand before expansion.

## Recommended First Release

- `text2cypher.strict`: 30 samples
- `graphrag.logic`: 15 samples
- one README
- one rubric

This gives enough coverage to measure routing-adjacent answer quality without making the first pass too large to maintain.
