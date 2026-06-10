# Text2Cypher Query Employees V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic `text2cypher_query_employees` MCP tool that resolves structured HR filter values, executes parameterized preset Cypher, and returns paginated employee cards with matched evidence to both `hr-boss-agent` and external systems.

**Architecture:** Implement the preset-query capability in the Text2Cypher repository as an optional `EmployeePresetQueryService` injected into `Text2CypherEngine`. Keep `text2cypher_answer_question` unchanged. DeerFlow constructs the optional service behind `TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED`, exposes the new MCP tool to `hr-boss-agent`, and routes explicit employee-list filtering to the new tool while preserving `answer_question` for aggregations and unsupported questions.

**Tech Stack:** Python 3.11/3.12, Pydantic v2, Neo4j Python driver, FastMCP, pytest, DeerFlow custom-agent configuration and skills.

---

## Implementation Constraints

- This implementation spans two repositories:
  - Text2Cypher: `D:\study\my-mcp\text2cypher`
  - DeerFlow: `D:\python_project\deer-flow`
- The Text2Cypher repository currently has unrelated user changes in:
  - `.env.example`
  - `README.md`
  - `text2cypher/config.py`
  - `text2cypher/core/planner.py`
- Do not revert, overwrite, or stage those existing Text2Cypher changes. V1 reads the feature flag in the DeerFlow launcher and does not require modifying those four files.
- The new MCP function is named `query_employees` inside Text2Cypher. DeerFlow exposes it with the MCP server prefix as `text2cypher_query_employees`.
- `text2cypher_answer_question` must retain its existing behavior and test results. It does not call `EmployeePresetQueryService` in V1.
- All caller-provided filter values must be passed as Neo4j query parameters. No caller value may be interpolated into Cypher text.
- Detailed HR graph semantics remain in `backend/.deer-flow/agents/hr-boss-agent/text2cypher-profile.md`; the skill contains routing rules only.

## File Structure

### Text2Cypher Repository

- Create `text2cypher/core/employee_query_models.py`
  - Own request, resolution, statement, employee-card, pagination, and result contracts.
- Create `text2cypher/core/employee_filter_resolver.py`
  - Resolve structured filter values using deterministic graph-value lookup and dimension-specific ambiguity policy.
- Create `text2cypher/core/employee_query_builder.py`
  - Build parameterized page-ID and employee-card Cypher from trusted fragments.
- Create `text2cypher/core/employee_query_service.py`
  - Orchestrate validation, resolution, two-stage execution, error contracts, and timing.
- Modify `text2cypher/core/validator.py`
  - Support parameterized `EXPLAIN` and recognize `OrgUnit.org_unit_name`.
- Modify `text2cypher/core/executor.py`
  - Support parameterized validation and execution.
- Modify `text2cypher/core/engine.py`
  - Accept an optional employee-query service and expose `query_employees`.
- Modify `text2cypher/adapters/mcp/tools.py`
  - Add the structured MCP function and sanitized call-log payload.
- Modify `text2cypher/adapters/mcp/server.py`
  - Register `query_employees` only when the engine has the service enabled.
- Modify `text2cypher/adapters/mcp/call_logging.py`
  - Allow a per-tool output sanitizer so employee cards are not written to logs.
- Create `tests/unit/test_employee_query_models.py`
- Create `tests/unit/test_employee_filter_resolver.py`
- Create `tests/unit/test_employee_query_builder.py`
- Create `tests/unit/test_employee_query_service.py`
- Modify `tests/unit/test_validator.py`
- Modify `tests/unit/test_executor.py`
- Modify `tests/unit/test_engine.py`
- Modify `tests/unit/test_mcp_server.py`
- Modify `tests/unit/test_call_logging.py`
- Create `tests/integration/test_live_query_employees.py`

### DeerFlow Repository

- Modify `scripts/run_text2cypher_mcp.py`
  - Construct and inject `EmployeePresetQueryService` only when the feature flag is enabled.
- Modify local-only `extensions_config.json`
  - Enable the feature for the shared local workspace, but do not stage this ignored file.
- Modify `extensions_config.example.json`
- Modify `deployment/hr-boss/extensions_config.docker.json`
  - Enable the employee-query tool in local, example, and HR Boss deployment configurations.
- Modify `backend/.deer-flow/agents/hr-boss-agent/config.yaml`
  - Allow `text2cypher_query_employees`.
- Modify `skills/custom/hr-boss/SKILL.md`
  - Replace the single-entry rule with explicit dual-tool routing.
- Modify `backend/.deer-flow/agents/hr-boss-agent/text2cypher-profile.md`
  - Record the preset tool's supported dimension semantics as the business source of truth.
- Modify `AGENTS.md`
  - Update the high-level architecture and public Text2Cypher tool roles.
- Modify `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
  - Update the recommendation fast-path fallback prompt to choose between the two Text2Cypher tools.
- Modify `backend/scripts/run_hr_boss_eval.py`
  - Permit `query_employees` as a valid boss-facing Text2Cypher route without changing strict aggregation expectations.
- Modify `backend/tests/test_hr_boss_prompt_contract.py`
- Modify `backend/tests/test_hr_boss_latency_policy.py`
- Modify `backend/tests/test_mcp_filtering.py`
- Modify `backend/tests/test_hr_boss_eval_runner.py`
- Create `backend/tests/test_text2cypher_employee_query_launcher.py`
- Modify `deployment/hr-boss-agent.md`

---

### Task 1: Define Employee Query Contracts

**Repository:** `D:\study\my-mcp\text2cypher`

**Files:**
- Create: `text2cypher/core/employee_query_models.py`
- Create: `tests/unit/test_employee_query_models.py`

- [ ] **Step 1: Write failing request-validation tests**

```python
import pytest
from pydantic import ValidationError

