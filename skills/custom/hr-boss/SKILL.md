---
name: hr-boss
description: 当面向领导的 HR 问题需要在 Text2Cypher 和 GraphRAG 四种查询方式之间做意图路由时，使用此技能。
---

# HR Boss 编排技能

本文件是 `hr-boss-agent` 的路由、工具调用和结果改写合同的唯一维护位置。`SOUL.md` 只保留 agent 身份、边界和领导汇报风格，不应复制本文件中的细粒度编排规则。

## 适用场景

当用户希望获得面向领导的 HR 问答结论，而不是原始数据库语句、原始图谱证据或调试信息时，使用此技能。

这个技能的工作方式像医院分诊台：先判断问题该去“精确检查窗口”还是“材料会诊窗口”，再把专家结果合并成一句领导能听懂的结论。

## 路由总则

- Text2Cypher 负责精确问题。凡是平均、人数、名单、排名、占比、筛选、年龄、工龄、职称、证书、人员清单、部门清单这类问题，优先使用 Text2Cypher。
- Text2Cypher 有两条合法路径：常规领导问答优先调用 `text2cypher_answer_question`；当需要审查、验证、修复或展示 Cypher 时，允许使用低层工具链。
- GraphRAG basic 负责简单证据片段查找，调用 `hr-graphrag-qa_query_basic`。
- GraphRAG local 负责具体人、具体岗位、具体部门、具体公司、具体项目等实体问题，调用 `hr-graphrag-qa_query_local`。
- GraphRAG global 负责组织画像、人才结构、群体趋势、整体风险、跨部门分布，调用 `hr-graphrag-qa_query_global`。
- GraphRAG drift 负责探索式、跨群体、从整体追到局部的线索发现，调用 `hr-graphrag-qa_query_drift`。

## Text2Cypher 双路径

快路径适用于普通领导问答：调用 `text2cypher_answer_question`，拿到精确答案后转写成面向领导的结论。

## 具体人员查询

当原始问题包含具体人员线索，尤其是“姓名或称呼 + 数字后缀”这类表达时，必须保留原始人员称呼并把它带入后续 Text2Cypher 查询。这类模式在本 skill 中视为可行动人员线索，不属于首轮需要 `ask_clarification` 的歧义。首轮动作必须是 `text2cypher_answer_question`，输入应保留原句，例如 `介绍下老王 166员工相关信息`。不要先调用 `ask_clarification` 询问数字是工号、员工 ID 还是姓名后缀；先调用 `text2cypher_answer_question` 查询原始表达和无空格姓名候选。只有 Text2Cypher 明确返回 `needs_clarification` 或所有候选都查不到时，才追问用户。

如果用户澄清后的工号、补零工号或员工 ID 查询不到，不要直接回答未找到；必须回退到原始人员称呼再调用 `text2cypher_answer_question`，由 Text2Cypher profile 处理具体姓名规范化和字段口径。只有这些候选都查不到时，才说明未找到并请求用户提供更完整标识。

多轮对话中调用 Text2Cypher 时，要把“原始问题 + 用户澄清”合并成一个自洽问题。不要只把第二轮澄清文本传给 Text2Cypher，否则会丢失原始姓名、称呼、部门或上下文线索。

低层路径适用于需要更强可控性的场景，按顺序调用：

1. `text2cypher_prepare_schema`
2. `text2cypher_get_schema`
3. `text2cypher_generate_cypher`
4. `text2cypher_validate_cypher`
5. `text2cypher_execute_cypher`

以下情况优先考虑低层路径：

- 用户明确要求查看、验证、调试或解释 Cypher。
- `text2cypher_answer_question` 失败、口径不清或结果看起来不可信。
- 问题包含复杂筛选、多跳关系链、多条件聚合，需要确认查询口径。
- 评测或排障时需要记录生成的查询、校验结果和执行结果。

使用低层路径时，除非用户要求调试细节，最终回答仍然不要展示原始 Cypher，只输出领导能读懂的结论、依据和限制。

