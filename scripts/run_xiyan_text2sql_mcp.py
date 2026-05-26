from __future__ import annotations

import os
import re
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Callable


DEFAULT_BUSINESS_RULES_ROOT = (
    Path(os.environ.get("XIYAN_TEXT2SQL_BUSINESS_RULES", ""))
    if os.environ.get("XIYAN_TEXT2SQL_BUSINESS_RULES")
    else Path(__file__).resolve().parents[1] / "knowledge" / "business-rules"
)
DEFAULT_SQL_PROMPT_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "xiyan-text2sql" / "generate_sql_prompts.log"
XIYAN_SQL_MAX_TOKENS = 1024
MID_OR_ABOVE_TITLE_LEVELS = "employee_info.`最高职称级别` IN ('中级', '副高级', '正高级')"
QUALIFICATION_EXPLICIT_TERMS = ("资质", "资格", "证书", "职称资质", "职称资格")


def _normalize_question_text(text: str) -> str:
    return "".join(text.split())


def _uses_default_mid_or_above_title_policy(question: str) -> bool:
    normalized = _normalize_question_text(question)
    has_mid_or_above_title = (
        "中级及以上职称" in normalized
        or "中级以上职称" in normalized
        or ("中级" in normalized and "以上" in normalized and "职称" in normalized)
    )
    mentions_qualification_scope = any(term in normalized for term in QUALIFICATION_EXPLICIT_TERMS)
    return has_mid_or_above_title and not mentions_qualification_scope


def _sql_references_qualification(sql: str) -> bool:
    return re.search(r"(?i)(?:`?qualification`?)", sql) is not None


def _sql_uses_highest_title_level_filter(sql: str) -> bool:
    return (
        "最高职称级别" in sql
        and "中级" in sql
        and "副高级" in sql
        and "正高级" in sql
    )


def _mid_or_above_title_policy_error(question: str, sql: str) -> str | None:
    if not _uses_default_mid_or_above_title_policy(question):
        return None
    if not _sql_references_qualification(sql):
        if _sql_uses_highest_title_level_filter(sql):
            return None
        return (
            "Business rule violation: 用户问“中级及以上职称”且未明确要求资质/资格/证书口径时，"
            f"SQL 必须包含 {MID_OR_ABOVE_TITLE_LEVELS}。"
        )
    return (
        "Business rule violation: 用户问“中级及以上职称”且未明确要求资质/资格/证书口径时，"
        f"SQL 必须只按 {MID_OR_ABOVE_TITLE_LEVELS} 判断，不得引用 qualification 表。"
    )


def _append_mid_or_above_title_guard(question: str, evidence: str = "") -> str:
    evidence = evidence.strip()
    if not _uses_default_mid_or_above_title_policy(question):
        return evidence
    guard = (
        "[Business Rule Enforcement]\n"
        "For questions about 中级及以上职称 that do not explicitly ask for 资质/资格/证书 records, "
        f"use only {MID_OR_ABOVE_TITLE_LEVELS}. Do not JOIN qualification and do not use EXISTS qualification."
    )
    if not evidence:
        return guard
    return f"{evidence}\n\n{guard}"


def _validation_with_business_rule_error(validation: dict[str, Any], error_message: str) -> dict[str, Any]:
    updated = dict(validation)
    updated["valid"] = False
    updated["error_type"] = "business_rule_violation"
    updated["error_message"] = error_message
    warnings = list(updated.get("warnings") or [])
    warnings.append(error_message)
    updated["warnings"] = warnings
    return updated


def _failed_execution_payload(sql: str, validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "sql": sql,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "duration_ms": 0.0,
        "success": False,
        "error_type": validation.get("error_type"),
        "error_message": validation.get("error_message"),
    }


def _build_repair_evidence(evidence: str, sql: str, failure_reason: str) -> str:
    prefix = evidence.strip()
    suffix = (
        "Previous SQL failed.\n"
        f"Failure: {failure_reason}\n"
        f"SQL:\n{sql}"
    )
    return f"{prefix}\n\n{suffix}".strip()


def load_business_rules_md(business_rules_root: Path, database_id: str) -> str:
    rules_path = business_rules_root / database_id / "rules.md"
    if not rules_path.exists():
        return ""
    try:
        return rules_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise RuntimeError(f"Failed to load business rules: {rules_path}") from exc