from text2cypher.core.employee_query_models import EmployeeQueryRequest


def test_request_requires_at_least_one_filter() -> None:
    with pytest.raises(ValidationError, match="at least one employee filter"):
        EmployeeQueryRequest()


def test_request_normalizes_values_and_enforces_page_limit() -> None:
    request = EmployeeQueryRequest(
        titles=[" 高级工程师 ", "高级工程师", ""],
        departments=["研发中心"],
        limit=50,
    )

    assert request.titles == ["高级工程师"]
    assert request.departments == ["研发中心"]
    assert request.active_filters() == {
        "titles": ["高级工程师"],
        "departments": ["研发中心"],
    }

    with pytest.raises(ValidationError):
        EmployeeQueryRequest(titles=["高级工程师"], limit=51)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_employee_query_models.py -v
```

Expected: FAIL because `employee_query_models` does not exist.

- [ ] **Step 3: Add the request and response models**

Create models with these stable field names:

```python
FILTER_DIMENSIONS = (
    "titles",
    "departments",
    "positions",
    "subsidiaries",
    "majors",
    "projects",
    "performance_ratings",
    "schools",
)


class EmployeeQueryRequest(BaseModel):
    titles: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    subsidiaries: list[str] = Field(default_factory=list)
    majors: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    performance_ratings: list[str] = Field(default_factory=list)
    schools: list[str] = Field(default_factory=list)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator(*FILTER_DIMENSIONS, mode="before")
    @classmethod
    def normalize_dimension_values(cls, value: object) -> list[str]:
        values = value if isinstance(value, list) else []
        return list(
            dict.fromkeys(
                str(item).strip()
                for item in values
                if item is not None and str(item).strip()
            )
        )

    @model_validator(mode="after")
    def require_filter(self) -> "EmployeeQueryRequest":
        if not self.active_filters():
            raise ValueError("at least one employee filter is required")
        return self

    def active_filters(self) -> dict[str, list[str]]:
        return {name: list(getattr(self, name)) for name in FILTER_DIMENSIONS if getattr(self, name)}
```

Also define:

```python
class EmployeeFilterResolution(BaseModel):
    selected_values: dict[str, list[str]] = Field(default_factory=dict)
    needs_clarification: bool = False
    limitation: str | None = None


class EmployeeQueryStatement(BaseModel):
    cypher: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class EmployeeCard(BaseModel):
    employee_id: str
    name: str
    current_subsidiary: str | None = None
    current_department: str | None = None
    current_position: str | None = None
    titles: list[str] = Field(default_factory=list)
    matched_evidence: dict[str, Any] = Field(default_factory=dict)


class EmployeeQueryPagination(BaseModel):
    offset: int
    limit: int
    returned_count: int
    has_more: bool


class EmployeeQueryResult(BaseModel):
    status: Literal["success", "needs_clarification", "invalid_request", "query_failed"]
    answerable: bool
    scope: dict[str, Any] = Field(default_factory=dict)
    selected_values: dict[str, list[str]] = Field(default_factory=dict)
    employees: list[EmployeeCard] = Field(default_factory=list)
    pagination: EmployeeQueryPagination
    limitation: str | None = None
    timing: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 4: Run the model tests**

Run:

```powershell
python -m pytest tests/unit/test_employee_query_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the contracts**

```powershell
git add text2cypher/core/employee_query_models.py tests/unit/test_employee_query_models.py
git commit -m "新增员工查询数据合同"
```

---

### Task 2: Add Parameterized Cypher Validation And Execution

**Repository:** `D:\study\my-mcp\text2cypher`

**Files:**
- Modify: `text2cypher/core/validator.py`
- Modify: `text2cypher/core/executor.py`
- Modify: `tests/unit/test_validator.py`
- Modify: `tests/unit/test_executor.py`

- [ ] **Step 1: Write failing parameter propagation tests**

Add a fake session that accepts `session.run(query, parameters)` and assert:

```python
def test_validate_passes_parameters_to_explain() -> None:
    parameters = {"titles": ["高级工程师"]}
    result = validator.validate(
        "MATCH (t:Title) WHERE t.title_name IN $titles RETURN t",
        parameters=parameters,
    )
    assert result.valid is True
    assert captured == [
        (
            "EXPLAIN MATCH (t:Title) WHERE t.title_name IN $titles RETURN t",
            30.0,
            parameters,
        )
    ]


def test_execute_validated_passes_parameters_to_session() -> None:
    result = executor.execute_validated(
        "MATCH (e:Employee) WHERE e.employee_id IN $employee_ids RETURN e",
        parameters={"employee_ids": ["E001"]},
    )
    assert result.records == [{"employee_id": "E001"}]
    assert captured_parameters == {"employee_ids": ["E001"]}
```

Add a validator test that accepts:

```cypher
MATCH (target:OrgUnit)
WHERE target.org_unit_name IN $departments
RETURN target
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_validator.py tests/unit/test_executor.py -v
```

Expected: FAIL because the methods do not accept `parameters`, and `OrgUnit.org_unit_name` is not registered.

- [ ] **Step 3: Extend validator and executor signatures**

Implement backward-compatible optional parameters:

```python
def validate(
    self,
    cypher: str,
    timeout_seconds: float | None = None,
    parameters: dict[str, object] | None = None,
) -> ValidationResult:
    query = Query(f"EXPLAIN {normalized}", timeout=timeout)
    if parameters:
        session.run(query, parameters).consume()
    else:
        session.run(query).consume()
