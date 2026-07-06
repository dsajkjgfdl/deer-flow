from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "backend" / "scripts" / "clean_huoju_hr_mysql.py"

spec = importlib.util.spec_from_file_location("clean_huoju_hr_mysql", SCRIPT_PATH)
assert spec is not None
assert spec.loader is not None
clean_script = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = clean_script
spec.loader.exec_module(clean_script)


def test_is_current_employee_status_uses_confirmed_scope():
    assert clean_script.is_current_employee_status("正式员工") is True
    assert clean_script.is_current_employee_status("试用员工") is True
    assert clean_script.is_current_employee_status("实习") is True
    assert clean_script.is_current_employee_status("返聘") is True
    assert clean_script.is_current_employee_status("劳务派遣-正式") is True

    assert clean_script.is_current_employee_status("顾问") is False
    assert clean_script.is_current_employee_status("离职") is False
    assert clean_script.is_current_employee_status("辞职") is False
    assert clean_script.is_current_employee_status("实习终止") is False
    assert clean_script.is_current_employee_status("返聘终止") is False
    assert clean_script.is_current_employee_status("劳务派遣") is False
    assert clean_script.is_current_employee_status("临时工") is False
    assert clean_script.is_current_employee_status("劳务工") is False
    assert clean_script.is_current_employee_status("待分配") is False


def test_parse_business_date_marks_default_and_current_sentinels():
    default_date = clean_script.parse_business_date("1900-01-01 00:00:00")
    assert default_date.date_value is None
    assert default_date.is_default_date is True
    assert default_date.is_current_sentinel is False

    current_end = clean_script.parse_business_date("2199-12-31 00:00:00")
    assert current_end.date_value is None
    assert current_end.is_default_date is False
    assert current_end.is_current_sentinel is True

    normal_date = clean_script.parse_business_date("2024-05-06 12:30:00")
    assert str(normal_date.date_value) == "2024-05-06"
    assert normal_date.is_default_date is False
    assert normal_date.is_current_sentinel is False


def test_parse_as_of_date_accepts_cli_date():
    assert clean_script.parse_as_of_date("2026-07-02") == clean_script.date(2026, 7, 2)
    assert clean_script.parse_as_of_date(None) is None


def test_parse_args_accepts_as_of_date():
    args = clean_script.parse_args(["--as-of-date", "2026-07-02"])

    assert args.as_of_date == "2026-07-02"


def test_build_employee_dimension_prefers_latest_change_for_current_fields():
    base_rows = [
        {
            "员工编号": " E001 ",
            "员工姓名": " 张三 ",
            "组织": "福建火炬电子科技股份有限公司",
            "是否涉密": "是",
            "入司日期": "1900-01-01 00:00:00",
            "身份证信息": "350000199001011234",
            "手机号码": "13800138000",
            "电子邮箱": "zhangsan@example.com",
        }
    ]
    change_rows = [
        {
            "员工编号": "E001",
            "部门": "旧部门",
            "职位": "工程师",
            "用工关系状态": "正式员工",
            "开始日期": "2020-01-01 00:00:00",
            "结束日期": "2021-01-01 00:00:00",
        },
        {
            "员工编号": "E001",
            "部门": "新部门",
            "职位": "高级工程师",
            "用工关系状态": "返聘",
            "开始日期": "2024-01-01 00:00:00",
            "结束日期": "2199-12-31 00:00:00",
        },
    ]

    employees, errors = clean_script.build_employee_dimension(base_rows, change_rows)

    assert errors == []
    assert employees == [
        {
            "employee_id": "E001",
            "employee_name": "张三",
            "source_org": "福建火炬电子科技股份有限公司",
            "confidential_flag": "是",
            "gender": None,
            "age": None,
            "age_band": None,
            "tenure_years": None,
            "current_department": "新部门",
            "current_position": "高级工程师",
            "employment_status": "返聘",
            "is_current_employee": 1,
            "join_date": None,
            "is_default_join_date": 1,
            "id_card_present": 1,
            "mobile_valid": 1,
            "email_present": 1,
        }
    ]