def append_business_rule_evidence(
    business_rules_root: Path,
    database_id: str,
    evidence: str = "",
) -> str:
    rules_md = load_business_rules_md(business_rules_root, database_id)
    evidence = evidence.strip()
    if not rules_md:
        return evidence
    header = "[Business Rules]\nThe following business definitions apply to this database. Use them to disambiguate terms in the user question.\n\n"
    if not evidence:
        return header + rules_md
    return f"{evidence}\n\n{header}{rules_md}"


def append_generate_sql_prompt_log(prompt_log_path: Path, prompt_text: str) -> None:
    prompt_log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with prompt_log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"===== generate_sql prompt @ {timestamp} =====\n")
        handle.write(prompt_text)
        handle.write("\n\n")


def build_logged_sql_callable(
    sql_callable: Callable[..., str],
    prompt_template: str,
    prompt_log_path: Path,
) -> Callable[..., str]:
    def logged_sql_callable(**kwargs: Any) -> str:
        prompt_text = prompt_template.format(
            dialect=kwargs.get("dialect", ""),
            db_mschema=kwargs.get("db_mschema", ""),
            question=kwargs.get("question", ""),
            evidence=kwargs.get("evidence", ""),
        )
        try:
            append_generate_sql_prompt_log(prompt_log_path, prompt_text)
        except OSError:
            pass
        return sql_callable(**kwargs)

    return logged_sql_callable


@dataclass(frozen=True)
class LauncherSettings:
    repo_root: Path
    databases_config: Path
    api_key: str
    prompt_log_path: Path


class QuietEngineProxy:
    """Wrap noisy XiYan engine methods so MCP stdout stays JSON-only."""

    def __init__(self, engine: Any, business_rules_root: Path | None = None) -> None:
        self._engine = engine
        self._business_rules_root = business_rules_root or DEFAULT_BUSINESS_RULES_ROOT

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        with redirect_stdout(StringIO()):
            return getattr(self._engine, method_name)(*args, **kwargs)

    def list_databases(self) -> Any:
        return self._call("list_databases")

    def prepare_schema(self, database_id: str, refresh: bool = False) -> Any:
        return self._call("prepare_schema", database_id, refresh=refresh)

    def get_relevant_schema(self, database_id: str, question: str, max_tables: int = 8) -> Any:
        return self._call("get_relevant_schema", database_id, question, max_tables=max_tables)

    def generate_sql(self, database_id: str, question: str, evidence: str = "") -> Any:
        evidence = append_business_rule_evidence(
            business_rules_root=self._business_rules_root,
            database_id=database_id,
            evidence=evidence,
        )
        evidence = _append_mid_or_above_title_guard(question, evidence)
        return self._call("generate_sql", database_id, question, evidence=evidence)

    def validate_sql(self, database_id: str, sql: str) -> Any:
        return self._call("validate_sql", database_id, sql)

    def execute_sql(self, database_id: str, sql: str, max_rows: int = 100) -> Any:
        return self._call("execute_sql", database_id, sql, max_rows=max_rows)

    def answer_question(
        self,
        database_id: str,
        question: str,
        evidence: str = "",
        max_rows: int = 100,
        auto_repair: bool = True,
    ) -> Any:
        evidence = append_business_rule_evidence(
            business_rules_root=self._business_rules_root,
            database_id=database_id,
            evidence=evidence,
        )
        evidence = _append_mid_or_above_title_guard(question, evidence)
        generation, validation = self._generate_and_validate(database_id, question, evidence)

        validation_repair_attempted = False
        execution_repair_attempted = False
        if not validation.get("valid") and auto_repair:
            validation_repair_attempted = True
            generation, validation = self._generate_and_validate(
                database_id,
                question,
                _build_repair_evidence(
                    evidence,
                    generation.get("sql", ""),
                    validation.get("error_message") or "Validation failed.",
                ),
            )

        execution = _failed_execution_payload(generation.get("sql", ""), validation)
        if validation.get("valid"):
            execution = self._call("execute_sql", database_id, generation["sql"], max_rows=max_rows)

        if validation.get("valid") and not execution.get("success") and auto_repair:
            execution_repair_attempted = True
            generation, validation = self._generate_and_validate(
                database_id,
                question,
                _build_repair_evidence(
                    evidence,
                    generation.get("sql", ""),
                    execution.get("error_message") or "Execution failed.",
                ),
            )
            execution = _failed_execution_payload(generation.get("sql", ""), validation)
            if validation.get("valid"):
                execution = self._call("execute_sql", database_id, generation["sql"], max_rows=max_rows)

        return {
            "database_id": database_id,
            "question": question,
            "sql": generation.get("sql", ""),
            "repair_attempted": validation_repair_attempted or execution_repair_attempted,
            "validation_repair_attempted": validation_repair_attempted,
            "execution_repair_attempted": execution_repair_attempted,
            "generation": generation,
            "validation": validation,
            "execution": execution,
        }

    def _generate_and_validate(
        self,
        database_id: str,
        question: str,
        evidence: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        generation = self._call("generate_sql", database_id, question, evidence=evidence)
        validation = self._call("validate_sql", database_id, generation["sql"])
        policy_error = _mid_or_above_title_policy_error(question, generation["sql"])
        if validation.get("valid") and policy_error:
            validation = _validation_with_business_rule_error(validation, policy_error)
        return generation, validation


def resolve_settings() -> LauncherSettings:
    repo_raw = os.getenv("XIYAN_TEXT2SQL_REPO")
    if not repo_raw:
        raise RuntimeError("XIYAN_TEXT2SQL_REPO is required")

    databases_raw = os.getenv("XIYAN_TEXT2SQL_DATABASES_CONFIG")
    if not databases_raw:
        raise RuntimeError("XIYAN_TEXT2SQL_DATABASES_CONFIG is required")

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is required")

    repo_root = Path(repo_raw).expanduser().resolve()
    databases_config = Path(databases_raw).expanduser().resolve()

    if not repo_root.exists():
        raise RuntimeError(f"XIYAN_TEXT2SQL_REPO does not exist: {repo_root}")
    if not databases_config.exists():
        raise RuntimeError(f"XIYAN_TEXT2SQL_DATABASES_CONFIG does not exist: {databases_config}")

    prompt_log_raw = os.getenv("XIYAN_TEXT2SQL_PROMPT_LOG_PATH")
    prompt_log_path = (
        Path(prompt_log_raw).expanduser().resolve()
        if prompt_log_raw
        else DEFAULT_SQL_PROMPT_LOG_PATH
    )

    return LauncherSettings(
        repo_root=repo_root,
        databases_config=databases_config,
        api_key=api_key,
        prompt_log_path=prompt_log_path,
    )


def _ensure_repo_on_path(repo_root: Path) -> None:
    repo_path = str(repo_root)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)


