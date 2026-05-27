# HR Boss Evaluation Dataset

This directory contains two separate evaluation tracks:

- `text2cypher.strict` for exact-answer evaluation
- `graphrag.logic` for logic-and-evidence evaluation
- `boss.e2e` for minimal end-to-end boss-style questions
- `term_resolution.strict` for field-value alias, ambiguity, and unresolved-term behavior

## Minimal Boss E2E Set

`boss.e2e.jsonl` is generated from `boss_questions.md` and intentionally keeps each case to four fields:

```json
{"id":"boss_e2e_001","category":"query","question":"研发那边现在有多少人？","expected":"识别研发相关组织并查询当前人数；如果存在多个研发口径，应先澄清。"}
```

Categories:

- `query`: answer from available structured or graph evidence when the business口径 is clear enough.
- `analyze`: summarize from evidence and state boundaries.
- `clarify`: ask a follow-up before querying because the boss wording is underspecified.
- `insufficient`: state the data gap instead of inventing facts.
- `talent_match`: recommend candidate people from structured filters plus GraphRAG evidence, with match reasons and clear limitations.

Run it with both HR Boss tools available:

```powershell
cd D:\study\deer-flow\backend
uv run python scripts/run_hr_boss_eval.py --track boss.e2e --rounds 1 --output-jsonl ../docs/evaluation/hr-boss/boss-e2e-run-results.jsonl --output-md ../docs/evaluation/hr-boss/boss-e2e-run-results.md
```

## Term Resolution Strict Set

`term_resolution.strict.jsonl` focuses on the Text2Cypher field-value correction stage. A passing run should either call `text2cypher_resolve_terms` directly or return `term_resolution` from `text2cypher_answer_question`.

```powershell
cd D:\study\deer-flow\backend
uv run python scripts/run_hr_boss_eval.py --track term_resolution.strict --rounds 1 --output-jsonl ../docs/evaluation/hr-boss/term-resolution-run-results.jsonl --output-md ../docs/evaluation/hr-boss/term-resolution-run-results.md
```

## Boss-Aligned Evaluation Sets (v2)

Based on boss interview feedback (`../boss_qwestion_answer.txt`), new evaluation cases were designed to align with actual leadership needs:

- `text2cypher.boss.jsonl` — 15 new Text2Cypher questions mapped to boss dashboard / budget / ad-hoc / deep needs
- `graphrag.boss.jsonl` — 9 new GraphRAG questions mapped to boss analytical needs
- `boss-needs-mapping.md` — full traceability: boss quotes → eval cases, including which boss needs *cannot* yet be answered with current data

### Boss Need Coverage Summary

| Boss Scenario | Text2Cypher | GraphRAG | Not Queryable |
|--------------|-------------|----------|---------------|
| 常规看板 (Dashboard) | 5 cases | 2 cases | 流失率, 满意度, 培训 |
| 预算审批 (Budget) | 3 cases | 2 cases | 工作负荷, 薪酬对标 |
| 临时会议 (Ad-hoc) | 4 cases | 2 cases | 离职率 |
| 深层问题 (Deep) | 3 cases | 3 cases | 离职原因, 参与度, 福利, 内外部招聘对比 |

10 boss needs are marked as "not queryable with current data" — see `boss-needs-mapping.md` for details.

### Running Boss-Aligned Cases

```powershell
cd D:\study\deer-flow\backend

# Run boss-aligned Text2Cypher cases
uv run python scripts/run_hr_boss_eval.py --track text2cypher.boss --rounds 3

# Run boss-aligned GraphRAG cases
uv run python scripts/run_hr_boss_eval.py --track graphrag.boss --rounds 1

# Run single boss case
uv run python scripts/run_hr_boss_eval.py --id boss_t2c_dashboard_001
```

## Original Evaluation Sets (v1)

Human-readable views:

- `text2cypher.strict.md` mirrors `text2cypher.strict.jsonl`
- `graphrag.logic.md` mirrors `graphrag.logic.jsonl`

Machine-readable sources:

- `text2cypher.strict.jsonl`
- `graphrag.logic.jsonl`

Batch runner:

```powershell
cd D:\study\deer-flow\backend
uv run python scripts/run_hr_boss_eval.py --limit 3
```

The runner calls `hr-boss-agent` and writes:

- `docs/evaluation/hr-boss/run-results.jsonl`
- `docs/evaluation/hr-boss/run-results.md`

Useful manual runs:

```powershell
# Run only strict Text2Cypher cases
uv run python scripts/run_hr_boss_eval.py --track text2cypher.strict --rounds 3

# Run only GraphRAG logic cases
uv run python scripts/run_hr_boss_eval.py --track graphrag.logic --rounds 3

# Run selected cases
uv run python scripts/run_hr_boss_eval.py --id t2c_average_001 --id rag_org_portrait_001
```

Source of truth:

- `docs/superpowers/specs/2026-05-09-hr-boss-eval-dataset-design.md`
- `docs/hr-agent-wecom-demo-script.md`
- reviewed HR graph snapshot identified by `snapshot_id`

Rules:

- Do not compute a composite weighted total score.
- Keep strict-answer and logic-only scoring separate.
- Use a frozen snapshot id for all gold answers in the first release.


由大模型模拟boss回复实现多轮对话回复后评测

cd D:\study\deer-flow\backend
uv run python scripts/run_hr_boss_eval.py --track boss.e2e --run-xiyan-sql --conversation-mode simulate --max-turns 3 --simulator-model-name qwen3.5-plus