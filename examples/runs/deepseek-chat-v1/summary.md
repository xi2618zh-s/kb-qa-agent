# 运行汇总（v1 基线）：openai / deepseek-chat

通过 12/12 个用例。每个用例的步骤、参数、返回摘要和决策依据见同目录下的 `<用例ID>.md`，完整数据（含发给模型的消息）见 `<用例ID>.json`。

| 指标 | 值 |
|---|---|
| 轮次 / 模型调用次数 | 14 / 43 |
| 每轮平均步数 / 工具调用 | 3.1 / 3.2 |
| 回答平均字数（answered 与冲突） | 229.8 |
| 每条回答平均引用数 | 2.6 |
| finish 被退回次数 | 0 |
| 失败的工具调用（含注入故障） | 6 |
| 输入 / 输出 token | 97509 / 8861 |

| 用例 | 验收点 | 各轮状态 | 步数 | 结论 |
|---|---|---|---|---|
| [C01_clear_answer](C01_clear_answer.md) | 明确答案 | `answered` | 3 | 通过 |
| [C02_paraphrase](C02_paraphrase.md) | 改写后的相似问题 | `answered` | 3 | 通过 |
| [C03_conflict](C03_conflict.md) | 文档冲突 | `conflict_needs_confirmation` | 3 | 通过 |
| [C04_conflict_then_user_confirms](C04_conflict_then_user_confirms.md) | 文档冲突、上下文追问 | `conflict_needs_confirmation` → `answered` | 3 / 2 | 通过 |
| [C05_context_followup](C05_context_followup.md) | 上下文追问 | `answered` → `answered` | 3 / 3 | 通过 |
| [C06_out_of_scope](C06_out_of_scope.md) | 资料外问题、信息或资料不足 | `insufficient_evidence` | 3 | 通过 |
| [C07_query_rewrite](C07_query_rewrite.md) | 改写后的相似问题、检索改进 | `answered` | 3 | 通过 |
| [C08_tool_failure_transient](C08_tool_failure_transient.md) | 工具失败 | `answered` | 4 | 通过 |
| [C09_tool_failure_persistent](C09_tool_failure_persistent.md) | 工具失败 | `tool_error` | 5 | 通过 |
| [C10_step_limit](C10_step_limit.md) | 步数上限 | `incomplete` | 2 | 通过 |
| [C11_doc_removed_no_conflict](C11_doc_removed_no_conflict.md) | 明确答案、替换文档 | `answered` | 3 | 通过 |
| [C12_doc_scoped_resolves_conflict](C12_doc_scoped_resolves_conflict.md) | 文档冲突、替换文档 | `answered` | 3 | 通过 |
