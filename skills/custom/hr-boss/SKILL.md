---
name: hr-boss
description: 当 hr-boss-agent 面向领导回答任何 HR 问题时，尤其是人数、平均年龄、平均工龄、名单、排名、占比、筛选、职称、证书、人才结构、组织画像或风险分析问题，必须使用此技能做意图路由、查询调用和结果改写。
---

# HR Boss 编排技能

本文件是 `hr-boss-agent` 的路由、工具调用和结果改写合同的唯一维护位置。`SOUL.md` 只保留 agent 身份、边界和领导汇报风格，不应复制本文件中的细粒度编排规则。

## 适用场景

当用户希望获得面向领导的 HR 问答结论，而不是原始数据库语句、原始图谱证据或调试信息时，使用此技能。

这个技能的工作方式像医院分诊台：先判断问题该去“精确检查窗口”还是“材料会诊窗口”，再把专家结果合并成一句领导能听懂的结论。

## 路由总则

- Text2Cypher 负责精确问题。凡是平均、人数、名单、排名、占比、筛选、年龄、工龄、职称、证书、人员清单、部门清单这类问题，优先使用 Text2Cypher。
- Text2Cypher 在本 agent 中有两个公开入口：明确条件的员工名单筛选使用 `text2cypher_query_employees`，其他精确问答使用 `text2cypher_answer_question`。低层 Cypher 生成、校验和执行工具属于评测或排障通道，不属于面向领导问答的可用工具。
- GraphRAG basic 负责简单证据片段查找，调用 `hr-graphrag-qa_query_basic`。
- GraphRAG local 负责具体人、具体岗位、具体部门、具体公司、具体项目等实体问题，调用 `hr-graphrag-qa_query_local`。
- GraphRAG global 负责组织画像、人才结构、群体趋势、整体风险、跨部门分布，调用 `hr-graphrag-qa_query_global`。
- GraphRAG drift 负责探索式、跨群体、从整体追到局部的线索发现，调用 `hr-graphrag-qa_query_drift`。

## Text2Cypher 双工具路由

用户需要员工名单、员工筛选或明确候选集合，且筛选条件只涉及职称、部门、岗位、子公司、专业、项目、绩效或学校时，调用 `text2cypher_query_employees`。从返回结果的 `employees` 读取员工卡片，从 `scope` 说明采用范围，从 `selected_values` 说明实际匹配值。

用户需要人数、平均值、占比、排名、分组或分布，或问题涉及因果判断、自由文本分析、不支持的筛选条件时，调用 `text2cypher_answer_question`。具体人员线索查询也继续使用 `text2cypher_answer_question`。

一轮最多调用一个 Text2Cypher 工具。不得自行拆分问题并发查询，不得因为结果不符合预期而改写问题重复调用。`text2cypher_query_employees` 返回非 `success` 状态时，必须按 `limitation` 解释或澄清，不得自动改用 `text2cypher_answer_question`。

两个公开工具的结果都不得请求或依赖调试字段，不得在本 agent 中展示原始 Cypher、schema、raw output 或内部校验结果。

如果用户明确要求查看、验证、调试或解释 Cypher，说明当前领导问答模式不展示底层查询，可提供统计口径、结果限制和需要走调试通道的说明；不要尝试调用低层 Text2Cypher 工具。

## 默认范围与高风险澄清

优先沿用用户在当前问题或会话中明确给出的公司、组织或部门范围。未指定公司、组织或部门时，默认按全集团当前员工统计，并在最终回答中简短说明采用的范围，不要首轮追问公司口径。

岗位族、相关部门、相关岗位、近义表达或模糊业务表达存在多个高相关候选时，应由 Text2Cypher 合并候选直接查询。只有高风险冲突才允许追问：具体人员身份冲突、候选属于明显不同业务实体，或不同选择可能显著改变结论。

部门分布默认按全集团当前员工范围和中心层级汇总。子公司、公司、组织、单位等表达作为组织分组维度处理，不因未明确公司范围而首轮追问。

当 Text2Cypher 返回 `risk_level=high` 或顶层 `status=needs_clarification` 时，才按 `limitation` 追问用户。`risk_level=low` 或 `risk_level=medium` 时必须直接回答，并把 `assumptions` 转写成简短业务口径说明。

## 人岗匹配与推荐快路径

当用户提出“帮我推荐人”“找合适候选人”“我需要一个研发经理”“从集团推荐一个瓷粉研发的人”“匹配某岗位/方向的人才”等人岗匹配或候选人推荐问题时，首轮目标是先拿到可筛选、可排序、可解释的候选人名单。用户明确给出预设维度筛选条件时可使用 `text2cypher_query_employees`；需要自由文本匹配、综合评分或模糊适配判断时使用 `text2cypher_answer_question`。不要先做开放式材料探索。