```

```python
from itertools import islice


def execute(
    self,
    cypher: str,
    max_rows: int = 100,
    parameters: dict[str, object] | None = None,
) -> ExecutionResult:
    validation = (
        self._validator.validate(cypher, parameters=parameters)
        if parameters
        else self._validator.validate(cypher)
    )
    if not validation.valid:
        raise ValueError(validation.error or "Cypher validation failed")
    return self.execute_validated(
        validation.normalized_cypher,
        max_rows=max_rows,
        parameters=parameters,
    )


def execute_validated(
    self,
    cypher: str,
    max_rows: int = 100,
    timeout_seconds: float | None = None,
    parameters: dict[str, object] | None = None,
) -> ExecutionResult:
    query = Query(cypher, timeout=timeout)
    result = session.run(query, parameters) if parameters else session.run(query)
    rows = [dict(row) for row in islice(result, max_rows + 1)]
```

Add this validator property whitelist:

```python
"OrgUnit": {
    "center_name",
    "full_path",
    "org_name",
    "org_unit_name",
},
```

- [ ] **Step 4: Run validator and executor tests**

Run:

```powershell
python -m pytest tests/unit/test_validator.py tests/unit/test_executor.py -v
```

Expected: PASS, including all pre-existing tests.

- [ ] **Step 5: Commit parameter support**

```powershell
git add text2cypher/core/validator.py text2cypher/core/executor.py tests/unit/test_validator.py tests/unit/test_executor.py
git commit -m "支持参数化Cypher执行"
```

---

### Task 3: Implement Deterministic Filter Resolution

**Repository:** `D:\study\my-mcp\text2cypher`

**Files:**
- Create: `text2cypher/core/employee_filter_resolver.py`
- Create: `tests/unit/test_employee_filter_resolver.py`

- [ ] **Step 1: Write failing resolution tests**

Cover exact resolution, explainable multi-value expansion, high-risk ambiguity, unresolved values, and all eight dimension mappings:

```python
def test_resolver_selects_exact_and_expandable_position_values() -> None:
    resolver = EmployeeFilterResolver(
        candidate_provider=FakeCandidateProvider(
            {
                ("positions", "研发岗"): ["研发工程师", "研发经理"],
                ("titles", "高级工程师"): ["高级工程师"],
            }
        )
    )

    result = resolver.resolve(
        EmployeeQueryRequest(positions=["研发岗"], titles=["高级工程师"])
    )

    assert result.needs_clarification is False
    assert result.selected_values == {
        "positions": ["研发工程师", "研发经理"],
        "titles": ["高级工程师"],
    }


def test_resolver_clarifies_multiple_project_candidates() -> None:
    result = resolver.resolve(EmployeeQueryRequest(projects=["瓷粉项目"]))
    assert result.needs_clarification is True
    assert "瓷粉项目" in result.limitation
```

- [ ] **Step 2: Run the resolver tests and verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_employee_filter_resolver.py -v
```

Expected: FAIL because the resolver does not exist.

- [ ] **Step 3: Implement fixed dimension specifications and resolution policy**

Use these graph-value sources:

```python
@dataclass(frozen=True)
class DimensionSpec:
    label: str
    property: str
    expandable: bool = False
    high_risk: bool = False
    exact_only: bool = False


class CandidateProvider(Protocol):
    def __call__(
        self,
        *,
        dimension: str,
        source: str,
        spec: DimensionSpec,
        limit: int,
    ) -> list[str]:
        pass


DIMENSION_SPECS = {
    "titles": DimensionSpec("Title", "title_name", expandable=True),
    "departments": DimensionSpec("OrgUnit", "org_unit_name", high_risk=True),
    "positions": DimensionSpec("Position", "position_name", expandable=True),
    "subsidiaries": DimensionSpec("Employee", "current_org_name", high_risk=True),
    "majors": DimensionSpec("EducationExperience", "major", expandable=True),
    "projects": DimensionSpec("ProjectExperience", "project_name", high_risk=True),
    "performance_ratings": DimensionSpec("PerformanceAssessment", "assessment_result", exact_only=True),
    "schools": DimensionSpec("EducationExperience", "school_name", high_risk=True),
}
```

The production candidate provider must select a spec only by a validated dimension key and execute fixed label/property pairs from `DIMENSION_SPECS`:

```python
spec = DIMENSION_SPECS[dimension]
cypher = (
    f"MATCH (n:`{spec.label}`) "
    f"WITH DISTINCT trim(toString(n.`{spec.property}`)) AS value "
    "WHERE value <> '' "
    "AND NOT value IN $invalid_values "
    "AND any(term IN $search_terms WHERE toLower(value) CONTAINS toLower(term)) "
    "RETURN value ORDER BY value LIMIT $limit"
)
```

Use this dependency boundary so unit tests inject candidates without Neo4j while production reuses the parameterized executor:

```python
class EmployeeFilterResolver:
    def __init__(
        self,
        *,
        executor: CypherExecutor | None = None,
        candidate_provider: CandidateProvider | None = None,
    ) -> None:
        if executor is None and candidate_provider is None:
            raise ValueError("executor or candidate_provider is required")
        self._executor = executor
        self._candidate_provider = candidate_provider
```

Resolution policy:

- Exact normalized match always wins.
- `performance_ratings` requires an exact match.
- `positions`, `titles`, and `majors` may select all strong, explainable candidates.
- `departments`, `subsidiaries`, `projects`, and `schools` require one unambiguous selected value per source value.
- Any unresolved or high-risk ambiguous value returns `needs_clarification` before employee filtering.

- [ ] **Step 4: Run resolver tests**

Run:

```powershell
python -m pytest tests/unit/test_employee_filter_resolver.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit deterministic resolution**

```powershell
git add text2cypher/core/employee_filter_resolver.py tests/unit/test_employee_filter_resolver.py
git commit -m "新增员工筛选术语解析"
```

---

### Task 4: Build Trusted Preset Cypher

**Repository:** `D:\study\my-mcp\text2cypher`

**Files:**
- Create: `text2cypher/core/employee_query_builder.py`
- Create: `tests/unit/test_employee_query_builder.py`

- [ ] **Step 1: Write failing builder tests**

Test every dimension, same-dimension parameter lists, cross-dimension `AND`, stable pagination, latest performance semantics, and injection resistance:

```python
def test_page_query_uses_parameters_and_exists_fragments() -> None:
    statement = builder.build_page_query(
        selected_values={
            "titles": ["高级工程师", "正高级工程师"],
            "projects": ["瓷粉项目"],
        },
        offset=0,
        limit=20,
    )

    assert "t.title_name IN $titles" in statement.cypher
    assert "pe.project_name IN $projects" in statement.cypher
    assert "高级工程师" not in statement.cypher
    assert statement.parameters["titles"] == ["高级工程师", "正高级工程师"]
    assert statement.parameters["projects"] == ["瓷粉项目"]
    assert statement.parameters["fetch_limit"] == 21


def test_department_query_uses_org_unit_descendants() -> None:
    statement = builder.build_page_query(
        selected_values={"departments": ["IT部"]},
        offset=0,
        limit=20,
    )
    assert "CURRENTLY_ASSIGNED_TO_ORG_UNIT" in statement.cypher
    assert "CONTAINS_ORG_UNIT*0.." in statement.cypher


def test_latest_performance_filter_orders_before_limit() -> None:
    statement = builder.build_page_query(
        selected_values={"performance_ratings": ["A"]},
        offset=0,
        limit=20,
    )
    assert "ORDER BY coalesce(pa.assessment_year_int, -1) DESC" in statement.cypher
    assert "LIMIT 1" in statement.cypher
```

- [ ] **Step 2: Run builder tests and verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_employee_query_builder.py -v
```

Expected: FAIL because the builder does not exist.

- [ ] **Step 3: Implement the page query fragment registry**

The base scope must always be:

```cypher
MATCH (e:Employee)
WHERE (
    (e)-[:CURRENTLY_IN_DEPARTMENT]->(:Department)
    OR (e)-[:CURRENTLY_IN_POSITION]->(:Position)
  )
```

Register these trusted filter fragments:

```python
FILTER_FRAGMENTS = {
    "titles": """EXISTS {
      MATCH (e)-[:HAS_TITLE]->(t:Title)
      WHERE t.title_name IN $titles
    }""",
    "departments": """EXISTS {
      MATCH (e)-[:CURRENTLY_ASSIGNED_TO_ORG_UNIT]->(leaf:OrgUnit)
      MATCH (target:OrgUnit)-[:CONTAINS_ORG_UNIT*0..]->(leaf)
      WHERE target.org_unit_name IN $departments
    }""",
    "positions": """EXISTS {
      MATCH (e)-[:CURRENTLY_IN_POSITION]->(p:Position)
      WHERE p.position_name IN $positions
    }""",
    "subsidiaries": "e.current_org_name IN $subsidiaries",
    "majors": """EXISTS {
      MATCH (e)-[:HAS_EDUCATION]->(ed:EducationExperience)
      WHERE ed.major IN $majors
    }""",
    "projects": """EXISTS {
      MATCH (e)-[:HAS_PROJECT_EXPERIENCE]->(pe:ProjectExperience)
      WHERE pe.project_name IN $projects
    }""",
    "performance_ratings": """EXISTS {
      MATCH (pa:PerformanceAssessment)
      WHERE pa.employee_id = e.employee_id
      WITH pa
      ORDER BY coalesce(pa.assessment_year_int, -1) DESC, pa.performance_key DESC
      LIMIT 1
      WHERE pa.assessment_result IN $performance_ratings
      RETURN pa
    }""",
    "schools": """EXISTS {
      MATCH (e)-[:HAS_EDUCATION]->(ed:EducationExperience)
      WHERE ed.school_name IN $schools
    }""",
}
```

Append:

```cypher
RETURN DISTINCT e.employee_id AS employee_id
ORDER BY employee_id
SKIP $offset
LIMIT $fetch_limit
```

- [ ] **Step 4: Implement the employee-card query**

`build_card_query(employee_ids, selected_values)` must:

- load only the current page using `$employee_ids`
- return `employee_id`, `name`, `current_subsidiary`, `current_department`, and `current_position`
- always collect title names into `titles`
- include only requested dimensions in `matched_evidence`
- use independent evidence subqueries such as `CALL { WITH e MATCH (e)-[:HAS_PROJECT_EXPERIENCE]->(pe:ProjectExperience) WHERE pe.project_name IN $projects RETURN collect(DISTINCT pe.project_name) AS matched_projects }` so one-to-many relationships do not multiply employee rows
- order by employee identifier

The returned record keys must exactly match `EmployeeCard`.

- [ ] **Step 5: Run builder tests**

Run:

