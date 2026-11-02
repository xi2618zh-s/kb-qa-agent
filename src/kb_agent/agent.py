"""The decision loop: model picks an action -> code executes it -> model sees the observation.

The code never decides what to do next. It only executes tools, enforces the step
and tool-call limits, and rejects a `finish` whose citations or status do not hold
up, sending the reasons back so the model can correct itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
import time
from typing import Any, Dict, List, Optional, Set
import unicodedata

from .llm.base import LLM, LLMError, ToolCall
from .prompts import PROTOCOL_REMINDER, build_messages
from .tools import FINISH_STATUSES, TOOL_SPECS, ToolBox, summarize_observation

_MAX_QUOTE_CHARS = 300
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# Structural numbers are not facts: document / section ids (D01, D01-S2, S2) and list markers.
_DOC_REF = re.compile(r"(?<![A-Za-z0-9])(?:D\d+(?:-S\d+)?|S\d+)(?![0-9])", re.IGNORECASE)
# Clause references such as "第 2 条" / "第 1 节" point at document structure, not facts.
_CLAUSE_REF = re.compile(r"第\s*\d+\s*[条节款章段项]")
# List markers at line start or right after whitespace / punctuation ("：1. 《…》"); not decimals.
_LIST_MARKER = re.compile(r"(?m)(?:^|(?<=[\s：:；;。，,、]))[(（]?\d+[.、)）](?!\d)")
# Chinese numerals count only as quantities followed by a unit ("三年", "十五天"), so words such as
# "一般", "两份文档" or "分三档" are left alone.
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_CN_QUANTITY = re.compile(r"([零〇一二两三四五六七八九十百千]+)(?=\s*(?:个工作日|工作日|个月|小时|分钟|天|日|周|月|年|元|岁|位|倍))")
# Enclosed numerals (①, ⑵, ❶ ...) are list markers too; NFKC would otherwise turn them into digits.
_ENCLOSED = re.compile(r"[①-⓿❶-➓㉑-㉟㊱-㊿]")


@dataclass
class Limits:
    max_steps: int = 8
    max_tool_calls: int = 12


@dataclass
class Citation:
    doc_id: str
    title: str
    version_date: str
    quote: str


@dataclass
class AgentResult:
    status: str
    answer: str
    citations: List[Citation]
    gaps: List[str]
    clarification_question: str
    stop_reason: str
    steps_used: int
    tool_calls_used: int
    limits: Limits
    trace: List[Dict[str, Any]] = field(default_factory=list)
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self, include_transcript: bool = False) -> Dict[str, Any]:
        data = asdict(self)
        if not include_transcript:
            data.pop("transcript")
        return data

    def history_summary(self) -> str:
        """How this turn is shown to the model in the next turn's history."""
        lines = [f"[{self.status}] {self.answer}".strip()]
        if self.clarification_question:
            lines.append(f"待确认：{self.clarification_question}")
        for item in self.citations:
            lines.append(f"引用 {item.doc_id}《{item.title}》({item.version_date})：{item.quote}")
        return "\n".join(lines)


@dataclass
class FinishCheck:
    problems: List[str]
    citations: List[Citation]


def _unescape_newlines(text: str) -> str:
    """Models sometimes double-escape newlines inside JSON, leaving a literal backslash-n."""
    return text.replace("\\r\\n", "\n").replace("\\n", "\n")


def _chinese_to_int(numeral: str) -> int:
    total = current = 0
    for char in numeral:
        if char in _CN_DIGITS:
            current = _CN_DIGITS[char]
        else:
            total += (current or 1) * _CN_UNITS[char]
            current = 0
    return total + current


def _numbers(text: str) -> Set[str]:
    text = _CN_QUANTITY.sub(lambda m: f" {_chinese_to_int(m.group(1))} ", _unescape_newlines(text))
    normalized = unicodedata.normalize("NFKC", _ENCLOSED.sub(" ", text))
    cleaned = _LIST_MARKER.sub(" ", _CLAUSE_REF.sub(" ", _DOC_REF.sub(" ", normalized)))
    return set(_NUMBER.findall(cleaned))