def build_engine(settings: LauncherSettings):
    _ensure_repo_on_path(settings.repo_root)

    try:
        from llama_index.llms.dashscope import DashScope, DashScopeGenerationModels
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("DashScope is required to build the XiYan Text2SQL engine") from exc

    from components import dummy_sql_generator
    from default_prompts import DEFAULT_SQL_GEN_TMPL
    from text2sql.core.connection_registry import ConnectionRegistry
    from text2sql.core.engine import Text2SQLEngine
    from text2sql.core.schema_cache import SchemaCache
    from text2sql.core.schema_loader import SchemaLoader
    from text2sql.core.schema_retriever import SchemaRetriever
    from text2sql.core.sql_generator import PromptSqlGenerator
    from text2sql.core.sql_planner import SqlPlanner
    from text2sql.core.sql_validator import SqlValidator
    from text2sql.integrations.xiyan.schema_enhancer import XiYanSchemaEnhancer

    registry = ConnectionRegistry.from_json_file(settings.databases_config)
    llm = DashScope(
        model_name=DashScopeGenerationModels.QWEN_PLUS,
        api_key=settings.api_key,
        max_tokens=XIYAN_SQL_MAX_TOKENS,
    )

    return Text2SQLEngine(
        registry=registry,
        schema_loader=SchemaLoader(),
        schema_cache=SchemaCache(settings.repo_root / ".text2sql_cache"),
        schema_enhancer=XiYanSchemaEnhancer(llm=llm),
        schema_retriever=SchemaRetriever(),
        sql_planner=SqlPlanner(),
        sql_generator=PromptSqlGenerator(
            llm=llm,
            sql_callable=build_logged_sql_callable(
                sql_callable=dummy_sql_generator,
                prompt_template=DEFAULT_SQL_GEN_TMPL,
                prompt_log_path=settings.prompt_log_path,
            ),
        ),
        sql_validator=SqlValidator(),
    )


def create_server(engine: Any):
    from text2sql.adapters.mcp.server import create_server as _create_server

    return _create_server(engine)


def build_server():
    settings = resolve_settings()
    engine = build_engine(settings)
    return create_server(QuietEngineProxy(engine))


def main() -> None:
    server = build_server()
    server.run(
        transport="stdio",
        show_banner=False,
        log_level="error",
    )


if __name__ == "__main__":
    main()
