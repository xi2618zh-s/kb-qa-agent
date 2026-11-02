"""Offline stand-in for the model: a small heuristic policy over the same observations.

It lets the whole loop run without an API key and proves the plumbing (tools,
guards, traces, limits). Its decisions are hand-written heuristics: they react to
tool results, but they show nothing about how a real model decides.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Dict, List, Tuple

from ..prompts import QUESTION_PREFIX
from .base import LLMReply, ToolCall, assistant_message

# A hit counts as relevant when its weighted coverage clears both an absolute floor
# and half of the best hit's coverage.
MIN_COVERAGE = 0.15
RELATIVE_COVERAGE = 0.5
_FOLLOW_UP = re.compile(r"^(那|那么|这个|它|如果)|呢[？?]?$")
_DEICTIC = re.compile(r"^(这个|那个|这笔|那笔|这项|它)")
_QUESTION_WORDS = re.compile(r"[？?！!。，,、；;：:]|什么|怎么|多久|多少|哪个|哪些|如何|是否|请问|一下|吗|呢|吧")
_QUANTITY = re.compile(r"(\d+(?:\.\d+)?)\s*(个工作日|个月|小时|天|日|元|GB|年|位)")


@dataclass
class _Action:
    name: str
    args: Dict[str, Any]
    result: Dict[str, Any]


def _parse(messages: List[Dict[str, Any]]) -> Tuple[str, List[str], List[_Action]]:
    start = max(
        i
        for i, message in enumerate(messages)
        if message["role"] == "user" and str(message["content"]).startswith(QUESTION_PREFIX)
    )
    question = messages[start]["content"][len(QUESTION_PREFIX) :]
    earlier_questions = [m["content"] for m in messages[1:start] if m["role"] == "user"]
    pending: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    actions: List[_Action] = []
    for message in messages[start + 1 :]:
        if message["role"] == "assistant":
            for call in message.get("tool_calls", []):
                pending[call["id"]] = (call["function"]["name"], json.loads(call["function"]["arguments"] or "{}"))
        elif message["role"] == "tool":
            name, args = pending.pop(message["tool_call_id"], ("?", {}))
            actions.append(_Action(name, args, json.loads(message["content"])))
    return question, earlier_questions, actions


class MockLLM:
    provider = "mock"
    model = "heuristic-policy"

    def __init__(self) -> None:
        self._calls = 0

    def complete(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMReply:
        name, args = self._decide(*_parse(messages))
        self._calls += 1
        call = ToolCall(
            id=f"mock-{self._calls}", name=name, arguments=args, raw_arguments=json.dumps(args, ensure_ascii=False)
        )
        return LLMReply(tool_calls=[call], content="", assistant_message=assistant_message("", [call]))

    def _decide(self, question: str, earlier: List[str], actions: List[_Action]) -> Tuple[str, Dict[str, Any]]:
        if actions and not actions[-1].result.get("ok"):
            last = actions[-1]
            code = last.result.get("error_code")
            if code == "TOOL_UNAVAILABLE":
                streak = 0
                for action in reversed(actions):
                    if action.name != last.name or action.result.get("error_code") != code:
                        break
                    streak += 1
                if streak < 2:
                    return last.name, {**last.args, "reason": f"{last.name} 返回临时故障，重试一次"}
                return _finish(
                    "tool_error",
                    "知识库工具连续失败，暂时无法查询，本轮不给出答案。",
                    gaps=[f"{last.name} 连续 {streak} 次不可用，未能获取相关制度原文"],
                    reason=f"{last.name} 连续 {streak} 次失败，停止重试",
                )
            if code in ("FINISH_REJECTED", "TOOL_BUDGET_EXHAUSTED"):
                return _finish(
                    "insufficient_evidence",
                    "未能形成可通过校验的答案。",
                    gaps=[last.result.get("error", code)],
                    reason="上一步被拒绝，改为报告资料缺口",
                )

        searches = [a for a in actions if a.name == "search_docs" and a.result.get("ok")]
        if not actions and not earlier and _DEICTIC.search(question.strip()):
            return _finish(
                "need_clarification",
                "问题中的指代词没有可对应的对象，无法确定要查询哪项制度。",
                clarification="请说明具体是哪项费用或事项（例如费用类型、金额、发生时间），我再查对应的制度。",
                reason="问题以指代词开头且没有对话历史，先追问再检索",
            )
        if not searches:
            follow_up = bool(earlier) and bool(_FOLLOW_UP.search(question.strip()))
            query = f"{question} {earlier[-1]}" if follow_up else question
            reason = "问题是追问，结合上一轮问题检索" if follow_up else "先检索与问题相关的制度段落"
            return "search_docs", {"query": query, "reason": reason}

        last_search = searches[-1]
        query = last_search.args["query"]
        hits = last_search.result.get("results", [])
        best = max((hit["coverage"] for hit in hits), default=0.0)
        threshold = max(MIN_COVERAGE, RELATIVE_COVERAGE * best)
        relevant = [hit for hit in hits if hit["coverage"] >= threshold]
        if not relevant:
            if len(searches) < 2:
                rewritten = " ".join(_QUESTION_WORDS.sub(" ", query).split()) or query
                return "search_docs", {
                    "query": rewritten,
                    "reason": f"检索结果与问题关联度低（最高覆盖率 {best:.0%}），去掉疑问词后重新检索",
                }
            return _finish(
                "insufficient_evidence",
                "知识库中没有找到与该问题相关的制度或说明，无法作答。",
                gaps=[f"未检索到与“{question}”相关的文档"],
                reason=f"两次检索都没有相关段落（最高覆盖率 {best:.0%}）",
            )

        doc_order = list(dict.fromkeys(hit["doc_id"] for hit in relevant))
        titles = {hit["doc_id"]: hit["title"] for hit in relevant}
        pinned = [doc_id for doc_id in doc_order if titles[doc_id] in question]
        candidates = pinned or doc_order[:3]
        reads = {a.result["doc_id"]: a.result for a in actions if a.name == "read_doc" and a.result.get("ok")}
        for doc_id in candidates:
            if doc_id not in reads:
                return "read_doc", {
                    "doc_id": doc_id,
                    "reason": f"检索命中 {doc_id}《{titles[doc_id]}》，读取原文以便核对和引用",
                }

        texts: Dict[str, List[str]] = {}
        for doc_id in candidates:
            by_id = {s["section_id"]: s["text"] for s in reads[doc_id]["sections"]}
            texts[doc_id] = [by_id[h["section_id"]] for h in relevant if h["doc_id"] == doc_id and h["section_id"] in by_id]
        meta = {doc_id: f"{doc_id}《{titles[doc_id]}》({reads[doc_id]['version_date']})" for doc_id in candidates}

        if len(candidates) >= 2:
            # unit -> doc_id -> (first value, the section text it came from)
            values: Dict[str, Dict[str, Tuple[str, str]]] = {}
            for doc_id in candidates:
                for text in texts[doc_id]:
                    for number, unit in _QUANTITY.findall(text):
                        values.setdefault(unit, {}).setdefault(doc_id, (number, text))
            for found in values.values():
                if len(found) > 1 and len({number for number, _ in found.values()}) > 1:
                    lines = [f"{meta[doc_id]}规定：{text.rstrip('。')}" for doc_id, (_, text) in found.items()]
                    return _finish(
                        "conflict_needs_confirmation",
                        "多份制度对该事项的规定不一致。" + "；".join(lines) + "。原文没有写明适用范围或优先级，无法确定以哪份为准。",
                        citations=[{"doc_id": doc_id, "quote": text} for doc_id, (_, text) in found.items()],
                        gaps=["各文档之间的适用范围和优先级未写明"],
                        clarification="请确认您适用哪份制度：" + "、".join(meta[doc_id] for doc_id in found) + "？",
                        reason="已读取的文档对同一事项给出不同数值，且未写明优先级",
                    )

        doc_id = candidates[0]
        quotes = texts[doc_id][:2]
        return _finish(
            "answered",
            f"根据 {meta[doc_id]}：" + "；".join(quote.rstrip("。") for quote in quotes) + "。",
            citations=[{"doc_id": doc_id, "quote": quote} for quote in quotes],
            reason=f"{doc_id} 原文直接回答了问题，未发现其他文档的不同规定",
        )


def _finish(
    status: str,
    answer: str,
    *,
    reason: str,
    citations: Any = (),
    gaps: Any = (),
    clarification: str = "",
) -> Tuple[str, Dict[str, Any]]:
    return "finish", {
        "status": status,
        "answer": answer,
        "citations": list(citations),
        "gaps": list(gaps),
        "clarification_question": clarification,
        "reason": reason,
    }
