from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_hr_boss_skill_bans_raw_graph_identifiers_in_leader_answers():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "不得在最终回答中原样输出" in skill
    assert "CURRENTLY_IN_DEPARTMENT" in skill
    assert "当前所属部门" in skill


def test_text2cypher_profile_uses_org_unit_hierarchy_for_department_scope():
    profile = (
        REPO_ROOT
        / ".deer-flow"
        / "agents"
        / "hr-boss-agent"
        / "text2cypher-profile.md"
    ).read_text(encoding="utf-8")

    assert "CURRENTLY_IN_DEPARTMENT" in profile
    assert "CURRENTLY_IN_POSITION" in profile
    assert "不要使用 OrgUnit 判断当前员工" in profile
    assert "CURRENTLY_ASSIGNED_TO_ORG_UNIT" in profile
    assert "CONTAINS_ORG_UNIT" in profile
    assert "向下包含所有子级组织单元" in profile
    assert "软件开发组" in profile
    assert "股份公司本部在数据库中的组织名" in profile
    assert "用户确认按部门口径" in profile
    assert "仍必须使用 `OrgUnit` 层级筛选" in profile
    assert "不得使用 `Department.department_name`" in profile
    assert "Department` 只可用于当前员工口径判断" in profile


def test_subsidiary_distribution_clarification_does_not_make_huoju_parent_scope():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")
    profile = (
        REPO_ROOT
        / ".deer-flow"
        / "agents"
        / "hr-boss-agent"
        / "text2cypher-profile.md"
    ).read_text(encoding="utf-8")
    assert "子公司分布" in skill
    assert "不等于用户已确认全集团范围" in skill
    assert "不得把“福建火炬电子科技股份有限公司（本部）”表述为可包含下属子公司的父级范围" in skill
    assert "不是集团母公司口径" in profile
    assert "不能替代最高优先级公司口径澄清规则" in profile


def test_department_distribution_groups_by_org_unit_center_name():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")
    profile = (
        REPO_ROOT
        / ".deer-flow"
        / "agents"
        / "hr-boss-agent"
        / "text2cypher-profile.md"
    ).read_text(encoding="utf-8")

    assert "部门分布" in profile
    assert "OrgUnit.center_name" in profile
    assert "不得按 `Employee.current_department_name` 聚合" in profile
    assert "中心层级口径" in profile
    assert "不要表述为“当前所属部门”" in profile
    assert "“部门分布”只是分组维度" in skill
    assert "“部门分布”只是分组维度" in profile
