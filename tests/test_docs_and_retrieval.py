import pytest

from kb_agent.config import DEFAULT_DOCS_DIR, ROOT
from kb_agent.docs import DocumentError, load_knowledge_base, parse_document
from kb_agent.retrieval import BM25Index, tokenize


def test_documents_parse_metadata_and_sections(kb):
    doc = kb.get("D01")
    assert doc.title == "费用报销管理办法"
    assert doc.version_date == "2023-03-01"
    assert [s.section_id for s in doc.sections] == ["D01-S1", "D01-S2", "D01-S3", "D01-S4"]
    assert "30 天内" in doc.section("D01-S2").text
    assert len(kb) == 7


def test_overlay_replaces_document_and_exclude_removes_it():
    scoped = load_knowledge_base(DEFAULT_DOCS_DIR, ROOT / "data" / "variants" / "d02_scoped")
    assert scoped.get("D02").section("D02-S0").title == "适用范围"
    without = load_knowledge_base(DEFAULT_DOCS_DIR, exclude=["D02"])
    assert "D02" not in without and "D01" in without


def test_malformed_document_is_rejected():
    with pytest.raises(DocumentError):
        parse_document("no header\n## 1. x\ny", "bad.md")
    with pytest.raises(DocumentError):
        parse_document("---\ndoc_id: X\ntitle: t\nversion_date: 2024/01/01\n---\n## 1. a\nb", "bad.md")


def test_tokenize_uses_chinese_bigrams_and_ascii_words():
    assert tokenize("报销期限 VPN") == ["报销", "销期", "期限", "vpn"]


def test_conflicting_documents_are_both_retrieved(kb):
    hits = BM25Index(kb).search("报销期限是多久？", 5)
    assert [hit.doc_id for hit in hits[:2]] == ["D01", "D02"]


def test_unknown_terms_give_low_coverage_and_rewrite_recovers(kb):
    index = BM25Index(kb)
    assert max((hit.coverage for hit in index.search("WFH 要先申请什么？")), default=0) < 0.1
    best = index.search("远程办公 申请")[0]
    assert best.section_id == "D05-S2" and best.coverage > 0.9
