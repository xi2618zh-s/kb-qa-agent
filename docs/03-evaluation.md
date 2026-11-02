# 03 评估：测试预期、实际结果、失败和限制

## 三层验证

| 层 | 验证什么 | 怎么跑 | 结果 |
|---|---|---|---|
| 机制测试 | 循环、校验和上限是否按设计工作。用脚本化的假模型逐步驱动，每个测试只验证一条规则 | `python -m pytest` | 47/47 通过，见 [examples/test_results.txt](../examples/test_results.txt) |
| 离线用例回归 | 15 个验收用例的完整链路（工具、校验、trace、上限、多轮），由 Mock 驱动 | `python main.py run-cases --provider mock` | 15/15 通过，见 [examples/runs/mock/summary.md](../examples/runs/mock/summary.md) |
| 真实模型 | 同一组用例由 DeepSeek（`deepseek-chat`）驱动，检验**模型自己的决策** | `python main.py run-cases --provider openai` | 15/15 通过，见 [examples/runs/deepseek-chat/summary.md](../examples/runs/deepseek-chat/summary.md) |
| 稳定性 | 每个用例独立跑 3 次 | `python main.py run-cases --provider openai --repeat 3` | 45/45 次通过，每个用例 3/3，见 [stability/summary.md](../examples/runs/deepseek-chat/stability/summary.md) |