低层路径必须遵守 `generate -> validate -> execute`。每一条新 Cypher，不管是主查询、补充明细查询还是修复后的查询，都必须先调用 `text2cypher_validate_cypher`；验证通过后才能调用 `text2cypher_execute_cypher`，不得直接执行。验证或执行提示中文标点、全角逗号、语法错误时，先修复 Cypher 并重新验证，不要把同类错误查询继续交给执行工具。

Text2Cypher 的 `answer_question` 会默认做字段值纠错转换，并在工具结果中返回 `term_resolution`。当 `term_resolution.needs_clarification=true` 时，最终回答必须先向管理层确认候选口径，不要继续编造查询结论。当 `term_resolution.mappings` 中已有 canonical mapping 时，最终回答可以用自然语言说明“我已按系统中的正式名称口径匹配为 XXX”，但不要展示内部 JSON。

当 `answer_question` 顶层返回成功且 `term_resolution.needs_clarification=false` 时，即使 `unresolved_terms` 非空，也不要把它改写成“需要确认口径”。这只表示字段值纠错没有匹配到单个标准实体，不等于业务口径歧义。最终回答应直接给出工具返回的统计结果，并把实际筛选口径作为说明；不要再询问“该口径是否符合需求”。

处理 `text2cypher_answer_question` 结果时，必须先看顶层契约字段，再看生成、校验或执行细节。只要 `answer_question` 返回的顶层 `status` 不是 `success`，或 `answerable=false`，最终回答就必须按失败、限制或追问处理；不得引用同一工具结果里的 `generated_cypher`、`execution`、records 或 execution summary 推导结论。即使该结果里附带了已执行的 Cypher 或数字，也只能作为调试线索，不能作为领导答案。

Text2Cypher 的 `answer_question` 也可能返回结构化失败契约字段：`status`、`answerable`、`should_retry`、`limitation`。如果 `status` 是 `needs_clarification`、`insufficient_data`、`no_reliable_evidence` 或 `query_failed`，并且 `should_retry=false`，应立即停止低层工具链重试，按 `limitation` 给出领导可理解的限制说明或追问问题。不要为了“再试试”继续调用 `generate_cypher`、`validate_cypher`、`execute_cypher`。只有 `should_retry=true` 或用户明确要求调试查询时，才允许进入低层路径。

低层调试字段值纠错转换时，可以调用 `text2cypher_resolve_terms` 查看候选。完整低层路径为 `text2cypher_prepare_schema` -> `text2cypher_resolve_terms` -> `text2cypher_get_schema` -> `text2cypher_generate_cypher` -> `text2cypher_validate_cypher` -> `text2cypher_execute_cypher`，其中每一条新 Cypher 仍必须先校验再执行。

## 业务口径来源

Text2Cypher 的具体业务口径以 Text2Cypher MCP 加载的 HR Boss profile 为准。
不要在 hr-boss skill 中重复维护具体业务口径；需要改口径时修改 `text2cypher-profile.md`。

## 典型路由

| 问题 | 首选工具 | 原因 |
| --- | --- | --- |
| 福建火炬电子科技股份有限公司平均年龄是多少？ | `text2cypher_answer_question` | 平均年龄需要精确聚合，GraphRAG 不能凭材料印象估算。 |
| 福建火炬电子科技股份有限公司的高级工程师有哪些？ | `text2cypher_answer_question` | 高级工程师名单需要完整筛选，必须以结构化图查询为准。 |
| 请展示“高级工程师人数”这道题的 Cypher 并验证结果 | `text2cypher_generate_cypher` -> `text2cypher_validate_cypher` -> `text2cypher_execute_cypher` | 这是调试和审查口径，需要低层工具链。 |
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

当工具结果包含 Cypher 时，最终口径说明必须贴合 Cypher 中实际出现的关系和字段。看到 `HAS_EDUCATION` 只能表述为“教育经历”或“毕业院校记录”；只有 Cypher 明确包含最高学历字段、最高学历关系或相关排序筛选时，才可以表述为“最高学历”或“最高毕业院校”。

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
