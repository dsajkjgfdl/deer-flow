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

    assert "一轮最多调用一个 Text2Cypher 工具" in skill
    assert "不得自行拆分问题并发查询" in skill
    assert "`assumptions`" in skill
    assert "`risk_level=high`" in skill
    assert "不得在同一轮再次调用 Text2Cypher" in skill
    assert "`failure_code`" in skill
    assert "`failure_detail`" in skill


def test_recommendation_questions_converge_after_text2cypher_or_graphrag_failure():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "推荐类和找人类任务的工具预算" in skill
    assert "Text2Cypher 返回 success 且 `should_retry=false` 后，必须直接基于该结果输出候选和限制" in skill
    assert "不得继续扩大搜索、改写关键词或再次调用任何工具" in skill
    assert "GraphRAG 返回错误、超时、证据不足或空结果时，本轮不得再调用其他 GraphRAG 工具" in skill
    assert "当 Text2Cypher 已返回至少一条候选、员工或项目记录时，即使候选较少，也要给出首推/备选和限制说明" in skill


def test_recommendation_questions_use_context_aware_llm_orchestration():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "## 人岗匹配与推荐" in skill
    assert "人岗匹配与推荐快路径" not in skill
    assert "必须结合完整对话" in skill
    assert "首次推荐、继续推荐、修改推荐条件，还是查询上一轮候选详情" in skill
    assert "只能来自当前线程中的真实用户消息、工具结果和最终回答" in skill
    assert "不得把 `<memory>` 中的跨线程摘要视为上一轮推荐" in skill
    assert "再推荐三个" in skill
    assert "换一批" in skill
    assert "还有其他人吗" in skill
    assert "沿用上一轮" in skill
    assert "避免重复上一轮已推荐人员" in skill
    assert "自洽的自然语言问题" in skill
    assert "严格按用户本轮要求的人数" in skill
    assert "将 `max_rows` 设为该人数" in skill
    assert "不新增结构化排除名单" in skill
    assert "没有可继承的推荐上下文" in skill
    assert "不得向用户展示“推荐查询结果类型不是 recommendation”" in skill
    assert "不得为了补全详情再次调用 Text2Cypher" in skill
    assert "研发经理" in skill
    assert "明确给出预设维度筛选条件时可使用 `text2cypher_query_employees`" in skill
    assert "自由文本匹配、综合评分或模糊适配判断时使用 `text2cypher_answer_question`" in skill
    assert "当前这一轮不要调用任何 GraphRAG" in skill
    assert "直接基于 Text2Cypher 返回的候选明细回答" in skill
    assert "最多前 3 位" in skill
    assert "max_rows=5" in skill
    assert "不要使用 Markdown 表格" in skill
    assert "不要在结尾主动追问" in skill
    assert "全集团" in skill


def test_expatriate_expert_questions_avoid_management_judgment_filters():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "`expatriate_expert`" in skill
    assert "优先把问题改写成候选检索问题" in skill
    assert "候选检索问题，不是完整管理建议作文" in skill
    assert "不得把“技术能力扎实、能独立面对客户、沟通能力强、稳定可靠" in skill
    assert "不能作为 Text2Cypher 的 WHERE 条件" in skill
    assert "坏例子" in skill
    assert "好例子" in skill
    assert "MLCC" in skill
    assert "其中“适合外派、能独立面对客户”等判断留给最终回答阶段" in skill


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


def test_hr_boss_defines_fast_text2cypher_tool_routing():
    config = (
        REPO_ROOT / ".deer-flow" / "agents" / "hr-boss-agent" / "config.yaml"
    ).read_text(encoding="utf-8")
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    profile = (
        REPO_ROOT
        / ".deer-flow"
        / "agents"
        / "hr-boss-agent"
        / "text2cypher-profile.md"
    ).read_text(encoding="utf-8")

    assert "- text2cypher_query_employees" in config
    assert "- text2cypher_get_employee_profile" in config
    assert "- read_file" in config
    assert "员工名单、员工筛选或明确候选集合" in skill
    assert "组织当前人数" in skill
    assert "`mode=count`" in skill
    assert "具体员工基础档案" in skill
    assert "`text2cypher_get_employee_profile`" in skill
    assert "提供员工原始标识" in skill
    assert "必须逐字保留用户原文或上一轮工具结果中的员工标识" in skill
    assert "不得自行推断、递增、换算或替换员工编号" in skill
    assert "姓名或称呼 + 数字后缀" in skill
    assert "平均值、占比、排名、分组或分布" in skill
    assert "一轮最多调用一个 Text2Cypher 工具" in skill
    assert "不得自动改用 `text2cypher_answer_question`" in skill
    assert "绩效只匹配最近一期" in profile
    assert "项目匹配全部项目经历" in profile
    assert "员工基础档案和结构化详情按用户原始人员标识查询" in profile
    assert "`Employee.employee_id` 与 `Employee.employee_name` 上做精确匹配" in profile
    assert "不得根据历史上下文、数字顺序或脱敏样例命名规律推断" in profile
    assert "员工基础档案允许查询历史员工" in profile
    assert "不得默认返回电话、社会关系等敏感字段" in profile


def test_hr_boss_routes_specific_employee_detail_fields_to_employee_profile_sections():
    skill = (REPO_ROOT.parent / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    profile = (
        REPO_ROOT
        / ".deer-flow"
        / "agents"
        / "hr-boss-agent"
        / "text2cypher-profile.md"
    ).read_text(encoding="utf-8")

    assert "教育背景、绩效记录、工作经历、项目经历、资格证书、职称信息、岗位变动记录、荣誉奖惩、全部信息" in skill
    assert "具体人员扩展字段必须调用 `text2cypher_get_employee_profile`" in skill
    assert "通过 `sections` 选择需要的详情" in skill
    assert "绩效记录传 `performance`" in skill
    assert "全部信息传 `all`" in skill
    assert "具体人员扩展字段必须调用 `text2cypher_answer_question`" not in skill
    assert "不得因为基础档案默认只返回固定字段就回答无法查询" in skill
    assert "不得建议联系人事档案部门或系统管理员" in skill
    assert "员工基础档案和结构化详情按用户原始人员标识查询" in profile
    assert "具体人员扩展查询" in profile
    assert "`Employee.employee_id` 和 `Employee.employee_name`" in profile
    assert "不得只把 `yuangong...` 或真实姓名当作 `Employee.employee_id`" in profile
    assert "荣誉奖惩" in profile