```powershell
python -m pytest tests/unit/test_employee_query_builder.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the preset builder**

```powershell
git add text2cypher/core/employee_query_builder.py tests/unit/test_employee_query_builder.py
git commit -m "新增员工预设查询构建"
```

---

### Task 5: Implement The Two-Stage Employee Query Service

**Repository:** `D:\study\my-mcp\text2cypher`

**Files:**
- Create: `text2cypher/core/employee_query_service.py`
- Create: `tests/unit/test_employee_query_service.py`

- [ ] **Step 1: Write failing service contract tests**

Use fake resolver, builder, validator, executor, and clock implementations. Cover:

```python
def test_service_runs_page_then_card_query_and_sets_has_more() -> None:
    result = service.query(EmployeeQueryRequest(titles=["高级工程师"], limit=2))

    assert result.status == "success"
    assert result.answerable is True
    assert [employee.employee_id for employee in result.employees] == ["E001", "E002"]
    assert result.pagination.returned_count == 2
    assert result.pagination.has_more is True
    assert result.scope == {
        "current_employees_only": True,
        "performance_scope": "latest",
        "project_scope": "all_history",
    }


def test_service_returns_clarification_without_filter_query() -> None:
    result = service.query(EmployeeQueryRequest(projects=["瓷粉项目"]))
    assert result.status == "needs_clarification"
    assert result.answerable is False
    assert executor.calls == []


def test_service_returns_success_for_empty_result() -> None:
    result = service.query(EmployeeQueryRequest(titles=["高级工程师"]))
    assert result.status == "success"
    assert result.employees == []
    assert result.pagination.has_more is False


def test_service_converts_validation_or_execution_error_to_query_failed() -> None:
    assert result.status == "query_failed"
    assert result.answerable is False
    assert result.employees == []
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_employee_query_service.py -v
```

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement service orchestration**

Implement this dependency boundary:

```python
class EmployeePresetQueryService:
    def __init__(
        self,
        *,
        resolver: EmployeeFilterResolver,
        builder: EmployeePresetCypherBuilder,
        validator: CypherValidator,
        executor: CypherExecutor,
        clock=time.perf_counter,
    ) -> None:
        self._resolver = resolver
        self._builder = builder
        self._validator = validator
        self._executor = executor
        self._clock = clock
```

Add `query(self, request: EmployeeQueryRequest) -> EmployeeQueryResult` with this exact execution order:

1. Resolve filter values.
2. Return `needs_clarification` before building employee queries when resolution is unsafe.
3. Build and validate the page-ID query with parameters.
4. Execute it with `max_rows=request.limit + 1`.
5. Derive `has_more` and retain only the requested page IDs.
6. Return successful empty results without running the card query.
7. Build, validate, and execute the card query for page IDs.
8. Convert records to `EmployeeCard`.
9. Return timing fields for resolution, filtering, card loading, and total duration.
10. Convert validation or execution exceptions into `query_failed`; do not leak raw Cypher.

- [ ] **Step 4: Run service tests**

Run:

```powershell
python -m pytest tests/unit/test_employee_query_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the service**

```powershell
git add text2cypher/core/employee_query_service.py tests/unit/test_employee_query_service.py
git commit -m "新增员工预设查询服务"
```

---

### Task 6: Expose The Optional MCP Tool And Sanitize Logs

**Repository:** `D:\study\my-mcp\text2cypher`

**Files:**
- Modify: `text2cypher/core/engine.py`
- Modify: `text2cypher/adapters/mcp/tools.py`
- Modify: `text2cypher/adapters/mcp/server.py`
- Modify: `text2cypher/adapters/mcp/call_logging.py`
- Modify: `tests/unit/test_engine.py`
- Modify: `tests/unit/test_mcp_server.py`
- Modify: `tests/unit/test_call_logging.py`

- [ ] **Step 1: Write failing engine and MCP tests**

Add tests proving:

- an engine without `EmployeePresetQueryService` exposes the existing seven tools only
- an engine with the service exposes eight tools including `query_employees`
- MCP arguments are converted into `EmployeeQueryRequest`
- an MCP request with no active filters returns `status=invalid_request` instead of raising a tool exception
- `answer_question` output and existing public contract are unchanged
- query-employee call logs contain status, selected values, timing, returned count, and `has_more`, but not employee cards

Example MCP assertion:

```python
result = toolkit["query_employees"](
    titles=["高级工程师"],
    departments=[],
    positions=[],
    subsidiaries=[],
    majors=[],
    projects=[],
    performance_ratings=[],
    schools=[],
    offset=0,
    limit=20,
)

assert result["status"] == "success"
assert fake_service.request.titles == ["高级工程师"]
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_engine.py tests/unit/test_mcp_server.py tests/unit/test_call_logging.py -v
```

Expected: FAIL because the optional engine service and MCP tool do not exist.

- [ ] **Step 3: Add optional engine support**

Extend `Text2CypherEngine.__init__`:

```python
employee_query_service: EmployeePresetQueryService | None = None,
```

Add:

```python
@property
def employee_query_enabled(self) -> bool:
    return self._employee_query_service is not None


def query_employees(self, request: EmployeeQueryRequest) -> EmployeeQueryResult:
    if self._employee_query_service is None:
        raise RuntimeError("Employee preset query is disabled")
    return self._employee_query_service.query(request)
```

Do not alter `answer_question`.

- [ ] **Step 4: Add conditional MCP registration**

