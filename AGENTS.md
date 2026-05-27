# HR Boss Agent Architecture

本仓库中的 `hr-boss-agent` 是面向领导演示的 HR 智能问答代理。它不是新的 DeerFlow 核心运行时组件，而是在自定义 agent 层通过一个编排 skill 和两个专业 MCP 完成路由、查询和结论转写。

## Source Files

- Agent 配置：`backend/.deer-flow/agents/hr-boss-agent/config.yaml`
- Agent 行为提示：`backend/.deer-flow/agents/hr-boss-agent/SOUL.md`
- Text2Cypher 业务口径：`backend/.deer-flow/agents/hr-boss-agent/text2cypher-profile.md`
- 编排 skill：`skills/custom/hr-boss/SKILL.md`

## Prompt Layering Restrictions

为避免提示上下文互相竞争和业务口径漂移，`hr-boss-agent` 的文档必须按职责分层维护：

- `SOUL.md` 只保留 agent 身份、运行边界、权威性原则和面向领导的回答风格。
- `skills/custom/hr-boss/SKILL.md` 是路由、工具调用顺序、异常处理和结果改写规则的唯一维护位置。
- `text2cypher-profile.md` 是 Text2Cypher 细粒度业务口径的唯一维护位置。
- 不要把 `hr-boss` skill 的详细路由规则复制到 `SOUL.md`，也不要把 profile 中的人数、名单、排名、当前员工、职称、组织归属等细粒度口径复制到 `SOUL.md` 或 `SKILL.md`。
- 修改路由和工具编排时，优先修改 `SKILL.md`；修改业务口径时，优先修改 `text2cypher-profile.md`；其他文档只保留引用和高层说明。

## Runtime Shape

`hr-boss-agent` 当前配置：

- `name`: `hr-boss-agent`
- `model`: `qwen3.5-plus`
- `skills`: 只挂载 `hr-boss`
- `mcp_servers`: `hr-graphrag-qa` 和 `text2cypher`

架构上可以理解为：

```text
leader HR question
        |
        v
hr-boss-agent
        |
        v
hr-boss orchestration skill
        |
        +--> text2cypher MCP       精确人数、平均值、名单、排名、占比、筛选
        |
        +--> hr-graphrag-qa MCP    证据检索、语义解释、组织画像、趋势和探索分析
```

## Skill Contract

`hr-boss` 是该 agent 唯一挂载的业务编排 skill。它负责先判断领导问题属于精确查询还是材料解读，再选择对应 MCP，并把工具结果改写成领导可直接理解的结论。

不要把 `text2cypher`、`graphrag` 等多个低层 skill 直接挂到 `hr-boss-agent` 上。该 agent 的提示上下文应保持为一个清晰的编排合同，避免多个工具手册相互竞争。

## MCP Responsibilities

`text2cypher` MCP 负责结构化 HR 图谱的精确查询。遇到平均、人数、名单、排名、占比、筛选、年龄、工龄、职称清单、证书清单、人员清单、部门人数、公司人数等问题时，优先走 Text2Cypher。

常规领导问答优先调用：

- `text2cypher_answer_question`

需要查看、验证、修复或解释查询口径时，使用低层工具链：

- `text2cypher_prepare_schema`
- `text2cypher_get_schema`
- `text2cypher_generate_cypher`
- `text2cypher_validate_cypher`
- `text2cypher_execute_cypher`

低层工具链必须遵守 `generate -> validate -> execute`。每一条新 Cypher，包括补充明细查询和修复后的查询，都必须先校验，通过后才能执行。

`hr-graphrag-qa` MCP 负责材料证据和语义解释：

- `hr-graphrag-qa_query_basic`: 简单证据片段查找。
- `hr-graphrag-qa_query_local`: 具体人、岗位、部门、证书、项目、公司实体等局部事实。
- `hr-graphrag-qa_query_global`: 组织画像、人才结构、群体趋势、整体风险、跨部门分布。
- `hr-graphrag-qa_query_drift`: 探索式分析、跨群体线索、从整体到局部的风险发现。

## Business Semantics Source Of Truth

为了保持业务口径一致，Text2Cypher 的具体业务规则以 `backend/.deer-flow/agents/hr-boss-agent/text2cypher-profile.md` 为准。不要在 `SOUL.md`、`skills/custom/hr-boss/SKILL.md` 或其他文档中重复维护同一套细粒度口径。

当前 profile 明确了以下规则：

- 分组、排名和 Top N 默认只统计有效维度值，排除 `null`、空字符串、纯空格、`未填写`、`未知`、`无`、`N/A`。
- 学校、部门、岗位、职称、证书、专业等维度进入 `COUNT`、`ORDER BY`、`LIMIT` 前应先过滤无效值。
- `高级工程师` 属于 Title（职称）口径，不属于 Position（岗位）口径。
- 查询“福建火炬电子科技股份有限公司”的员工统计时，优先使用当前组织口径；结果异常时再交叉检查其他组织关系口径。
- 人数、平均值、名单、排名、占比、筛选等精确问题必须来自结构化图数据库查询，不得凭材料印象估算。

需要调整业务口径时，优先修改 `text2cypher-profile.md`，并确认 Text2Cypher MCP 加载的是同一份 profile。

## Term Resolution Candidate Expansion

`AGENTS.md` 只记录候选扩展的高层设计约束；具体业务口径仍以 `text2cypher-profile.md` 和 Text2Cypher 实现为准。

- Term Resolution candidates 不只是调试信息。对于“研发工程师”“销售工程师”等岗位族统计问题，可以在 `needs_clarification=true` 的同时继续返回统计结果，但最终回答必须说明采用的候选岗位范围或统计口径。
- 当 Position 候选值传给 Cypher 生成器时，优先使用 Term Resolution 召回的完整 candidates，而不是任意截断的 top N，避免展示候选、生成 Cypher 和最终说明之间出现不必要的口径漂移。
- 这是面向领导演示体验的折中：低风险岗位族聚合可以“先给结果，再说明口径”；不要隐藏歧义和扩展范围。
- 该策略主要适用于岗位族聚合。公司、组织、具体人员、项目、证书等高风险实体不应盲目套用全量候选扩展，必要时应澄清或使用确认后的标准值。
- 需要关注候选列表过长、弱相关候选、历史或封存值混入、候选召回变化导致统计结果变化等风险。后续可考虑区分“真歧义”和“可解释扩展”，并用结构化 `selected_values` 或包含口径降低风险。

## Authority Rules

- Text2Cypher 对精确数值、聚合结果、过滤名单和排序结果具有最高权威性。
- GraphRAG 对语义解释、证据归纳、整体结构和探索性分析具有最高权威性。
- 不要让 GraphRAG 覆盖 Text2Cypher 的精确查询结果。
- 同一个问题同时包含精确统计和背景解释时，先用 Text2Cypher 得到确定结果，再用 GraphRAG 做解释补充。
- GraphRAG 证据不足时，应说明证据不足，不要编造。

## Answer Style

面向领导的回答应先结论、再依据、最后限制：

1. 结论：直接回答数字、名单或判断。
2. 依据：说明使用了结构化图数据库查询，或使用了 GraphRAG 证据分析。
3. 限制：如果证据不足、字段缺失或口径不明确，明确说明。

除非用户明确要求调试细节，不要输出原始 Cypher、原始 GraphRAG JSON 或内部路由思考。
