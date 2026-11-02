# C09_tool_failure_persistent

- 验收点：工具失败
- 说明：知识库全部工具持续不可用，应返回 tool_error 和资料缺口，不得编造答案。
- 模型：`mock` / `heuristic-policy`
- 运行选项：`{"fail": ["*:always"]}`
- 生成时间：2026-11-02T23:20:11+08:00
- 结论：通过

## 第 1 轮

**问题**：云笺笔记的离线模式哪个版本能用？

| 步 | 动作 | 参数 | 决策依据（模型给出的 reason） | 返回摘要 | 后续动作 |
|---|---|---|---|---|---|
| 1 | `search_docs` | {"query": "云笺笔记的离线模式哪个版本能用？"} | 先检索与问题相关的制度段落 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `search_docs` |
| 2 | `search_docs` | {"query": "云笺笔记的离线模式哪个版本能用？"} | search_docs 返回临时故障，重试一次 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `finish` |
| 3 | `finish` | {"status": "tool_error", "answer": "知识库工具连续失败，暂时无法查询，本轮不给出答案。", "citations": [], "gaps": ["search_docs 连续 2 次不可用，未能获取相关制度原文"], "clarification_question": ""} | search_docs 连续 2 次失败，停止重试 | 结果通过校验，本轮结束 | `（结束）` |

**结果**：`tool_error`（工具故障） · 结束原因 `finished` · 用了 3/8 步、2/12 次工具调用

**回答**：知识库工具连续失败，暂时无法查询，本轮不给出答案。

**资料缺口**：search_docs 连续 2 次不可用，未能获取相关制度原文

**预期检查**：通过
- [x] status：实际 tool_error，期望 ['tool_error']
- [x] 资料缺口非空：1 条
- [x] 无引用：实际引用 []
