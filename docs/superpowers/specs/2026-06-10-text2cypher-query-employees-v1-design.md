# Text2Cypher Query Employees V1 Design

## Summary

Text2Cypher will add a deterministic employee-filtering MCP tool named
`text2cypher_query_employees`. The tool serves both `hr-boss-agent` and external
business systems. It accepts structured employee filter dimensions, resolves
natural-language values to graph values, executes parameterized preset Cypher,
and returns paginated employee cards with matched evidence.

V1 supports these dimensions:

- title
- department
- position
- subsidiary
- major
- project
- latest performance rating
- school

Values within one dimension use `OR`. Different dimensions use `AND`.

The existing `text2cypher_answer_question` tool remains unchanged in V1.
`query_employees` handles deterministic employee-list filtering, while
`answer_question` remains the general natural-language entry point for
aggregations, rankings, distributions, and questions outside the preset
filter contract.

## Goals

- Reduce latency and variance for common employee-list filtering questions.
- Give agents and external systems one stable structured employee-query API.
- Avoid LLM-based Cypher generation on the preset query path.
- Preserve current employee, organization, and business semantics.
- Return explainable employee cards showing why each employee matched.
- Keep the existing `text2cypher_answer_question` behavior unchanged.

## Non-Goals

- Supporting arbitrary Cypher, arbitrary Boolean condition trees, or custom
  query expressions.
- Supporting counts, averages, percentages, grouped distributions, or rankings.
- Scoring or ranking candidates by suitability.
- Allowing callers to request arbitrary return fields.
- Adding an internal preset-query fast path to `text2cypher_answer_question`.
- Replacing the general Text2Cypher generation pipeline.

## Tool Roles And Boundaries

### `text2cypher_query_employees`

`query_employees` is a deterministic domain-query API. It is selected when the
desired result is a list of employees matching supported filter dimensions.

Typical questions:

- 查询研发中心的高级工程师
- 找出参与过瓷粉项目且最近一期绩效为 A 的员工
- 查询某子公司中指定岗位和专业的人员
- 推荐符合若干明确条件的候选人

The result is always a collection of employee cards. The tool does not perform
aggregations or infer conclusions from the result set.

### `text2cypher_answer_question`

`answer_question` remains the general natural-language HR query entry point.
It handles questions requiring generated Cypher or result shapes outside the
preset employee-card contract.

Typical questions:

- 符合条件的员工有多少人
- 各子公司的高级工程师占比
- 哪个部门相关人员最多
- 这些员工的平均年龄是多少

The two tools are peers on the MCP surface but have different domain roles.
They do not call each other in V1.

## Architecture

```text
hr-boss-agent / external business system
                    |
                    v
       text2cypher_query_employees
                    |
                    v
       EmployeePresetQueryService
          |         |          |
          v         v          v
 FilterNormalizer  Term       PresetCypherBuilder
                   Resolution          |
                                       v
                              Validator / Executor
                                       |
                                       v
                       employee cards + matched evidence
```

`EmployeePresetQueryService` is the single owner of the preset employee-query
workflow. Its responsibilities are:

1. validate and normalize request arguments
2. resolve natural-language filter values
3. reject unresolved or high-risk ambiguous values
4. build parameterized Cypher from trusted dimension fragments
5. validate and execute the query
6. load employee cards and matched evidence for the current page
7. return a stable response contract

`text2cypher_answer_question` continues using its existing planner, generator,
validator, and executor flow.

## MCP Request Contract

```python
text2cypher_query_employees(
    titles: list[str] | None = None,
    departments: list[str] | None = None,
    positions: list[str] | None = None,
    subsidiaries: list[str] | None = None,
    majors: list[str] | None = None,
    projects: list[str] | None = None,
    performance_ratings: list[str] | None = None,
    schools: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict
```

At least one filter dimension is required. Empty strings and duplicate values
are removed during normalization.

V1 pagination constraints:

- `offset` must be zero or greater
- default `limit` is `20`
- maximum `limit` is `50`
- ordering is stable and deterministic by employee identifier

Example:

```json
{
  "departments": ["研发中心"],
  "titles": ["高级工程师", "正高级工程师"],
  "projects": ["瓷粉项目"],
  "performance_ratings": ["A"],
  "limit": 20
}
```

The request means:

```text
department = 研发中心
AND title IN (高级工程师, 正高级工程师)
AND project = 瓷粉项目
AND latest performance rating = A
```

## Filter Semantics

### Shared Rules