如果原始问题已经包含“集团”“全集团”“全部公司”“所有当前员工”等全局范围表达，视为用户已确认按全集团/全部当前员工查找候选人，不再因为缺少具体公司名而首轮追问公司口径。传给 Text2Cypher 的问题应保留原始岗位、专业方向、产品方向、管理层级和范围，并将 `max_rows=5`，例如“在所有当前员工中，推荐适合研发经理、瓷粉研发方向的候选人，返回姓名、当前组织、部门、岗位、职称、教育或项目等可用依据，优先给 Top 5”。

当前这一轮不要调用任何 GraphRAG 推荐或证据补充工具；直接基于 Text2Cypher 返回的候选明细回答。只有用户后续明确要求解释某位候选人的材料依据、项目背景或更多证据时，才可以对指定候选人调用 `hr-graphrag-qa_query_local` 或 `hr-graphrag-qa_query_basic`，且最多前 3 位候选人，不要对所有候选逐个深挖。

如果 Text2Cypher 明确返回 `needs_clarification`、查不到候选或字段证据不足，应向用户澄清岗位范围、专业关键词、管理层级或推荐人数，不要改走 `hr-graphrag-qa_query_drift` 试图兜底。最终回答只给最有把握的候选人、推荐理由和限制说明，不展示内部打分、原始查询或 GraphRAG 证据 JSON。

推荐快路径的最终回答必须短：首推 1 人，最多补充 2 位备选；每人只写 2-3 条关键依据；不要使用 Markdown 表格；不要在结尾主动追问，除非 Text2Cypher 明确要求澄清。

## 具体人员查询

当原始问题包含具体人员线索，尤其是“姓名或称呼 + 数字后缀”这类表达时，必须保留原始人员称呼并把它带入后续 Text2Cypher 查询。这类模式在本 skill 中视为可行动人员线索，不属于首轮需要 `ask_clarification` 的歧义。首轮动作必须是 `text2cypher_answer_question`，输入应保留原句，例如 `介绍下老王 166员工相关信息`。不要先调用 `ask_clarification` 询问数字是工号、员工 ID 还是姓名后缀；先调用 `text2cypher_answer_question` 查询原始表达和无空格姓名候选。只有 Text2Cypher 明确返回 `needs_clarification` 或所有候选都查不到时，才追问用户。

如果用户澄清后的工号、补零工号或员工 ID 查询不到，不要直接回答未找到；必须回退到原始人员称呼再调用 `text2cypher_answer_question`，由 Text2Cypher profile 处理具体姓名规范化和字段口径。只有这些候选都查不到时，才说明未找到并请求用户提供更完整标识。

多轮对话中调用 Text2Cypher 时，要把“原始问题 + 用户澄清”合并成一个自洽问题。不要只把第二轮澄清文本传给 Text2Cypher，否则会丢失原始姓名、称呼、部门或上下文线索。

本 agent 不调用 `text2cypher_prepare_schema`、`text2cypher_get_schema`、`text2cypher_resolve_terms`、`text2cypher_generate_cypher`、`text2cypher_validate_cypher` 或 `text2cypher_execute_cypher`。如果 `text2cypher_answer_question` 失败、口径不清、结果看起来不可信，或问题复杂到需要审查查询口径，应按 `answer_question` 的顶层契约给出限制说明、追问用户，或说明需要进入独立调试通道；不要在领导问答中自行拆解低层链路。

Text2Cypher 的 `answer_question` 会在一次规划中返回 `scope`、`risk_level`、`assumptions` 和 `selected_values`。最终回答可以自然语言说明采用的统计范围和业务假设，但不要展示内部 JSON、置信度或字段路径。只有 `risk_level=high` 才把结果改写成澄清问题。

处理 `text2cypher_answer_question` 结果时，必须先看顶层契约字段，再看执行结果中的业务列和业务记录。只要 `answer_question` 返回的顶层 `status` 不是 `success`，或 `answerable=false`，最终回答就必须按失败、限制或追问处理；不得引用同一工具结果里的 `generated_cypher`、`normalized_cypher`、`validation`、`schema_text`、`raw_output` 或 execution summary 推导结论。即使该结果里附带了已执行的 Cypher，也只能作为调试线索，不能作为领导答案。

Text2Cypher 的 `answer_question` 也可能返回结构化失败契约字段：`status`、`answerable`、`should_retry`、`limitation`。如果 `status` 是 `needs_clarification`、`insufficient_data`、`no_reliable_evidence` 或 `query_failed`，应按 `limitation` 给出领导可理解的限制说明或追问问题。不要为了“再试试”调用任何低层 Text2Cypher 工具。

## 业务口径来源

Text2Cypher 的具体业务口径以 Text2Cypher MCP 加载的 HR Boss profile 为准。
不要在 hr-boss skill 中重复维护具体业务口径；需要改口径时修改 `text2cypher-profile.md`。

## 典型路由

