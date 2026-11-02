"""Load the synthetic knowledge base from Markdown files with a small front-matter header."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, Iterable, Iterator, Optional, Tuple

_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n(.*)\Z", re.DOTALL)
_HEADING = re.compile(r"^##\s+(.+?)\s*$")
_NUMBERED = re.compile(r"^(\d+)[.、．]\s*(.+)$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REQUIRED = ("doc_id", "title", "version_date")


class DocumentError(ValueError):
    """Raised when a knowledge-base file is malformed."""


@dataclass(frozen=True)
class Section:
    section_id: str
    title: str
    text: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    version_date: str
    owner: str
    sections: Tuple[Section, ...]
    path: str

    def section(self, section_id: str) -> Optional[Section]:
        for item in self.sections:
            if item.section_id == section_id:
                return item
        return None


class KnowledgeBase:
    """Read-only mapping of doc_id -> Document."""

    def __init__(self, documents: Iterable[Document]):
        self._docs: Dict[str, Document] = {}
        for doc in documents:
            self._docs[doc.doc_id] = doc

    def __contains__(self, doc_id: object) -> bool:
        return doc_id in self._docs

    def __iter__(self) -> Iterator[Document]:
        return iter(sorted(self._docs.values(), key=lambda d: d.doc_id))

    def __len__(self) -> int:
        return len(self._docs)

    def get(self, doc_id: str) -> Optional[Document]:
        return self._docs.get(doc_id)


def parse_document(text: str, path: str = "") -> Document:
    match = _FRONT_MATTER.match(text.lstrip("﻿"))
    if not match:
        raise DocumentError(f"{path}: 缺少 --- 包围的元数据头")
    header, body = match.groups()

    meta: Dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise DocumentError(f"{path}: 元数据行格式应为 key: value，实际为 {line!r}")
        meta[key.strip()] = value.strip()
    missing = [key for key in _REQUIRED if not meta.get(key)]
    if missing:
        raise DocumentError(f"{path}: 缺少元数据 {missing}")
    if not _DATE.match(meta["version_date"]):
        raise DocumentError(f"{path}: version_date 应为 YYYY-MM-DD")

    doc_id = meta["doc_id"]
    sections = []
    heading: Optional[str] = None
    lines: list = []

    def flush() -> None:
        content = " ".join(item.strip() for item in lines if item.strip())
        if heading is None and not content:
            return
        title = heading or "正文"
        number = str(len(sections) + 1)
        numbered = _NUMBERED.match(title)
        if numbered:
            number, title = numbered.groups()
        sections.append(Section(section_id=f"{doc_id}-S{number}", title=title, text=content))

    for line in body.splitlines():
        found = _HEADING.match(line)
        if found:
            flush()
            heading, lines = found.group(1), []
        else:
            lines.append(line)
    flush()

    if not sections:
        raise DocumentError(f"{path}: 正文为空")
    ids = [item.section_id for item in sections]
    if len(ids) != len(set(ids)):
        raise DocumentError(f"{path}: 段落编号重复 {ids}")
    return Document(
        doc_id=doc_id,
        title=meta["title"],
        version_date=meta["version_date"],
        owner=meta.get("owner", ""),
        sections=tuple(sections),
        path=path,
    )


def _load_dir(directory: Path) -> Dict[str, Document]:
    if not directory.is_dir():
        raise DocumentError(f"文档目录不存在：{directory}")
    docs: Dict[str, Document] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        doc = parse_document(path.read_text(encoding="utf-8"), str(path))
        if doc.doc_id in docs:
            raise DocumentError(f"{directory}: doc_id {doc.doc_id} 重复")
        docs[doc.doc_id] = doc
    return docs


def load_knowledge_base(
    docs_dir: Path,
    overlay_dir: Optional[Path] = None,
    exclude: Iterable[str] = (),
) -> KnowledgeBase:
    """Load docs_dir, replace same-id documents from overlay_dir, then drop excluded ids."""
    docs = _load_dir(Path(docs_dir))
    if overlay_dir is not None:
        docs.update(_load_dir(Path(overlay_dir)))
    for doc_id in exclude:
        docs.pop(doc_id, None)
    if not docs:
        raise DocumentError("知识库为空")
    return KnowledgeBase(docs.values())