Add the public MCP function with the request contract from the design. Construct `EmployeeQueryRequest` inside a `try` block; convert `pydantic.ValidationError` into an `EmployeeQueryResult` with `status="invalid_request"`, `answerable=false`, an empty employee list, request pagination, and a user-facing `limitation`. Add the function to the toolkit only when `engine.employee_query_enabled` is true. In `create_server`, register it only when present.

- [ ] **Step 5: Add per-tool log sanitization**

Extend logging without changing existing tool behavior:

```python
def log_mcp_tool_call(
    tool_name: str,
    func: F,
    *,
    output_sanitizer: Callable[[Any], Any] | None = None,
) -> F:
    sanitized_output = output_sanitizer(output) if output_sanitizer else output
    event["output"] = to_jsonable(sanitized_output)
```

For `query_employees`, log only:

```python
{
    "status": payload.get("status"),
    "answerable": payload.get("answerable"),
    "selected_values": payload.get("selected_values", {}),
    "timing": payload.get("timing", {}),
    "returned_count": payload.get("pagination", {}).get("returned_count", 0),
    "has_more": payload.get("pagination", {}).get("has_more", False),
}
```

- [ ] **Step 6: Run engine, MCP, and logging tests**

Run:

```powershell
python -m pytest tests/unit/test_engine.py tests/unit/test_mcp_server.py tests/unit/test_call_logging.py -v
```

Expected: PASS.

- [ ] **Step 7: Run the complete Text2Cypher unit suite**

Run:

```powershell
python -m pytest tests/unit -v
```

Expected: PASS with no `answer_question` regressions.

- [ ] **Step 8: Commit MCP exposure**

```powershell
git add text2cypher/core/engine.py text2cypher/adapters/mcp/tools.py text2cypher/adapters/mcp/server.py text2cypher/adapters/mcp/call_logging.py tests/unit/test_engine.py tests/unit/test_mcp_server.py tests/unit/test_call_logging.py
git commit -m "暴露员工预设查询工具"
```

---

### Task 7: Add A Live Employee Query Integration Test

**Repository:** `D:\study\my-mcp\text2cypher`

**Files:**
- Create: `tests/integration/test_live_query_employees.py`

- [ ] **Step 1: Write the opt-in live test**

The test must skip unless `TEXT2CYPHER_RUN_LIVE_SMOKE_TESTS=1`. Construct the real resolver, builder, validator, executor, and service using environment settings, then query one configured title value:

```python
@pytest.mark.skipif(
    os.getenv("TEXT2CYPHER_RUN_LIVE_SMOKE_TESTS") != "1",
    reason="live Neo4j smoke test is opt-in",
)
def test_live_query_employees_returns_parameterized_employee_cards() -> None:
    settings = AppSettings.from_env()
    validator = CypherValidator(settings)
    executor = CypherExecutor(settings, validator=validator)
    service = EmployeePresetQueryService(
        resolver=EmployeeFilterResolver(executor=executor),
        builder=EmployeePresetCypherBuilder(),
        validator=validator,
        executor=executor,
    )
    title = os.environ["TEXT2CYPHER_LIVE_EMPLOYEE_QUERY_TITLE"]
    result = service.query(EmployeeQueryRequest(titles=[title], limit=5))

    assert result.status == "success"
    assert result.selected_values["titles"]
    assert result.pagination.returned_count <= 5
    assert all(employee.employee_id and employee.name for employee in result.employees)
```

- [ ] **Step 2: Run integration tests without live opt-in**

Run:

```powershell
python -m pytest tests/integration/test_live_query_employees.py -v
```

Expected: SKIPPED.

- [ ] **Step 3: Run the live test with a known title**

Run:

```powershell
$env:TEXT2CYPHER_RUN_LIVE_SMOKE_TESTS='1'
$env:TEXT2CYPHER_LIVE_EMPLOYEE_QUERY_TITLE='高级工程师'
python -m pytest tests/integration/test_live_query_employees.py -v
```

Expected: PASS against the configured Neo4j database.

- [ ] **Step 4: Commit the integration test**

```powershell
git add tests/integration/test_live_query_employees.py
git commit -m "新增员工查询集成测试"
```

---

### Task 8: Wire The Optional Service Into DeerFlow Startup

**Repository:** `D:\python_project\deer-flow`

**Files:**
- Modify: `scripts/run_text2cypher_mcp.py`
- Modify: `extensions_config.json`
- Modify: `extensions_config.example.json`
- Modify: `deployment/hr-boss/extensions_config.docker.json`
- Create: `backend/tests/test_text2cypher_employee_query_launcher.py`
- Modify: `deployment/hr-boss-agent.md`

- [ ] **Step 1: Write failing launcher contract tests**

Test the environment parser independently and verify all deployed Text2Cypher configs set the flag:

```python
import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = REPO_ROOT / "scripts" / "run_text2cypher_mcp.py"
spec = importlib.util.spec_from_file_location("run_text2cypher_mcp_root", LAUNCHER_PATH)
assert spec and spec.loader
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_employee_query_flag_defaults_disabled(monkeypatch) -> None:
    monkeypatch.delenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", raising=False)
    assert launcher.employee_query_enabled() is False


def test_employee_query_flag_accepts_true(monkeypatch) -> None:
    monkeypatch.setenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", "true")
    assert launcher.employee_query_enabled() is True


def test_hr_boss_text2cypher_configs_enable_employee_query() -> None:
    config_paths = [
        REPO_ROOT / "extensions_config.example.json",
        REPO_ROOT / "deployment" / "hr-boss" / "extensions_config.docker.json",
    ]
    for path in config_paths:
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["mcpServers"]["text2cypher"]["env"]["TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED"] == "true"
```