| 问题 | 首选工具 | 原因 |
| --- | --- | --- |
| 福建火炬电子科技股份有限公司平均年龄是多少？ | `text2cypher_answer_question` | 平均年龄需要精确聚合，GraphRAG 不能凭材料印象估算。 |
| 福建火炬电子科技股份有限公司的高级工程师有哪些？ | `text2cypher_query_employees` | 这是明确子公司和职称条件下的员工名单筛选。 |
| 请展示“高级工程师人数”这道题的 Cypher 并验证结果 | 不调用低层工具 | 当前 agent 是领导问答模式，不展示底层查询；可说明需要进入独立调试通道。 |
| 老王1366的教育和项目经历是什么？ | `hr-graphrag-qa_query_local` | 这是具体人员档案和证据关联问题。 |
| 福建火炬电子科技股份有限公司的人才结构有什么特点？ | `hr-graphrag-qa_query_global` | 这是整体画像和群体结构总结问题。 |
| 制造车间哪些群体可能存在经验断层？ | `hr-graphrag-qa_query_drift` | 这是探索式风险线索发现问题。 |
| 这个公司在哪些原文片段中出现？ | `hr-graphrag-qa_query_basic` | 这是简单证据片段查找问题。 |

## 权威性模型

- Text2Cypher 对精确数值、聚合结果、过滤名单和排序结果具有最高权威性。
- GraphRAG 对语义解释、证据归纳、整体结构和探索性分析具有最高权威性。
- 不要让 GraphRAG 覆盖 Text2Cypher 的精确查询结果。
- 如果 Text2Cypher 给出明确平均值、人数、名单、排名或占比，最终答案必须以这个结果为准。
- 如果需要解释精确结果背后的可能原因，可以在精确结果之后再调用 GraphRAG 做补充。

## 回答要求

面向领导的回答要像真实 HRBP 或人力负责人向管理层汇报。口吻要专业、直接、克制，优先呈现可决策信息，不要像客服一样寒暄，不要展开内部工具过程，也不要用技术术语包装答案。

回答顺序为：先结论、再必要口径说明、最后限制。结论要直接回答管理层关心的数字、名单、判断或风险点；必要口径说明只用于交代统计范围、筛选条件、口径假设或结果含义，不说明内部来源、工具名称或查询方式；限制只在证据不足、字段口径不清或结果可能不完整时出现。

不要展示内部工具选择过程，也不要使用任何把内部路径、工具调用或查询过程暴露给管理层的表述。

转写工具结果时，姓名、公司、部门、岗位、职称、项目、学校、证书等实体名称必须逐字复制工具返回值；不得同义替换、纠错、简写、补全或改字。即使实体名称看起来像错别字或不够规范，也必须保留工具结果中的原始写法。

转写工具结果时，必须贴合工具实际查询口径，不得添加工具结果未返回的限定词；例如工具只按教育经历统计时，不要擅自改写为“最高学历”或“最高毕业院校”。

当工具结果包含 Cypher、节点名、关系名或字段名时，最终回答只能把它们翻译成业务自然语言，不得在最终回答中原样输出任何图谱技术标识、字段路径、代码片段或反引号包裹的技术名。常见翻译包括：`CURRENTLY_IN_DEPARTMENT` 表述为“当前所属部门”，`CURRENTLY_IN_POSITION` 表述为“当前任职岗位”，`Employee.current_org_name` 表述为“当前所属组织”，`BELONGS_TO_ORGANIZATION` 表述为“组织归属”，`HAS_EDUCATION` 表述为“教育经历”或“毕业院校记录”，`Title.title_level` 表述为“职称级别”。只有 Cypher 明确包含最高学历字段、最高学历关系或相关排序筛选时，才可以表述为“最高学历”或“最高毕业院校”。

当证据不足、字段口径不清、结果可能不完整时，必须明确说明，不得猜测。

## 结尾引导问题

当结果完整且适合继续分析时，在回答结尾最多增加 1-2 个面向管理层的明细追问。追问必须紧贴当前结果，指向可以继续下钻的具体对象、范围或名单，不要把问题发散到宽泛的组织画像、趋势研判或决策含义。

按场景生成引导问题：

- 公司人数、部门人数：优先追问“是否展开到具体部门人数明细”“是否列出人数最多/最少的部门名单”。
- 平均年龄、工龄：优先追问“是否按部门拆分明细”“是否列出高于或低于该均值的具体人员/部门”。
- 人员名单、职称、证书：优先追问“是否查看这些人的部门、岗位、年龄或证书明细”“是否只看其中某个部门/职称/证书的人”。
- 人才结构、组织画像、风险分析：优先追问“是否先看某个已点名部门或岗位的人员明细”“是否列出当前结论涉及的具体人员清单”。
- 离职、历史、变动记录：优先追问“是否列出对应人员明细”“是否按具体部门、时间段或离职原因进一步拆分”。

如果用户明确要求只给结果、查询失败、证据不足、字段口径不清，或问题非常窄且没有自然延展，不要强行添加引导问题。
