"""Loop mechanics and code-enforced guards, driven by a scripted model."""

from kb_agent.agent import Limits, run_agent
from kb_agent.tools import FailureInjector, ToolBox

D01_QUOTE = "员工应在费用发生之日起 30 天内通过 OA 系统提交报销申请。"


def _search(query="报销期限"):
    return ("search_docs", {"query": query, "reason": "先检索"})


def _read(doc_id="D01"):
    return ("read_doc", {"doc_id": doc_id, "reason": "读取原文"})


def _finish(status="answered", answer="报销期限为 30 天。", citations=None, **extra):
    args = {
        "status": status,
        "answer": answer,
        "citations": [{"doc_id": "D01", "quote": D01_QUOTE}] if citations is None else citations,
        "gaps": extra.pop("gaps", []),
        "reason": "可以作答",
    }
    args.update(extra)
    return ("finish", args)


def test_citation_must_come_from_text_that_was_read(kb, scripted):
    llm = scripted([_search(), _finish(), _read(), _finish()])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))

    assert result.status == "answered"
    assert [entry["action"] for entry in result.trace] == ["search_docs", "finish", "read_doc", "finish"]
    rejected = llm.seen[2][-1]  # the model saw the rejection before choosing read_doc
    assert "FINISH_REJECTED" in rejected["content"] and "read_doc" in rejected["content"]
    assert result.citations[0].doc_id == "D01" and result.citations[0].version_date == "2023-03-01"


def test_reworded_quote_is_rejected(kb, scripted):
    bad = [{"doc_id": "D01", "quote": "员工需在 30 天内提交报销"}]
    llm = scripted([_read(), _finish(citations=bad), _finish()])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert result.status == "answered"
    assert result.trace[1]["ok"] is False and "逐字" in result.trace[1]["observation"]


def test_numbers_in_answer_must_appear_in_citations_or_question(kb, scripted):
    llm = scripted([_read(), _finish(answer="报销期限为 45 天。"), _finish()])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert "45" in result.trace[1]["observation"]
    assert result.answer == "报销期限为 30 天。"


def test_section_ids_and_list_markers_are_not_treated_as_facts(kb, scripted):
    answer = "依据 D01-S2、S2 两处说明：\n1. 期限为 30 天。\n2. 逾期须附情况说明。③ 选项：① 按 D01 ② 其他"
    llm = scripted([_read(), _finish(answer=answer)])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert result.status == "answered", result.trace[-1]["observation"]


def test_clause_refs_and_inline_list_markers_are_not_treated_as_facts(kb, scripted):
    # Forms DeepSeek actually produced in v2.1: clause references, inline markers after
    # punctuation, and list markers behind a double-escaped newline (literal backslash-n).
    answer = (
        "期限为 30 天，见《费用报销管理办法》（D01）第 2 条「报销期限」与第 1 节。"
        "要点：1. 30 天内提交；2、逾期附说明。\\n\\n3. 由 OA 系统提交。"
    )
    llm = scripted([_read(), _finish(answer=answer)])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert result.status == "answered", result.trace[-1]["observation"]
    assert "\\n" not in result.answer and "\n\n3. 由 OA" in result.answer  # shown as real newlines


