# C09_tool_failure_persistent

- 验收点：工具失败
- 说明：知识库全部工具持续不可用，应返回 tool_error 和资料缺口，不得编造答案。
- 模型：`openai` / `deepseek-chat`
- 运行选项：`{"fail": ["*:always"]}`
- 生成时间：2026-11-02T18:40:44+08:00
- 结论：通过

## 第 1 轮

**问题**：云笺笔记的离线模式哪个版本能用？

| 步 | 动作 | 参数 | 决策依据（模型给出的 reason） | 返回摘要 | 后续动作 |
|---|---|---|---|---|---|
| 1 | `search_docs` | {"query": "云笺笔记 离线模式 版本"} | 用户询问云笺笔记离线模式可用的版本，先检索相关产品 FAQ | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `search_docs` |
| 2 | `search_docs` | {"query": "云笺笔记 离线模式 版本"} | 上次检索返回 TOOL_UNAVAILABLE，按规则重试同一检索 | 失败 TOOL_UNAVAILABLE：模拟故障（注入）：search_docs 服务暂时不可用 | `finish` |
| 3 | `finish` | {"status": "tool_error", "answer": "无法回答：检索工具 search_docs 连续两次返回 TOOL_UNAVAILABLE（服务暂时不可用），因此未能获取云笺笔记离线模式相关版本要求的任何知识库资料。请稍后重试，或联系知识库管理员确认检索服务状态。", "citations":… | 同一检索工具连续两次不可用，按规则不再重试，直接报告工具故障 | 结果通过校验，本轮结束 | `（结束）` |

**结果**：`tool_error`（工具故障） · 结束原因 `finished` · 用了 3/8 步、2/12 次工具调用

**回答**：无法回答：检索工具 search_docs 连续两次返回 TOOL_UNAVAILABLE（服务暂时不可用），因此未能获取云笺笔记离线模式相关版本要求的任何知识库资料。请稍后重试，或联系知识库管理员确认检索服务状态。

**资料缺口**：未能检索到云笺笔记产品 FAQ 中关于离线模式及适用版本的原文资料（search_docs 连续 2 次不可用）

**预期检查**：通过
- [x] status：实际 tool_error，期望 ['tool_error']
- [x] 资料缺口非空：1 条
- [x] 无引用：实际引用 []
