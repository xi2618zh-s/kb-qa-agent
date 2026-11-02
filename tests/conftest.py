from pathlib import Path
import json
import sys
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kb_agent.config import DEFAULT_DOCS_DIR  # noqa: E402
from kb_agent.docs import load_knowledge_base  # noqa: E402
from kb_agent.llm.base import LLMReply, ToolCall, assistant_message  # noqa: E402


@pytest.fixture
def kb():
    return load_knowledge_base(DEFAULT_DOCS_DIR)


class ScriptedLLM:
    """Replays a fixed list of actions and records what the model would have seen.

    Each script item is (tool_name, arguments), ("<text>", content) for a reply with
    no tool call, or ("<raw>", tool_name, raw_json) for unparsable arguments.
    """

    provider = "scripted"
    model = "scripted"

    def __init__(self, script: List[Any]):
        self.script = list(script)
        self.seen: List[List[Dict[str, Any]]] = []

    def complete(self, messages, tools):
        self.seen.append([dict(message) for message in messages])
        if not self.script:
            raise AssertionError("script exhausted")
        item = self.script.pop(0)
        if item[0] == "<text>":
            return LLMReply(tool_calls=[], content=item[1], assistant_message=assistant_message(item[1], []))
        if item[0] == "<raw>":
            call = ToolCall(id=f"s{len(self.seen)}", name=item[1], arguments={}, raw_arguments=item[2], parse_error="bad json")
        else:
            name, args = item
            call = ToolCall(
                id=f"s{len(self.seen)}", name=name, arguments=args, raw_arguments=json.dumps(args, ensure_ascii=False)
            )
        return LLMReply(tool_calls=[call], content="", assistant_message=assistant_message("", [call]))

    def observations(self) -> List[Dict[str, Any]]:
        """Tool results the model received, in order (from the last recorded request)."""
        if not self.seen:
            return []
        return [json.loads(m["content"]) for m in self.seen[-1] if m["role"] == "tool"]


@pytest.fixture
def scripted():
    return ScriptedLLM