- [ ] **Step 2: Run the launcher tests and verify they fail**

Run from `D:\python_project\deer-flow\backend`:

```powershell
uv run pytest tests/test_text2cypher_employee_query_launcher.py -v
```

Expected: FAIL because the flag helper and config entries do not exist.

- [ ] **Step 3: Construct the optional service**

In `scripts/run_text2cypher_mcp.py`, add:

```python
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def employee_query_enabled() -> bool:
    return os.getenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", "").strip().lower() in TRUE_ENV_VALUES
```

Construct one shared validator and executor. When enabled, construct:

```python
employee_query_service = EmployeePresetQueryService(
    resolver=EmployeeFilterResolver(executor=executor),
    builder=EmployeePresetCypherBuilder(),
    validator=validator,
    executor=executor,
)
```

Pass it to `Text2CypherEngine`. When disabled, pass `None`. Do not alter `answer_question` dependencies.

- [ ] **Step 4: Enable and document the feature flag**

Add:

```json
"TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED": "true"
```

to the tracked example and Docker Text2Cypher MCP environment blocks, and add it to the ignored local `extensions_config.json` for local verification. Update `deployment/hr-boss-agent.md` to state that disabling the flag removes `text2cypher_query_employees` while preserving `text2cypher_answer_question`.

- [ ] **Step 5: Run launcher contract tests**

Run:

```powershell
uv run pytest tests/test_text2cypher_employee_query_launcher.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit startup wiring**

```powershell
git add ../scripts/run_text2cypher_mcp.py ../extensions_config.example.json ../deployment/hr-boss/extensions_config.docker.json tests/test_text2cypher_employee_query_launcher.py ../deployment/hr-boss-agent.md
git commit -m "接入员工查询启动配置"
```

---

### Task 9: Expose The Tool And Define Agent Routing

**Repository:** `D:\python_project\deer-flow`

**Files:**
- Modify: `backend/.deer-flow/agents/hr-boss-agent/config.yaml`
- Modify: `skills/custom/hr-boss/SKILL.md`
- Modify: `backend/.deer-flow/agents/hr-boss-agent/text2cypher-profile.md`
- Modify: `AGENTS.md`
- Modify: `backend/tests/test_hr_boss_prompt_contract.py`
- Modify: `backend/tests/test_mcp_filtering.py`

- [ ] **Step 1: Write failing routing-contract tests**

Add assertions that:

```python
assert "text2cypher_query_employees" in allowed_tools
assert "员工名单、员工筛选或明确候选集合" in skill
assert "人数、平均值、占比、排名、分组或分布" in skill
assert "一轮最多调用一个 Text2Cypher 工具" in skill
assert "不得自动改用 `text2cypher_answer_question`" in skill
assert "绩效只匹配最近一期" in profile
assert "项目匹配全部项目经历" in profile
```

Update MCP filtering tests so the allowed tool list includes the two public Text2Cypher tools but continues excluding `text2cypher_execute_cypher`.

- [ ] **Step 2: Run routing tests and verify they fail**

Run from `D:\python_project\deer-flow\backend`:

```powershell
uv run pytest tests/test_hr_boss_prompt_contract.py tests/test_mcp_filtering.py -v
```

Expected: FAIL because the tool and routing rules are absent.

- [ ] **Step 3: Add the tool to the agent configuration**

Add:

```yaml
allowed_tools:
  - ask_clarification
  - text2cypher_query_employees
  - text2cypher_answer_question
  - hr-graphrag-qa_query_basic
  - hr-graphrag-qa_query_local
  - hr-graphrag-qa_query_global
  - hr-graphrag-qa_query_drift
```

- [ ] **Step 4: Replace the single-entry skill rule with a dual-tool contract**

The skill must state:

- Use `text2cypher_query_employees` when the desired result is an employee list, employee filtering result, or explicit candidate set and all requested filters fit the supported dimensions.
- Use `text2cypher_answer_question` for counts, averages, percentages, rankings, grouping, distributions, causal questions, free-form analysis, and unsupported filters.
- Explicit-condition recommendation questions may use `query_employees`; vague suitability scoring remains with `answer_question`.
- Call at most one Text2Cypher tool per turn.
- A non-success `query_employees` result must be explained or clarified; never retry it through `answer_question`.
- Read employee cards from `employees`, adopted scope from `scope`, and resolved terms from `selected_values`.

- [ ] **Step 5: Update the profile and project architecture**

Add the supported dimension semantics to `text2cypher-profile.md` without copying routing rules. Update `AGENTS.md` so the public Text2Cypher surface lists both tools and their distinct roles.

- [ ] **Step 6: Run routing tests**

Run:

```powershell
uv run pytest tests/test_hr_boss_prompt_contract.py tests/test_mcp_filtering.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit agent routing**

```powershell
git add .deer-flow/agents/hr-boss-agent/config.yaml ../skills/custom/hr-boss/SKILL.md .deer-flow/agents/hr-boss-agent/text2cypher-profile.md ../AGENTS.md tests/test_hr_boss_prompt_contract.py tests/test_mcp_filtering.py
git commit -m "更新员工查询路由规则"
```

---

### Task 10: Make Recommendation Fast Path And Evaluation Aware Of The Tool

**Repository:** `D:\python_project\deer-flow`

