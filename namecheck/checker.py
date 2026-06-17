"""Pipeline orchestration: pair scoring + dictionary-based suggestion."""
from itertools import permutations

from .normalize import tokenize, is_plausible_name
from .romanize import canonical_tokens
from .scorer import norm_score
from .features import NGramIndex

AUTO_ACCEPT = 0.15   # silent accept / normalize
REVIEW = 0.40        # "Did you mean ...?" band upper bound


def _variants(raw: str, country: str):
    """Canonical comparison strings: joined tokens, with/without particles,
    plus token-order permutations (name inversion check)."""
    out = set()
    for strip in (True, False):
        toks = tokenize(raw, strip_particles=strip)
        if not toks:
            continue
        ctoks = canonical_tokens(toks, country)
        perms = permutations(ctoks) if len(ctoks) <= 4 else [tuple(ctoks)]
        for p in perms:
            out.add("".join(p))  # joined: neutralizes split/merge & spacing
    return out


def score_pair(name_a: str, name_b: str, country: str = "") -> float:
    """Normalized mismatch score between two names. 0 = same name."""
    va, vb = _variants(name_a, country), _variants(name_b, country)
    if not va or not vb:
        return 1.0
    best = 1.0
    for a in va:
        for b in vb:
            s = norm_score(a, b)
            if s < best:
                best = s
                if best == 0.0:
                    return 0.0
    # Subset handling: missing middle token (LE PHUONG THUY vs LE THI PHUONG THUY)
    ta = set(tokenize(name_a))
    tb = set(tokenize(name_b))
    if ta and tb and (ta <= tb or tb <= ta) and len(ta & tb) >= 2:
        best = min(best, 0.1)
    return best


def verdict(score: float) -> str:
    if score < AUTO_ACCEPT:
        return "accept"
    if score < REVIEW:
        return "review"
    return "mismatch"


class NameChecker:
    """Spell checker backed by a per-country dictionary of verified names."""

    def __init__(self):
        self._index = {}    # country -> NGramIndex over canonical full names
        self._display = {}  # country -> {canonical: original}

    def add_reference(self, name: str, country: str):
        country = country.lower()
        idx = self._index.setdefault(country, NGramIndex())
        disp = self._display.setdefault(country, {})
        for v in _variants(name, country):
            idx.add(v)
            disp.setdefault(v, name)

    def check(self, raw: str, country: str, top_k: int = 3):
        """Return dict: status + ranked suggestions from the dictionary."""
        country = country.lower()
        if not is_plausible_name(raw):
            return {"status": "unparseable", "suggestions": []}
        idx = self._index.get(country)
        if idx is None:
            return {"status": "no_dictionary", "suggestions": []}
        best = []
        for q in _variants(raw, country):
            for cand in idx.candidates(q, top_k=40):
                s = norm_score(q, cand)
                best.append((s, self._display[country][cand]))
        # dedupe by display name, keep best score
        seen = {}
        for s, name in sorted(best):
            if name not in seen:
                seen[name] = s
        ranked = sorted(seen.items(), key=lambda kv: kv[1])[:top_k]
        if not ranked:
            return {"status": "unknown", "suggestions": []}
        top_score = ranked[0][1]
        return {
            "status": verdict(top_score),
            "suggestions": [{"name": n, "score": round(s, 3)} for n, s in ranked],
        }
