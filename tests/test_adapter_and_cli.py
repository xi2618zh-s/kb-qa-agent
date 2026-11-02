"""OpenAI-compatible adapter (with a fake client, no network) and the CLI entry point."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from kb_agent.agent import run_agent
from kb_agent.llm.base import LLMError
from kb_agent.llm.openai_compat import OpenAICompatLLM
from kb_agent.tools import TOOL_SPECS, ToolBox

ROOT = Path(__file__).resolve().parents[1]


def _response(name, arguments, call_id="call_1"):
    call = SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))
    message = SimpleNamespace(content=None, tool_calls=[call])
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        # Snapshot like a real client that serialises the request at call time.
        self.requests.append({**kwargs, "messages": [dict(m) for m in kwargs.get("messages", [])]})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(responses):
    completions = FakeCompletions(responses)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_adapter_sends_tools_and_parses_tool_calls():
    client, completions = _client([_response("search_docs", '{"query": "报销期限", "reason": "先检索"}')])
    llm = OpenAICompatLLM(model="deepseek-chat", client=client)
    reply = llm.complete([{"role": "user", "content": "q"}], TOOL_SPECS)

    request = completions.requests[0]
    assert request["model"] == "deepseek-chat" and request["tool_choice"] == "auto"
    assert [tool["function"]["name"] for tool in request["tools"]] == ["search_docs", "read_doc", "finish"]
    assert reply.tool_calls[0].arguments == {"query": "报销期限", "reason": "先检索"}
    assert reply.assistant_message["tool_calls"][0]["id"] == "call_1"
    assert reply.usage == {"prompt_tokens": 100, "completion_tokens": 20}


def test_adapter_reports_bad_json_and_api_errors():
    client, _ = _client([_response("read_doc", "{oops"), RuntimeError("401 invalid key")])
    llm = OpenAICompatLLM(model="m", client=client)
    assert llm.complete([], TOOL_SPECS).tool_calls[0].parse_error
    with pytest.raises(LLMError, match="401"):
        llm.complete([], TOOL_SPECS)


def test_agent_runs_through_the_adapter(kb):
    quote = "员工应在费用发生之日起 30 天内通过 OA 系统提交报销申请。"
    finish = {
        "status": "answered",
        "answer": "30 天内提交。",
        "citations": [{"doc_id": "D01", "quote": quote}],
        "gaps": [],
        "reason": "D01 原文给出期限",
    }
    client, completions = _client(
        [
            _response("read_doc", '{"doc_id": "D01", "reason": "读原文"}', "c1"),
            _response("finish", json.dumps(finish, ensure_ascii=False), "c2"),
        ]
    )
    result = run_agent("报销期限是多久？", llm=OpenAICompatLLM(model="m", client=client), toolbox=ToolBox(kb))
    assert result.status == "answered"
    second = completions.requests[1]["messages"]
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"
    assert second[-2]["tool_calls"][0]["function"]["name"] == "read_doc"


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "main.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=120,
    )


def test_cli_ask_with_mock_outputs_json():
    proc = _run_cli("ask", "报销期限是多久？", "--provider", "mock", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["result"]["status"] == "conflict_needs_confirmation"
    assert payload["result"]["trace"][0]["action"] == "search_docs"


def test_cli_run_cases_writes_records(tmp_path):
    proc = _run_cli("run-cases", "--provider", "mock", "--only", "C01,C09", "--out", str(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert {path.name for path in tmp_path.iterdir()} >= {"C01_clear_answer.json", "C01_clear_answer.md", "summary.md"}
    record = json.loads((tmp_path / "C09_tool_failure_persistent.json").read_text(encoding="utf-8"))
    assert record["turns"][0]["result"]["status"] == "tool_error"
    assert "finish 被退回次数" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_cli_repeat_writes_stability_summary(tmp_path):
    proc = _run_cli("run-cases", "--provider", "mock", "--only", "C03", "--repeat", "2", "--out", str(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    runs = json.loads((tmp_path / "C03_conflict.json").read_text(encoding="utf-8"))
    assert len(runs) == 2 and all(run["passed"] for run in runs)
    assert "| [C03_conflict](C03_conflict.md) | 2/2 |" in (tmp_path / "summary.md").read_text(encoding="utf-8")
