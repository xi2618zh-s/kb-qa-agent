"""Render run records as Markdown for human review (JSON is written alongside)."""

from __future__ import annotations

import json
from typing import Any, Dict, List

_STATUS_LABEL = {
    "answered": "已回答",
    "conflict_needs_confirmation": "文档冲突，待用户确认",
    "need_clarification": "需要追问",
    "insufficient_evidence": "资料不足",
    "tool_error": "工具故障",
    "incomplete": "未完成（达到上限）",
    "llm_error": "模型调用失败",
}


def _cell(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_turn(turn: Dict[str, Any]) -> List[str]:
    result = turn["result"]
    lines = [f"**问题**：{turn['question']}", ""]
    lines += [
        "| 步 | 动作 | 参数 | 决策依据（模型给出的 reason） | 返回摘要 | 后续动作 |",
        "|---|---|---|---|---|---|",
    ]
    for entry in result["trace"]:
        lines.append(
            f"| {entry['step']} | `{entry['action']}` | {_cell(entry.get('arguments', {}))} | "
            f"{_cell(entry.get('reason', ''))} | {_cell(entry.get('observation', ''), 220)} | "
            f"`{entry.get('next_action', '')}` |"
        )
    limits = result["limits"]
    lines += [
        "",
        f"**结果**：`{result['status']}`（{_STATUS_LABEL.get(result['status'], '')}） · 结束原因 `{result['stop_reason']}` · "
        f"用了 {result['steps_used']}/{limits['max_steps']} 步、{result['tool_calls_used']}/{limits['max_tool_calls']} 次工具调用",
        "",
        f"**回答**：{result['answer'] or '（无）'}",
    ]
    if result["citations"]:
        lines.append("")
        lines.append("**引用**：")
        for item in result["citations"]:
            lines.append(f"- {item['doc_id']}《{item['title']}》（{item['version_date']}）：“{item['quote']}”")
    if result["clarification_question"]:
        lines += ["", f"**待确认**：{result['clarification_question']}"]
    if result["gaps"]:
        lines += ["", "**资料缺口**：" + "；".join(result["gaps"])]
    if result.get("error"):
        lines += ["", f"**错误**：{result['error']}"]
    checks = turn.get("checks", [])
    if checks:
        lines += ["", "**预期检查**：" + ("通过" if turn.get("passed") else "未通过")]
        for check in checks:
            lines.append(f"- [{'x' if check['passed'] else ' '}] {check['name']}：{check['detail']}")
    return lines


def render_case(record: Dict[str, Any]) -> str:
    lines = [
        f"# {record['case_id']}",
        "",
        f"- 验收点：{'、'.join(record.get('acceptance', []))}",
        f"- 说明：{record.get('description', '')}",
        f"- 模型：`{record['provider']}` / `{record['model']}`",
        f"- 运行选项：`{json.dumps(record.get('options', {}), ensure_ascii=False)}`",
        f"- 生成时间：{record['generated_at']}",
        f"- 结论：{'通过' if record['passed'] else '未通过'}",
    ]
    for index, turn in enumerate(record["turns"], 1):
        lines += ["", f"## 第 {index} 轮", ""]
        lines += render_turn(turn)
    return "\n".join(lines) + "\n"


def suite_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate behaviour metrics over every turn of every record."""
    turns = [turn["result"] for record in records for turn in record["turns"]]
    answered = [r for r in turns if r["status"] in ("answered", "conflict_needs_confirmation")]
    prompt_tokens = completion_tokens = 0
    for result in turns:
        seen_steps = set()
        for entry in result["trace"]:
            if entry["step"] in seen_steps:
                continue  # parallel calls in one step share one model response
            seen_steps.add(entry["step"])
            usage = entry.get("usage") or {}
            prompt_tokens += usage.get("prompt_tokens", 0)
            completion_tokens += usage.get("completion_tokens", 0)

    def mean(values: List[float]) -> float:
        return round(sum(values) / len(values), 1) if values else 0.0

    return {
        "turns": len(turns),
        "model_calls": sum(r["steps_used"] for r in turns),
        "avg_steps": mean([r["steps_used"] for r in turns]),
        "avg_tool_calls": mean([r["tool_calls_used"] for r in turns]),
        "avg_answer_chars": mean([len(r["answer"]) for r in answered]),
        "avg_citations": mean([len(r["citations"]) for r in answered]),
        "finish_rejections": sum(
            1 for r in turns for e in r["trace"] if e["action"] == "finish" and not e.get("ok")
        ),
        "failed_tool_calls": sum(
            1 for r in turns for e in r["trace"] if e["action"] in ("search_docs", "read_doc") and not e.get("ok")
        ),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def render_metrics(metrics: Dict[str, Any]) -> List[str]:
    return [
        "| 指标 | 值 |",
        "|---|---|",
        f"| 轮次 / 模型调用次数 | {metrics['turns']} / {metrics['model_calls']} |",
        f"| 每轮平均步数 / 工具调用 | {metrics['avg_steps']} / {metrics['avg_tool_calls']} |",
        f"| 回答平均字数（answered 与冲突） | {metrics['avg_answer_chars']} |",
        f"| 每条回答平均引用数 | {metrics['avg_citations']} |",
        f"| finish 被退回次数 | {metrics['finish_rejections']} |",
        f"| 失败的工具调用（含注入故障） | {metrics['failed_tool_calls']} |",
        f"| 输入 / 输出 token | {metrics['prompt_tokens']} / {metrics['completion_tokens']} |",
    ]


def render_summary(records: List[Dict[str, Any]], title: str) -> str:
    passed = sum(1 for record in records if record["passed"])
    lines = [
        f"# {title}",
        "",
        f"通过 {passed}/{len(records)} 个用例。每个用例的步骤、参数、返回摘要和决策依据见同目录下的 `<用例ID>.md`，完整数据（含发给模型的消息）见 `<用例ID>.json`。",
        "",
        *render_metrics(suite_metrics(records)),
        "",
        "| 用例 | 验收点 | 各轮状态 | 步数 | 结论 |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        statuses = " → ".join(f"`{turn['result']['status']}`" for turn in record["turns"])
        steps = " / ".join(str(turn["result"]["steps_used"]) for turn in record["turns"])
        lines.append(
            f"| [{record['case_id']}]({record['case_id']}.md) | {'、'.join(record.get('acceptance', []))} | "
            f"{statuses} | {steps} | {'通过' if record['passed'] else '未通过'} |"
        )
    return "\n".join(lines) + "\n"


def render_stability(runs_by_case: List[List[Dict[str, Any]]], title: str) -> str:
    flat = [record for runs in runs_by_case for record in runs]
    repeat = len(runs_by_case[0]) if runs_by_case else 0
    stable = sum(1 for runs in runs_by_case if all(record["passed"] for record in runs))
    lines = [
        f"# {title}",
        "",
        f"每个用例独立运行 {repeat} 次。{stable}/{len(runs_by_case)} 个用例每次都通过；"
        f"总计 {sum(1 for r in flat if r['passed'])}/{len(flat)} 次通过。每次运行的完整 trace 见 `<用例ID>.md`。",
        "",
        *render_metrics(suite_metrics(flat)),
        "",
        "| 用例 | 通过次数 | 各次最终状态 | 各次步数 |",
        "|---|---|---|---|",
    ]
    for runs in runs_by_case:
        statuses = " / ".join(f"`{record['turns'][-1]['result']['status']}`" for record in runs)
        steps = " / ".join("+".join(str(t["result"]["steps_used"]) for t in record["turns"]) for record in runs)
        passed = sum(1 for record in runs if record["passed"])
        case_id = runs[0]["case_id"]
        lines.append(f"| [{case_id}]({case_id}.md) | {passed}/{len(runs)} | {statuses} | {steps} |")
    return "\n".join(lines) + "\n"
