# HR Boss Text2Cypher Profile

## 适用范围

当前 Text2Cypher 服务用于 HR Boss Agent 的人力资源图谱问答。所有 Cypher 生成、校验、执行和修复都必须遵守本 profile 中的业务口径。

## 字段值纠错转换口径

Text2Cypher 在生成 Cypher 前会先执行字段值纠错转换，并把结果记录在 `term_resolution` 中。该阶段只负责把用户口语中的公司、部门、岗位、职称等业务词映射到图谱中真实存在的字段值，不能替代下面的组织、职称、当前员工等业务口径。

只有命中唯一高置信 canonical value 时才允许自动替换问题文本；如果多个候选接近，必须通过 `term_resolution.needs_clarification` 暴露歧义，由 HR Boss Agent 先追问确认。没有候选时应保留原词并记录未命中，不得编造字段值。

## 具体人员实体口径

当用户用“中文姓名/称呼 + 空格 + 数字”指代具体员工时，应同时保留人员姓名候选并做无空格规范化。例如“老王 166”应作为 `Employee.employee_name = "老王166"` 的候选查询，不应只按裸数字查询工号。

除非用户明确给出完整员工编号格式（如 `yuangong3219`），否则带有姓名或称呼上下文的数字后缀不得优先覆盖 `Employee.employee_name` 候选。若裸数字工号、补零工号或姓名含空格形式查询不到，应继续尝试无空格的姓名精确匹配。

用户询问“基本信息、岗位、绩效”等员工档案信息时，“岗位”是需要返回的字段，不是岗位筛选值；不得因为“岗位”未命中 `Position.position_name` 字段值而触发术语澄清或中断查询。

## 分组和排名口径

排名或分组统计默认只统计有效维度值。Top N 问题也按这个口径处理。

除非用户明确要求统计“未填写”“未知”或空白项，否则分组字段必须排除：

- null
- 空字符串
- 仅包含空格的字符串
- 未填写
- 未知
- 无
- N/A

学校、部门、岗位、职称、证书、专业等维度进入 COUNT、ORDER BY、LIMIT 前，应先过滤无效值。

如果执行结果中排名或分组维度列出现 null、空字符串、未填写、未知等无效维度值，必须视为结果质量问题。遇到质量问题时，不要直接返回结果，应修复 Cypher，重新校验并重新执行。

上述默认过滤规则不适用于用户明确要求统计无效值的场景。用户问“专业为空”“专业为无”“专业未填写”等问题时，应保留空值、空字符串和 `无` 条件，并按教育经历 `EducationExperience.major` 统计当前员工去重；不得使用不存在的 `Employee.major` 属性，也不要改写为员工主数据最高专业口径。

## 职称和岗位口径

“高级工程师”在当前 HR 图谱中属于 Title（职称）口径，不属于 Position（岗位）口径。

用户问“中高级职称”时，默认按“中级及以上职称”处理，即 Title.title_level 必须包含 `中级`、`副高级`、`正高级`。不要把“中高级职称”简化成仅统计 `副高级`、`正高级`，也不应因为“中高级职称”没有匹配到单个职称名称而触发澄清。

用户问以下问题时，应优先使用 Title 节点或职称字段查询，不应优先使用 Position：

- 高级工程师有多少人
- 高级工程师有哪些
- 高级工程师名单

如果按 Position 查询不到记录，应自动改用 Title 口径重新查询。

## 组织口径

当用户问“福建火炬电子科技股份有限公司”的员工统计时，应优先使用当前组织口径。

当用户在组织限定中说“股份”或“股份公司”时，“股份”“股份公司”指福建火炬电子科技股份有限公司，应作为该组织的明确别名处理，不应触发组织澄清。生成 Cypher 时应追加 `Employee.current_org_name = "福建火炬电子科技股份有限公司"` 或等价的 `Organization.org_name = "福建火炬电子科技股份有限公司"` 组织过滤。

用户问“子公司”“各子公司”“公司”“组织”“单位”等分组统计时，统一视为组织维度；图谱侧优先使用 `Employee.current_org_name` 作为当前组织/子公司字段。该类泛化维度词不是具体组织名称，不应因为 term_resolution 无法匹配到单个 `Organization.org_name` 字段值而触发澄清；只要 Cypher 已使用 `Employee.current_org_name`、`Organization.org_name` 或 `BELONGS_TO_ORGANIZATION` 表达组织维度，即可继续查询。

组织过滤只在用户明确指定公司、部门或组织时追加。用户只问“员工”“人员”“985员工”“高级工程师”等泛化员工统计时，不得默认限定到福建火炬电子科技股份有限公司，也不得把示例公司的组织过滤套用到未指定组织的问题上。

如果图谱中同时存在 Employee.current_org_name 和 BELONGS_TO_ORGANIZATION 关系，应优先选择更完整、更稳定的当前组织关系口径，并在结果明显异常时尝试另一种组织口径交叉检查。

## 当前员工口径