def check_finish(
    args: Dict[str, Any], toolbox: ToolBox, question: str, history: List[Dict[str, str]]
) -> FinishCheck:
    problems: List[str] = []
    status = args.get("status")
    if status not in FINISH_STATUSES:
        problems.append(f"status 必须是 {', '.join(FINISH_STATUSES)} 之一")
    answer = str(args.get("answer") or "").strip()
    clarification = str(args.get("clarification_question") or "").strip()
    gaps = args.get("gaps") or []
    if not isinstance(gaps, list):
        problems.append("gaps 必须是字符串数组")
        gaps = []

    raw = args.get("citations") or []
    if not isinstance(raw, list):
        problems.append("citations 必须是数组")
        raw = []
    citations: List[Citation] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            problems.append(f"第 {index} 条引用格式应为 {{doc_id, quote}}")
            continue
        doc_id = str(item.get("doc_id") or "").strip()
        quote = str(item.get("quote") or "").strip().strip("“”\"「」『』")
        doc = toolbox.kb.get(doc_id)
        if doc is None:
            problems.append(f"第 {index} 条引用的文档 {doc_id or '(空)'} 不存在")
        elif not quote:
            problems.append(f"第 {index} 条引用缺少 quote")
        elif len(quote) > _MAX_QUOTE_CHARS:
            problems.append(f"第 {index} 条引用超过 {_MAX_QUOTE_CHARS} 字，请只摘录支持回答的句子")
        elif not toolbox.was_read(doc_id, quote):
            problems.append(
                f"第 {index} 条引用不是 {doc_id} 已读取原文中的逐字片段；请先用 read_doc 读取，并逐字摘录（不要改写或加省略号）"
            )
        else:
            citations.append(Citation(doc_id, doc.title, doc.version_date, quote))

    cited_docs = {item.doc_id for item in citations}
    if status == "answered":
        if not answer:
            problems.append("answered 需要非空的 answer")
        if not citations:
            problems.append("answered 至少需要 1 条有效引用")
    elif status == "conflict_needs_confirmation":
        if len(cited_docs) < 2:
            problems.append("conflict_needs_confirmation 需要引用至少 2 份不同文档的原文")
        if not clarification:
            problems.append("conflict_needs_confirmation 需要在 clarification_question 中请用户确认适用的制度")
        else:
            unnamed = [
                item.doc_id
                for item in citations
                if item.doc_id not in clarification and item.title not in clarification
            ]
            if unnamed:
                problems.append(
                    f"clarification_question 要把可选的制度逐一列出（文档 ID 或标题），缺少 {', '.join(sorted(set(unnamed)))}"
                )
    elif status == "need_clarification":
        if not clarification:
            problems.append("need_clarification 需要填写 clarification_question")
    elif status in ("insufficient_evidence", "tool_error"):
        if not [gap for gap in gaps if str(gap).strip()]:
            problems.append(f"{status} 需要在 gaps 中说明缺少哪些资料")
        if raw:
            problems.append(
                f"{status} 不应附带引用：如果原文能回答问题的一部分，请改用 answered，并把缺失的部分写进 gaps"
            )

    if status in ("answered", "conflict_needs_confirmation") and citations:
        allowed = _numbers(question)
        for turn in history:
            allowed |= _numbers(turn.get("content", ""))
        for item in citations:
            allowed |= _numbers(item.quote) | _numbers(item.version_date)
        unsupported = sorted(_numbers(answer) - allowed, key=lambda value: float(value))
        if unsupported:
            problems.append(
                f"answer 中的数字 {', '.join(unsupported)} 在引用原文和用户问题中找不到；请补充对应引用或删除这些数字"
            )
    return FinishCheck(problems=problems, citations=citations)


def _tool_message(call_id: str, observation: Dict[str, Any]) -> Dict[str, Any]:
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(observation, ensure_ascii=False)}