- Different non-empty dimensions use `AND`.
- Resolved values within one dimension use `OR`.
- Employee-list queries include only current employees by default.
- Employee identity is deduplicated before pagination.
- Callers cannot override current-employee scope in V1.
- Caller-provided values are always Cypher parameters and never interpolated
  into query text.

### Dimension Rules

| Dimension | V1 semantics |
| --- | --- |
| Title | Match resolved title values; title and position remain separate concepts. |
| Department | Resolve to `OrgUnit`; include the target unit and descendant units. |
| Position | Match the employee's current position. |
| Subsidiary | Match the employee's current organization/subsidiary value. |
| Major | Match any education-experience major. |
| Project | Match any historical project experience. |
| Performance | Match only the employee's latest performance record. |
| School | Match any education-experience school. |

Detailed business semantics remain owned by the Text2Cypher HR profile. The MCP
tool contract and DeerFlow skill must not duplicate graph field paths or
fine-grained business rules.

## Term Resolution

Natural-language filter values are resolved before Cypher is built. Resolution
should prefer deterministic value catalogs, aliases, and indexed matching.
Using an LLM for every value would reduce the latency benefit of the preset
query path.

Resolution produces selected standard values per dimension:

```json
{
  "selected_values": {
    "departments": ["信息管理中心"],
    "titles": ["高级工程师"]
  }
}
```

Low-risk aliases and explainable position-family expansion may resolve to
multiple standard values. High-risk entities must not be blindly expanded.
Departments, subsidiaries, projects, and schools return
`needs_clarification` when multiple materially different candidates remain.

The response must disclose resolved values so the agent or external caller can
explain the adopted scope.

## Preset Cypher Construction

V1 must not maintain one large query containing every possible graph
relationship. `PresetCypherBuilder` owns:

- one trusted current-employee base clause
- one trusted `EXISTS` filter fragment per supported dimension
- one trusted stable ordering and pagination clause
- a fixed employee-card loading query

Only fragments corresponding to non-empty dimensions are included. All values,
offsets, limits, and employee identifiers are passed as parameters.

Conceptual filter query:

```cypher
MATCH (e:Employee)
WHERE current_employee_condition
  AND EXISTS {
    MATCH (e)-[:HAS_TITLE]->(t:Title)
    WHERE t.title_name IN $titles
  }
  AND EXISTS {
    MATCH (e)-[:PARTICIPATED_IN]->(p:Project)
    WHERE p.project_name IN $projects
  }
RETURN DISTINCT e.employee_id AS employee_id
ORDER BY employee_id
SKIP $offset
LIMIT $fetch_limit
```

The exact labels, relationships, and properties are defined by the Text2Cypher
repository and HR profile. The conceptual example is not a source of truth for
graph field names.

Using independent `EXISTS` fragments prevents one-to-many title, project,
education, and performance relationships from creating a large Cartesian
product.

## Two-Stage Query Flow

The service performs two deterministic queries:

1. Filter and paginate employee identifiers.
2. Load employee cards and matched evidence only for identifiers on the page.

The first query requests `limit + 1` identifiers. The extra identifier is used
to calculate `has_more`; V1 does not execute a separate full `COUNT` query.

The second query must return only evidence related to requested filters. For
example, when the request filters on project and performance, the response
includes matched project values and the matched latest performance value
without expanding unrelated historical records.

## Response Contract

Successful response:

```json
{
  "status": "success",
  "answerable": true,
  "scope": {
    "current_employees_only": true,
    "performance_scope": "latest",
    "project_scope": "all_history"
  },
  "selected_values": {
    "departments": ["研发中心"],
    "titles": ["高级工程师"]
  },
  "employees": [
    {
      "employee_id": "E001",
      "name": "张三",
      "current_subsidiary": "某子公司",
      "current_department": "研发中心",
      "current_position": "研发工程师",
      "titles": ["高级工程师"],
      "matched_evidence": {
        "projects": ["瓷粉项目"],
        "performance_rating": "A"
      }
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 20,
    "returned_count": 1,
    "has_more": false
  },
  "limitation": null
}
```

The normal response does not expose generated Cypher, raw schema, graph field
paths, validation details, or internal confidence scores.

Supported top-level statuses:

| Status | Meaning |
| --- | --- |
| `success` | Query executed successfully, including an empty employee list. |
| `needs_clarification` | One or more high-risk values remain ambiguous. |
| `invalid_request` | Request has no filters or violates argument limits. |
| `query_failed` | Validation or execution failed. |

Non-success responses set `answerable=false`, return an empty employee list,
and provide a user-facing `limitation`.

## Agent Routing

`hr-boss-agent` will expose both:

- `text2cypher_query_employees`
- `text2cypher_answer_question`

