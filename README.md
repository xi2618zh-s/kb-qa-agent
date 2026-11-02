# 冲突感知的企业知识问答 Agent

> Conflict-aware knowledge-base QA agent: a model-driven ReAct loop over search / read tools, with code-enforced citation checks, conflict handling and step limits.

**企业知识问答 Agent。** 帮助员工从制度和产品 FAQ 中找到有原文依据的答案。资料冲突、资料缺失或工具故障时，Agent 会明确说明，不编造答案。

每一步做什么由模型决定：模型选择检索、读取原文、改写查询或结束，程序执行工具，模型看到结果后再决定下一步。程序负责校验：引用必须是本轮读过的原文；报冲突时必须拿出两份文档；答案里的数字必须有出处；步数有上限。

## 评审入口

| 想看什么 | 去哪里 |
|---|---|
| 验收用例（输入和预期） | [examples/cases.json](examples/cases.json) |
| 真实模型运行记录（步骤、参数、返回摘要、决策依据） | [examples/runs/deepseek-chat/summary.md](examples/runs/deepseek-chat/summary.md) |
| 稳定性（每个用例跑 3 次） | [examples/runs/deepseek-chat/stability/summary.md](examples/runs/deepseek-chat/stability/summary.md) |
| v1 基线和 v2 改进前后对比 | [docs/03-evaluation.md#v2-改进前后对比](docs/03-evaluation.md#v2-改进前后对比) |
| 离线 Mock 运行记录 | [examples/runs/mock/summary.md](examples/runs/mock/summary.md) |
| 测试结果 | [examples/test_results.txt](examples/test_results.txt) |
| 需求、方案、评估、AI 使用、复盘 | [docs/](docs/) |
| 决策循环和校验代码 | [src/kb_agent/agent.py](src/kb_agent/agent.py) |

## 环境与安装

需要 Python 3.9 及以上。离线 Mock 只用标准库，**不装任何依赖也能运行**。

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

macOS / Linux 把 `.venv/Scripts/python` 换成 `.venv/bin/python`。下面的命令统一写 `python`，在虚拟环境里请用上面的完整路径（这样不需要 activate，可以避开 PowerShell 执行策略的问题）。

## 配置

不配置任何变量时默认使用离线 Mock。要用真实模型，把 [.env.example](.env.example) 复制为 `.env` 并填写：

| 变量 | 说明 |
|---|---|
| `LLM_PROVIDER` | `openai`（任意 OpenAI 兼容接口）或 `mock` |
| `LLM_API_KEY` | 模型服务的 key（`.env` 已在 `.gitignore` 中，不会被提交） |
| `LLM_BASE_URL` | DeepSeek 为 `https://api.deepseek.com`；通义千问为 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | 如 `deepseek-chat`、`qwen-plus` |
| `LLM_TIMEOUT` | 单次请求超时，单位秒，默认 60 |

## 运行

问一个问题（离线）：

```bash
python main.py ask "报销期限是多久？" --provider mock
```

用真实模型（需要先配置 `.env`）：

```bash
python main.py ask "报销期限是多久？" --provider openai
```

多轮对话，可以接着追问，空行退出：

```bash
python main.py chat --provider openai
```

跑全部验收用例，运行记录写到 `examples/runs/<模型名>/`：

```bash
python main.py run-cases --provider openai
```

每个用例独立跑 3 次，统计稳定性，结果写到 `examples/runs/<模型名>/stability/`：

```bash
python main.py run-cases --provider openai --repeat 3
```

只跑部分用例：

```bash
python main.py run-cases --provider mock --only C03,C08
```

### 常用参数

| 参数 | 作用 |
|---|---|
| `--fail search_docs:once` | 故障注入。格式为 `工具:once\|always\|N`，`*` 表示所有工具，可以重复写多个 |
| `--max-steps 2` | 每轮最多调用模型的次数，默认 8；达到上限返回 `incomplete` |
| `--max-tool-calls N` | 每轮最多业务工具调用次数，默认 12 |
| `--exclude-docs D02` | 临时移除文档 |
| `--overlay-dir data/variants/d02_scoped` | 用目录中的同 ID 文档替换原文档 |
| `--docs-dir DIR` | 换一个知识库目录 |
| `--history FILE` | `ask` 时传入对话历史 JSON |
| `--json` / `--save FILE` | 输出或保存完整 JSON（含 trace） |

### 替换文档、观察答案变化

文档就是 `data/docs/` 下的 Markdown 文件，每次运行都会重新读取，不需要重建索引。把 D01 的"30 天"改成别的数字，或执行下面的命令，可以看到答案和动作的变化：

```bash
python main.py ask "报销期限是多久？" --exclude-docs D02
```

```bash
python main.py ask "报销期限是多久？" --overlay-dir data/variants/d02_scoped
```

## 测试

```bash
python -m pytest
```

共 47 个离线测试，不访问网络，覆盖：

- 文档解析和检索；
- 循环与校验：引用、数字、冲突、追问、部分可答、步数上限、工具失败不自动重试、协议错误；
- 15 个验收用例（用 Mock 跑）；
- 修改文档后答案随之改变；
- 适配器（用假客户端）和命令行入口。

## 目录

```text
src/kb_agent/        代码：agent.py（循环与校验）、tools.py、retrieval.py、docs.py、prompts.py、llm/
tests/               离线测试
data/docs/           合成知识库（D01–D07）；data/variants/ 是文档变体
examples/cases.json  15 个验收用例
examples/runs/       每个用例的输入、输出和 trace（.md 方便阅读，.json 是完整数据）
                     deepseek-chat/ 是最终版（v2.3）；deepseek-chat-v1/、-v2.0/、-v2.1/、-v2.2/ 是改进过程中的记录
docs/                01 需求 · 02 方案 · 03 评估 · 04 AI 使用 · 05 复盘
```

## 边界与限制

- **离线 Mock 只验证流程。** 它是读取工具结果的启发式规则，不代表真实模型的决策效果：做不了语义改写（C07），也读不懂适用范围（C12）和替代关系（C14）。
- 检索是字面匹配（BM25 + 中文字二元组），同义词要靠模型改写查询。知识库只有 7 份合成文档。
- 文档冲突由模型判断，程序只保证"报冲突时必须引用两份文档的原文"。
- 数字校验只检查阿拉伯数字和带单位的中文数字（"三年""四十五天"）。"分三档""两种情况"这类不带单位的计数不检查。推导出的数字（如"0 天"）会被有意退回，每次多花 1 步。
- 更多限制和失败情况见 [docs/03-evaluation.md](docs/03-evaluation.md)。

## 结果一览

| 验证 | 结果 |
|---|---|
| 离线测试 | 47/47 通过 |
| 15 个用例 · 离线 Mock | 15/15 符合预期（只验证流程） |
| 15 个用例 · DeepSeek `deepseek-chat` | 15/15 通过 |
| 稳定性 · 15 个用例 × 3 次 | 45/45 次通过，每个用例 3/3 |
| v1 → v2 | 持续失败时的检索次数 5 → 2；冲突追问改为列出选项；部分可答不再在两种状态间摇摆；3 次重复运行中 `finish` 被退回的次数从 10 次降到 1 次，校验误判从 4 次降到 0 次；回答字数约减少 8–9%（效果有限）。详见 [03-evaluation.md](docs/03-evaluation.md#v2-改进前后对比) |

## 用时与完成情况

- **用时**（2026-11-02，AI 辅助）：
  - v1：16:24 开始，17:15 完成代码、测试、离线和真实模型运行记录及文档初稿，约 50 分钟，不含等待配置 API key 的时间；
  - v2.0 和 v2.1：约 18:25–18:50，约 25 分钟；
  - v2.2：约 18:50–19:05，约 15 分钟，修正条款引用和句中序号后重跑；
  - v2.3：约 23:15–23:35，约 20 分钟，加入中文数字换算后重跑；
  - 每一版都包括"完整运行 + 3 次稳定性运行"。

- **已完成**：题目要求的全部验收点、步数上限、替换文档验证、离线 Mock 入口、真实模型运行记录、稳定性评估、docs/01–05。

