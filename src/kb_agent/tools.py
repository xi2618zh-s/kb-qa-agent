"""Business tools (search_docs, read_doc), their JSON schemas, and failure injection.

Tools never raise: every outcome, including injected faults, is returned as an
observation dict so the model can decide what to do next. Nothing here retries.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
import unicodedata

from .docs import KnowledgeBase
from .retrieval import BM25Index

_REASON = {"type": "string", "description": "一句话说明选择这一步的依据（基于上一步的结果）"}

SEARCH_SPEC: Dict[str, Any] = {
    "name": "search_docs",
    "description": (
        "在企业知识库中检索段落（BM25 字词匹配，不理解同义词）。返回文档 ID、标题、版本日期、段落 ID、片段、得分、"
        "coverage（查询词按稀有度加权后被该段落覆盖的比例，0–1）和命中词。"
        "片段只用于定位；要引用必须先用 read_doc 读取原文。结果与问题无关时可以换关键词再检索。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索词，尽量使用制度原文中可能出现的说法"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 8, "description": "返回条数，默认 5"},
            "reason": _REASON,
        },
        "required": ["query", "reason"],
    },
}

READ_SPEC: Dict[str, Any] = {
    "name": "read_doc",
    "description": "读取文档原文（含元数据：标题、版本日期、发布部门）。不传 section_id 时返回全文，便于查看适用范围、优先级等条款。",
    "parameters": {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档 ID，如 D01"},
            "section_id": {"type": "string", "description": "可选，段落 ID，如 D01-S2"},
            "reason": _REASON,
        },
        "required": ["doc_id", "reason"],
    },
}

FINISH_STATUSES = (
    "answered",
    "conflict_needs_confirmation",
    "need_clarification",
    "insufficient_evidence",
    "tool_error",
)

FINISH_SPEC: Dict[str, Any] = {
    "name": "finish",
    "description": "结束本轮并提交结构化结果。程序会校验引用和状态，不通过会返回原因，你可以修改后再提交。",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": list(FINISH_STATUSES),
                "description": (
                    "answered=有依据的回答；conflict_needs_confirmation=文档规定冲突且未写明适用范围或优先级，需用户确认；"
                    "need_clarification=问题缺少必要条件；insufficient_evidence=知识库没有依据；tool_error=工具故障导致无法获取资料"
                ),
            },
            "answer": {"type": "string", "description": "给员工的回答；冲突时写清各文档的规定；无法回答时说明原因"},
            "citations": {
                "type": "array",
                "description": "引用，quote 必须逐字摘自 read_doc 返回的原文",
                "items": {
                    "type": "object",
                    "properties": {"doc_id": {"type": "string"}, "quote": {"type": "string"}},
                    "required": ["doc_id", "quote"],
                },
            },
            "gaps": {"type": "array", "items": {"type": "string"}, "description": "资料缺口或未确认事项，没有则为空数组"},
            "clarification_question": {"type": "string", "description": "需要用户确认或补充的问题；不需要时为空字符串"},
            "reason": _REASON,
        },
        "required": ["status", "answer", "citations", "gaps", "reason"],
    },
}

TOOL_SPECS: List[Dict[str, Any]] = [SEARCH_SPEC, READ_SPEC, FINISH_SPEC]


def normalize_text(text: str) -> str:
    """Comparison form: NFKC (full-width punctuation -> ASCII) and no whitespace."""
    return "".join(unicodedata.normalize("NFKC", text).split())


def _error(code: str, message: str, retryable: bool = False) -> Dict[str, Any]:
    return {"ok": False, "error_code": code, "error": message, "retryable": retryable}


class FailureInjector:
    """Simulated outages. Spec: "<tool>:<once|always|N>", tool may be "*" for all tools."""

    def __init__(self, specs: Iterable[str] = ()):
        self._remaining: Dict[str, int] = {}
        for spec in specs:
            tool, _, mode = spec.partition(":")
            mode = mode or "once"
            if mode == "always":
                count = -1
            elif mode == "once":
                count = 1
            elif mode.isdigit() and int(mode) > 0:
                count = int(mode)
            else:
                raise ValueError(f"无法解析故障注入参数 {spec!r}，格式为 tool:once|always|N")
            self._remaining[tool.strip()] = count

    def check(self, tool: str) -> Optional[str]:
        for key in (tool, "*"):
            count = self._remaining.get(key, 0)
            if count == 0:
                continue
            if count > 0:
                self._remaining[key] = count - 1
            return f"模拟故障（注入）：{tool} 服务暂时不可用"
        return None


class ToolBox:
    """Executes business tools for one agent turn and remembers which original text was read."""

    def __init__(self, kb: KnowledgeBase, failures: Optional[FailureInjector] = None):
        self.kb = kb
        self.index = BM25Index(kb)
        self.failures = failures or FailureInjector()
        self._read: Dict[str, List[str]] = {}

    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        handler = {"search_docs": self._search, "read_doc": self._read_doc}.get(name)
        if handler is None:
            return _error("UNKNOWN_TOOL", f"未知工具 {name}，可用工具为 search_docs、read_doc、finish")
        fault = self.failures.check(name)
        if fault:
            return _error("TOOL_UNAVAILABLE", fault, retryable=True)
        return handler(arguments)

    def was_read(self, doc_id: str, quote: str) -> bool:
        needle = normalize_text(quote)
        return bool(needle) and any(needle in normalize_text(text) for text in self._read.get(doc_id, []))

    def read_doc_ids(self) -> List[str]:
        return sorted(self._read)

    def _search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return _error("INVALID_ARGUMENTS", "query 必须是非空字符串")
        top_k = arguments.get("top_k", 5)
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            return _error("INVALID_ARGUMENTS", "top_k 必须是整数")
        top_k = min(max(top_k, 1), 8)
        hits = self.index.search(query.strip(), top_k)
        result: Dict[str, Any] = {
            "ok": True,
            "query": query.strip(),
            "result_count": len(hits),
            "results": [hit.to_dict() for hit in hits],
        }
        if not hits:
            result["note"] = "没有检索到匹配段落"
        return result

    def _read_doc(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = arguments.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            return _error("INVALID_ARGUMENTS", "doc_id 必须是非空字符串")
        doc = self.kb.get(doc_id.strip())
        if doc is None:
            return _error("DOC_NOT_FOUND", f"文档 {doc_id} 不存在")
        section_id = arguments.get("section_id")
        sections = list(doc.sections)
        if section_id:
            section = doc.section(str(section_id).strip())
            if section is None:
                ids = ", ".join(item.section_id for item in doc.sections)
                return _error("SECTION_NOT_FOUND", f"{doc.doc_id} 中没有段落 {section_id}，可用段落：{ids}")
            sections = [section]
        texts = self._read.setdefault(doc.doc_id, [])
        texts.extend(f"{item.title}\n{item.text}" for item in sections)
        return {
            "ok": True,
            "doc_id": doc.doc_id,
            "title": doc.title,
            "version_date": doc.version_date,
            "owner": doc.owner,
            "sections": [
                {"section_id": item.section_id, "title": item.title, "text": item.text} for item in sections
            ],
        }


def summarize_observation(tool: str, observation: Dict[str, Any]) -> str:
    """One-line summary for traces."""
    if not observation.get("ok"):
        problems = observation.get("problems")
        detail = "；".join(problems) if problems else observation.get("error", "")
        return f"失败 {observation.get('error_code', '')}：{detail}"
    if tool == "search_docs":
        results = observation.get("results", [])
        if not results:
            return f"检索“{observation.get('query', '')}”：0 条结果"
        top = ", ".join(f"{item['section_id']}({item['score']})" for item in results)
        return f"检索“{observation.get('query', '')}”：{len(results)} 条 — {top}"
    if tool == "read_doc":
        ids = ", ".join(item["section_id"] for item in observation.get("sections", []))
        return f"读取 {observation['doc_id']}《{observation['title']}》({observation['version_date']})：{ids}"
    if tool == "finish":
        return "结果通过校验，本轮结束"
    return "成功"