def run_agent(
    question: str,
    *,
    llm: LLM,
    toolbox: ToolBox,
    history: Optional[List[Dict[str, str]]] = None,
    limits: Optional[Limits] = None,
) -> AgentResult:
    limits = limits or Limits()
    history = list(history or [])
    messages = build_messages(question, history, limits.max_steps)
    trace: List[Dict[str, Any]] = []
    tool_calls_used = 0

    def result(status: str, stop_reason: str, step: int, **fields: Any) -> AgentResult:
        for index, entry in enumerate(trace):
            entry["next_action"] = trace[index + 1]["action"] if index + 1 < len(trace) else "（结束）"
        return AgentResult(
            status=status,
            answer=fields.get("answer", ""),
            citations=fields.get("citations", []),
            gaps=fields.get("gaps", []),
            clarification_question=fields.get("clarification_question", ""),
            stop_reason=stop_reason,
            steps_used=step,
            tool_calls_used=tool_calls_used,
            limits=limits,
            trace=trace,
            transcript=messages,
            error=fields.get("error", ""),
        )

    for step in range(1, limits.max_steps + 1):
        started = time.perf_counter()
        try:
            reply = llm.complete(messages, TOOL_SPECS)
        except LLMError as exc:
            return result(
                "llm_error",
                "llm_error",
                step,
                gaps=["模型调用失败，本轮没有得到答案"],
                error=str(exc),
            )
        llm_ms = round((time.perf_counter() - started) * 1000)
        messages.append(reply.assistant_message)

        if not reply.tool_calls:
            trace.append(
                {
                    "step": step,
                    "action": "（未调用工具）",
                    "arguments": {},
                    "reason": "",
                    "ok": False,
                    "observation": f"模型输出了文字而不是工具调用，已提示其按协议继续：{reply.content[:120]}",
                    "llm_ms": llm_ms,
                    "usage": reply.usage,
                }
            )
            messages.append({"role": "user", "content": PROTOCOL_REMINDER})
            continue

        for call in reply.tool_calls:
            entry: Dict[str, Any] = {
                "step": step,
                "action": call.name,
                "arguments": {k: v for k, v in call.arguments.items() if k != "reason"},
                "reason": str(call.arguments.get("reason") or "").strip(),
                "llm_ms": llm_ms,
                "usage": reply.usage,
            }
            observation = _handle_call(call, toolbox, question, history, limits, tool_calls_used)
            if observation.pop("_counted", False):
                tool_calls_used += 1
            accepted = observation.pop("_accepted", None)
            observation["steps_left"] = limits.max_steps - step
            messages.append(_tool_message(call.id, observation))
            entry["ok"] = bool(observation.get("ok"))
            entry["observation"] = summarize_observation(call.name, observation)
            trace.append(entry)
            if accepted is not None:
                return result(
                    call.arguments["status"],
                    "finished",
                    step,
                    answer=_unescape_newlines(str(call.arguments.get("answer") or "")).strip(),
                    citations=accepted.citations,
                    gaps=[str(gap).strip() for gap in call.arguments.get("gaps") or [] if str(gap).strip()],
                    clarification_question=_unescape_newlines(
                        str(call.arguments.get("clarification_question") or "")
                    ).strip(),
                )

    return result(
        "incomplete",
        "step_limit_reached",
        limits.max_steps,
        gaps=[
            f"达到步数上限（{limits.max_steps} 步），未完成检索和查证；已读取的文档：{', '.join(toolbox.read_doc_ids()) or '无'}"
        ],
    )


def _handle_call(
    call: ToolCall,
    toolbox: ToolBox,
    question: str,
    history: List[Dict[str, str]],
    limits: Limits,
    tool_calls_used: int,
) -> Dict[str, Any]:
    if call.parse_error:
        return {"ok": False, "error_code": "INVALID_ARGUMENTS", "error": f"参数不是合法 JSON：{call.parse_error}"}
    if call.name == "finish":
        check = check_finish(call.arguments, toolbox, question, history)
        if check.problems:
            return {
                "ok": False,
                "error_code": "FINISH_REJECTED",
                "problems": check.problems,
                "error": "结果未通过校验，请根据 problems 修改后重新调用 finish，或继续检索/读取",
            }
        return {"ok": True, "accepted": True, "_accepted": check}
    if tool_calls_used >= limits.max_tool_calls:
        return {
            "ok": False,
            "error_code": "TOOL_BUDGET_EXHAUSTED",
            "error": f"工具调用次数已达上限（{limits.max_tool_calls} 次），请用已有信息调用 finish",
        }
    observation = toolbox.execute(call.name, call.arguments)
    observation["_counted"] = True
    return observation
