"""BM25 over document sections, tokenised as Chinese character bigrams plus ASCII words.

Character bigrams need no segmentation dictionary and work well enough on a small
synthetic corpus. Semantic gaps (e.g. "WFH" vs "远程办公") are left to the model,
which can rewrite the query and search again.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math
import re
from typing import Dict, List, Tuple

from .docs import Document, KnowledgeBase, Section

_TOKEN = re.compile(r"[一-鿿]+|[a-z0-9]+")
# Question words carry no topical signal; they are dropped from queries only.
STOP_TOKENS = frozenset(
    {"什么", "怎么", "多久", "多少", "是多", "哪个", "哪些", "如何", "是否", "几天", "有几", "请问", "一下"}
)
_SNIPPET_CHARS = 80


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in _TOKEN.finditer(text.lower()):
        run = match.group()
        if "一" <= run[0] <= "鿿":
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        else:
            tokens.append(run)
    return tokens


def content_tokens(text: str) -> List[str]:
    return [token for token in tokenize(text) if token not in STOP_TOKENS]


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    title: str
    version_date: str
    section_id: str
    section_title: str
    snippet: str
    score: float
    coverage: float
    matched_terms: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["matched_terms"] = list(self.matched_terms)
        return data


def _snippet(section: Section, terms: Tuple[str, ...]) -> str:
    text = section.text
    if len(text) <= _SNIPPET_CHARS:
        return text
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, min(positions) - 20) if positions else 0
    end = min(len(text), start + _SNIPPET_CHARS)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


class BM25Index:
    def __init__(self, kb: KnowledgeBase, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._entries: List[Tuple[Document, Section, Counter, int]] = []
        df: Counter = Counter()
        for doc in kb:
            for section in doc.sections:
                tokens = tokenize(f"{doc.title} {section.title} {section.text}")
                counts = Counter(tokens)
                self._entries.append((doc, section, counts, len(tokens)))
                df.update(counts.keys())
        total = len(self._entries)
        self._avg_len = sum(entry[3] for entry in self._entries) / max(total, 1)
        self._idf = {
            term: math.log((total - freq + 0.5) / (freq + 0.5) + 1.0) for term, freq in df.items()
        }
        self._max_idf = math.log((total + 0.5) / 0.5 + 1.0)

    def search(self, query: str, top_k: int = 5) -> List[SearchHit]:
        terms = list(dict.fromkeys(content_tokens(query)))
        # Coverage weights each query term by rarity; terms absent from the corpus get the
        # maximum weight, so a query about something the corpus never mentions scores low.
        weights = {term: self._idf.get(term, self._max_idf) for term in terms}
        total_weight = sum(weights.values()) or 1.0
        hits: List[SearchHit] = []
        for doc, section, counts, length in self._entries:
            score = 0.0
            matched = []
            for term in terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                matched.append(term)
                norm = tf + self.k1 * (1 - self.b + self.b * length / self._avg_len)
                score += self._idf[term] * tf * (self.k1 + 1) / norm
            if score > 0:
                hits.append(
                    SearchHit(
                        doc_id=doc.doc_id,
                        title=doc.title,
                        version_date=doc.version_date,
                        section_id=section.section_id,
                        section_title=section.title,
                        snippet=_snippet(section, tuple(matched)),
                        score=round(score, 3),
                        coverage=round(sum(weights[term] for term in matched) / total_weight, 3),
                        matched_terms=tuple(matched),
                    )
                )
        hits.sort(key=lambda hit: (-hit.score, hit.section_id))
        return hits[:top_k]