用户查询中的“员工”“人员”“公司人数”“部门人数”“平均年龄”“名单”等默认全部指当前员工。除非用户明确指定离职、辞职、历史、曾
任或变动记录，否则不得把没有当前部门且没有当前岗位关系的员工纳入统计。

当前员工的主口径为：员工存在当前部门或当前岗位关系。未明确指定公司、部门或组织时，不得默认限定到福建火炬电子科技股份有限公司。不要仅使用 `BELONGS_TO_ORGANIZATION` 或 `Employee.current_org_name` 判断当前员工，因为离职或辞职员工也可能保留组织归属信息。

除非用户明确询问“涉密”“保密”“非涉密”或指定要排除涉密员工，否则当前员工统计不得默认追加 `Employee.confidential_flag` 过滤条件。保密标识不是通用在职员工过滤条件。

标准 Cypher 口径（用户未指定公司、部门或组织时）：

```cypher
MATCH (e:Employee)
WHERE (
    (e)-[:CURRENTLY_IN_DEPARTMENT]->(:Department)
    OR (e)-[:CURRENTLY_IN_POSITION]->(:Position)
  )
RETURN count(DISTINCT e)
```

生成涉及员工明细、聚合、排名、分组或筛选的 Cypher 时，应先把上述当前员工过滤条件放在员工范围限定中；和其它 AND 筛选条件组合时，必须把当前员工 OR 条件整体放进括号，避免 `AND` 优先级高于 `OR` 导致后续筛选只作用在当前岗位分支。只有用户明确指定组织、部门或公司时，才追加对应组织关系或部门关系过滤。继续使用 `DISTINCT e` 避免当前部门和当前岗位关系造成重复计数。

查询平均年龄、平均司龄等员工级平均值时，应对当前员工范围内的唯一 `Employee` 节点计算平均值。若查询路径可能因为当前部门、当前岗位或其它明细关系重复同一员工，应先 `WITH DISTINCT e` 后再执行 `avg(e.age)`、`avg(e.tenure_years)` 等聚合，避免重复加权。

## 985/211 学校口径

“985员工”“985院校员工”“985毕业员工”默认按任一教育经历中的学校层次统计，以 `EducationExperience.school_type` 为准，不是组织、部门或学校名称口径，也不等同于最高学历院校。不得使用 `School.school_type` 统计 985/211 学校类型；学校节点上的同名属性属于冗余属性，不能作为员工教育经历的学校类型事实。除非用户明确询问“最高学历”“最高毕业院校”或类似口径，否则不得把该统计改写为最高学历口径。

用户询问“985”时，默认表示教育经历学校类型包含 985，既包括 `school_type = "985"`，也包括 `school_type = "985/211"` 等组合值。生成 Cypher 时应使用 `ed.school_type CONTAINS "985"`；不要使用学校节点 `s` 上的 `school_type` 属性，也不要只使用 `ed.school_type = "985"`。用户明确要求“仅985、不含211组合值”时，才允许使用精确匹配。

该口径是业务别名，不应触发 term_resolution.needs_clarification。即使 `term_resolution` 没有把“985”解析成组织、学校名或字段值，只要问题语义是学校层次或教育背景，就应继续按 `EducationExperience.school_type` 口径生成查询。

统计“985员工”的人数、名单、分组或占比时，仍必须先套用当前员工口径，并使用 `DISTINCT e` 避免同一员工多条教育经历造成重复计数。

## 离职员工口径
 如果要查“离职员工”，应该结合 EmploymentChange.employment_status 或 change_type：
```
  MATCH (e:Employee)-[:BELONGS_TO_ORGANIZATION]->(o:Organization)
  MATCH (e)-[:HAS_EMPLOYMENT_CHANGE]->(c:EmploymentChange)
  WHERE o.org_name = "福建火炬电子科技股份有限公司"
    AND c.end_date STARTS WITH "2199"
    AND c.employment_status IN ["离职", "辞职", "辞退", "退休", "实习终止", "返聘终止"]
  RETURN count(DISTINCT e) AS former_employee_count
```

## 变动原因因果口径

当用户问“因为绩效不达标被辞退”“因为工作表现不佳被降职”“由于某原因离职”等因果问题时，不能只把绩效记录和雇佣变动记录拼在一起推断因果。必须依赖 `EmploymentChange.change_reason`、`EmploymentChange.record_json` 中明确的变动原因证据，或其他明确原因字段。若只能查到绩效结果、辞退/离职/降职状态，但查不到明确原因，应返回 `status=no_reliable_evidence`、`answerable=false`、`should_retry=false`，并在 `limitation` 中说明无法可靠证明因果关系，不要编造名单。

## 结果质量规则

对于人数、平均值、名单、排名、占比、筛选等精确问题，结果必须来自结构化图数据库查询，不得凭材料印象估算。

如果生成、校验、执行或修复后仍无法得到可靠结果，应返回失败或限制说明，不要编造答案。
