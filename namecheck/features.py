"""Layer 3: character n-grams + inverted index for fast candidate retrieval."""
import heapq
from collections import defaultdict


def ngrams(s: str, n: int = 3):
    s = f"^{s}$"
    if len(s) < n:
        return {s}
    return {s[i:i + n] for i in range(len(s) - n + 1)}


class NGramIndex:
    """Inverted 3-gram index over dictionary names; Jaccard prefilter."""

    def __init__(self, n: int = 3):
        self.n = n
        self.index = defaultdict(set)
        self.entries = {}  # name -> precomputed grams
        self.glen = {}     # name -> len(grams), precomputed once

    def add(self, name: str):
        if name in self.entries:
            return
        grams = ngrams(name, self.n)
        self.entries[name] = grams
        self.glen[name] = len(grams)
        for g in grams:
            self.index[g].add(name)

    def candidates(self, query: str, top_k: int = 25):
        qgrams = ngrams(query, self.n)
        nq = len(qgrams)
        counts = defaultdict(int)
        for g in qgrams:
            for name in self.index.get(g, ()):
                counts[name] += 1
        glen = self.glen
        scored = (
            (cnt / (nq + glen[name] - cnt), name)
            for name, cnt in counts.items()
        )
        # nlargest(top_k, ...) reproduces sorted(reverse=True)[:top_k] exactly
        # (total order on (jaccard, name) tuples), so results are bit-identical.
        return [name for _, name in heapq.nlargest(top_k, scored)]
