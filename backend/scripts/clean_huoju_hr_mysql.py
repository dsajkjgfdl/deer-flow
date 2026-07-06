#!/usr/bin/env python3
"""Build cleaned Huoju HR MySQL tables from imported raw API tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Sequence


DEFAULT_DATABASE = "huoju_hr"
DEFAULT_RAW_TABLE_PREFIX = "hr_"
CLEAN_TABLES = (
    "dim_employee",
    "dim_org_path",
    "dim_org_unit",
    "dim_department",
    "dim_position",
    "dim_employment_status",
    "dim_education_level",
    "dim_performance_grade",
    "dim_title_level",
    "fact_employee_change",
    "fact_employee_org_path",
    "fact_employee_contract",
    "fact_education",
    "fact_performance",
    "fact_job_title",
    "fact_professional_qualification",
    "fact_project_experience",
    "dws_employee_profile",
    "dq_hr_cleaning_errors",
)

NULL_MARKERS = {"", "无", "未知", "未填写", "N/A", "n/a", "NULL", "null", "None", "-", "--", "<?>"}
CURRENT_EMPLOYEE_STATUSES = {"正式员工", "试用员工", "实习", "返聘", "劳务派遣-正式"}
DEFAULT_DATE_SENTINELS = {"1900-01-01", "1899-12-31"}
CURRENT_END_DATE_SENTINELS = {"2199-12-31", "9999-12-31"}
EDUCATION_LEVEL_RANKS = {
    "博士": 70,
    "博士研究生": 70,
    "硕士": 60,
    "硕士研究生": 60,
    "研究生": 60,
    "本科": 40,
    "大专以下": 20,
    "大专": 30,
    "专科": 30,
    "中专": 20,
    "高中": 20,
    "初中": 10,
}
PERFORMANCE_GRADE_RANKS = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
TITLE_LEVEL_RANKS = {"正高级": 50, "高级": 40, "中级": 30, "初级": 20}


@dataclass(frozen=True)
class BusinessDate:
    date_value: date | None
    is_default_date: bool
    is_current_sentinel: bool


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return None if text in NULL_MARKERS else text


def _field(row: dict[str, Any], name: str) -> str | None:
    return clean_text(row.get(name))


def _first_field(row: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = _field(row, name)
        if value is not None:
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    if number is None:
        return None
    return int(number)


def parse_business_date(value: Any) -> BusinessDate:
    text = clean_text(value)
    if not text:
        return BusinessDate(date_value=None, is_default_date=False, is_current_sentinel=False)
    normalized = text.replace("/", "-")
    match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", normalized)
    if not match:
        return BusinessDate(date_value=None, is_default_date=False, is_current_sentinel=False)
    date_text = match.group(1)
    parts = date_text.split("-")
    date_text = f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    if date_text in DEFAULT_DATE_SENTINELS:
        return BusinessDate(date_value=None, is_default_date=True, is_current_sentinel=False)
    if date_text in CURRENT_END_DATE_SENTINELS:
        return BusinessDate(date_value=None, is_default_date=False, is_current_sentinel=True)
    try:
        parsed = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return BusinessDate(date_value=None, is_default_date=False, is_current_sentinel=False)
    return BusinessDate(date_value=parsed, is_default_date=False, is_current_sentinel=False)


def calculate_tenure_years(join_date: date | None, as_of_date: date | None = None) -> float | None:
    if join_date is None:
        return None
    effective_as_of_date = as_of_date or date.today()
    if join_date > effective_as_of_date:
        return None
    return round((effective_as_of_date - join_date).days / 365.25, 2)


def parse_as_of_date(value: str | None) -> date | None:
    if not value:
        return None
    parsed = parse_business_date(value)
    if parsed.date_value is None:
        raise ValueError(f"Invalid as-of date: {value}")
    return parsed.date_value


def is_current_employee_status(status: Any) -> bool:
    return clean_text(status) in CURRENT_EMPLOYEE_STATUSES


def _mobile_valid(value: Any) -> int:
    text = clean_text(value)
    if not text:
        return 0
    return 1 if re.fullmatch(r"1\d{10}", re.sub(r"\D", "", text)) else 0


def _latest_change_sort_key(row: dict[str, Any]) -> tuple[date, int, date]:
    start = parse_business_date(row.get("开始日期"))
    end = parse_business_date(row.get("结束日期"))
    start_date = start.date_value or date.min
    end_date = end.date_value or date.max if end.is_current_sentinel else end.date_value or date.min
    return start_date, 1 if end.is_current_sentinel else 0, end_date


def latest_change_by_employee(change_rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in change_rows:
        employee_id = _field(row, "员工编号")
        if not employee_id:
            continue
        if employee_id not in latest or _latest_change_sort_key(row) > _latest_change_sort_key(latest[employee_id]):
            latest[employee_id] = row
    return latest


def build_employee_dimension(
    base_rows: Sequence[dict[str, Any]],
    change_rows: Sequence[dict[str, Any]],
    *,
    as_of_date: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    latest_changes = latest_change_by_employee(change_rows)
    effective_as_of_date = as_of_date or date.today()
    employees: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for row in base_rows:
        employee_id = _field(row, "员工编号")
        if not employee_id:
            errors.append(
                {
                    "source_table": "hr_baseinfo",
                    "employee_id": None,
                    "error_type": "missing_employee_id",
                    "details": {"员工姓名": _field(row, "员工姓名")},
                }
            )
            continue
        if employee_id in seen_ids:
            errors.append(
                {
                    "source_table": "hr_baseinfo",
                    "employee_id": employee_id,
                    "error_type": "duplicate_employee_id",
                    "details": {},
                }
            )
            continue
        seen_ids.add(employee_id)
        latest_change = latest_changes.get(employee_id, {})
        status = _field(latest_change, "用工关系状态")
        join_date = parse_business_date(row.get("入司日期"))
        employees.append(
            {
                "employee_id": employee_id,
                "employee_name": _field(row, "员工姓名"),
                "source_org": _field(row, "组织"),
                "confidential_flag": _field(row, "是否涉密"),
                "gender": _field(row, "性别"),
                "age": _int_or_none(_field(row, "年龄")),
                "age_band": _field(row, "年龄分段"),
                "tenure_years": calculate_tenure_years(join_date.date_value, effective_as_of_date),
                "current_department": _field(latest_change, "部门"),
                "current_position": _field(latest_change, "职位"),
                "employment_status": status,
                "is_current_employee": 1 if is_current_employee_status(status) else 0,
                "join_date": join_date.date_value,
                "is_default_join_date": 1 if join_date.is_default_date else 0,
                "id_card_present": 1 if _field(row, "身份证信息") else 0,
                "mobile_valid": _mobile_valid(row.get("手机号码")),
                "email_present": 1 if _field(row, "电子邮箱") else 0,
            }
        )
    return employees, errors


def org_path_id(org_path: str) -> str:
    return hashlib.sha1(org_path.encode("utf-8")).hexdigest()


def split_org_path(org_path: str | None) -> list[str | None]:
    parts = [part for part in (clean_text(org_path) or "").split("_") if clean_text(part)]
    return [*parts[:6], *([None] * max(0, 6 - len(parts)))]


def _path_parts(org_path: str) -> list[str]:
    return [part for part in org_path.split("_") if part]


def _is_prefix_path(candidate_parent: str, candidate_child: str) -> bool:
    parent_parts = _path_parts(candidate_parent)
    child_parts = _path_parts(candidate_child)
    return len(parent_parts) < len(child_parts) and child_parts[: len(parent_parts)] == parent_parts


def _path_company(org_path: str | None) -> str | None:
    levels = split_org_path(org_path)
    return levels[1]


def _org_path_profile_fields(org_path: str | None) -> dict[str, str | None]:
    parts = _path_parts(clean_text(org_path) or "")
    return {
        "current_org_name": parts[1] if len(parts) > 1 else None,
        "current_center_name": parts[2] if len(parts) > 2 else None,
        "current_org_unit_name": parts[-1] if parts else None,
        "current_org_full_path": "_".join(parts) if parts else None,
    }


def _classify_employee_org_paths(paths: Sequence[dict[str, Any]]) -> dict[str, str]:
    classifications: dict[str, str] = {}
    normalized_paths = [_field(path, "组织架构") for path in paths]
    valid_paths = [path for path in normalized_paths if path]
    for row, path in zip(paths, normalized_paths):
        if not path:
            continue
        org = _field(row, "组织")
        if org and _path_company(path) and org != _path_company(path):
            classifications[path] = "cross_org_review"
            continue
        has_hierarchy_peer = any(
            other
            and other != path
            and (_is_prefix_path(path, other) or _is_prefix_path(other, path))
            for other in valid_paths
        )
        if has_hierarchy_peer:
            classifications[path] = "hierarchy_duplicate"
        elif len(valid_paths) > 1:
            classifications[path] = "matrix_or_parttime"
        else:
            classifications[path] = "current_path"
    return classifications


def build_org_path_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    employee_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    org_path_by_id: dict[str, dict[str, Any]] = {}
    facts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    rows_by_employee: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        employee_id = _field(row, "员工编号")
        org_path = _field(row, "组织架构")
        if not employee_id:
            errors.append(
                {
                    "source_table": "hr_organizationalstructure",
                    "employee_id": None,
                    "error_type": "missing_employee_id",
                    "details": {"组织": _field(row, "组织")},
                }
            )
            continue
        if employee_id not in employee_ids:
            errors.append(
                {
                    "source_table": "hr_organizationalstructure",
                    "employee_id": employee_id,
                    "error_type": "orphan_employee_id",
                    "details": {"组织架构": org_path},
                }
            )
        if not org_path:
            errors.append(
                {
                    "source_table": "hr_organizationalstructure",
                    "employee_id": employee_id,
                    "error_type": "missing_org_path",
                    "details": {"组织": _field(row, "组织")},
                }
            )
            continue
        rows_by_employee.setdefault(employee_id, []).append(row)
        path_id = org_path_id(org_path)
        if path_id not in org_path_by_id:
            levels = split_org_path(org_path)
            org_path_by_id[path_id] = {
                "org_path_id": path_id,
                "org_path": org_path,
                "level_1": levels[0],
                "level_2": levels[1],
                "level_3": levels[2],
                "level_4": levels[3],
                "level_5": levels[4],
                "level_6": levels[5],
                "depth": len([level for level in levels if level]),
            }

    for employee_id, employee_rows in rows_by_employee.items():
        classifications = _classify_employee_org_paths(employee_rows)
        for row in employee_rows:
            org_path = _field(row, "组织架构")
            if not org_path:
                continue
            org = _field(row, "组织")
            company = _path_company(org_path)
            facts.append(
                {
                    "employee_id": employee_id,
                    "employee_name": _field(row, "员工姓名"),
                    "org": org,
                    "org_path_id": org_path_id(org_path),
                    "org_path": org_path,
                    "path_relation_type": classifications.get(org_path, "current_path"),
                    "org_company_mismatch": 1 if org and company and org != company else 0,
                }
            )
    return list(org_path_by_id.values()), facts, errors


def build_org_unit_dimension(org_paths: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    org_unit_by_id: dict[str, dict[str, Any]] = {}
    for org_path_row in org_paths:
        parts = _path_parts(str(org_path_row.get("org_path") or ""))
        for depth in range(1, len(parts) + 1):
            prefix_parts = parts[:depth]
            full_path = "_".join(prefix_parts)
            unit_id = org_path_id(full_path)
            if unit_id in org_unit_by_id:
                continue
            parent_path = "_".join(prefix_parts[:-1]) if depth > 1 else None
            org_unit_by_id[unit_id] = {
                "org_unit_id": unit_id,
                "org_unit_name": prefix_parts[-1],
                "org_full_path": full_path,
                "parent_org_unit_id": org_path_id(parent_path) if parent_path else None,
                "parent_org_full_path": parent_path,
                "org_name": prefix_parts[1] if depth >= 2 else None,
                "center_name": prefix_parts[2] if depth >= 3 else None,
                "depth": depth,
            }
    return sorted(org_unit_by_id.values(), key=lambda row: (row["org_full_path"], row["depth"]))


def merge_contract_rows(
    employee_contract_rows: Sequence[dict[str, Any]],
    other_contract_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for source_table, rows in (
        ("hr_employeecontract", employee_contract_rows),
        ("hr_othercontracts", other_contract_rows),
    ):
        for row in rows:
            contract_no = _field(row, "合同编号")
            if not contract_no:
                errors.append(
                    {
                        "source_table": source_table,
                        "employee_id": _field(row, "员工编号"),
                        "error_type": "missing_contract_no",
                        "details": {},
                    }
                )
                continue
            if contract_no not in merged:
                merged[contract_no] = {
                    "contract_no": contract_no,
                    "employee_id": _field(row, "员工编号"),
                    "contract_status": _field(row, "合同状态"),
                    "source_tables": source_table,
                    "raw_payload": row,
                }
            else:
                source_tables = merged[contract_no]["source_tables"].split(",")
                if source_table not in source_tables:
                    source_tables.append(source_table)
                merged[contract_no]["source_tables"] = ",".join(source_tables)
    return list(merged.values()), errors


def build_employee_change_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    employee_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in rows:
        row_errors = _employee_errors_for_fact("hr_employeechangerecords", row, employee_ids)
        errors.extend(row_errors)
        employee_id = _field(row, "员工编号")
        if row_errors:
            continue
        start_date = parse_business_date(row.get("开始日期"))
        end_date = parse_business_date(row.get("结束日期"))
        status = _field(row, "用工关系状态")
        facts.append(
            {
                "change_id": _stable_row_id("employee_change", row),
                "employee_id": employee_id,
                "employee_name": _field(row, "员工姓名"),
                "department": _field(row, "部门"),
                "position": _field(row, "职位"),
                "change_type": _field(row, "变动类型"),
                "employment_status": status,
                "start_date": start_date.date_value,
                "end_date": end_date.date_value,
                "is_current_interval": 1 if end_date.is_current_sentinel else 0,
                "is_current_employee_status": 1 if is_current_employee_status(status) else 0,
                "raw_payload": row,
            }
        )
    dimensions = {
        "dim_department": _sorted_single_column_dimension("department_name", (fact["department"] for fact in facts)),
        "dim_position": _sorted_single_column_dimension("position_name", (fact["position"] for fact in facts)),
        "dim_employment_status": [
            {"employment_status": status, "is_current_employee_status": 1 if is_current_employee_status(status) else 0}
            for status in sorted({fact["employment_status"] for fact in facts if fact["employment_status"]})
        ],
    }
    return facts, dimensions, errors


def build_education_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    employee_ids: set[str],
    today: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    today = today or date.today()
    facts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    highest_by_employee: dict[str, int] = {}
    for row in rows:
        row_errors = _employee_errors_for_fact("hr_educationexperience", row, employee_ids)
        errors.extend(row_errors)
        employee_id = _field(row, "员工编号")
        if row_errors:
            continue
        education_level = _field(row, "学历")
        education_rank = _rank_from_mapping(education_level, EDUCATION_LEVEL_RANKS)
        enrollment_date = parse_business_date(row.get("入学时间"))
        graduation_date = parse_business_date(row.get("毕业时间"))
        is_highest = 1 if str(row.get("最高学历") or "").strip() == "1" else 0
        if is_highest:
            highest_by_employee[employee_id or ""] = highest_by_employee.get(employee_id or "", 0) + 1
        facts.append(
            {
                "education_id": _stable_row_id("education", row),
                "employee_id": employee_id,
                "employee_name": _field(row, "员工姓名"),
                "education_level": education_level,
                "education_level_rank": education_rank,
                "major": _field(row, "专业"),
                "school": _field(row, "毕业学校"),
                "school_type": _field(row, "学校类型"),
                "is_highest_education": is_highest,
                "enrollment_date": enrollment_date.date_value,
                "is_default_enrollment_date": 1 if enrollment_date.is_default_date else 0,
                "graduation_date": graduation_date.date_value,
                "is_expected_graduation": 1 if graduation_date.date_value and graduation_date.date_value > today else 0,
                "raw_payload": row,
            }
        )
    for employee_id, count in highest_by_employee.items():
        if count > 1:
            errors.append(_error("hr_educationexperience", employee_id, "multiple_highest_education", {"count": count}))
    dimensions = {
        "dim_education_level": _ranked_dimension(
            "education_level",
            "sort_rank",
            ((fact["education_level"], fact["education_level_rank"]) for fact in facts),
        )
    }
    return facts, dimensions, errors


def build_performance_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    employee_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, int | None]] = set()
    for row in rows:
        row_errors = _employee_errors_for_fact("hr_performancerecord", row, employee_ids)
        errors.extend(row_errors)
        employee_id = _field(row, "员工编号")
        if row_errors:
            continue
        year = _extract_year(row.get("考核年份"))
        key = (employee_id, year)
        if key in seen_keys:
            errors.append(_error("hr_performancerecord", employee_id, "duplicate_employee_performance_year", {"year": year}))
        seen_keys.add(key)
        result = _field(row, "考核结果")
        grade = _performance_grade(result)
        grade_rank = PERFORMANCE_GRADE_RANKS.get(grade or "", 0)
        facts.append(
            {
                "performance_id": _stable_row_id("performance", row),
                "employee_id": employee_id,
                "employee_name": _field(row, "员工姓名"),
                "assessment_year": year,
                "performance_result": result,
                "performance_grade": grade,
                "performance_grade_rank": grade_rank,
                "manager_comment_present": 1 if _field(row, "主管评价") else 0,
                "raw_payload": row,
            }
        )
    dimensions = {
        "dim_performance_grade": _ranked_dimension(
            "performance_grade",
            "sort_rank",
            ((fact["performance_grade"], fact["performance_grade_rank"]) for fact in facts),
        )
    }
    return facts, dimensions, errors


def build_job_title_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    employee_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    highest_by_employee: dict[str, int] = {}
    for row in rows:
        row_errors = _employee_errors_for_fact("hr_jobtitleinfo", row, employee_ids)
        errors.extend(row_errors)
        employee_id = _field(row, "员工编号")
        if row_errors:
            continue
        title_level = _field(row, "职称级别")
        level_rank = _rank_from_mapping(title_level, TITLE_LEVEL_RANKS)
        is_highest = 1 if str(row.get("最高职称") or "").strip() == "1" else 0
        if is_highest:
            highest_by_employee[employee_id or ""] = highest_by_employee.get(employee_id or "", 0) + 1
        facts.append(
            {
                "job_title_id": _stable_row_id("job_title", row),
                "employee_id": employee_id,
                "employee_name": _field(row, "员工姓名"),
                "title_name": _field(row, "职称内容"),
                "title_level": title_level,
                "title_level_rank": level_rank,
                "is_highest_title": is_highest,
                "certificate_no": _field(row, "证书编号"),
                "issuer": _field(row, "评定单位"),
                "awarded_date": _date_or_none(row.get("职称授予时间")),
                "raw_payload": row,
            }
        )
    for employee_id, count in highest_by_employee.items():
        if count > 1:
            errors.append(_error("hr_jobtitleinfo", employee_id, "multiple_highest_title", {"count": count}))
    dimensions = {
        "dim_title_level": _ranked_dimension(
            "title_level",
            "sort_rank",
            ((fact["title_level"], fact["title_level_rank"]) for fact in facts),
        )
    }
    return facts, dimensions, errors


def build_professional_qualification_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    employee_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in rows:
        row_errors = _employee_errors_for_fact("hr_professionalqualification", row, employee_ids)
        errors.extend(row_errors)
        employee_id = _field(row, "员工编号")
        if row_errors:
            continue
        facts.append(
            {
                "qualification_id": _stable_row_id("professional_qualification", row),
                "employee_id": employee_id,
                "employee_name": _field(row, "员工姓名"),
                "qualification_name": _field(row, "职业资格"),
                "qualification_level": _field(row, "职业资格级别"),
                "issuer": _field(row, "授予单位"),
                "acquired_date": _date_or_none(row.get("获取时间")),
                "raw_payload": row,
            }
        )
    return facts, errors


def build_project_experience_outputs(
    rows: Sequence[dict[str, Any]],
    *,
    employee_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in rows:
        row_errors = _employee_errors_for_fact("hr_projectexperience", row, employee_ids)
        errors.extend(row_errors)
        employee_id = _field(row, "员工编号")
        if row_errors:
            continue
        end_date = parse_business_date(row.get("结束时间"))
        facts.append(
            {
                "project_experience_id": _stable_row_id("project_experience", row),
                "employee_id": employee_id,
                "employee_name": _field(row, "员工姓名"),
                "project_name": _field(row, "项目名称"),
                "project_role": _field(row, "担任角色"),
                "start_date": _date_or_none(row.get("开始时间")),
                "end_date": end_date.date_value,
                "is_current_project": 1 if end_date.is_current_sentinel else 0,
                "responsibility_present": 1 if _field(row, "主要职责") else 0,
                "raw_payload": row,
            }
        )
    return facts, errors


def quote_identifier(identifier: str) -> str:
    if not identifier or "`" in identifier or "\x00" in identifier:
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f"`{identifier}`"


def connect_mysql(*, host: str, port: int, user: str, password: str, database: str) -> Any:
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - runtime dependency guard.
        raise RuntimeError("Missing dependency pymysql. Install backend dependencies before running cleaner.") from exc
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )


def read_raw_rows(connection: Any, table_name: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT raw_payload FROM {quote_identifier(table_name)}")
        payloads = cursor.fetchall()
    rows: list[dict[str, Any]] = []
    for item in payloads:
        raw_payload = item[0]
        if isinstance(raw_payload, dict):
            rows.append(raw_payload)
        else:
            rows.append(json.loads(raw_payload))
    return rows


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _stable_row_id(prefix: str, row: dict[str, Any]) -> str:
    payload = _json_dumps(row)
    return hashlib.sha1(f"{prefix}:{payload}".encode("utf-8")).hexdigest()


def _error(source_table: str, employee_id: str | None, error_type: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_table": source_table,
        "employee_id": employee_id,
        "error_type": error_type,
        "details": details,
    }


def _employee_errors_for_fact(source_table: str, row: dict[str, Any], employee_ids: set[str]) -> list[dict[str, Any]]:
    employee_id = _field(row, "员工编号")
    if not employee_id:
        return [_error(source_table, None, "missing_employee_id", {"员工姓名": _field(row, "员工姓名")})]
    if employee_id not in employee_ids:
        return [_error(source_table, employee_id, "orphan_employee_id", {"员工姓名": _field(row, "员工姓名")})]
    return []


def _date_or_none(value: Any) -> date | None:
    return parse_business_date(value).date_value


def _rank_from_mapping(value: str | None, mapping: dict[str, int], default: int = 0) -> int:
    if not value:
        return default
    for key, rank in mapping.items():
        if key in value:
            return rank
    return default


def _extract_year(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(\d{4})", text)
    return int(match.group(1)) if match else None


def _performance_grade(value: str | None) -> str | None:
    if not value:
        return None
    match = re.match(r"\s*([SABCD])", value, flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def _sorted_single_column_dimension(name: str, values: Iterable[str | None]) -> list[dict[str, Any]]:
    return [{name: value} for value in sorted({value for value in values if value})]


def _ranked_dimension(name: str, rank_name: str, values: Iterable[tuple[str | None, int]]) -> list[dict[str, Any]]:
    by_value: dict[str, int] = {}
    for value, rank in values:
        if value and value not in by_value:
            by_value[value] = rank
    return [{name: value, rank_name: by_value[value]} for value in sorted(by_value)]


def _rows_by_employee(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_employee: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        employee_id = row.get("employee_id")
        if employee_id:
            by_employee.setdefault(employee_id, []).append(row)
    return by_employee


def _date_sort_value(value: Any) -> date:
    return value if isinstance(value, date) else date.min


def build_employee_profile_outputs(
    *,
    employees: Sequence[dict[str, Any]],
    org_facts: Sequence[dict[str, Any]],
    educations: Sequence[dict[str, Any]],
    performances: Sequence[dict[str, Any]],
    job_titles: Sequence[dict[str, Any]],
    qualifications: Sequence[dict[str, Any]],
    projects: Sequence[dict[str, Any]],
    errors: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    org_by_employee = _rows_by_employee(org_facts)
    education_by_employee = _rows_by_employee(educations)
    performance_by_employee = _rows_by_employee(performances)
    title_by_employee = _rows_by_employee(job_titles)
    qualification_by_employee = _rows_by_employee(qualifications)
    project_by_employee = _rows_by_employee(projects)
    error_employee_ids = {error.get("employee_id") for error in errors if error.get("employee_id")}

    relation_priority = {
        "current_path": 0,
        "hierarchy_duplicate": 1,
        "matrix_or_parttime": 2,
        "cross_org_review": 3,
    }
    profiles: list[dict[str, Any]] = []
    for employee in employees:
        employee_id = employee["employee_id"]
        employee_orgs = org_by_employee.get(employee_id, [])
        primary_org = min(
            employee_orgs,
            key=lambda row: (
                relation_priority.get(str(row.get("path_relation_type") or ""), 99),
                str(row.get("org_path") or ""),
            ),
            default=None,
        )
        highest_education = max(
            education_by_employee.get(employee_id, []),
            key=lambda row: (
                int(row.get("is_highest_education") or 0),
                int(row.get("education_level_rank") or 0),
                _date_sort_value(row.get("graduation_date")),
            ),
            default=None,
        )
        latest_performance = max(
            performance_by_employee.get(employee_id, []),
            key=lambda row: (
                int(row.get("assessment_year") or 0),
                int(row.get("performance_grade_rank") or 0),
            ),
            default=None,
        )
        highest_title = max(
            title_by_employee.get(employee_id, []),
            key=lambda row: (
                int(row.get("is_highest_title") or 0),
                int(row.get("title_level_rank") or 0),
                _date_sort_value(row.get("awarded_date")),
            ),
            default=None,
        )

        has_org_path = 1 if employee_orgs else 0
        has_multi_org_path = 1 if len(employee_orgs) > 1 else 0
        has_cross_org_review = 1 if any(row.get("path_relation_type") == "cross_org_review" for row in employee_orgs) else 0
        has_cleaning_error = 1 if employee_id in error_employee_ids else 0
        org_fields = _org_path_profile_fields(primary_org.get("org_path") if primary_org else None)
        current_department = employee.get("current_department")
        current_org_unit_name = org_fields["current_org_unit_name"]
        department_org_unit_mismatch = 1 if current_department and current_org_unit_name and current_department != current_org_unit_name else 0
        data_quality_flags = []
        if not has_org_path:
            data_quality_flags.append("no_org_path")
        if has_multi_org_path:
            data_quality_flags.append("multi_org_path")
        if has_cross_org_review:
            data_quality_flags.append("cross_org_review")
        if has_cleaning_error:
            data_quality_flags.append("has_cleaning_error")

        profiles.append(
            {
                "employee_id": employee_id,
                "employee_name": employee.get("employee_name"),
                "source_org": employee.get("source_org"),
                "join_date": employee.get("join_date"),
                "confidential_flag": employee.get("confidential_flag"),
                "gender": employee.get("gender"),
                "age": employee.get("age"),
                "age_band": employee.get("age_band"),
                "tenure_years": employee.get("tenure_years"),
                "current_department": current_department,
                "current_position": employee.get("current_position"),
                "employment_status": employee.get("employment_status"),
                "is_current_employee": employee.get("is_current_employee", 0),
                "current_org_name": org_fields["current_org_name"],
                "current_center_name": org_fields["current_center_name"],
                "current_org_unit_name": current_org_unit_name,
                "current_org_full_path": org_fields["current_org_full_path"],
                "department_org_unit_mismatch": department_org_unit_mismatch,
                "primary_org_path": primary_org.get("org_path") if primary_org else None,
                "org_path_count": len(employee_orgs),
                "has_org_path": has_org_path,
                "has_multi_org_path": has_multi_org_path,
                "has_cross_org_review": has_cross_org_review,
                "highest_education_level": highest_education.get("education_level") if highest_education else None,
                "highest_education_rank": highest_education.get("education_level_rank") if highest_education else 0,
                "highest_school": highest_education.get("school") if highest_education else None,
                "highest_major": highest_education.get("major") if highest_education else None,
                "latest_performance_year": latest_performance.get("assessment_year") if latest_performance else None,
                "latest_performance_result": latest_performance.get("performance_result") if latest_performance else None,
                "latest_performance_grade": latest_performance.get("performance_grade") if latest_performance else None,
                "latest_performance_grade_rank": latest_performance.get("performance_grade_rank") if latest_performance else 0,
                "highest_title_name": highest_title.get("title_name") if highest_title else None,
                "highest_title_level": highest_title.get("title_level") if highest_title else None,
                "highest_title_level_rank": highest_title.get("title_level_rank") if highest_title else 0,
                "qualification_count": len(qualification_by_employee.get(employee_id, [])),
                "project_count": len(project_by_employee.get(employee_id, [])),
                "has_cleaning_error": has_cleaning_error,
                "data_quality_flags": data_quality_flags,
            }
        )
    return profiles


def _drop_clean_tables(connection: Any) -> None:
    with connection.cursor() as cursor:
        for table_name in reversed(CLEAN_TABLES):
            cursor.execute(f"DROP TABLE IF EXISTS {quote_identifier(table_name)}")
    connection.commit()


def _create_clean_tables(connection: Any) -> None:
    ddl_statements = [
        """
        CREATE TABLE `dim_employee` (
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `source_org` VARCHAR(255) NULL,
          `confidential_flag` VARCHAR(16) COLLATE utf8mb4_bin NULL,
          `gender` VARCHAR(32) COLLATE utf8mb4_bin NULL,
          `age` INT NULL,
          `age_band` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `tenure_years` DOUBLE NULL,
          `current_department` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `current_position` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `employment_status` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `is_current_employee` TINYINT NOT NULL,
          `join_date` DATE NULL,
          `is_default_join_date` TINYINT NOT NULL,
          `id_card_present` TINYINT NOT NULL,
          `mobile_valid` TINYINT NOT NULL,
          `email_present` TINYINT NOT NULL,
          PRIMARY KEY (`employee_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_org_path` (
          `org_path_id` CHAR(40) NOT NULL,
          `org_path` TEXT NOT NULL,
          `level_1` VARCHAR(255) NULL,
          `level_2` VARCHAR(255) NULL,
          `level_3` VARCHAR(255) NULL,
          `level_4` VARCHAR(255) NULL,
          `level_5` VARCHAR(255) NULL,
          `level_6` VARCHAR(255) NULL,
          `depth` TINYINT NOT NULL,
          PRIMARY KEY (`org_path_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_org_unit` (
          `org_unit_id` CHAR(40) NOT NULL,
          `org_unit_name` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
          `org_full_path` TEXT NOT NULL,
          `parent_org_unit_id` CHAR(40) NULL,
          `parent_org_full_path` TEXT NULL,
          `org_name` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `center_name` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `depth` TINYINT NOT NULL,
          PRIMARY KEY (`org_unit_id`),
          KEY `idx_dim_org_unit_name` (`org_unit_name`),
          KEY `idx_dim_org_unit_parent` (`parent_org_unit_id`),
          KEY `idx_dim_org_unit_org_name` (`org_name`),
          KEY `idx_dim_org_unit_center_name` (`center_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_department` (
          `department_name` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
          PRIMARY KEY (`department_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_position` (
          `position_name` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
          PRIMARY KEY (`position_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_employment_status` (
          `employment_status` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
          `is_current_employee_status` TINYINT NOT NULL,
          PRIMARY KEY (`employment_status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_education_level` (
          `education_level` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
          `sort_rank` INT NOT NULL,
          PRIMARY KEY (`education_level`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_performance_grade` (
          `performance_grade` VARCHAR(16) COLLATE utf8mb4_bin NOT NULL,
          `sort_rank` INT NOT NULL,
          PRIMARY KEY (`performance_grade`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dim_title_level` (
          `title_level` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
          `sort_rank` INT NOT NULL,
          PRIMARY KEY (`title_level`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_employee_org_path` (
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `org` VARCHAR(255) NULL,
          `org_path_id` CHAR(40) NOT NULL,
          `org_path` TEXT NOT NULL,
          `path_relation_type` VARCHAR(64) NOT NULL,
          `org_company_mismatch` TINYINT NOT NULL,
          PRIMARY KEY (`employee_id`, `org_path_id`),
          KEY `idx_fact_employee_org_path_type` (`path_relation_type`),
          KEY `idx_fact_employee_org_path_org_path_id` (`org_path_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_employee_contract` (
          `contract_no` VARCHAR(128) NOT NULL,
          `employee_id` VARCHAR(64) NULL,
          `contract_status` VARCHAR(64) NULL,
          `source_tables` VARCHAR(255) NOT NULL,
          `raw_payload` JSON NOT NULL,
          PRIMARY KEY (`contract_no`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_employee_change` (
          `change_id` CHAR(40) NOT NULL,
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `department` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `position` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `change_type` VARCHAR(128) NULL,
          `employment_status` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `start_date` DATE NULL,
          `end_date` DATE NULL,
          `is_current_interval` TINYINT NOT NULL,
          `is_current_employee_status` TINYINT NOT NULL,
          `raw_payload` JSON NOT NULL,
          PRIMARY KEY (`change_id`),
          KEY `idx_fact_employee_change_employee` (`employee_id`),
          KEY `idx_fact_employee_change_current` (`is_current_interval`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_education` (
          `education_id` CHAR(40) NOT NULL,
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `education_level` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `education_level_rank` INT NOT NULL,
          `major` VARCHAR(255) NULL,
          `school` VARCHAR(255) NULL,
          `school_type` VARCHAR(128) NULL,
          `is_highest_education` TINYINT NOT NULL,
          `enrollment_date` DATE NULL,
          `is_default_enrollment_date` TINYINT NOT NULL,
          `graduation_date` DATE NULL,
          `is_expected_graduation` TINYINT NOT NULL,
          `raw_payload` JSON NOT NULL,
          PRIMARY KEY (`education_id`),
          KEY `idx_fact_education_employee` (`employee_id`),
          KEY `idx_fact_education_highest` (`is_highest_education`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_performance` (
          `performance_id` CHAR(40) NOT NULL,
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `assessment_year` INT NULL,
          `performance_result` VARCHAR(128) NULL,
          `performance_grade` VARCHAR(16) COLLATE utf8mb4_bin NULL,
          `performance_grade_rank` INT NOT NULL,
          `manager_comment_present` TINYINT NOT NULL,
          `raw_payload` JSON NOT NULL,
          PRIMARY KEY (`performance_id`),
          KEY `idx_fact_performance_employee_year` (`employee_id`, `assessment_year`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_job_title` (
          `job_title_id` CHAR(40) NOT NULL,
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `title_name` VARCHAR(255) NULL,
          `title_level` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `title_level_rank` INT NOT NULL,
          `is_highest_title` TINYINT NOT NULL,
          `certificate_no` VARCHAR(255) NULL,
          `issuer` VARCHAR(255) NULL,
          `awarded_date` DATE NULL,
          `raw_payload` JSON NOT NULL,
          PRIMARY KEY (`job_title_id`),
          KEY `idx_fact_job_title_employee` (`employee_id`),
          KEY `idx_fact_job_title_highest` (`is_highest_title`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_professional_qualification` (
          `qualification_id` CHAR(40) NOT NULL,
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `qualification_name` VARCHAR(255) NULL,
          `qualification_level` VARCHAR(128) NULL,
          `issuer` VARCHAR(255) NULL,
          `acquired_date` DATE NULL,
          `raw_payload` JSON NOT NULL,
          PRIMARY KEY (`qualification_id`),
          KEY `idx_fact_professional_qualification_employee` (`employee_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `fact_project_experience` (
          `project_experience_id` CHAR(40) NOT NULL,
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `project_name` VARCHAR(255) NULL,
          `project_role` VARCHAR(128) NULL,
          `start_date` DATE NULL,
          `end_date` DATE NULL,
          `is_current_project` TINYINT NOT NULL,
          `responsibility_present` TINYINT NOT NULL,
          `raw_payload` JSON NOT NULL,
          PRIMARY KEY (`project_experience_id`),
          KEY `idx_fact_project_experience_employee` (`employee_id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dws_employee_profile` (
          `employee_id` VARCHAR(64) NOT NULL,
          `employee_name` VARCHAR(255) NULL,
          `source_org` VARCHAR(255) NULL,
          `join_date` DATE NULL,
          `confidential_flag` VARCHAR(16) COLLATE utf8mb4_bin NULL,
          `gender` VARCHAR(32) COLLATE utf8mb4_bin NULL,
          `age` INT NULL,
          `age_band` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `tenure_years` DOUBLE NULL,
          `current_department` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `current_position` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `employment_status` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `is_current_employee` TINYINT NOT NULL,
          `current_org_name` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `current_center_name` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `current_org_unit_name` VARCHAR(255) COLLATE utf8mb4_bin NULL,
          `current_org_full_path` TEXT NULL,
          `department_org_unit_mismatch` TINYINT NOT NULL,
          `primary_org_path` TEXT NULL,
          `org_path_count` INT NOT NULL,
          `has_org_path` TINYINT NOT NULL,
          `has_multi_org_path` TINYINT NOT NULL,
          `has_cross_org_review` TINYINT NOT NULL,
          `highest_education_level` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `highest_education_rank` INT NOT NULL,
          `highest_school` VARCHAR(255) NULL,
          `highest_major` VARCHAR(255) NULL,
          `latest_performance_year` INT NULL,
          `latest_performance_result` VARCHAR(128) NULL,
          `latest_performance_grade` VARCHAR(16) COLLATE utf8mb4_bin NULL,
          `latest_performance_grade_rank` INT NOT NULL,
          `highest_title_name` VARCHAR(255) NULL,
          `highest_title_level` VARCHAR(64) COLLATE utf8mb4_bin NULL,
          `highest_title_level_rank` INT NOT NULL,
          `qualification_count` INT NOT NULL,
          `project_count` INT NOT NULL,
          `has_cleaning_error` TINYINT NOT NULL,
          `data_quality_flags` JSON NOT NULL,
          PRIMARY KEY (`employee_id`),
          KEY `idx_dws_employee_profile_current` (`is_current_employee`),
          KEY `idx_dws_employee_profile_gender` (`gender`),
          KEY `idx_dws_employee_profile_age` (`age`),
          KEY `idx_dws_employee_profile_age_band` (`age_band`),
          KEY `idx_dws_employee_profile_department` (`current_department`),
          KEY `idx_dws_employee_profile_org_name` (`current_org_name`),
          KEY `idx_dws_employee_profile_center_name` (`current_center_name`),
          KEY `idx_dws_employee_profile_org_unit_name` (`current_org_unit_name`),
          KEY `idx_dws_employee_profile_dept_org_mismatch` (`department_org_unit_mismatch`),
          KEY `idx_dws_employee_profile_position` (`current_position`),
          KEY `idx_dws_employee_profile_education` (`highest_education_level`),
          KEY `idx_dws_employee_profile_performance` (`latest_performance_grade`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE `dq_hr_cleaning_errors` (
          `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          `source_table` VARCHAR(128) NOT NULL,
          `employee_id` VARCHAR(64) NULL,
          `error_type` VARCHAR(128) NOT NULL,
          `details` JSON NOT NULL,
          PRIMARY KEY (`id`),
          KEY `idx_dq_hr_cleaning_errors_type` (`error_type`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ]
    with connection.cursor() as cursor:
        for ddl in ddl_statements:
            cursor.execute(ddl)
    connection.commit()


def _insert_dict_rows(connection: Any, table_name: str, rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> int:
    if not rows:
        return 0
    quoted_columns = ", ".join(quote_identifier(column) for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})"
    values = []
    for row in rows:
        values.append(
            tuple(
                _json_dumps(row.get(column)) if column in {"details", "raw_payload", "data_quality_flags"} else row.get(column)
                for column in columns
            )
        )
    with connection.cursor() as cursor:
        cursor.executemany(sql, values)
    connection.commit()
    return len(rows)


def build_clean_outputs(raw_tables: dict[str, list[dict[str, Any]]], *, as_of_date: date | None = None) -> dict[str, list[dict[str, Any]]]:
    employees, employee_errors = build_employee_dimension(
        raw_tables.get("hr_baseinfo", []),
        raw_tables.get("hr_employeechangerecords", []),
        as_of_date=as_of_date,
    )
    employee_ids = {employee["employee_id"] for employee in employees}
    org_paths, org_facts, org_errors = build_org_path_outputs(
        raw_tables.get("hr_organizationalstructure", []),
        employee_ids=employee_ids,
    )
    org_units = build_org_unit_dimension(org_paths)
    contracts, contract_errors = merge_contract_rows(
        raw_tables.get("hr_employeecontract", []),
        raw_tables.get("hr_othercontracts", []),
    )
    employee_changes, change_dimensions, change_errors = build_employee_change_outputs(
        raw_tables.get("hr_employeechangerecords", []),
        employee_ids=employee_ids,
    )
    educations, education_dimensions, education_errors = build_education_outputs(
        raw_tables.get("hr_educationexperience", []),
        employee_ids=employee_ids,
    )
    performances, performance_dimensions, performance_errors = build_performance_outputs(
        raw_tables.get("hr_performancerecord", []),
        employee_ids=employee_ids,
    )
    job_titles, title_dimensions, title_errors = build_job_title_outputs(
        raw_tables.get("hr_jobtitleinfo", []),
        employee_ids=employee_ids,
    )
    qualifications, qualification_errors = build_professional_qualification_outputs(
        raw_tables.get("hr_professionalqualification", []),
        employee_ids=employee_ids,
    )
    projects, project_errors = build_project_experience_outputs(
        raw_tables.get("hr_projectexperience", []),
        employee_ids=employee_ids,
    )
    cleaning_errors = [
        *employee_errors,
        *org_errors,
        *contract_errors,
        *change_errors,
        *education_errors,
        *performance_errors,
        *title_errors,
        *qualification_errors,
        *project_errors,
    ]
    employee_profiles = build_employee_profile_outputs(
        employees=employees,
        org_facts=org_facts,
        educations=educations,
        performances=performances,
        job_titles=job_titles,
        qualifications=qualifications,
        projects=projects,
        errors=cleaning_errors,
    )
    return {
        "dim_employee": employees,
        "dim_org_path": org_paths,
        "dim_org_unit": org_units,
        "dim_department": change_dimensions["dim_department"],
        "dim_position": change_dimensions["dim_position"],
        "dim_employment_status": change_dimensions["dim_employment_status"],
        "dim_education_level": education_dimensions["dim_education_level"],
        "dim_performance_grade": performance_dimensions["dim_performance_grade"],
        "dim_title_level": title_dimensions["dim_title_level"],
        "fact_employee_change": employee_changes,
        "fact_employee_org_path": org_facts,
        "fact_employee_contract": contracts,
        "fact_education": educations,
        "fact_performance": performances,
        "fact_job_title": job_titles,
        "fact_professional_qualification": qualifications,
        "fact_project_experience": projects,
        "dws_employee_profile": employee_profiles,
        "dq_hr_cleaning_errors": cleaning_errors,
    }


def clean_database(connection: Any, *, raw_table_prefix: str = DEFAULT_RAW_TABLE_PREFIX, as_of_date: date | None = None) -> dict[str, int]:
    raw_table_names = [
        f"{raw_table_prefix}baseinfo",
        f"{raw_table_prefix}employeechangerecords",
        f"{raw_table_prefix}organizationalstructure",
        f"{raw_table_prefix}employeecontract",
        f"{raw_table_prefix}othercontracts",
        f"{raw_table_prefix}educationexperience",
        f"{raw_table_prefix}performancerecord",
        f"{raw_table_prefix}jobtitleinfo",
        f"{raw_table_prefix}professionalqualification",
        f"{raw_table_prefix}projectexperience",
    ]
    raw_tables = {table_name: read_raw_rows(connection, table_name) for table_name in raw_table_names}
    outputs = build_clean_outputs(raw_tables, as_of_date=as_of_date)
    _drop_clean_tables(connection)
    _create_clean_tables(connection)
    counts = {
        "dim_employee": _insert_dict_rows(
            connection,
            "dim_employee",
            outputs["dim_employee"],
            [
                "employee_id",
                "employee_name",
                "source_org",
                "confidential_flag",
                "gender",
                "age",
                "age_band",
                "tenure_years",
                "current_department",
                "current_position",
                "employment_status",
                "is_current_employee",
                "join_date",
                "is_default_join_date",
                "id_card_present",
                "mobile_valid",
                "email_present",
            ],
        ),
        "dim_org_path": _insert_dict_rows(
            connection,
            "dim_org_path",
            outputs["dim_org_path"],
            ["org_path_id", "org_path", "level_1", "level_2", "level_3", "level_4", "level_5", "level_6", "depth"],
        ),
        "dim_org_unit": _insert_dict_rows(
            connection,
            "dim_org_unit",
            outputs["dim_org_unit"],
            [
                "org_unit_id",
                "org_unit_name",
                "org_full_path",
                "parent_org_unit_id",
                "parent_org_full_path",
                "org_name",
                "center_name",
                "depth",
            ],
        ),
        "dim_department": _insert_dict_rows(
            connection,
            "dim_department",
            outputs["dim_department"],
            ["department_name"],
        ),
        "dim_position": _insert_dict_rows(
            connection,
            "dim_position",
            outputs["dim_position"],
            ["position_name"],
        ),
        "dim_employment_status": _insert_dict_rows(
            connection,
            "dim_employment_status",
            outputs["dim_employment_status"],
            ["employment_status", "is_current_employee_status"],
        ),
        "dim_education_level": _insert_dict_rows(
            connection,
            "dim_education_level",
            outputs["dim_education_level"],
            ["education_level", "sort_rank"],
        ),
        "dim_performance_grade": _insert_dict_rows(
            connection,
            "dim_performance_grade",
            outputs["dim_performance_grade"],
            ["performance_grade", "sort_rank"],
        ),
        "dim_title_level": _insert_dict_rows(
            connection,
            "dim_title_level",
            outputs["dim_title_level"],
            ["title_level", "sort_rank"],
        ),
        "fact_employee_change": _insert_dict_rows(
            connection,
            "fact_employee_change",
            outputs["fact_employee_change"],
            [
                "change_id",
                "employee_id",
                "employee_name",
                "department",
                "position",
                "change_type",
                "employment_status",
                "start_date",
                "end_date",
                "is_current_interval",
                "is_current_employee_status",
                "raw_payload",
            ],
        ),
        "fact_employee_org_path": _insert_dict_rows(
            connection,
            "fact_employee_org_path",
            outputs["fact_employee_org_path"],
            [
                "employee_id",
                "employee_name",
                "org",
                "org_path_id",
                "org_path",
                "path_relation_type",
                "org_company_mismatch",
            ],
        ),
        "fact_employee_contract": _insert_dict_rows(
            connection,
            "fact_employee_contract",
            outputs["fact_employee_contract"],
            ["contract_no", "employee_id", "contract_status", "source_tables", "raw_payload"],
        ),
        "fact_education": _insert_dict_rows(
            connection,
            "fact_education",
            outputs["fact_education"],
            [
                "education_id",
                "employee_id",
                "employee_name",
                "education_level",
                "education_level_rank",
                "major",
                "school",
                "school_type",
                "is_highest_education",
                "enrollment_date",
                "is_default_enrollment_date",
                "graduation_date",
                "is_expected_graduation",
                "raw_payload",
            ],
        ),
        "fact_performance": _insert_dict_rows(
            connection,
            "fact_performance",
            outputs["fact_performance"],
            [
                "performance_id",
                "employee_id",
                "employee_name",
                "assessment_year",
                "performance_result",
                "performance_grade",
                "performance_grade_rank",
                "manager_comment_present",
                "raw_payload",
            ],
        ),
        "fact_job_title": _insert_dict_rows(
            connection,
            "fact_job_title",
            outputs["fact_job_title"],
            [
                "job_title_id",
                "employee_id",
                "employee_name",
                "title_name",
                "title_level",
                "title_level_rank",
                "is_highest_title",
                "certificate_no",
                "issuer",
                "awarded_date",
                "raw_payload",
            ],
        ),
        "fact_professional_qualification": _insert_dict_rows(
            connection,
            "fact_professional_qualification",
            outputs["fact_professional_qualification"],
            [
                "qualification_id",
                "employee_id",
                "employee_name",
                "qualification_name",
                "qualification_level",
                "issuer",
                "acquired_date",
                "raw_payload",
            ],
        ),
        "fact_project_experience": _insert_dict_rows(
            connection,
            "fact_project_experience",
            outputs["fact_project_experience"],
            [
                "project_experience_id",
                "employee_id",
                "employee_name",
                "project_name",
                "project_role",
                "start_date",
                "end_date",
                "is_current_project",
                "responsibility_present",
                "raw_payload",
            ],
        ),
        "dws_employee_profile": _insert_dict_rows(
            connection,
            "dws_employee_profile",
            outputs["dws_employee_profile"],
            [
                "employee_id",
                "employee_name",
                "source_org",
                "join_date",
                "confidential_flag",
                "gender",
                "age",
                "age_band",
                "tenure_years",
                "current_department",
                "current_position",
                "employment_status",
                "is_current_employee",
                "current_org_name",
                "current_center_name",
                "current_org_unit_name",
                "current_org_full_path",
                "department_org_unit_mismatch",
                "primary_org_path",
                "org_path_count",
                "has_org_path",
                "has_multi_org_path",
                "has_cross_org_review",
                "highest_education_level",
                "highest_education_rank",
                "highest_school",
                "highest_major",
                "latest_performance_year",
                "latest_performance_result",
                "latest_performance_grade",
                "latest_performance_grade_rank",
                "highest_title_name",
                "highest_title_level",
                "highest_title_level_rank",
                "qualification_count",
                "project_count",
                "has_cleaning_error",
                "data_quality_flags",
            ],
        ),
        "dq_hr_cleaning_errors": _insert_dict_rows(
            connection,
            "dq_hr_cleaning_errors",
            outputs["dq_hr_cleaning_errors"],
            ["source_table", "employee_id", "error_type", "details"],
        ),
    }
    return counts


def _env_default(name: str, default: str) -> str:
    return os.environ.get(name, default)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean imported Huoju HR MySQL raw tables into analysis tables.")
    parser.add_argument("--mysql-host", default=_env_default("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(_env_default("MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=_env_default("MYSQL_USER", "root"))
    parser.add_argument("--mysql-password", default=os.environ.get("MYSQL_PASSWORD", "123456"))
    parser.add_argument("--database", default=_env_default("HUOJU_MYSQL_DATABASE", DEFAULT_DATABASE))
    parser.add_argument("--raw-table-prefix", default=DEFAULT_RAW_TABLE_PREFIX)
    parser.add_argument(
        "--as-of-date",
        default=os.environ.get("HUOJU_HR_CLEAN_AS_OF_DATE"),
        help="Date used to calculate tenure_years from join_date, for example 2026-07-02. Defaults to the run date.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    connection = connect_mysql(
        host=args.mysql_host,
        port=args.mysql_port,
        user=args.mysql_user,
        password=args.mysql_password,
        database=args.database,
    )
    try:
        counts = clean_database(
            connection,
            raw_table_prefix=args.raw_table_prefix,
            as_of_date=parse_as_of_date(args.as_of_date),
        )
    finally:
        connection.close()
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