The orchestration skill routes based on desired result shape:

- Employee list, employee filtering, or explicit candidate set:
  `query_employees`
- Count, average, percentage, ranking, grouping, distribution, or unsupported
  natural-language query: `answer_question`

The agent may call at most one Text2Cypher tool per turn. If
`query_employees` returns a non-success status, the agent must explain the
limitation or ask the requested clarification. It must not automatically retry
the same question through `answer_question`.

The tool-selection rules belong in `skills/custom/hr-boss/SKILL.md`.
Fine-grained dimension semantics remain in
`backend/.deer-flow/agents/hr-boss-agent/text2cypher-profile.md`.

## Performance And Safety

The preset path is expected to be faster and more stable because it avoids:

- schema selection by an LLM
- natural-language query planning by an LLM
- Cypher generation by an LLM
- generated-query repair attempts

Performance safeguards:

- Prefer deterministic term resolution.
- Use `EXISTS` fragments for independent dimensions.
- Paginate identifiers before loading employee-card details.
- Cap page size at 50.
- Return only matched evidence for the requested dimensions.
- Add or verify indexes for properties used by preset filters.

Safety safeguards:

- Use a whitelist of trusted query fragments.
- Pass every caller value as a Cypher parameter.
- Reject unknown dimensions and invalid pagination.
- Run the resulting Cypher through the existing validator before execution.
- Apply existing data-access controls and audit logging to the new MCP tool.
- Never expose raw Cypher through the normal tool response.

## Observability

The new tool should emit structured metrics without logging sensitive employee
card contents:

- request status
- requested dimensions
- number of input values per dimension
- resolution duration
- filter-query duration
- card-loading duration
- returned employee count
- `has_more`
- clarification and failure reason categories

Logs may include selected standard dimension values when existing audit policy
allows them, but must not log full employee results by default.

## Testing

### Text2Cypher Repository

- Request normalization removes blanks and duplicates.
- A request without filters returns `invalid_request`.
- Same-dimension values use `OR`.
- Cross-dimension filters use `AND`.
- Current-employee filtering is always applied.
- Department scope includes descendant `OrgUnit` values.
- Position matches only current positions.
- Performance matches only the latest record.
- Project, major, and school match historical records.
- Multiple matching relationships do not duplicate employees.
- High-risk ambiguous values return `needs_clarification`.
- User values cannot alter generated Cypher text.
- Pagination is stable and `has_more` is correct.
- Card loading returns only requested matched evidence.
- Validator or executor failures return `query_failed`.
- The preset path does not invoke the Cypher-generation LLM.

### DeerFlow Repository

- `hr-boss-agent` allows `text2cypher_query_employees`.
- Employee-list questions route to `query_employees`.
- Count, average, ranking, and distribution questions route to
  `answer_question`.
- The agent invokes at most one Text2Cypher tool per turn.
- A failed preset query does not trigger an automatic fallback to
  `answer_question`.
- Existing `answer_question` routing and evaluation behavior remains unchanged.

## Rollout

The feature is guarded by:

```text
TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED=true
```

When disabled, the MCP server does not expose `text2cypher_query_employees`.
`text2cypher_answer_question` remains available and unchanged.

Recommended rollout order:

1. Implement and verify the service and MCP tool in the Text2Cypher repository.
2. Exercise the tool directly with a representative employee-filter dataset.
3. Enable the tool for external-system integration testing.
4. Add the tool and routing contract to `hr-boss-agent`.
5. Compare latency, correctness, and failure rates with the existing
   `answer_question` path.

## Acceptance Criteria

- Supported employee-filter queries execute without invoking the Cypher
  generation LLM.
- Results follow cross-dimension `AND` and same-dimension `OR` semantics.
- Results use current-employee scope, latest-performance scope, and
  all-history project scope.
- Employee cards include matched evidence and do not contain duplicate
  employees.
- Ambiguous high-risk values are disclosed and clarified instead of blindly
  expanded.
- `text2cypher_answer_question` behavior and existing evaluations are
  unchanged.
- Agent employee-list questions select `query_employees`; aggregation questions
  continue selecting `answer_question`.
- Preset employee-list queries demonstrate lower and less variable latency than
  comparable generated-Cypher queries.

## Future Work

Potential follow-up work, explicitly outside V1:

- Reuse `EmployeePresetQueryService` as an internal fast path from
  `text2cypher_answer_question`.
- Add total-count support when callers need it.
- Add approved sort modes and candidate-scoring rules.
- Add time-range parameters for project and performance history.
- Add structured include/exclude filters or a constrained condition tree.
