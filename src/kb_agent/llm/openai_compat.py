"""Any OpenAI-compatible chat-completions endpoint (DeepSeek, Qwen/DashScope, ...)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import LLMError, LLMReply, ToolCall, assistant_message


class OpenAICompatLLM:
    provider = "openai"

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        client: Any = None,
    ):
        self.model = model
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise LLMError("未安装 openai 包，请先运行 pip install -r requirements.txt") from exc
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2)
        self._client = client

    def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMReply:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[{"type": "function", "function": spec} for spec in tools],
                tool_choice="auto",
                temperature=0,
            )
        except Exception as exc:  # the SDK already retried transient errors
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        if not getattr(response, "choices", None):
            raise LLMError("模型返回中没有 choices")

        message = response.choices[0].message
        calls: List[ToolCall] = []
        for item in message.tool_calls or []:
            raw = item.function.arguments or "{}"
            try:
                arguments = json.loads(raw)
                error = None if isinstance(arguments, dict) else "参数必须是 JSON 对象"
            except json.JSONDecodeError as exc:
                arguments, error = {}, str(exc)
            calls.append(
                ToolCall(
                    id=item.id,
                    name=item.function.name,
                    arguments=arguments if isinstance(arguments, dict) else {},
                    raw_arguments=raw,
                    parse_error=error,
                )
            )
        usage: Dict[str, int] = {}
        if getattr(response, "usage", None) is not None:
            usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
            }
        content = message.content or ""
        return LLMReply(tool_calls=calls, content=content, assistant_message=assistant_message(content, calls), usage=usage)