**Files:**
- Modify: `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- Modify: `backend/scripts/run_hr_boss_eval.py`
- Modify: `backend/tests/test_hr_boss_latency_policy.py`
- Modify: `backend/tests/test_hr_boss_eval_runner.py`

- [ ] **Step 1: Write failing fast-path and evaluation tests**

Add tests proving:

```python
def test_recommendation_fast_path_preserves_both_public_text2cypher_tools():
    tools = [
        SimpleNamespace(name="ask_clarification"),
        SimpleNamespace(name="text2cypher_query_employees"),
        SimpleNamespace(name="text2cypher_answer_question"),
        SimpleNamespace(name="hr-graphrag-qa_query_drift"),
    ]
    assert [tool.name for tool in filtered] == [
        "ask_clarification",
        "text2cypher_query_employees",
        "text2cypher_answer_question",
    ]


def test_boss_e2e_accepts_employee_query_route():
    assert ["text2cypher_query_employees"] in expected_routes_for("boss.e2e")
```

Also assert that the recommendation fallback prompt names both tools and explains explicit filters versus vague recommendation.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
uv run pytest tests/test_hr_boss_latency_policy.py tests/test_hr_boss_eval_runner.py -v
```

Expected: FAIL because the fallback prompt and evaluation routes know only `answer_question`.

- [ ] **Step 3: Update recommendation fallback prompt**

When the skill section cannot be loaded, the fallback must say:

```text
明确给出职称、部门、岗位、子公司、专业、项目、绩效或学校筛选条件，并要求员工名单时，调用 `text2cypher_query_employees`。
需要自由文本推荐、综合评分或不属于预设维度时，调用 `text2cypher_answer_question`。
不要调用 GraphRAG 或 `read_file`。
```

Keep the current direct-response wrapper limited to `text2cypher_answer_question`; V1 must not present stable employee-ID ordering as a suitability ranking.

- [ ] **Step 4: Update evaluation routes**

Add:

```python
TEXT2CYPHER_EMPLOYEE_QUERY_TOOL = "text2cypher_query_employees"
TEXT2CYPHER_EMPLOYEE_ROUTE = [TEXT2CYPHER_EMPLOYEE_QUERY_TOOL]
```

Keep `text2cypher.strict` and `term_resolution.strict` expecting `answer_question`. Add the employee route to the valid `boss.e2e` route alternatives.

- [ ] **Step 5: Run fast-path and evaluation tests**

Run:

```powershell
uv run pytest tests/test_hr_boss_latency_policy.py tests/test_hr_boss_eval_runner.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit compatibility changes**

```powershell
git add packages/harness/deerflow/agents/lead_agent/prompt.py scripts/run_hr_boss_eval.py tests/test_hr_boss_latency_policy.py tests/test_hr_boss_eval_runner.py
git commit -m "兼容员工查询推荐快路径"
```

---

### Task 11: Verify Both Repositories And Measure The New Path

**Repositories:**
- `D:\study\my-mcp\text2cypher`
- `D:\python_project\deer-flow`

- [ ] **Step 1: Verify the complete Text2Cypher unit suite**

Run from `D:\study\my-mcp\text2cypher`:

```powershell
python -m pytest tests/unit -v
```

Expected: PASS.

- [ ] **Step 2: Verify the live preset query**

Run:

```powershell
$env:TEXT2CYPHER_RUN_LIVE_SMOKE_TESTS='1'
$env:TEXT2CYPHER_LIVE_EMPLOYEE_QUERY_TITLE='高级工程师'
python -m pytest tests/integration/test_live_query_employees.py -v
```

Expected: PASS.

- [ ] **Step 3: Verify focused DeerFlow integration tests**

Run from `D:\python_project\deer-flow\backend`:

```powershell
uv run pytest tests/test_text2cypher_employee_query_launcher.py tests/test_hr_boss_prompt_contract.py tests/test_hr_boss_latency_policy.py tests/test_mcp_filtering.py tests/test_hr_boss_eval_runner.py -v
```

Expected: PASS.

- [ ] **Step 4: Verify wider DeerFlow agent/config regression tests**

Run:

```powershell
uv run pytest tests/test_agent_catalog.py tests/test_agent_config_fields.py tests/test_runtime_resolver.py tests/test_gateway_services.py tests/test_lead_agent_model_resolution.py -v
```

Expected: PASS.

- [ ] **Step 5: Confirm MCP tool exposure with the feature flag**

Start or inspect the Text2Cypher MCP server with:

```powershell
$env:TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED='true'
```

Confirm the available MCP tools include:

```text
text2cypher_query_employees
text2cypher_answer_question
```

Then set:

```powershell
$env:TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED='false'
```

Confirm `text2cypher_query_employees` is absent while `text2cypher_answer_question` remains available.

- [ ] **Step 6: Compare latency and LLM usage**

Run equivalent employee-list questions once through each tool and inspect Text2Cypher MCP call logs:

```text
query_employees:
- no Cypher-generation LLM call
- resolution_ms, filter_query_ms, card_query_ms, total_ms present

answer_question:
- existing planning/generation path unchanged
```

Record median and slowest observed latency for at least ten representative employee-list queries. Accept the rollout only when `query_employees` is faster and less variable, and all compared result sets follow the approved business scope.

- [ ] **Step 7: Inspect final diffs and repository status**

Run in both repositories:

```powershell
git diff --check
git status --short
git log --oneline -8
```

Expected:

- no whitespace errors
- no unrelated files staged
- the pre-existing Text2Cypher changes in `.env.example`, `README.md`, `text2cypher/config.py`, and `text2cypher/core/planner.py` remain intact and uncommitted unless the user separately requests otherwise
- all implementation commits use Chinese descriptions no longer than 20 characters