def test_build_employee_dimension_calculates_tenure_from_join_date():
    base_rows = [
        {
            "员工编号": "HJ1001",
            "员工姓名": "柯亚武",
            "入司日期": "2021-09-13 00:00:00",
            "司龄(年)": "0.4700",
        }
    ]
    change_rows = [
        {
            "员工编号": "HJ1001",
            "用工关系状态": "正式员工",
            "开始日期": "2021-09-13 00:00:00",
            "结束日期": "2199-12-31 00:00:00",
        }
    ]

    employees, errors = clean_script.build_employee_dimension(
        base_rows,
        change_rows,
        as_of_date=clean_script.date(2026, 7, 2),
    )

    assert errors == []
    assert employees[0]["join_date"] == clean_script.date(2021, 9, 13)
    assert employees[0]["tenure_years"] == 4.8


def test_build_org_path_outputs_dimension_fact_and_path_types():
    rows = [
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "组织": "福建火炬电子科技股份有限公司",
            "组织架构": "火炬电子_福建火炬电子科技股份有限公司_质量中心",
        },
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "组织": "福建火炬电子科技股份有限公司",
            "组织架构": "火炬电子_福建火炬电子科技股份有限公司_质量中心_质量管理部",
        },
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "组织": "福建火炬电子科技股份有限公司",
            "组织架构": "火炬电子_福建火炬电子科技股份有限公司_市场中心_应用工程部",
        },
        {
            "员工编号": "E002",
            "员工姓名": "李四",
            "组织": "福建毫米电子有限公司",
            "组织架构": "火炬电子_福建火炬电子科技股份有限公司_质量中心",
        },
        {
            "员工编号": "E003",
            "员工姓名": "王五",
            "组织": "福建毫米电子有限公司",
            "组织架构": "",
        },
    ]

    org_paths, facts, errors = clean_script.build_org_path_outputs(rows, employee_ids={"E001", "E002", "E003"})

    assert {path["org_path"] for path in org_paths} == {
        "火炬电子_福建火炬电子科技股份有限公司_质量中心",
        "火炬电子_福建火炬电子科技股份有限公司_质量中心_质量管理部",
        "火炬电子_福建火炬电子科技股份有限公司_市场中心_应用工程部",
    }
    by_path = {fact["org_path"]: fact for fact in facts if fact["employee_id"] == "E001"}
    assert by_path["火炬电子_福建火炬电子科技股份有限公司_质量中心"]["path_relation_type"] == "hierarchy_duplicate"
    assert by_path["火炬电子_福建火炬电子科技股份有限公司_质量中心_质量管理部"]["path_relation_type"] == "hierarchy_duplicate"
    assert by_path["火炬电子_福建火炬电子科技股份有限公司_市场中心_应用工程部"]["path_relation_type"] == "matrix_or_parttime"
    assert [fact for fact in facts if fact["employee_id"] == "E002"][0]["path_relation_type"] == "cross_org_review"
    assert errors == [
        {
            "source_table": "hr_organizationalstructure",
            "employee_id": "E003",
            "error_type": "missing_org_path",
            "details": {"组织": "福建毫米电子有限公司"},
        }
    ]


def test_build_org_unit_dimension_builds_tree_from_org_paths():
    org_paths = [
        {
            "org_path_id": clean_script.org_path_id("火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组"),
            "org_path": "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组",
        }
    ]

    org_units = clean_script.build_org_unit_dimension(org_paths)

    by_path = {unit["org_full_path"]: unit for unit in org_units}
    assert set(by_path) == {
        "火炬电子",
        "火炬电子_福建火炬电子科技股份有限公司",
        "火炬电子_福建火炬电子科技股份有限公司_信息管理中心",
        "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部",
        "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组",
    }
    leaf = by_path["火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组"]
    assert leaf == {
        "org_unit_id": clean_script.org_path_id(
            "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组"
        ),
        "org_unit_name": "软件开发组",
        "org_full_path": "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组",
        "parent_org_unit_id": clean_script.org_path_id("火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部"),
        "parent_org_full_path": "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部",
        "org_name": "福建火炬电子科技股份有限公司",
        "center_name": "信息管理中心",
        "depth": 5,
    }