def test_chinese_numerals_in_the_question_support_arabic_numbers(kb, scripted):
    # v2.2: the question said "满三年", the answer said "3 年" and was wrongly rejected.
    llm = scripted([_read(), _finish(answer="员工入职满 3 年，报销期限为 30 天。")])
    result = run_agent("入职满三年的员工报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert result.status == "answered", result.trace[-1]["observation"]


def test_chinese_quantities_in_the_answer_are_checked_but_counts_are_not(kb, scripted):
    invented = _finish(answer="报销期限为三十天，逾期可再宽限四十五天。")
    counts = _finish(answer="两份文档一般分三档说明，报销期限为三十天。")
    llm = scripted([_read(), invented, counts])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert "数字 45" in result.trace[1]["observation"]  # "三十天" is supported, "四十五天" is not
    assert result.status == "answered", result.trace[-1]["observation"]


def test_derived_or_invented_numbers_are_still_rejected(kb, scripted):
    llm = scripted([_read(), _finish(answer="期限为 30 天，逾期后补交期为 0 天，共 1.5 个月。"), _finish()])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert "数字 0, 1.5" in result.trace[1]["observation"]
    assert result.status == "answered" and result.answer == "报销期限为 30 天。"


def test_conflict_status_requires_two_documents_and_a_question(kb, scripted):
    conflict = _finish(status="conflict_needs_confirmation", answer="D01 写 30 天，D02 写 15 天。")
    d02 = {"doc_id": "D02", "quote": "费用报销须在费用发生后 15 天内提交"}
    citations = [{"doc_id": "D01", "quote": D01_QUOTE}, d02]
    vague = _finish(
        status="conflict_needs_confirmation",
        answer="D01 写 30 天，D02 写 15 天。",
        citations=citations,
        clarification_question="请确认适用哪份制度？",
    )
    options = _finish(
        status="conflict_needs_confirmation",
        answer="D01 写 30 天，D02 写 15 天。",
        citations=citations,
        clarification_question="请确认适用 D01《费用报销管理办法》还是《费用报销操作指引》？",
    )
    llm = scripted([_read("D01"), _read("D02"), conflict, vague, options])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert "至少 2 份" in result.trace[2]["observation"]
    assert "clarification_question" in result.trace[2]["observation"]
    assert "缺少 D01, D02" in result.trace[3]["observation"]  # options must name every cited document
    assert result.status == "conflict_needs_confirmation"
    assert sorted(c.doc_id for c in result.citations) == ["D01", "D02"]


def test_insufficient_evidence_must_not_carry_citations(kb, scripted):
    partial = _finish(status="insufficient_evidence", answer="只找到部分依据", gaps=["缺少审批制度"])
    answered = _finish(gaps=["缺少审批制度"])
    llm = scripted([_read(), partial, answered])
    result = run_agent("报销期限和审批流程？", llm=llm, toolbox=ToolBox(kb))
    assert "改用 answered" in result.trace[1]["observation"]
    assert result.status == "answered" and result.gaps == ["缺少审批制度"]


def test_need_clarification_requires_a_question(kb, scripted):
    bare = _finish(status="need_clarification", answer="指代不明", citations=[])
    asks = _finish(status="need_clarification", answer="指代不明", citations=[], clarification_question="请问是哪项费用？")
    llm = scripted([bare, asks])
    result = run_agent("这个能报销吗？", llm=llm, toolbox=ToolBox(kb))
    assert "clarification_question" in result.trace[0]["observation"]
    assert result.status == "need_clarification" and result.clarification_question == "请问是哪项费用？"


def test_step_limit_returns_explicit_incomplete_status(kb, scripted):
    llm = scripted([_search(), _read(), _read("D02")])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb), limits=Limits(max_steps=3))
    assert result.status == "incomplete"
    assert result.stop_reason == "step_limit_reached"
    assert result.steps_used == 3 and result.answer == "" and not result.citations
    assert "D01" in result.gaps[0] and "D02" in result.gaps[0]


def test_tool_call_budget_is_enforced(kb, scripted):
    llm = scripted([_search(), _search("报销"), _finish(status="insufficient_evidence", citations=[], gaps=["预算用完"])])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb), limits=Limits(max_tool_calls=1))
    assert result.tool_calls_used == 1
    assert "TOOL_BUDGET_EXHAUSTED" in result.trace[1]["observation"]


def test_tool_failure_is_returned_to_model_without_automatic_retry(kb, scripted):
    give_up = _finish(status="tool_error", answer="检索不可用", citations=[], gaps=["search_docs 不可用"])
    llm = scripted([_search(), give_up])
    toolbox = ToolBox(kb, FailureInjector(["search_docs:once"]))
    result = run_agent("报销期限是多久？", llm=llm, toolbox=toolbox)

    assert [entry["action"] for entry in result.trace] == ["search_docs", "finish"]
    assert result.trace[0]["ok"] is False
    assert "TOOL_UNAVAILABLE" in llm.seen[1][-1]["content"]
    assert result.status == "tool_error" and result.tool_calls_used == 1


def test_text_reply_triggers_protocol_reminder(kb, scripted):
    llm = scripted([("<text>", "报销期限是 30 天"), _read(), _finish()])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert result.trace[0]["action"] == "（未调用工具）"
    assert llm.seen[1][-1]["content"].startswith("[系统提示]")
    assert result.status == "answered"


def test_invalid_json_arguments_are_reported(kb, scripted):
    llm = scripted([("<raw>", "search_docs", "{not json"), _read(), _finish()])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert "INVALID_ARGUMENTS" in result.trace[0]["observation"]


def test_history_reaches_the_model(kb, scripted):
    history = [{"role": "user", "content": "工作满 3 年有几天年假？"}, {"role": "assistant", "content": "[answered] 5 天"}]
    llm = scripted([_read(), _finish()])
    run_agent("那报销呢？", llm=llm, toolbox=ToolBox(kb), history=history)
    first_request = llm.seen[0]
    assert [m["role"] for m in first_request] == ["system", "user", "assistant", "user"]
    assert first_request[1]["content"] == history[0]["content"]
    assert first_request[-1]["content"] == "当前问题：那报销呢？"


def test_trace_records_reason_and_next_action(kb, scripted):
    llm = scripted([_search(), _read(), _finish()])
    result = run_agent("报销期限是多久？", llm=llm, toolbox=ToolBox(kb))
    assert [entry["next_action"] for entry in result.trace] == ["read_doc", "finish", "（结束）"]
    assert result.trace[0]["reason"] == "先检索"
    assert "reason" not in result.trace[0]["arguments"]
