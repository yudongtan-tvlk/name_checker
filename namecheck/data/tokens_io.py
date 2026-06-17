"""Read/write/finalize the per-country token cache.

Cache format: ``token<TAB>rank<TAB>is_curated`` (3 columns). Reads tolerate the
legacy 2-column ``token<TAB>rank`` form (is_curated defaults to 0), so migrated
pre-refactor caches load unchanged.

Rank is a dense rank derived from summed cross-source frequency (1 = most
common). ``is_curated`` marks tokens that came from a curated/gold source
(corrections, popular_names); it drives quarantine protection and is decoupled
from rank.
"""
import os

from namecheck.data.config import NO_RANK


def read_tokens(path):
    """-> (ranks {token: rank}, curated set). Missing file -> ({}, set())."""
    ranks, curated = {}, set()
    if not os.path.exists(path):
        return ranks, curated
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            tok = parts[0]
            ranks[tok] = int(parts[1]) if len(parts) > 1 and parts[1] else NO_RANK
            if len(parts) > 2 and parts[2] == "1":
                curated.add(tok)
    return ranks, curated


def write_tokens(path, ranks, curated=()):
    """Write token<TAB>rank<TAB>is_curated, sorted by token."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    curated = set(curated)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(
            f"{t}\t{r}\t{1 if t in curated else 0}"
            for t, r in sorted(ranks.items())
        ))


def finalize_ranks(freq, curated, min_freq=1, max_tokens=None):
    """Summed-frequency dict -> dense ranks (1 = most common).

    Non-curated tokens with freq < min_freq are dropped (evidence floor).
    If max_tokens is set and the survivors exceed it, keep the most-frequent
    max_tokens tokens; curated tokens are ALWAYS kept (and don't count toward the
    cap's non-curated budget). Ties broken by token for determinism.
    Returns (ranks {token: rank}, curated_kept set).
    """
    curated = set(curated)
    kept = {t: fr for t, fr in freq.items() if fr >= min_freq or t in curated}
    if max_tokens and len(kept) > max_tokens:
        cur = [t for t in kept if t in curated]
        noncur = sorted((t for t in kept if t not in curated),
                        key=lambda t: (-kept[t], t))
        room = max(0, max_tokens - len(cur))
        keep_set = set(cur) | set(noncur[:room])
        kept = {t: fr for t, fr in kept.items() if t in keep_set}
    # sort by frequency desc, then token asc for stable, deterministic ranks
    ordered = sorted(kept, key=lambda t: (-kept[t], t))
    ranks = {t: i + 1 for i, t in enumerate(ordered)}
    curated_kept = {t for t in curated if t in ranks}
    return ranks, curated_kept
