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
    assert "股份公司组织树筛选应兼容" in profile
