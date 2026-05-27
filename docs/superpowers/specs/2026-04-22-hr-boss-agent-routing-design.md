# DeerFlow HR Boss Agent Routing Design

## Summary

DeerFlow will add an `hr-boss-agent` orchestration design for answering HR management questions with accuracy-first behavior on top of three existing specialized capabilities:

- `text2sql` for structured fact and metric retrieval against the source MySQL database
- `text2cypher` for relationship and graph-path retrieval against the HR graph view
- `graphrag` for policy, definition, and semantic evidence synthesis against the HR semantic view

The approved architecture is:

- one unified `hr-boss-agent` acts as the entry point for boss-facing HR questions
- the agent uses coarse routing to select one primary expert path
- the agent then invokes one default verification path instead of treating all three experts as equal voters
- the agent applies explicit authority rules across SQL, Cypher, and GraphRAG outputs
- the final response is forced into one of three answer grades:
  - direct answer
  - qualified answer
  - refuse and escalate

The resulting first-version flow is:

1. the boss asks a question
2. `hr-boss-agent` classifies the question into a coarse intent bucket
3. the agent selects one primary execution path
4. the agent invokes one verification path by default
5. the agent applies authority and conflict rules
6. the agent returns a direct answer, a qualified answer, or a refusal depending on evidence quality

## Goals

- Maximize answer accuracy over latency and cost.
- Provide one boss-facing agent instead of exposing three separate specialist skills directly.
- Use SQL, Cypher, and GraphRAG as complementary views over the same HR data rather than as equal-vote experts.
- Make refusal behavior explicit instead of letting the model guess when evidence is weak.
- Support mixed HR questions that combine metrics, relationships, and explanations.

## Non-Goals

- Building a fully real-time synchronization layer between MySQL, Neo4j, and GraphRAG in phase one.
- Treating the three capabilities as independent truth sources for majority voting.
- Solving generic enterprise BI or open-domain question answering.
- Reworking DeerFlow core runtime, skill loading, or MCP loading architecture in this design phase.
- Eliminating all manual review for high-risk HR judgments.

## Existing Context

The current project already contains the required building blocks:

- `skills/custom/text2sql/SKILL.md`
- `skills/custom/text2cypher/SKILL.md`
- `skills/custom/graphrag/SKILL.md`
- `backend/.deer-flow/agents/text2sql-agent`
- `backend/.deer-flow/agents/text2cypher-agent`
- `backend/.deer-flow/agents/graphrag-agent`
- `extensions_config.json` registrations for the three local MCP-backed integrations

The source business data is in MySQL:

```text
mysql://root:123456@127.0.0.1:3306/test
```

For phase one, the approved assumption is:

- `text2sql` queries the source MySQL facts
- `text2cypher` and `graphrag` are synchronized offline from the same source data
- data freshness can be treated as effectively consistent for now

This means the three paths should be treated as one-source, three-view reasoning surfaces:

- SQL view
- graph relationship view
- semantic explanation view

## Options Considered

Three architecture options were considered.

### 1. Full Parallel Voting

Run `text2sql`, `text2cypher`, and `graphrag` for every question and let the model summarize all three outputs.

Pros:

- broad cold-start coverage
- low dependence on classifier quality

Cons:

- highest latency and cost
- conflict handling is difficult
- invites the model to flatten contradictions into a polished but unreliable answer
- treats same-source views as if they were independent truth sources

### 2. Pure Single-Route Selection

Route each question to exactly one expert path and return only that result.

Pros:

- simplest execution model
- lowest runtime cost

Cons:

- brittle when question type is mixed or ambiguous
- depends too heavily on routing quality at a stage where real boss-question distribution is still unknown
- too risky for an accuracy-first first release

### 3. Coarse Routing with Default Cross-Validation

Select one primary path, invoke one default verification path, and use explicit authority rules to arbitrate conflicts.

Pros:

- accuracy-first without full three-way parallelism
- supports mixed questions better than pure single-route selection
- keeps expert roles clear
- reduces free-form model synthesis risk

Cons:

- more orchestration logic than pure single-route selection
- still requires careful conflict rules

## Final Decision

The approved first-version design is option 3:

- use coarse routing
- use one primary expert by default
- use one verification expert by default
- invoke the third expert only for conflict, high-risk questions, or mixed-question decomposition
- never use simple majority voting across the three paths

## Authority Model

The approved authority model is domain-specific rather than global.

### SQL Authority

`text2sql` is the highest-authority source for:

- counts
- ratios
- rankings
- aggregates
- filtered lists
- comparisons across groups
- any question whose final answer depends on structured numeric facts

### Cypher Authority

`text2cypher` is the highest-authority source for:

- reporting lines
- organization paths
- employee-to-team relations
- multi-hop graph traversal
- graph-shaped reasoning about who belongs to what chain

If a Cypher answer contains numeric claims such as counts or rankings, those numeric claims should be checked by SQL.

### GraphRAG Authority

`graphrag` is the highest-authority source for:

- policy explanation
- business-definition explanation
- semantic evidence synthesis
- why-style answers that depend on narrative or policy context
- FAQ-like HR interpretation tasks

GraphRAG may explain a fact, but it must not override SQL on numerical results or Cypher on relationship structure.

## Output Contract

All three specialist paths should ultimately feed the orchestrator in a normalized shape:

```json
{
  "status": "success|partial|failed",
  "answer": "Natural-language answer",
  "confidence": 0.0,
  "evidence": [
    "Short evidence item"
  ],
  "has_structured_result": true,
  "conflict_flag": false,
  "limitations": [
    "Known limitation or caveat"
  ],
  "source_type": "sql|cypher|graphrag"
}
```

This contract is required so the orchestrator can grade the final answer consistently instead of relying on unconstrained summarization.

## Coarse Routing Model

The first version should use explicit routing rules, not a learned classifier.

### SQL-First Signals

Route primarily to `text2sql` when the question asks about:

- how many
- rate
- percentage
- top N
- ranking
- average
- median
- trend
- month-over-month or year-over-year comparisons

Representative examples:

- "How many resignations did the engineering department have last month?"
- "Which department has the highest turnover rate?"
- "What is the hiring completion trend over the last three months?"

### Cypher-First Signals

Route primarily to `text2cypher` when the question asks about:

- who reports to whom
- organization chain
- leader path
- employee-team affiliation
- cross-team or cross-department relationship paths

Representative examples:

- "Who does employee A report to?"
- "Which organization line does this department belong to?"
- "How many reporting levels separate employee A from director B?"

### GraphRAG-First Signals

Route primarily to `graphrag` when the question asks about:

- policy
- rule
- definition
- business interpretation
- why-style explanation
- compliance or procedural explanation

Representative examples:

- "What is the annual leave policy?"
- "How is turnover rate defined?"
- "Why has a department recently become unstable?"

## Default Verification Matrix

The approved default execution matrix is:

| Question Type | Primary Path | Default Verification Path | Third Path Trigger |
|---|---|---|---|
| fact and metric questions | `text2sql` | `graphrag` | when graph relationship context is required |
| relationship questions | `text2cypher` | `graphrag` or `text2sql` depending on numeric content | when explanation and structure both matter |
| policy and explanation questions | `graphrag` | `text2sql` or `text2cypher` if factual claims appear | when explanation contains material facts needing proof |
| mixed questions | decomposed sequence | depends on sub-question | use all three only through explicit decomposition |

### Fact Questions

Default path:

- primary: `text2sql`
- verification: `graphrag`

Reason:

- SQL answers the fact
- GraphRAG explains the metric definition or policy meaning when needed

### Relationship Questions

Default path:

- primary: `text2cypher`
- verification: `graphrag`

Optional numeric verification:

- if the answer contains counts, rankings, or distribution claims, also verify the numeric part with `text2sql`

### Explanation Questions

Default path:

- primary: `graphrag`
- verification: `text2sql`

Reason:

- GraphRAG explains the answer
- SQL proves or rejects quantitative claims embedded in the explanation

## Mixed-Question Decomposition

Mixed questions must not be answered by free-form three-way summarization.

Instead, the orchestrator should split them into ordered sub-questions.

Example:

```text
Which department has the highest recent turnover rate, who owns it, and why might that be happening?
```

Approved decomposition:

1. `text2sql` finds the department with the highest departure rate
2. `text2cypher` finds the responsible leader or reporting owner
3. `graphrag` explains likely reasons using policy or semantic evidence
4. the orchestrator combines the results under the answer-grading rules

## Answer Grading Model

The final answer must be classified into one of three grades.

### 1. Direct Answer

Use only when all of the following are true:

- primary path status is `success`
- verification path supports the main conclusion strongly enough
- no material conflict exists
- the question meaning is clear enough
- evidence is concrete and displayable
- primary confidence is at least `0.8`

Additional hard rules:

- numeric questions must not be graded as direct answer without structured results
- causal or explanation-heavy questions must not be graded as direct answer without at least two distinct supporting evidence signals

### 2. Qualified Answer

Use when any of the following is true:

- primary path succeeded but verification is only partial
- the question is answerable but has mild metric or terminology ambiguity
- the evidence supports a likely answer but not a final conclusion
- confidence is between `0.5` and `0.8`

Qualified answers must:

- lead with the best supported current conclusion
- explicitly state the caveat
- separate uncertain points from established facts

### 3. Refuse and Escalate

Use when any of the following is true:

- primary path failed
- primary and verification paths materially conflict
- evidence is insufficient for a reliable answer
- ambiguity remains too high after clarification
- the question is high-risk and evidence is not closed
- confidence is too low to support a safe answer

Refusal must:

- avoid speculative conclusions
- state that the current evidence is insufficient or conflicting
- indicate what kind of human review or additional confirmation is needed

## High-Risk Question Policy

The first version should be conservative for high-risk HR questions such as:

- salary fairness judgments
- promotion or elimination causality judgments
- disciplinary or compliance judgments
- discrimination-sensitive comparisons
- legal or labor-risk interpretation with employee impact

For these categories:

- strong evidence is required
- verification is mandatory
- refusal is preferred over weak inference

## Error Handling Model

The orchestrator should handle failures in four categories.

### 1. Specialist Tool Failure

Examples:

- MCP path unavailable
- query generation failure
- execution failure
- validation failure

Expected behavior:

- record the failure explicitly
- do not silently ignore it
- downgrade to qualified answer or refusal depending on remaining evidence

### 2. Routing Ambiguity

Examples:

- the question mixes metric, relationship, and explanation signals
- the entity or time scope is unclear

Expected behavior:

- decompose when possible
- otherwise ask for clarification
- do not force a single-route answer when the routing basis is weak

### 3. Evidence Conflict

Examples:

- GraphRAG explanation claims a metric interpretation that does not match SQL results
- Cypher implies a relationship outcome that contradicts the known graph structure or SQL-backed roster facts

Expected behavior:

- apply the authority hierarchy
- if the conflict remains material, refuse and escalate

### 4. High-Risk Incompleteness

Examples:

- explanation exists but fact support is missing
- fact support exists but policy meaning is unclear for a sensitive judgment

Expected behavior:

- prefer qualified answer or refusal
- never turn incomplete evidence into a decisive HR judgment

## Minimal Implementation Scope

The approved first implementation scope is:

- define an `hr-boss-agent` orchestration design
- add coarse routing rules
- add normalized specialist output contract
- add answer-grading rules
- add mixed-question decomposition logic
- keep current specialist integrations as the execution backends

This phase intentionally excludes:

- real-time cross-store freshness handling
- learned routing models
- full evaluation automation against real boss question logs
- replacing current specialist engines
- removing human escalation for high-risk topics

## Acceptance Criteria

This design is successful when all of the following are true:

1. boss-facing HR questions can enter one unified orchestration path
2. the orchestrator can choose a primary path and a default verification path
3. fact questions default to SQL authority
4. relationship questions default to Cypher authority
5. explanation questions default to GraphRAG authority
6. mixed questions are decomposed rather than handled through unconstrained three-way summarization
7. every final answer is explicitly classified as:
   - direct answer
   - qualified answer
   - refuse and escalate
8. high-risk HR questions behave conservatively by default

## Validation Strategy

Validation should happen in three layers.

### 1. Routing Validation

Build a simulated benchmark set that covers:

- fact questions
- relationship questions
- explanation questions
- mixed questions
- high-risk questions

Each case should verify:

- primary path choice
- verification path choice
- whether decomposition is triggered

### 2. Specialist Result Validation

For each simulated question, verify:

- whether the specialist path succeeded
- whether structured evidence exists
- whether conflicts are surfaced
- whether the normalized output contract is populated correctly

### 3. Final Answer Validation

For each simulated question, verify:

- final answer grade
- whether evidence and caveats are surfaced correctly
- whether refusal happens on conflict or insufficiency

## Final Decision

The approved HR boss-agent design is:

- one unified `hr-boss-agent` orchestrates three existing specialist capabilities
- the system uses coarse routing plus default cross-validation, not full parallel voting
- SQL, Cypher, and GraphRAG are treated as complementary views over the same HR source data
- answer quality is governed by explicit authority rules and three answer grades
- mixed and high-risk questions are handled conservatively by decomposition, qualification, or refusal rather than by optimistic synthesis
