# 稳定性：openai / deepseek-chat × 3

每个用例独立运行 3 次。15/15 个用例每次都通过；总计 45/45 次通过。每次运行的完整 trace 见 `<用例ID>.md`。

| 指标 | 值 |
|---|---|
| 轮次 / 模型调用次数 | 51 / 149 |
| 每轮平均步数 / 工具调用 | 2.9 / 3.1 |
| 回答平均字数（answered 与冲突） | 212.6 |
| 每条回答平均引用数 | 2.4 |
| finish 被退回次数 | 1 |
| 失败的工具调用（含注入故障） | 9 |
| 输入 / 输出 token | 376023 / 30746 |

| 用例 | 通过次数 | 各次最终状态 | 各次步数 |
|---|---|---|---|
| [C01_clear_answer](C01_clear_answer.md) | 3/3 | `answered` / `answered` / `answered` | 3 / 4 / 4 |
| [C02_paraphrase](C02_paraphrase.md) | 3/3 | `answered` / `answered` / `answered` | 3 / 3 / 3 |
| [C03_conflict](C03_conflict.md) | 3/3 | `conflict_needs_confirmation` / `conflict_needs_confirmation` / `conflict_needs_confirmation` | 3 / 3 / 3 |
| [C04_conflict_then_user_confirms](C04_conflict_then_user_confirms.md) | 3/3 | `answered` / `answered` / `answered` | 3+2 / 3+2 / 3+2 |
| [C05_context_followup](C05_context_followup.md) | 3/3 | `answered` / `answered` / `answered` | 3+3 / 4+3 / 3+3 |
| [C06_out_of_scope](C06_out_of_scope.md) | 3/3 | `insufficient_evidence` / `insufficient_evidence` / `insufficient_evidence` | 4 / 4 / 3 |
| [C07_query_rewrite](C07_query_rewrite.md) | 3/3 | `answered` / `answered` / `answered` | 3 / 3 / 3 |
| [C08_tool_failure_transient](C08_tool_failure_transient.md) | 3/3 | `answered` / `answered` / `answered` | 4 / 3 / 4 |
| [C09_tool_failure_persistent](C09_tool_failure_persistent.md) | 3/3 | `tool_error` / `tool_error` / `tool_error` | 3 / 3 / 3 |
| [C10_step_limit](C10_step_limit.md) | 3/3 | `incomplete` / `incomplete` / `incomplete` | 2 / 2 / 2 |
| [C11_doc_removed_no_conflict](C11_doc_removed_no_conflict.md) | 3/3 | `answered` / `answered` / `answered` | 3 / 3 / 3 |
| [C12_doc_scoped_resolves_conflict](C12_doc_scoped_resolves_conflict.md) | 3/3 | `answered` / `answered` / `answered` | 3 / 3 / 3 |
| [C13_tiered_not_conflict](C13_tiered_not_conflict.md) | 3/3 | `answered` / `answered` / `answered` | 3 / 3 / 3 |
| [C14_superseded_version](C14_superseded_version.md) | 3/3 | `answered` / `answered` / `answered` | 3 / 3 / 4 |
| [C15_ambiguous_reference](C15_ambiguous_reference.md) | 3/3 | `need_clarification` / `need_clarification` / `need_clarification` | 1 / 1 / 1 |