Mock 的结果只证明流程正确，不证明决策质量（见 [02-solution.md](02-solution.md#离线-mock-的边界)）。题目要求的"模型根据不同工具结果调整动作"，以真实模型的运行记录为准。

**版本说明：**

| 版本 | 改动 | 记录位置 |
|---|---|---|
| v1 | 12 个用例，初版规则 | [deepseek-chat-v1/](../examples/runs/deepseek-chat-v1/summary.md) |
| v2.0 | 加入 6 项改进决策和 3 个新用例 | [deepseek-chat-v2.0/](../examples/runs/deepseek-chat-v2.0/summary.md) |
| v2.1 | 修正圆圈序号误判，解决决策 3 与数字校验的冲突 | [deepseek-chat-v2.1/](../examples/runs/deepseek-chat-v2.1/summary.md) |
| v2.2 | 排除条款引用（"第 2 条"）和句中序号，还原字面 `\n` | [deepseek-chat-v2.2/](../examples/runs/deepseek-chat-v2.2/summary.md) |
| v2.3 | 换算带单位的中文数字（"满三年"），**最终版** | [deepseek-chat/](../examples/runs/deepseek-chat/summary.md) |

## 机制测试覆盖的规则

| 测试 | 规则 |
|---|---|
| `test_citation_must_come_from_text_that_was_read` | 只看过检索片段就引用会被退回；模型读取原文后重新提交才通过 |
| `test_reworded_quote_is_rejected` | 改写过的"引用"被退回 |
| `test_numbers_in_answer_must_appear_in_citations_or_question` | 答案写"45 天"而原文是 30 天时被退回 |
| `test_section_ids_and_list_markers_are_not_treated_as_facts` | 段落编号（S2）、行首序号（"2."）、圆圈序号（①②）不参与数字校验 |
| `test_clause_refs_and_inline_list_markers_are_not_treated_as_facts` | 条款引用（"第 2 条""第 1 节"）、句中序号（"：1. …；2、…"）、字面 `\n` 后的序号不参与数字校验；字面 `\n` 在答案中还原为换行 |
| `test_chinese_numerals_in_the_question_support_arabic_numbers` | 问题写"满三年"时，答案中的"3 年"有依据 |
| `test_chinese_quantities_in_the_answer_are_checked_but_counts_are_not` | 答案中的"四十五天"会被检查并退回；"两份文档""分三档"这类计数不检查 |
| `test_derived_or_invented_numbers_are_still_rejected` | 放宽之后，推导出的"0 天"、编造的"1.5 个月"仍然会被退回 |
| `test_conflict_status_requires_two_documents_and_a_question` | 报冲突时只引用一份文档、没有确认问题，或确认问题没有列出每份所引文档，都会被退回 |
| `test_insufficient_evidence_must_not_carry_citations` | `insufficient_evidence` 带引用会被退回，提示改用 `answered` 并在 `gaps` 写明缺失部分 |
| `test_need_clarification_requires_a_question` | `need_clarification` 必须有追问 |
| `test_step_limit_returns_explicit_incomplete_status` | 步数用完返回 `incomplete`，没有答案也没有引用，并列出已读文档 |
| `test_tool_call_budget_is_enforced` | 超过工具调用上限后返回 `TOOL_BUDGET_EXHAUSTED` |
| `test_tool_failure_is_returned_to_model_without_automatic_retry` | 工具失败只作为观察返回，程序不自动重试 |
| `test_text_reply_triggers_protocol_reminder` / `test_invalid_json_arguments_are_reported` | 模型没按协议调用工具、参数不是合法 JSON 时，都作为观察返回 |
| `test_history_reaches_the_model` | 对话历史按顺序传给模型 |
| `test_trace_records_reason_and_next_action` | trace 中有决策依据和后续动作 |
| `test_case_meets_its_expectations_with_mock[C01…C15]` | 15 个用例的预期 |
| `test_cases_cover_every_acceptance_point` | 用例覆盖了全部验收点 |
| `test_editing_a_document_changes_the_answer` | 把 D01 改成 45 天后，冲突变为 45 对 15；再删掉 D02，答案变为依据 D01 的 45 天 |
| `test_adapter_*` / `test_agent_runs_through_the_adapter` | OpenAI 兼容适配器的请求格式、工具调用解析、错误处理（用假客户端） |
| `test_cli_*` | 命令行入口、汇总中的指标、`--repeat` 生成的稳定性汇总 |

## 离线用例结果（Mock）

| 用例 | 验收点 | 预期 | 实际 | 记录 |
|---|---|---|---|---|
| C01 | 明确答案 | `answered`，引用 D03，含 5 | 一致 | [C01](../examples/runs/mock/C01_clear_answer.md) |
| C02 | 改写后的相似问题 | 同 C01 | 一致，引用和答案与 C01 相同 | [C02](../examples/runs/mock/C02_paraphrase.md) |
| C03 | 文档冲突 | `conflict_needs_confirmation`，引用 D01 和 D02，含 30 和 15 | 一致 | [C03](../examples/runs/mock/C03_conflict.md) |
| C04 | 冲突 → 用户确认 | 冲突，然后按 D02 回答 15 天 | 一致 | [C04](../examples/runs/mock/C04_conflict_then_user_confirms.md) |
| C05 | 上下文追问 | 第二轮回答"不享受年假" | 一致 | [C05](../examples/runs/mock/C05_context_followup.md) |
| C06 | 资料外问题 | `insufficient_evidence` | 一致：检索两次后停止 | [C06](../examples/runs/mock/C06_out_of_scope.md) |
| C07 | 检索改进 | Mock 预期 `insufficient_evidence`（做不了语义改写） | 一致 | [C07](../examples/runs/mock/C07_query_rewrite.md) |
| C08 | 工具临时失败 | 重试后 `answered` | 一致 | [C08](../examples/runs/mock/C08_tool_failure_transient.md) |
| C09 | 工具持续失败 | `tool_error`，没有引用 | 一致 | [C09](../examples/runs/mock/C09_tool_failure_persistent.md) |
| C10 | 步数上限 | `incomplete` / `step_limit_reached` | 一致 | [C10](../examples/runs/mock/C10_step_limit.md) |
| C11 | 移除 D02 | 依据 D01 回答 30 天 | 一致 | [C11](../examples/runs/mock/C11_doc_removed_no_conflict.md) |
| C12 | D02 写明适用范围 | Mock 预期仍报冲突（读不懂适用范围） | 一致 | [C12](../examples/runs/mock/C12_doc_scoped_resolves_conflict.md) |
| C13 | 分档数值不是冲突 | `answered` 或 `need_clarification` | `answered`（三档都在同一文档内，不比较） | [C13](../examples/runs/mock/C13_tiered_not_conflict.md) |
| C14 | 新版本写明替代关系 | Mock 预期仍报冲突（读不懂替代关系） | 一致 | [C14](../examples/runs/mock/C14_superseded_version.md) |
| C15 | 指代不明 | `need_clarification` | 一致 | [C15](../examples/runs/mock/C15_ambiguous_reference.md) |

C07、C12、C14 对 Mock 单独设了 `expect_mock`，因为这三个用例考的正是 Mock 没有的能力。真实模型使用 `expect` 中的标准预期。

## 真实模型结果（DeepSeek，最终版 v2.3）

- 模型：`deepseek-chat`，接口 `https://api.deepseek.com`，`temperature=0`。
- 运行时间：2026-11-02。
- 用量：主运行共 15 个用例、52 次模型调用，约 13.4 万输入 token、1.0 万输出 token。
- 汇总：[examples/runs/deepseek-chat/summary.md](../examples/runs/deepseek-chat/summary.md)。

| 用例 | 实际决策路径 | 结果 | 记录 |
|---|---|---|---|
| C01 明确答案 | 并行检索两组关键词 → 读 D03 → 再检索一次，排查折算等其他规定 → `finish` | `answered`：满 3 年 5 天 | [C01](../examples/runs/deepseek-chat/C01_clear_answer.md) |
| C02 改写问题 | 检索两次 → 读 D03 → `finish` | `answered`：5 天，引用与 C01 一致。答案把问题中的"满三年"写成"满 3 年"，一次通过校验 | [C02](../examples/runs/deepseek-chat/C02_paraphrase.md) |
| C03 文档冲突 | 检索两次 → 读 D01 → 读 D02 → `finish` | `conflict_needs_confirmation`：列出 30 天和 15 天，追问中列出 D01、D02 两个选项；**没有擅自回答 15 天** | [C03](../examples/runs/deepseek-chat/C03_conflict.md) |
| C04 冲突 → 用户确认 | 第 1 轮同 C03；第 2 轮按用户确认的文档检索 → 读 D02 | 第 2 轮 `answered`：按用户确认的《费用报销操作指引》回答 15 天 | [C04](../examples/runs/deepseek-chat/C04_conflict_then_user_confirms.md) |
| C05 上下文追问 | 第 2 轮把"那刚毕业……呢"结合上一轮改写成关于新员工年假的检索 → 读 D03 | `answered`：累计工作不满 1 年，不享受年假 | [C05](../examples/runs/deepseek-chat/C05_context_followup.md) |
| C06 资料外问题 | 用 4 组关键词检索，都没有相关结果 → `finish` | `insufficient_evidence`，没有凭常识作答 | [C06](../examples/runs/deepseek-chat/C06_out_of_scope.md) |
| C07 检索改进 | "WFH" 改写成"居家办公""远程办公" → 读 D05 → `finish` | `answered`：先申请开通 VPN；`gaps` 注明没有独立的居家办公审批制度 | [C07](../examples/runs/deepseek-chat/C07_query_rewrite.md) |
| C08 工具临时失败 | 检索 → **失败** → 模型决定重试 → 成功 → 读 D06 | `answered`：离线模式仅专业版可用 | [C08](../examples/runs/deepseek-chat/C08_tool_failure_transient.md) |
| C09 工具持续失败 | 检索连续失败 **2 次** → `finish` | `tool_error`：没有引用、没有答案 | [C09](../examples/runs/deepseek-chat/C09_tool_failure_persistent.md) |
| C10 步数上限 | 第 1 步并行两次检索，第 2 步并行读 D01、D02 → 步数用完 | `incomplete` / `step_limit_reached` | [C10](../examples/runs/deepseek-chat/C10_step_limit.md) |
| C11 移除 D02 | 检索两次 → 只读 D01 → `finish` | `answered`：30 天，引用 D01 | [C11](../examples/runs/deepseek-chat/C11_doc_removed_no_conflict.md) |
| C12 D02 写明适用范围 | 检索两次 → 读 D01 → 读 D02，发现"仅适用于市场部" → `finish` | `answered`：一般日常费用 30 天、市场部市场活动费用 15 天 | [C12](../examples/runs/deepseek-chat/C12_doc_scoped_resolves_conflict.md) |
| C13 分档不是冲突 | 检索两次 → 读 D03 → `finish` | `answered`：按 1–10 年 5 天、10–20 年 10 天、20 年以上 15 天分档说明，**没有误报冲突** | [C13](../examples/runs/deepseek-chat/C13_tiered_not_conflict.md) |
| C14 新版本替代旧版本 | 检索两次 → 并行读 D08、D02、D01 → `finish` | `answered`：依据 D08 回答 20 天，说明 D01 已废止、D02 不一致时以 D08 为准；三份文档都有引用 | [C14](../examples/runs/deepseek-chat/C14_superseded_version.md) |
| C15 指代不明 | 不检索，直接 `finish` | `need_clarification`：追问具体是哪类费用 | [C15](../examples/runs/deepseek-chat/C15_ambiguous_reference.md) |

### 稳定性（每个用例 3 次）

[stability/summary.md](../examples/runs/deepseek-chat/stability/summary.md)：15 个用例每个都是 3/3 通过，每次的最终状态都相同。v1 中在两种状态间摇摆的 C07，在加入"部分可答用 `answered`"规则后，v2 各版本的每次运行都是 `answered`。

这只说明在这 15 个用例上稳定，不代表在更大的问题集上也稳定。

### 模型根据不同工具结果调整动作

同一个问题，工具返回的结果不同，模型的后续动作和结论随之不同：

**路径 A：同样问"报销期限是多久？"，只改知识库内容**

| 知识库 | 读到的原文 | 模型的下一步 | 结论 |
|---|---|---|---|
| 原始（C03） | D01 写 30 天、D02 写 15 天，都没写适用范围 | 读完两份后停止，列出选项请用户确认 | `conflict_needs_confirmation` |
| 移除 D02（C11） | 只有 D01 | 读一份就作答 | `answered`：30 天 |
| D02 加上适用范围（C12） | D02 写明"仅适用于市场部，其他费用按 D01" | 按适用范围分别作答 | `answered`：30 天和 15 天并列 |
| 叠加 D08（C14） | D08 写明废止 D01、与 D02 不一致时以 D08 为准 | 三份都读，采用 D08 | `answered`：20 天 |

**路径 B：同样问"云笺笔记的离线模式哪个版本能用？"，只改工具的可用性**

| 工具状态 | 观察到的结果 | 模型的下一步 | 结论 |
|---|---|---|---|
| 第一次检索失败（C08） | `TOOL_UNAVAILABLE`，然后成功 | 重试一次，继续读 D06 | `answered` |
| 持续失败（C09） | 连续 2 次 `TOOL_UNAVAILABLE` | 按规则停止 | `tool_error`，不作答 |

**路径 C：检索结果的相关性不同**

| 用例 | 检索结果 | 模型的下一步 |
|---|---|---|
| C07 | "WFH"字面无匹配，改写成"居家办公""远程办公"后命中 D05 | 读 D05 后作答，缺失部分写进 `gaps` |
| C06 | 四组关键词都只命中无关文档 | 停止，返回 `insufficient_evidence` |
| C15 | 问题本身无法确定查询对象 | 不检索，直接追问 |

## v2 改进前后对比

v2 的改进决策见 [04-ai-usage.md](04-ai-usage.md#v2-改进的决策)。下表只比较 v1 就有的 C01–C12，保证用例集相同。

**主运行（每个用例 1 次）：**

| 指标 | v1 | v2.0 | v2.1 | v2.2 | v2.3（最终） |
|---|---|---|---|---|---|
| 通过 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| 每轮平均步数 / 工具调用 | 3.1 / 3.2 | 3.1 / 3.1 | 3.2 / 3.4 | 3.1 / 3.4 | 3.2 / 3.4 |
| 回答平均字数 | 229.8 | 211.4 | 211.6 | 208.5 | 208.4 |
| 每条回答平均引用数 | 2.6 | 2.2 | 2.2 | 2.3 | 2.1 |
| C09 持续失败时的检索次数 | 5 | 2 | 2 | 2 | 2 |
| `finish` 被退回次数 | 0 | 2 | 1 | 0 | 0 |

**稳定性运行（每个用例 3 次，v1 没有做）：**

| 指标 | v2.0 | v2.1 | v2.2 | v2.3（最终） |
|---|---|---|---|---|
| C01–C12 通过 | 36/36 | 36/36 | 36/36 | 36/36 |
| C01–C12 回答平均字数 / 引用数 | 200.9 / 2.0 | 211.8 / 2.2 | 211.9 / 2.2 | 208.7 / 2.2 |
| C01–C12 `finish` 被退回次数 | 7 | 4 | 1 | 0 |
| 全部 15 个用例 `finish` 被退回次数 | 10 | 6 | 2 | 1 |
| 其中属于校验误判的 | 2 | 4 | 1 | **0** |
| 其中按设计拦截的（数字确实没有出处） | 8 | 2 | 1 | 1 |

"误判"的判定口径：用最终版 v2.3 的规则回放每一次退回。被拦的数字在新规则下全部有依据的，算误判（结构性编号、中文数字等）；仍有数字没有出处的，算按设计拦截（推导出的数字、补充信息中未引用的数字）。

- v2.0 → v2.1 的下降主要来自提示词调整：模型不再在补充信息里写没有引用的数字，而不是放宽了校验。
- v2.1 → v2.3 的下降来自修正误判：条款引用、句中序号、字面 `\n`、中文数字。
- v2.3 唯一的一次退回是 C14：答案提到了 D02 的 15 天、版本日期和 D01 的 30 天，却没有引用这两份文档。这是校验按设计起作用。

**各项决策的效果：**

| 决策 | 效果 | 证据 |
|---|---|---|
| 1. 部分可答用 `answered` | 有效：C07 从摇摆变成每次都是 `answered`，缺失部分写进 `gaps` | C07 的稳定性记录 |
| 2. 连续 2 次失败就停 | 有效：C09 的检索次数从 5 次降到 2 次，v2 各次运行一致 | C09 |
| 3. 回答精简、不堆砌引用 | **效果有限**：字数约减少 9%（230 → 208），引用数从 2.6 降到约 2.1。模型仍常写一条"补充"，规则也允许一条 | 上表 |
| 4. 冲突追问列出选项 | 有效：C03、C04 的追问都改成列出 D01、D02 两个选项，不再夹带推测 | C03、C04 |
| 5. 稳定性评估 | 已完成：每个版本都是 45/45 | stability |
| 6. 新增反例用例 | 模型在 C13（分档）、C14（替代关系）、C15（指代不明）上都做对，3/3 次 | C13–C15 |
| 7–8. 修正数字校验误判 | 有效：3 次重复运行中的误判从 v2.1 的 4 次降到 v2.3 的 0 次 | 上表 |

## 真实运行中发现的问题和处理

| 版本 | 问题 | 证据 | 处理 |
|---|---|---|---|
| v1 | **数字校验误伤段落编号**：连通性测试中，答案因"数字 2 找不到出处"被退回两次，多花 2 步 | 正式跑用例前的单问测试（未保存记录） | 排除 `S2`、`D01-S2` 和行首序号，并补测试 |
| v1 | **C07 预期过窄**：首轮返回 `insufficient_evidence`。模型找到了 VPN 条款，但因为知识库没写 WFH 本身的审批，判定资料不足 | [v1 首轮记录](../examples/runs/deepseek-chat-v1/superseded/C07_query_rewrite.first-run.md) | v1 时先放宽预期。v2 加入"部分可答用 `answered`"规则（决策 1）后，预期重新收紧为 `answered`，各次运行都通过 |
| v2.0 | **圆圈序号被误判**：模型开始用 ①② 列选项，NFKC 归一化会把 ② 变成"2" | v2.0 稳定性记录中的退回原因 | 校验前先去掉圆圈序号，补测试 |
| v2.0 | **决策 3 与数字校验冲突**："引用只放支撑结论的原文"与"答案里的数字必须在引用中"互相矛盾。模型在补充信息里写了价格"30 元 / 298 元"（C08）、"7 个工作日"（C12）却不引用，于是被退回。v2.0 的 10 次退回中有 8 次属于这种情况 | v2.0 稳定性记录 | 把提示词改成"引用回答中实际用到的原文（结论和补充都算）；不值得引用的补充就不写"，决策 3 的本意不变。v2.1 中这类退回从 8 次降到 2 次 |
| v2.1 | **剩余 6 次退回**：3 次是条款引用"第 2 条「报销期限」""第 1 节"（C04、C11、C14）；1 次是模型把换行写成字面 `\n`，导致"1. 《…》"不在行首、没被识别为序号（C03）；1 次是推导出的"0 天"（C05）；1 次是条款引用加上未引用的 30 天、15 天（C14） | [v2.1 稳定性记录](../examples/runs/deepseek-chat-v2.1/stability/summary.md) | 排除条款引用和标点后的句中序号，校验前把字面 `\n` 还原为换行，答案展示时也做同样还原。修改前用 v2.1 的全部退回记录回放：结构性编号全部放行，"0 天"和未引用的数字仍被拦下 |
| v2.2 | **中文数字误判**：C02 的问题写"满三年"，答案写"3 年"，校验只认阿拉伯数字，在问题里找不到 3 | [v2.2 稳定性记录](../examples/runs/deepseek-chat-v2.2/stability/summary.md) | v2.3 换算"带单位的中文数字"，问题、引用、答案三方使用同一规则。修改前用所有版本中已通过的 167 条答案回放，**没有产生新的误判**。v2.3 中 C02 有 3/4 次写了"满 3 年"，都一次通过 |
| v2.3 | **剩余 1 次退回**：C14 提到了 D02 的天数和版本日期、D01 的天数，却没有引用这两份文档 | [v2.3 稳定性记录](../examples/runs/deepseek-chat/stability/summary.md) | 符合设计，模型补上引用后通过 |
| v2 | **提示词规则没被严格遵守**：规则要求资料外问题"最多换 2 次关键词"（共 3 次检索），C06 在 v2 的运行中几乎每次都检索 4 次 | 各版本 C06 记录 | 结果正确，也在步数上限之内，**未处理**。如需严格执行，可在代码里设置每轮检索次数上限 |

## 失败与限制

- **Mock 不证明决策质量**：它是人写的启发式规则，做不到 C07（语义改写）、C12（适用范围）、C14（替代关系）。
- **用例和数据都是自建的**：8 份合成文档（含变体）、15 个用例，规模小，没有盲测集。100% 通过只说明模型在这些用例上的表现。
- **稳定性样本小**：每个版本、每个用例只跑了 3 次，服务端模型更新后结果可能变化。
- **冲突由模型判断**：程序只保证"报冲突时必须引用两份文档的原文并列出选项"，无法阻止模型漏报冲突。漏报时 C03 的状态检查会失败。
- **数字校验的边界**：
  - 只检查带单位的中文数字。"分三档""两种情况"这类不带单位的计数不检查，所以由它们推导出的错误不会被发现；
  - 推导出的数字（如"0 天"）会被有意退回，代价是多 1 步；
  - 换算只覆盖常见单位和"千"以内的数字。
- **提示词规则不是硬约束**：C06 常比规定多检索一次；"回答精简"效果有限，平均约 210 字。
- **检索是字面匹配**：同义词依赖模型改写查询；改写失败时会返回资料不足，而不是答错。
