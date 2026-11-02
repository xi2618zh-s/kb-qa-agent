"""Command-line entry: ask / chat / run-cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

from .agent import AgentResult, Limits, run_agent
from .cases import load_cases, run_repeated, run_suite
from .config import DEFAULT_DOCS_DIR, ROOT, Settings, make_llm
from .docs import DocumentError, load_knowledge_base
from .llm.base import LLMError
from .tools import FailureInjector, ToolBox
from .trace import render_turn


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=["mock", "openai"], help="默认读取 LLM_PROVIDER，未设置时为 mock")
    parser.add_argument("--max-steps", type=int, default=8, help="每轮最多调用模型的次数（默认 8）")
    parser.add_argument("--max-tool-calls", type=int, default=12, help="每轮最多业务工具调用次数（默认 12）")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--overlay-dir", type=Path, help="叠加目录，同 doc_id 的文档会替换 docs-dir 中的版本")
    parser.add_argument("--exclude-docs", default="", help="逗号分隔，临时移除的文档 ID，如 D02")
    parser.add_argument(
        "--fail", action="append", default=[], help="故障注入，如 search_docs:once、read_doc:2、*:always，可重复"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb-agent", description="带引用和冲突处理的企业知识问答 Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="问一个问题")
    ask.add_argument("question")
    ask.add_argument("--history", type=Path, help="JSON 文件：[{\"role\": \"user\"|\"assistant\", \"content\": ...}]")
    ask.add_argument("--json", action="store_true", help="输出完整 JSON（含 trace）")
    ask.add_argument("--save", type=Path, help="把结果和 trace 写入该 JSON 文件")
    _common(ask)

    chat = sub.add_parser("chat", help="多轮对话（输入空行退出）")
    _common(chat)

    cases = sub.add_parser("run-cases", help="运行验收用例并写入运行记录")
    cases.add_argument("--cases", type=Path, default=ROOT / "examples" / "cases.json")
    cases.add_argument("--only", default="", help="逗号分隔的用例 ID 或前缀，如 C03,C08")
    cases.add_argument("--out", type=Path, help="输出目录，默认 examples/runs/<模型名>（重复运行时为其下的 stability/）")
    cases.add_argument("--repeat", type=int, default=1, help="每个用例独立运行的次数，大于 1 时生成稳定性汇总")
    cases.add_argument("--provider", choices=["mock", "openai"])
    return parser


def _print_result(question: str, result: AgentResult) -> None:
    print("\n".join(render_turn({"question": question, "result": result.to_dict()})))


def _setup(args: argparse.Namespace):
    settings = Settings.load()
    llm = make_llm(settings, args.provider)
    exclude = [item.strip() for item in args.exclude_docs.split(",") if item.strip()]
    kb = load_knowledge_base(args.docs_dir, args.overlay_dir, exclude)
    limits = Limits(max_steps=args.max_steps, max_tool_calls=args.max_tool_calls)
    return llm, kb, FailureInjector(args.fail), limits


def _cmd_ask(args: argparse.Namespace) -> int:
    llm, kb, failures, limits = _setup(args)
    history: List[Dict[str, str]] = []
    if args.history:
        history = json.loads(args.history.read_text(encoding="utf-8"))
    result = run_agent(args.question, llm=llm, toolbox=ToolBox(kb, failures), history=history, limits=limits)
    payload: Dict[str, Any] = {
        "question": args.question,
        "provider": llm.provider,
        "model": llm.model,
        "result": result.to_dict(include_transcript=True),
    }
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        payload["result"].pop("transcript")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_result(args.question, result)
    return 0 if result.status not in ("llm_error",) else 2


def _cmd_chat(args: argparse.Namespace) -> int:
    llm, kb, failures, limits = _setup(args)
    history: List[Dict[str, str]] = []
    print(f"模型：{llm.provider}/{llm.model}。输入问题，空行退出。")
    while True:
        try:
            question = input("\n你：").strip()
        except EOFError:
            break
        if not question:
            break
        result = run_agent(question, llm=llm, toolbox=ToolBox(kb, failures), history=history, limits=limits)
        _print_result(question, result)
        history += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": result.history_summary()},
        ]
    return 0


def _cmd_run_cases(args: argparse.Namespace) -> int:
    settings = Settings.load()
    llm = make_llm(settings, args.provider)
    only = [item.strip() for item in args.only.split(",") if item.strip()]
    cases = load_cases(args.cases, only)
    if not cases:
        print("没有匹配的用例", file=sys.stderr)
        return 1
    label = "mock" if llm.provider == "mock" else re.sub(r"[^A-Za-z0-9._-]+", "-", llm.model)
    if args.repeat > 1:
        out_dir = args.out or ROOT / "examples" / "runs" / label / "stability"
        print(f"运行 {len(cases)} 个用例 × {args.repeat} 次，模型 {llm.provider}/{llm.model}，输出到 {out_dir}")
        runs_by_case = run_repeated(cases, llm, out_dir, args.repeat)
        for runs in runs_by_case:
            statuses = " / ".join(run["turns"][-1]["result"]["status"] for run in runs)
            passed = sum(1 for run in runs if run["passed"])
            print(f"  {passed}/{len(runs)}  {runs[0]['case_id']:<36} {statuses}")
        unstable = [runs[0]["case_id"] for runs in runs_by_case if not all(run["passed"] for run in runs)]
        print(f"每次都通过 {len(runs_by_case) - len(unstable)}/{len(runs_by_case)}")
        return 1 if unstable else 0
    out_dir = args.out or ROOT / "examples" / "runs" / label
    print(f"运行 {len(cases)} 个用例，模型 {llm.provider}/{llm.model}，输出到 {out_dir}")
    records = run_suite(cases, llm, out_dir)
    for record in records:
        statuses = " -> ".join(turn["result"]["status"] for turn in record["turns"])
        print(f"  {'PASS' if record['passed'] else 'FAIL'}  {record['case_id']:<36} {statuses}")
    failed = [record["case_id"] for record in records if not record["passed"]]
    print(f"通过 {len(records) - len(failed)}/{len(records)}")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    handlers = {"ask": _cmd_ask, "chat": _cmd_chat, "run-cases": _cmd_run_cases}
    try:
        return handlers[args.command](args)
    except (LLMError, DocumentError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