def test_merge_contract_rows_deduplicates_and_keeps_source_tables():
    employee_contract = [{"合同编号": "C001", "员工编号": "E001", "合同状态": "生效"}]
    other_contracts = [{"合同编号": "C001", "员工编号": "E001", "合同状态": "生效"}]

    facts, errors = clean_script.merge_contract_rows(employee_contract, other_contracts)

    assert errors == []
    assert facts == [
        {
            "contract_no": "C001",
            "employee_id": "E001",
            "contract_status": "生效",
            "source_tables": "hr_employeecontract,hr_othercontracts",
            "raw_payload": {"合同编号": "C001", "员工编号": "E001", "合同状态": "生效"},
        }
    ]


def test_build_employee_change_facts_normalizes_dates_and_current_interval():
    rows = [
        {
            "员工编号": " E001 ",
            "员工姓名": "张三",
            "部门": " 质量部 ",
            "职位": "工程师",
            "变动类型": "组织调整",
            "用工关系状态": "正式员工",
            "开始日期": "2024-01-01 00:00:00",
            "结束日期": "2199-12-31 00:00:00",
        },
        {
            "员工姓名": "无编号",
            "部门": "质量部",
            "开始日期": "2024-01-01 00:00:00",
            "结束日期": "2024-12-31 00:00:00",
        },
    ]

    facts, dimensions, errors = clean_script.build_employee_change_outputs(rows, employee_ids={"E001"})

    assert facts == [
        {
            "change_id": facts[0]["change_id"],
            "employee_id": "E001",
            "employee_name": "张三",
            "department": "质量部",
            "position": "工程师",
            "change_type": "组织调整",
            "employment_status": "正式员工",
            "start_date": clean_script.date(2024, 1, 1),
            "end_date": None,
            "is_current_interval": 1,
            "is_current_employee_status": 1,
            "raw_payload": rows[0],
        }
    ]
    assert dimensions["dim_department"] == [{"department_name": "质量部"}]
    assert dimensions["dim_position"] == [{"position_name": "工程师"}]
    assert dimensions["dim_employment_status"] == [
        {"employment_status": "正式员工", "is_current_employee_status": 1}
    ]
    assert errors == [
        {
            "source_table": "hr_employeechangerecords",
            "employee_id": None,
            "error_type": "missing_employee_id",
            "details": {"员工姓名": "无编号"},
        }
    ]


def test_build_education_outputs_marks_highest_and_level_rank():
    rows = [
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "学历": "本科",
            "专业": "英语",
            "毕业学校": "泉州师范学院",
            "学校类型": "",
            "最高学历": 1,
            "入学时间": "1899-12-31 00:00:00",
            "毕业时间": "2027-07-01 00:00:00",
        }
    ]

    facts, dimensions, errors = clean_script.build_education_outputs(
        rows,
        employee_ids={"E001"},
        today=clean_script.date(2026, 6, 30),
    )

    assert errors == []
    assert facts == [
        {
            "education_id": facts[0]["education_id"],
            "employee_id": "E001",
            "employee_name": "张三",
            "education_level": "本科",
            "education_level_rank": 40,
            "major": "英语",
            "school": "泉州师范学院",
            "school_type": None,
            "is_highest_education": 1,
            "enrollment_date": None,
            "is_default_enrollment_date": 1,
            "graduation_date": clean_script.date(2027, 7, 1),
            "is_expected_graduation": 1,
            "raw_payload": rows[0],
        }
    ]
    assert dimensions["dim_education_level"] == [{"education_level": "本科", "sort_rank": 40}]


