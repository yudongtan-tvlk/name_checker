"""Layer 4: weighted Damerau-Levenshtein with regional substitution costs.

Pure Python (names are short); swap in rapidfuzz / weighted-levenshtein
C extensions for production throughput.
"""
from functools import lru_cache

# Phonetically plausible substitutions (symmetric). 1.0 elsewhere.
_CHEAP = {
    ("k", "g"): 0.3, ("p", "b"): 0.3, ("t", "d"): 0.3, ("c", "k"): 0.3,
    ("c", "s"): 0.4, ("j", "z"): 0.3, ("j", "y"): 0.4, ("l", "r"): 0.3,
    ("m", "n"): 0.4, ("f", "p"): 0.3, ("v", "w"): 0.3, ("v", "b"): 0.4,
    ("i", "y"): 0.2, ("u", "o"): 0.3, ("e", "i"): 0.4, ("a", "e"): 0.4,
    ("o", "a"): 0.5, ("u", "w"): 0.4, ("s", "z"): 0.3, ("g", "h"): 0.5,
    ("d", "r"): 0.5, ("e", "o"): 0.5,
}
SUB_COST = {}
for (a, b), w in _CHEAP.items():
    SUB_COST[(a, b)] = w
    SUB_COST[(b, a)] = w

VOWELS = set("aeiouy")
INDEL_VOWEL = 0.6   # dropping/adding a vowel is common (Jun Kyu/JunKyu, h endings)
INDEL_H = 0.4       # silent h (Kusuma/Kusumah, Anh/An, oh/o)
INDEL_DEFAULT = 1.0
TRANSPOSE = 0.4     # Nguyen/Ngyuen


def _indel(ch: str) -> float:
    if ch == "h":
        return INDEL_H
    if ch in VOWELS:
        return INDEL_VOWEL
    return INDEL_DEFAULT


@lru_cache(maxsize=200_000)
def weighted_dl(s: str, t: str) -> float:
    """Weighted Damerau-Levenshtein distance."""
    n, m = len(s), len(t)
    if n == 0:
        return sum(_indel(c) for c in t)
    if m == 0:
        return sum(_indel(c) for c in s)
    prev2 = None
    prev = [0.0] * (m + 1)
    for j in range(1, m + 1):
        prev[j] = prev[j - 1] + _indel(t[j - 1])
    for i in range(1, n + 1):
        cur = [prev[0] + _indel(s[i - 1])] + [0.0] * m
        for j in range(1, m + 1):
            sub = SUB_COST.get((s[i - 1], t[j - 1]), 1.0) if s[i - 1] != t[j - 1] else 0.0
            cur[j] = min(
                prev[j] + _indel(s[i - 1]),      # delete
                cur[j - 1] + _indel(t[j - 1]),   # insert
                prev[j - 1] + sub,               # substitute
            )
            if (i > 1 and j > 1 and s[i - 1] == t[j - 2] and s[i - 2] == t[j - 1]
                    and s[i - 1] != s[i - 2]):
                cur[j] = min(cur[j], prev2[j - 2] + TRANSPOSE)
        prev2, prev = prev, cur
    return prev[m]


def norm_score(s: str, t: str) -> float:
    """Normalized distance in [0, 1]; 0 = identical."""
    if s == t:
        return 0.0
    L = max(len(s), len(t))
    return weighted_dl(s, t) / L if L else 0.0
