"""Provider-neutral types. Messages use the OpenAI chat format as the canonical form."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:  # Python 3.8+
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore


class LLMError(RuntimeError):
    """The model call itself failed (network, auth, quota, malformed response)."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str = ""
    parse_error: Optional[str] = None


@dataclass
class LLMReply:
    tool_calls: List[ToolCall]
    content: str
    assistant_message: Dict[str, Any]
    usage: Dict[str, int] = field(default_factory=dict)


class LLM(Protocol):
    provider: str
    model: str

    def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMReply:
        ...


def assistant_message(content: str, calls: List[ToolCall]) -> Dict[str, Any]:
    message: Dict[str, Any] = {"role": "assistant", "content": content or ""}
    if calls:
        message["tool_calls"] = [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.raw_arguments}}
            for call in calls
        ]
    return message