def test_build_education_outputs_ranks_below_junior_college_lower_than_junior_college():
    rows = [
        {"员工编号": "E001", "学历": "大专"},
        {"员工编号": "E002", "学历": "大专以下"},
    ]

    facts, dimensions, errors = clean_script.build_education_outputs(
        rows,
        employee_ids={"E001", "E002"},
    )

    assert errors == []
    assert {fact["education_level"]: fact["education_level_rank"] for fact in facts} == {
        "大专": 30,
        "大专以下": 20,
    }
    assert dimensions["dim_education_level"] == [
        {"education_level": "大专", "sort_rank": 30},
        {"education_level": "大专以下", "sort_rank": 20},
    ]


def test_build_performance_outputs_extracts_year_and_grade_rank():
    rows = [
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "考核年份": "2023年",
            "考核结果": "A优秀",
            "主管评价": "表现好",
        }
    ]

    facts, dimensions, errors = clean_script.build_performance_outputs(rows, employee_ids={"E001"})

    assert errors == []
    assert facts == [
        {
            "performance_id": facts[0]["performance_id"],
            "employee_id": "E001",
            "employee_name": "张三",
            "assessment_year": 2023,
            "performance_result": "A优秀",
            "performance_grade": "A",
            "performance_grade_rank": 4,
            "manager_comment_present": 1,
            "raw_payload": rows[0],
        }
    ]
    assert dimensions["dim_performance_grade"] == [{"performance_grade": "A", "sort_rank": 4}]


def test_build_talent_fact_outputs_for_title_qualification_and_project():
    title_rows = [
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "最高职称": 1,
            "职称内容": "工程师",
            "职称级别": "中级",
            "证书编号": "T001",
            "评定单位": "评委会",
            "职称授予时间": "2024-05-01 00:00:00",
        }
    ]
    qualification_rows = [
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "职业资格": "VISUAL BASIC",
            "职业资格级别": "二级",
            "授予单位": "福建省教育厅",
            "获取时间": "2022-03-07 00:00:00",
        }
    ]
    project_rows = [
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "项目名称": "多芯组项目",
            "担任角色": "主持",
            "主要职责": "负责项目管理",
            "开始时间": "2021-01-01 00:00:00",
            "结束时间": "9999-12-31 00:00:00",
        }
    ]

    title_facts, title_dims, title_errors = clean_script.build_job_title_outputs(title_rows, employee_ids={"E001"})
    qualification_facts, qualification_errors = clean_script.build_professional_qualification_outputs(
        qualification_rows,
        employee_ids={"E001"},
    )
    project_facts, project_errors = clean_script.build_project_experience_outputs(project_rows, employee_ids={"E001"})

    assert title_errors == []
    assert title_facts[0] == {
        "job_title_id": title_facts[0]["job_title_id"],
        "employee_id": "E001",
        "employee_name": "张三",
        "title_name": "工程师",
        "title_level": "中级",
        "title_level_rank": 30,
        "is_highest_title": 1,
        "certificate_no": "T001",
        "issuer": "评委会",
        "awarded_date": clean_script.date(2024, 5, 1),
        "raw_payload": title_rows[0],
    }
    assert title_dims["dim_title_level"] == [{"title_level": "中级", "sort_rank": 30}]
    assert qualification_errors == []
    assert qualification_facts[0]["qualification_name"] == "VISUAL BASIC"
    assert qualification_facts[0]["qualification_level"] == "二级"
    assert qualification_facts[0]["acquired_date"] == clean_script.date(2022, 3, 7)
    assert project_errors == []
    assert project_facts[0]["project_name"] == "多芯组项目"
    assert project_facts[0]["end_date"] is None
    assert project_facts[0]["is_current_project"] == 1
    assert project_facts[0]["responsibility_present"] == 1


