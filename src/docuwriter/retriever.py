"""Small dependency-free BM25 retriever."""

from collections import Counter
import math
import re

from .models import ContextChunk, Placeholder


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class BM25ContextRetriever:
    def __init__(self, chunks: list[ContextChunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self._terms = [_tokens(chunk.text) for chunk in chunks]
        self._frequencies = [Counter(terms) for terms in self._terms]
        self._average_length = sum(map(len, self._terms)) / len(self._terms) if chunks else 0
        self._document_frequency: Counter[str] = Counter()
        for terms in self._terms:
            self._document_frequency.update(set(terms))

    def _score(self, query: list[str], index: int) -> float:
        frequencies = self._frequencies[index]
        length = len(self._terms[index])
        score = 0.0
        for term in query:
            frequency = frequencies[term]
            if not frequency:
                continue
            df = self._document_frequency[term]
            idf = math.log(1 + (len(self.chunks) - df + 0.5) / (df + 0.5))
            denominator = frequency + self.k1 * (1 - self.b + self.b * length / (self._average_length or 1))
            score += idf * frequency * (self.k1 + 1) / denominator
        return score

    def retrieve_for_batch(self, batch: list[Placeholder], max_chars: int) -> str:
        query = _tokens(" ".join(f"{p.section_path} {p.original_hint}" for p in batch))
        ranked = sorted(enumerate(self.chunks), key=lambda item: self._score(query, item[0]), reverse=True)
        selected: list[str] = []
        used = 0
        for _, chunk in ranked:
            page_suffix = f" | Page {chunk.page_number}" if chunk.page_number is not None else ""
            text = f"\n[{chunk.source_file}{page_suffix}:{chunk.chunk_index}] {chunk.text}"
            if used + len(text) > max_chars:
                continue
            selected.append(text)
            used += len(text) + 1
        return "\n".join(selected)
