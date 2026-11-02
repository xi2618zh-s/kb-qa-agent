"""Run the acceptance cases in examples/cases.json and check each turn against its expectations."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .agent import AgentResult, Limits, run_agent
from .config import DEFAULT_DOCS_DIR, ROOT
from .docs import load_knowledge_base
from .llm.base import LLM
from .tools import FailureInjector, ToolBox
from .trace import render_case, render_stability, render_summary


def check_expectations(result: AgentResult, expect: Dict[str, Any]) -> List[Dict[str, Any]]:
    cited = sorted({item.doc_id for item in result.citations})
    answer = result.answer
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    if "status" in expect:
        add("status", result.status in expect["status"], f"实际 {result.status}，期望 {expect['status']}")
    if "stop_reason" in expect:
        add("stop_reason", result.stop_reason == expect["stop_reason"], f"实际 {result.stop_reason}")
    if "cited_docs_include" in expect:
        missing = [doc for doc in expect["cited_docs_include"] if doc not in cited]
        add("引用包含", not missing, f"实际引用 {cited}，缺少 {missing}" if missing else f"实际引用 {cited}")
    if "cited_docs_exclude" in expect:
        extra = [doc for doc in expect["cited_docs_exclude"] if doc in cited]
        add("引用不含", not extra, f"实际引用 {cited}")
    if "answer_contains_any" in expect:
        found = [word for word in expect["answer_contains_any"] if word in answer]
        add("回答包含其一", bool(found), f"期望含 {expect['answer_contains_any']} 之一，找到 {found}")
    if "answer_contains_all" in expect:
        missing = [word for word in expect["answer_contains_all"] if word not in answer]
        add("回答包含全部", not missing, f"缺少 {missing}" if missing else "全部包含")
    if expect.get("gaps_nonempty"):
        add("资料缺口非空", bool(result.gaps), f"{len(result.gaps)} 条")
    if expect.get("no_citations"):
        add("无引用", not result.citations, f"实际引用 {cited}")
    return checks


def run_case(case: Dict[str, Any], llm: LLM, docs_dir: Path = DEFAULT_DOCS_DIR) -> Dict[str, Any]:
    options = case.get("options", {})
    overlay = options.get("overlay_dir")
    kb = load_knowledge_base(docs_dir, ROOT / overlay if overlay else None, options.get("exclude_docs", []))
    failures = FailureInjector(options.get("fail", []))
    limits = Limits(max_steps=options.get("max_steps", 8), max_tool_calls=options.get("max_tool_calls", 12))

    history: List[Dict[str, str]] = []
    turns: List[Dict[str, Any]] = []
    for turn in case["turns"]:
        result = run_agent(turn["question"], llm=llm, toolbox=ToolBox(kb, failures), history=history, limits=limits)
        use_mock = llm.provider == "mock" and "expect_mock" in turn
        expect = turn["expect_mock"] if use_mock else turn.get("expect", {})
        checks = check_expectations(result, expect)
        turns.append(
            {
                "question": turn["question"],
                "history_in": list(history),
                "expect": expect,
                "expect_source": "expect_mock" if use_mock else "expect",
                "checks": checks,
                "passed": all(check["passed"] for check in checks),
                "result": result.to_dict(include_transcript=True),
            }
        )
        history += [
            {"role": "user", "content": turn["question"]},
            {"role": "assistant", "content": result.history_summary()},
        ]
    return {
        "case_id": case["id"],
        "acceptance": case.get("acceptance", []),
        "description": case.get("description", ""),
        "provider": llm.provider,
        "model": llm.model,
        "options": options,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "passed": all(turn["passed"] for turn in turns),
        "turns": turns,
    }


def load_cases(path: Path, only: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if only:
        wanted = set(only)
        cases = [case for case in cases if case["id"] in wanted or case["id"].split("_")[0] in wanted]
    return cases


def run_suite(cases: List[Dict[str, Any]], llm: LLM, out_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    records = []
    for case in cases:
        record = run_case(case, llm)
        records.append(record)
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{case['id']}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (out_dir / f"{case['id']}.md").write_text(render_case(record), encoding="utf-8")
    if out_dir is not None and records:
        title = f"运行汇总：{llm.provider} / {llm.model}"
        existing = {path.stem for path in out_dir.glob("C*.json")}
        if existing - {record["case_id"] for record in records}:
            # Partial rerun: rebuild the summary from every record in the directory.
            records_for_summary = [
                json.loads(path.read_text(encoding="utf-8")) for path in sorted(out_dir.glob("C*.json"))
            ]
        else:
            records_for_summary = records
        (out_dir / "summary.md").write_text(render_summary(records_for_summary, title), encoding="utf-8")
    return records


def run_repeated(
    cases: List[Dict[str, Any]], llm: LLM, out_dir: Path, repeat: int
) -> List[List[Dict[str, Any]]]:
    """Run every case `repeat` times to measure how stable the model's decisions are."""
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_by_case = []
    for case in cases:
        runs = [run_case(case, llm) for _ in range(repeat)]
        runs_by_case.append(runs)
        (out_dir / f"{case['id']}.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        parts = [f"<!-- 第 {index} 次运行 -->\n{render_case(run)}" for index, run in enumerate(runs, 1)]
        (out_dir / f"{case['id']}.md").write_text("\n---\n\n".join(parts), encoding="utf-8")
    title = f"稳定性：{llm.provider} / {llm.model} × {repeat}"
    (out_dir / "summary.md").write_text(render_stability(runs_by_case, title), encoding="utf-8")
    return runs_by_case