def test_build_clean_outputs_includes_second_layer_tables():
    raw_tables = {
        "hr_baseinfo": [{"员工编号": "E001", "员工姓名": "张三"}],
        "hr_employeechangerecords": [
            {
                "员工编号": "E001",
                "员工姓名": "张三",
                "部门": "质量部",
                "职位": "工程师",
                "用工关系状态": "正式员工",
                "开始日期": "2024-01-01 00:00:00",
                "结束日期": "2199-12-31 00:00:00",
            }
        ],
        "hr_organizationalstructure": [],
        "hr_employeecontract": [],
        "hr_othercontracts": [],
        "hr_educationexperience": [{"员工编号": "E001", "学历": "本科", "最高学历": 1}],
        "hr_performancerecord": [{"员工编号": "E001", "考核年份": "2023年", "考核结果": "B良好"}],
        "hr_jobtitleinfo": [{"员工编号": "E001", "职称内容": "工程师", "职称级别": "中级", "最高职称": 1}],
        "hr_professionalqualification": [{"员工编号": "E001", "职业资格": "VISUAL BASIC"}],
        "hr_projectexperience": [{"员工编号": "E001", "项目名称": "多芯组项目"}],
    }

    outputs = clean_script.build_clean_outputs(raw_tables)

    assert outputs["fact_employee_change"]
    assert outputs["fact_education"]
    assert outputs["fact_performance"]
    assert outputs["fact_job_title"]
    assert outputs["fact_professional_qualification"]
    assert outputs["fact_project_experience"]
    assert outputs["dim_department"] == [{"department_name": "质量部"}]
    assert outputs["dim_position"] == [{"position_name": "工程师"}]
    assert outputs["dim_education_level"] == [{"education_level": "本科", "sort_rank": 40}]
    assert outputs["dim_performance_grade"] == [{"performance_grade": "B", "sort_rank": 3}]
    assert outputs["dim_title_level"] == [{"title_level": "中级", "sort_rank": 30}]


