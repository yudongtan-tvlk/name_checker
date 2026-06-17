"""1b. Confusion-pair priors mined from CS correction logs.

The CS corrections table is training data: aggregating (wrong, gold) token
pairs yields an empirical confusion table at two granularities:

  1. token level  — `an -> anh` seen verbatim in past corrections;
  2. char level   — recurring edit operations (`i->y`, h inserted after n,
                    `o->u`) that generalize to unseen token pairs.

At check time a token that is *valid by membership* but sits on the
high-risk side of a frequent confusion is downgraded to 'suspect' with the
confusion partner as the suggestion — a soft confirm, not a block. This is
the only mechanism that can catch errors which land on another valid name.
"""
from collections import Counter

MIN_TOKEN_SUPPORT = 2   # token-level pair: must recur in the logs
TOKEN_DOMINANCE = 2.0   # wrong->gold must outnumber gold->wrong by this factor
                        # (an<->anh corrections go both ways; only the side that
                        # is predominantly corrected AWAY FROM is high-risk)
MIN_CHAR_SUPPORT = 3    # char-level op: absolute floor
CHAR_OP_SHARE = 0.005   # ...and at least this share of the country's mined ops
                        # (absolute counts don't transfer across corpus sizes)
MAX_OPS = 2             # token pairs further apart than this are not "confusions"
MAX_APPLY_OPS = 1       # char-level *application* allows only single-op jumps
                        # (2-op applications flag far too many valid names)


def edit_ops(wrong, gold):
    """Minimal edit script wrong -> gold as ops with one char of context.

    Ops: ('sub', a, b)     a in wrong replaced by b
         ('ins', left, c)  c inserted after `left` ('^' = word start)
         ('del', left, c)  c deleted, preceded by `left`
    """
    n, m = len(wrong), len(gold)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j - 1] + (wrong[i - 1] != gold[j - 1]),
                          D[i - 1][j] + 1,
                          D[i][j - 1] + 1)
    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if (i > 0 and j > 0 and wrong[i - 1] == gold[j - 1]
                and D[i][j] == D[i - 1][j - 1]):
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and D[i][j] == D[i - 1][j - 1] + 1:
            ops.append(("sub", wrong[i - 1], gold[j - 1]))
            i, j = i - 1, j - 1
        elif j > 0 and D[i][j] == D[i][j - 1] + 1:
            ops.append(("ins", wrong[i - 1] if i > 0 else "^", gold[j - 1]))
            j = j - 1
        else:
            ops.append(("del", wrong[i - 2] if i > 1 else "^", wrong[i - 1]))
            i = i - 1
    return ops


class ConfusionModel:
    def __init__(self):
        self.token_pairs = {}   # country -> {wrong: Counter({gold: n})}
        self.char_ops = {}      # country -> Counter({op: n})
        self._floors = {}       # country -> cached char-op support floor

    def mine(self, triples):
        """triples: iterable of (wrong_token, gold_token, country)."""
        for wrong, gold, country in triples:
            tp = self.token_pairs.setdefault(country, {})
            tp.setdefault(wrong, Counter())[gold] += 1
            ops = edit_ops(wrong, gold)
            if len(ops) <= MAX_OPS:
                co = self.char_ops.setdefault(country, Counter())
                for op in ops:
                    co[op] += 1
        return self

    def token_hit(self, tok, country):
        """Mined gold for tok if this confusion recurs AND tok is the
        predominantly-corrected-away-from side, else None."""
        tp = self.token_pairs.get(country, {})
        counts = tp.get(tok)
        if not counts:
            return None
        gold, n = counts.most_common(1)[0]
        if gold == tok or n < MIN_TOKEN_SUPPORT:
            return None
        n_rev = tp.get(gold, {}).get(tok, 0)
        if n < TOKEN_DOMINANCE * max(n_rev, 1):
            return None
        return gold

    def _op_floor(self, country):
        if country not in self._floors:
            total = sum(self.char_ops.get(country, {}).values())
            self._floors[country] = max(MIN_CHAR_SUPPORT,
                                        int(CHAR_OP_SHARE * total))
        return self._floors[country]

    def ops_confusable(self, wrong, cand, country):
        """True if wrong -> cand consists solely of frequent mined char ops."""
        co = self.char_ops.get(country)
        if not co:
            return False
        ops = edit_ops(wrong, cand)
        if not ops or len(ops) > MAX_APPLY_OPS:
            return False
        floor = self._op_floor(country)
        return all(co.get(op, 0) >= floor for op in ops)

    def save(self, cache_dir):
        """Write per-country TSV artifacts for production use."""
        import os
        for country, tp in sorted(self.token_pairs.items()):
            path = os.path.join(cache_dir, f"confusions_{country}.tsv")
            with open(path, "w") as f:
                for wrong in sorted(tp):
                    for gold, n in tp[wrong].most_common():
                        f.write(f"{wrong}\t{gold}\t{n}\n")
        for country, co in sorted(self.char_ops.items()):
            path = os.path.join(cache_dir, f"confusion_ops_{country}.tsv")
            with open(path, "w") as f:
                for (kind, a, b), n in co.most_common():
                    f.write(f"{kind}\t{a}\t{b}\t{n}\n")

    def load_country(self, country, confusions_path, ops_path):
        """Populate one country's slice from per-country TSV artifacts.

        Inverse of save() for a single country (the new per-country cache layout
        stores confusions.tsv + confusion_ops.tsv inside data/cache/<country>/).
        Returns self so calls can be chained across countries.
        """
        import os
        if os.path.exists(confusions_path):
            tp = self.token_pairs.setdefault(country, {})
            for line in open(confusions_path, encoding="utf-8"):
                line = line.rstrip("\n")
                if not line:
                    continue
                wrong, gold, n = line.split("\t")
                tp.setdefault(wrong, Counter())[gold] += int(n)
        if os.path.exists(ops_path):
            co = self.char_ops.setdefault(country, Counter())
            for line in open(ops_path, encoding="utf-8"):
                line = line.rstrip("\n")
                if not line:
                    continue
                kind, a, b, n = line.split("\t")
                co[(kind, a, b)] += int(n)
        return self

    @classmethod
    def load(cls, country_paths):
        """country_paths: {country: (confusions_path, ops_path)} -> model."""
        m = cls()
        for country, (cp, op) in country_paths.items():
            m.load_country(country, cp, op)
        return m
