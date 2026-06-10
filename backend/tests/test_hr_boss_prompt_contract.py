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


def test_hr_boss_defaults_missing_scope_to_group_and_only_clarifies_high_risk_conflicts():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")
    profile = (
        REPO_ROOT
        / ".deer-flow"
        / "agents"
        / "hr-boss-agent"
        / "text2cypher-profile.md"
    ).read_text(encoding="utf-8")
    assert "未指定公司、组织或部门时，默认按全集团当前员工统计" in skill
    assert "只有高风险冲突才允许追问" in skill
    assert "同一业务类别的多个相关部门或岗位候选应合并查询" in profile
    assert "不得仅因为存在多个相关候选而要求用户确认口径" in profile


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
    assert "部门分布默认按全集团当前员工范围" in skill
    assert "部门分布默认按全集团当前员工范围" in profile


def test_hr_boss_uses_single_pass_contract_without_agent_retries():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "一轮最多调用一次 `text2cypher_answer_question`" in skill
    assert "不得自行拆分问题并发查询" in skill
    assert "`assumptions`" in skill
    assert "`risk_level=high`" in skill


def test_recommendation_questions_use_text2cypher_fast_path_before_graphrag():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "人岗匹配与推荐快路径" in skill
    assert "研发经理" in skill
    assert "首轮必须先调用 `text2cypher_answer_question`" in skill
    assert "当前这一轮不要调用任何 GraphRAG" in skill
    assert "直接基于 Text2Cypher 返回的候选明细回答" in skill
    assert "最多前 3 位" in skill
    assert "max_rows=5" in skill
    assert "不要使用 Markdown 表格" in skill
    assert "不要在结尾主动追问" in skill
    assert "全集团" in skill


def test_text2cypher_profile_defines_ceramic_research_recommendation_scope():
    profile = (
        REPO_ROOT
        / ".deer-flow"
        / "agents"
        / "hr-boss-agent"
        / "text2cypher-profile.md"
    ).read_text(encoding="utf-8")

    assert "人岗推荐和瓷粉研发候选人口径" in profile
    assert "不要把“集团”“全集团”“从集团”解析为具体 `Organization` 实体" in profile
    assert "不要因为“研发经理”“瓷粉研发方向”没有匹配到单个岗位或职称字段值而中断查询" in profile
    assert "当前岗位、当前部门、教育经历专业、工作经历、项目经历、资格证书和职称" in profile


def test_hr_boss_recommendation_fast_path_prompt_loads_rules_without_read_file():
    from deerflow.agents.lead_agent.prompt import apply_prompt_template
    from deerflow.config.app_config import get_app_config

    prompt = apply_prompt_template(
        agent_name="hr-boss-agent",
        available_skills={"hr-boss"},
        app_config=get_app_config(),
        hr_boss_recommendation_fast_path=True,
    )

    assert "<hr_boss_recommendation_fast_path>" in prompt
    assert "人岗匹配与推荐快路径" in prompt
    assert "max_rows=5" in prompt
    assert "Do not call `read_file`" in prompt
    assert "immediately call `read_file` on the skill's main file" not in prompt
    assert "Skill First: Always load the relevant skill" not in prompt