def test_build_employee_profile_outputs_summarizes_employee_facts():
    employees = [
        {
            "employee_id": "E001",
            "employee_name": "张三",
            "source_org": "火炬电子",
            "current_department": "信息管理中心",
            "current_position": "工程师",
            "employment_status": "正式员工",
            "is_current_employee": 1,
            "confidential_flag": "否",
            "join_date": clean_script.date(2019, 5, 20),
            "gender": "男",
            "age": 35,
            "age_band": "30-39",
            "tenure_years": 5.5,
        },
        {
            "employee_id": "E002",
            "employee_name": "李四",
            "source_org": "火炬电子",
            "current_department": None,
            "current_position": None,
            "employment_status": "离职",
            "is_current_employee": 0,
            "join_date": None,
            "gender": None,
            "age": None,
            "age_band": None,
            "tenure_years": None,
        },
    ]
    org_facts = [
        {
            "employee_id": "E001",
            "org_path": "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组",
            "path_relation_type": "current_path",
        },
        {
            "employee_id": "E001",
            "org_path": "火炬电子_福建火炬电子科技股份有限公司_研发中心",
            "path_relation_type": "cross_org_review",
        },
    ]
    educations = [
        {
            "employee_id": "E001",
            "education_level": "本科",
            "education_level_rank": 40,
            "school": "泉州师范学院",
            "major": "英语",
            "is_highest_education": 1,
            "graduation_date": clean_script.date(2022, 1, 5),
        },
        {
            "employee_id": "E001",
            "education_level": "大专",
            "education_level_rank": 30,
            "school": "福州大学",
            "major": "会计",
            "is_highest_education": 0,
            "graduation_date": clean_script.date(2010, 12, 30),
        },
    ]
    performances = [
        {
            "employee_id": "E001",
            "assessment_year": 2023,
            "performance_result": "B良好",
            "performance_grade": "B",
            "performance_grade_rank": 3,
        },
        {
            "employee_id": "E001",
            "assessment_year": 2024,
            "performance_result": "A优秀",
            "performance_grade": "A",
            "performance_grade_rank": 4,
        },
    ]
    job_titles = [
        {
            "employee_id": "E001",
            "title_name": "工程师",
            "title_level": "中级",
            "title_level_rank": 30,
            "is_highest_title": 1,
        }
    ]
    qualifications = [
        {"employee_id": "E001", "qualification_name": "VISUAL BASIC"},
        {"employee_id": "E001", "qualification_name": "数据库工程师"},
    ]
    projects = [{"employee_id": "E001", "project_name": "多芯组项目"}]
    errors = [{"employee_id": "E001", "error_type": "cross_org_review"}]

    profiles = clean_script.build_employee_profile_outputs(
        employees=employees,
        org_facts=org_facts,
        educations=educations,
        performances=performances,
        job_titles=job_titles,
        qualifications=qualifications,
        projects=projects,
        errors=errors,
    )

    assert profiles[0] == {
        "employee_id": "E001",
            "employee_name": "张三",
            "source_org": "火炬电子",
            "join_date": clean_script.date(2019, 5, 20),
            "confidential_flag": "否",
            "gender": "男",
            "age": 35,
        "age_band": "30-39",
        "tenure_years": 5.5,
        "current_department": "信息管理中心",
        "current_position": "工程师",
        "employment_status": "正式员工",
        "is_current_employee": 1,
        "current_org_name": "福建火炬电子科技股份有限公司",
        "current_center_name": "信息管理中心",
        "current_org_unit_name": "软件开发组",
        "current_org_full_path": "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组",
        "department_org_unit_mismatch": 1,
        "primary_org_path": "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组",
        "org_path_count": 2,
        "has_org_path": 1,
        "has_multi_org_path": 1,
        "has_cross_org_review": 1,
        "highest_education_level": "本科",
        "highest_education_rank": 40,
        "highest_school": "泉州师范学院",
        "highest_major": "英语",
        "latest_performance_year": 2024,
        "latest_performance_result": "A优秀",
        "latest_performance_grade": "A",
        "latest_performance_grade_rank": 4,
        "highest_title_name": "工程师",
        "highest_title_level": "中级",
        "highest_title_level_rank": 30,
        "qualification_count": 2,
        "project_count": 1,
        "has_cleaning_error": 1,
        "data_quality_flags": ["multi_org_path", "cross_org_review", "has_cleaning_error"],
    }
    assert profiles[1]["employee_id"] == "E002"
    assert profiles[1]["has_org_path"] == 0
    assert profiles[1]["current_org_unit_name"] is None
    assert profiles[1]["department_org_unit_mismatch"] == 0
    assert profiles[1]["data_quality_flags"] == ["no_org_path"]


