# C07_query_rewrite

- 验收点：改写后的相似问题、检索改进
- 说明：用户用缩写 WFH，知识库写的是“远程办公”，字面检索找不到，需要模型改写查询后找到 D05 并引用其中的 VPN 条款。知识库只写了远程办公要开通 VPN、没写 WFH 本身是否要审批，属于部分可答。v1 没有部分可答的规则，模型在 answered 和 insufficient_evidence 之间摇摆；v2 规定部分可答用 answered、缺失部分写进 gaps，预期收紧为 answered（过程见 docs/03-evaluation.md）。离线 Mock 没有语义改写能力，预期返回资料不足。
- 模型：`mock` / `heuristic-policy`
- 运行选项：`{}`
- 生成时间：2026-11-02T23:20:11+08:00
- 结论：通过

## 第 1 轮

**问题**：WFH 要先申请什么？

| 步 | 动作 | 参数 | 决策依据（模型给出的 reason） | 返回摘要 | 后续动作 |
|---|---|---|---|---|---|
| 1 | `search_docs` | {"query": "WFH 要先申请什么？"} | 先检索与问题相关的制度段落 | 检索“WFH 要先申请什么？”：5 条 — D04-S1(1.223), D07-S1(1.204), D06-S4(0.944), D03-S3(0.921), D04-S3(0.91) | `search_docs` |
| 2 | `search_docs` | {"query": "WFH 要先申请"} | 检索结果与问题关联度低（最高覆盖率 5%），去掉疑问词后重新检索 | 检索“WFH 要先申请”：5 条 — D04-S1(1.223), D07-S1(1.204), D06-S4(0.944), D03-S3(0.921), D04-S3(0.91) | `finish` |
| 3 | `finish` | {"status": "insufficient_evidence", "answer": "知识库中没有找到与该问题相关的制度或说明，无法作答。", "citations": [], "gaps": ["未检索到与“WFH 要先申请什么？”相关的文档"], "clarification_question": ""} | 两次检索都没有相关段落（最高覆盖率 7%） | 结果通过校验，本轮结束 | `（结束）` |

**结果**：`insufficient_evidence`（资料不足） · 结束原因 `finished` · 用了 3/8 步、2/12 次工具调用

**回答**：知识库中没有找到与该问题相关的制度或说明，无法作答。

**资料缺口**：未检索到与“WFH 要先申请什么？”相关的文档

**预期检查**：通过
- [x] status：实际 insufficient_evidence，期望 ['insufficient_evidence']
