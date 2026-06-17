"""Evaluate the namecheck prototype against the BQ correction-case CSV.

Three benchmarks:
1. Pair verification (positives): score(nameBefore, nameAfter) — real
   misspelling pairs should fall in accept/review bands.
2. Negative controls: score(nameBefore, OTHER person's nameAfter, same
   country) — different people should land in the mismatch band.
3. Suggestion: dictionary = all correct names per country; given the
   misspelled input, is the right name the top-1 suggestion?
"""
import csv
import random
import sys
from collections import defaultdict

from namecheck import score_pair, verdict, NameChecker, is_plausible_name
from namecheck import split_passengers, extract_name, classify_intent
from namecheck.normalize import fold

CSV = "bq-results-20260603-032146-1780456933979.csv"


def _recover_pair(before: str, after: str):
    """Use L0 extraction to recover a (before, after) pair from messy fields.
    Returns (extracted_before, extracted_after) or (None, None) if unrecoverable.
    """
    # Split multi-passenger blobs — take only single-passenger rows for now
    parts_b = split_passengers(before)
    parts_a = split_passengers(after)
    if len(parts_b) > 1 or len(parts_a) > 1:
        return None, None   # multi-pax: skip (would need alignment logic)

    b = parts_b[0] if parts_b else before
    a = parts_a[0] if parts_a else after

    if is_plausible_name(b) and is_plausible_name(a):
        return b, a

    # Try name extraction from free-text side(s)
    eb = b if is_plausible_name(b) else extract_name(b)
    ea = a if is_plausible_name(a) else extract_name(a)
    if eb and ea and is_plausible_name(eb) and is_plausible_name(ea):
        return eb, ea

    return None, None


def load_pairs(path=CSV):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    pairs = []
    skipped_intent = 0
    skipped_unrecoverable = 0
    for r in rows:
        b, a, c = r["nameBefore"].strip(), r["nameAfter"].strip(), r["origin_country"].strip().lower()
        intent = classify_intent(b, a)
        if intent != "spelling":
            skipped_intent += 1
            continue
        if is_plausible_name(b) and is_plausible_name(a):
            pairs.append((b, a, c))
            continue
        eb, ea = _recover_pair(b, a)
        if eb and ea:
            pairs.append((eb, ea, c))
        else:
            skipped_unrecoverable += 1
    print(f"rows={len(rows)}  spelling-intent={len(rows)-skipped_intent}  "
          f"recovered={len(pairs)}  skipped(non-spelling={skipped_intent}, "
          f"unrecoverable={skipped_unrecoverable})\n")
    return rows, pairs


def main():
    rows, pairs = load_pairs()
    print(f"rows={len(rows)}  clean evaluable pairs={len(pairs)} "
          f"({len(pairs)/len(rows):.0%}); rest need Layer-0 extraction\n")

    # ---- 1. positive pairs -------------------------------------------------
    by_country = defaultdict(lambda: defaultdict(int))
    overall = defaultdict(int)
    worst = []
    for before, after, ctry in pairs:
        s = score_pair(before, after, ctry)
        v = verdict(s)
        by_country[ctry][v] += 1
        overall[v] += 1
        worst.append((s, ctry, before, after))
    n = len(pairs)
    print("== 1. Positive pairs (customer misspelling vs corrected name) ==")
    print(f"{'country':12} {'n':>4} {'accept':>8} {'review':>8} {'mismatch':>9}")
    for ctry in sorted(by_country, key=lambda c: -sum(by_country[c].values())):
        d, t = by_country[ctry], sum(by_country[ctry].values())
        print(f"{ctry:12} {t:>4} {d['accept']/t:>7.1%} {d['review']/t:>7.1%} {d['mismatch']/t:>8.1%}")
    print(f"{'TOTAL':12} {n:>4} {overall['accept']/n:>7.1%} "
          f"{overall['review']/n:>7.1%} {overall['mismatch']/n:>8.1%}")
    print(f"\ncaught (accept+review): {(overall['accept']+overall['review'])/n:.1%}")
    print("\n10 hardest positives (highest score):")
    for s, c, b, a in sorted(worst, reverse=True)[:10]:
        print(f"  {s:.2f} [{c}] {b!r} -> {a!r}")

    # ---- 2. negative controls ---------------------------------------------
    rng = random.Random(42)
    grouped = defaultdict(list)
    for b, a, c in pairs:
        grouped[c].append((b, a))
    neg = defaultdict(int)
    n_neg = 0
    for c, lst in grouped.items():
        if len(lst) < 2:
            continue
        idx = list(range(len(lst)))
        shuffled = idx[1:] + idx[:1]  # derangement
        for i, j in zip(idx, shuffled):
            b, a = lst[i][0], lst[j][1]
            if fold(b) == fold(a):
                continue
            neg[verdict(score_pair(b, a, c))] += 1
            n_neg += 1
    print(f"\n== 2. Negative controls (different people, same country) n={n_neg} ==")
    print(f"false-accept: {neg['accept']/n_neg:.1%}   review: {neg['review']/n_neg:.1%}   "
          f"correctly mismatched: {neg['mismatch']/n_neg:.1%}")

    # ---- 3. suggestion / retrieval ----------------------------------------
    nc = NameChecker()
    for _, after, c in pairs:
        nc.add_reference(after, c)
    top1 = top3 = total = 0
    changed = [(b, a, c) for b, a, c in pairs if fold(b) != fold(a)]
    for before, after, c in changed:
        res = nc.check(before, c)
        names = [fold(s["name"]) for s in res["suggestions"]]
        gold = fold(after)
        total += 1
        if names and names[0] == gold:
            top1 += 1
        if gold in names[:3]:
            top3 += 1
    print(f"\n== 3. Suggestion ('Did you mean?') over {total} changed names ==")
    print(f"dictionary size: {sum(len(v) for v in grouped.values())} names")
    print(f"top-1 accuracy: {top1/total:.1%}   top-3 accuracy: {top3/total:.1%}")


if __name__ == "__main__":
    sys.exit(main())