def test_build_clean_outputs_includes_employee_profile_table():
    raw_tables = {
        "hr_baseinfo": [
            {
                "员工编号": "E001",
                "员工姓名": "张三",
                "入司日期": "2019-05-20 00:00:00",
                "是否涉密": "否",
                "性别": "男",
                "年龄": "35",
                "年龄分段": "30-39",
                "司龄(年)": "0.4700",
            }
        ],
        "hr_employeechangerecords": [
            {
                "员工编号": "E001",
                "员工姓名": "张三",
                "部门": "信息管理中心",
                "职位": "工程师",
                "用工关系状态": "正式员工",
                "开始日期": "2024-01-01 00:00:00",
                "结束日期": "2199-12-31 00:00:00",
            }
        ],
        "hr_organizationalstructure": [
            {
                "员工编号": "E001",
                "员工姓名": "张三",
                "组织": "火炬电子",
                "组织架构": "火炬电子_福建火炬电子科技股份有限公司_信息管理中心_IT部_软件开发组",
            }
        ],
        "hr_employeecontract": [],
        "hr_othercontracts": [],
        "hr_educationexperience": [{"员工编号": "E001", "学历": "本科", "最高学历": 1}],
        "hr_performancerecord": [{"员工编号": "E001", "考核年份": "2024年", "考核结果": "A优秀"}],
        "hr_jobtitleinfo": [{"员工编号": "E001", "职称内容": "工程师", "职称级别": "中级", "最高职称": 1}],
        "hr_professionalqualification": [{"员工编号": "E001", "职业资格": "VISUAL BASIC"}],
        "hr_projectexperience": [{"员工编号": "E001", "项目名称": "多芯组项目"}],
    }

    outputs = clean_script.build_clean_outputs(raw_tables, as_of_date=clean_script.date(2026, 7, 2))

    assert outputs["dim_employee"][0]["confidential_flag"] == "否"
    assert outputs["dws_employee_profile"][0]["employee_id"] == "E001"
    assert outputs["dws_employee_profile"][0]["confidential_flag"] == "否"
    assert outputs["dws_employee_profile"][0]["join_date"] == clean_script.date(2019, 5, 20)
    assert outputs["dws_employee_profile"][0]["gender"] == "男"
    assert outputs["dws_employee_profile"][0]["age"] == 35
    assert outputs["dws_employee_profile"][0]["age_band"] == "30-39"
    assert outputs["dws_employee_profile"][0]["tenure_years"] == 7.12
    assert outputs["dws_employee_profile"][0]["highest_education_level"] == "本科"
    assert outputs["dws_employee_profile"][0]["latest_performance_grade"] == "A"
    assert outputs["dws_employee_profile"][0]["qualification_count"] == 1
    assert outputs["dws_employee_profile"][0]["project_count"] == 1
    assert outputs["dws_employee_profile"][0]["current_org_name"] == "福建火炬电子科技股份有限公司"
    assert outputs["dws_employee_profile"][0]["current_center_name"] == "信息管理中心"
    assert outputs["dws_employee_profile"][0]["current_org_unit_name"] == "软件开发组"
    assert outputs["dws_employee_profile"][0]["department_org_unit_mismatch"] == 1
    assert outputs["dim_org_unit"]


def test_dictionary_natural_keys_use_binary_collation():
    class RecordingCursor:
        def __init__(self, statements):
            self.statements = statements

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, sql):
            self.statements.append(sql)

    class RecordingConnection:
        def __init__(self):
            self.statements = []

        def cursor(self):
            return RecordingCursor(self.statements)

        def commit(self):
            pass

    connection = RecordingConnection()

    clean_script._create_clean_tables(connection)

    ddl = "\n".join(connection.statements)
    assert "`org_unit_name` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL" in ddl
    assert "`org_name` VARCHAR(255) COLLATE utf8mb4_bin NULL" in ddl
    assert "`center_name` VARCHAR(255) COLLATE utf8mb4_bin NULL" in ddl
    assert "`department_name` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL" in ddl
    assert "`position_name` VARCHAR(255) COLLATE utf8mb4_bin NOT NULL" in ddl
    assert "`employment_status` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL" in ddl
    assert "`education_level` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL" in ddl
    assert "`performance_grade` VARCHAR(16) COLLATE utf8mb4_bin NOT NULL" in ddl
    assert "`title_level` VARCHAR(64) COLLATE utf8mb4_bin NOT NULL" in ddl
    assert "`confidential_flag` VARCHAR(16) COLLATE utf8mb4_bin NULL" in ddl
    assert "`gender` VARCHAR(32) COLLATE utf8mb4_bin NULL" in ddl
    assert "`age` INT NULL" in ddl
    assert "`age_band` VARCHAR(64) COLLATE utf8mb4_bin NULL" in ddl
    assert "`tenure_years` DOUBLE NULL" in ddl
