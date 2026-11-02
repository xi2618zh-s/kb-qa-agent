# C09_tool_failure_persistent

- 验收点：工具失败
- 说明：知识库全部工具持续不可用，应返回 tool_error 和资料缺口，不得编造答案。
- 模型：`openai` / `deepseek-chat`
- 运行选项：`{"fail": ["*:always"]}`
- 生成时间：2026-11-02T17:12:22+08:00
- 结论：通过

## 第 1 轮

**问题**：云笺笔记的离线模式哪个版本能用？

| 步 | 动作 | 参数 | 决策依据（模型给出的 reason） | 返回摘要 | 后续动作 |
|---|---|---|---|---|---|
| 1 | `search_docs` | {"query": "云笺笔记 离线模式 版本"} | 用户询问云笺笔记离线模式的可用版本，先用产品名和功能关键词检索。 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `search_docs` |
| 1 | `search_docs` | {"query": "离线模式 支持版本 产品 FAQ"} | 同时用通用说法检索，以防产品名未直接命中。 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `search_docs` |
| 2 | `search_docs` | {"query": "云笺笔记 离线模式"} | 上次检索因服务故障失败，重试同一检索以获取文档定位。 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `search_docs` |
| 3 | `search_docs` | {"query": "云笺笔记"} | 再次重试检索，改用更短的关键词以提高命中可能。 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `search_docs` |
| 4 | `search_docs` | {"query": "离线模式"} | 最后一次重试检索，仅用功能关键词，若仍失败则报告工具故障。 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `finish` |
| 5 | `finish` | {"status": "tool_error", "answer": "抱歉，知识库检索服务当前不可用（search_docs 连续多次返回 TOOL_UNAVAILABLE），我无法检索到云笺笔记离线模式的相关文档，因此不能确认哪个版本支持离线模式。为避免给出错误信息，本次不作回答，请稍后重试或联系知识库管理员。"… | 检索工具多次重试均返回服务不可用，无法获得任何文档依据，按规则报告工具故障。 | 结果通过校验，本轮结束 | `（结束）` |

**结果**：`tool_error`（工具故障） · 结束原因 `finished` · 用了 5/8 步、5/12 次工具调用

**回答**：抱歉，知识库检索服务当前不可用（search_docs 连续多次返回 TOOL_UNAVAILABLE），我无法检索到云笺笔记离线模式的相关文档，因此不能确认哪个版本支持离线模式。为避免给出错误信息，本次不作回答，请稍后重试或联系知识库管理员。

**资料缺口**：未能获取云笺笔记产品 FAQ / 版本说明文档：search_docs 服务连续 4 次返回 TOOL_UNAVAILABLE，无法定位任何文档，也无法读取原文。

**预期检查**：通过
- [x] status：实际 tool_error，期望 ['tool_error']
- [x] 资料缺口非空：1 条
- [x] 无引用：实际引用 []
