"""Acceptance cases end-to-end with the offline mock, plus document replacement."""

import shutil

import pytest

from kb_agent.agent import run_agent
from kb_agent.cases import load_cases, run_case
from kb_agent.config import DEFAULT_DOCS_DIR, ROOT
from kb_agent.docs import load_knowledge_base
from kb_agent.llm.mock import MockLLM
from kb_agent.tools import ToolBox

CASES = load_cases(ROOT / "examples" / "cases.json")


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_case_meets_its_expectations_with_mock(case):
    record = run_case(case, MockLLM())
    failed = [check for turn in record["turns"] for check in turn["checks"] if not check["passed"]]
    assert record["passed"], failed


def test_cases_cover_every_acceptance_point():
    covered = {point for case in CASES for point in case["acceptance"]}
    required = {"明确答案", "文档冲突", "资料外问题", "改写后的相似问题", "上下文追问", "工具失败", "步数上限"}
    assert required <= covered


def test_editing_a_document_changes_the_answer(tmp_path):
    docs = tmp_path / "docs"
    shutil.copytree(DEFAULT_DOCS_DIR, docs)
    d01 = docs / "D01.md"
    d01.write_text(d01.read_text(encoding="utf-8").replace("30 天内", "45 天内"), encoding="utf-8")

    with_conflict = run_agent("报销期限是多久？", llm=MockLLM(), toolbox=ToolBox(load_knowledge_base(docs)))
    assert with_conflict.status == "conflict_needs_confirmation"
    assert "45" in with_conflict.answer and "15" in with_conflict.answer

    (docs / "D02.md").unlink()
    single = run_agent("报销期限是多久？", llm=MockLLM(), toolbox=ToolBox(load_knowledge_base(docs)))
    assert single.status == "answered"
    assert "45" in single.answer and "30" not in single.answer
    assert [c.doc_id for c in single.citations] == ["D01"]
