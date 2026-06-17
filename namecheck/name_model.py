"""1c. Full-name probability model — one model per country.

A simple count-based positional-unigram + bigram model trained on the
verified internal corpus (gold corrected names). It scores a whole name
and flags structural anomalies that token-membership checks cannot see:

  - duplicated token (`Nguyen Nguyen thi hai yen`),
  - improbable token sequence (a transition never seen between two
    otherwise-common tokens),
  - a common token sitting in a slot it never occupies in real names.

No ML infrastructure: two Counters and add-k smoothing. The anomaly
threshold is the low percentile of the model's own training-name scores,
so each country is calibrated to its own name distribution.
"""
import json
import math
import os
from collections import Counter

SMOOTH_K = 0.5          # add-k smoothing on both models
POS_WEIGHT = 0.5        # blend of positional vs bigram log-prob
ANOMALY_PCTILE = 5.0    # names below this percentile of train scores are odd
MIN_TOK_LEN = 2         # ignore single-char initials in duplicate detection
BOUNDARY = "^"          # sequence start/end sentinel


def _slot(i, n):
    if n <= 1:
        return "solo"
    if i == 0:
        return "first"
    if i == n - 1:
        return "last"
    return "mid"


class NameModel:
    def __init__(self):
        self.pos_counts = {}        # slot -> Counter({token: n})
        self.pos_tot = Counter()    # slot -> total
        self.bg_counts = Counter()  # (prev, cur) -> n
        self.from_counts = Counter()  # prev -> n (times seen as a 'from')
        self.vocab = set()
        self.threshold = None       # log-prob below this => anomalous
        self.n_train = 0

    # -- training -------------------------------------------------------
    def fit(self, token_lists, calib_frac=0.2):
        """Train on (1-calib_frac) of names; calibrate the anomaly threshold
        on the held-out remainder. Calibrating on training names themselves
        measures memorization (their bigrams were all seen) and sets the
        threshold uselessly high -> ~100% false-flags on real held-out names."""
        names = [t for t in token_lists if t]
        n = len(names)
        n_cal = int(n * calib_frac)
        # deterministic split: every 1/calib_frac-th name is held out
        cal_idx = set(range(0, n, max(1, int(1 / calib_frac)))) if n_cal else set()
        train = [t for i, t in enumerate(names) if i not in cal_idx]
        calib = [names[i] for i in sorted(cal_idx)] or train
        for toks in train:
            self._add(toks)
        self.vocab.discard(BOUNDARY)
        scores = sorted(self.name_logprob(t) for t in calib)
        if scores:
            idx = max(0, min(len(scores) - 1,
                             int(len(scores) * ANOMALY_PCTILE / 100.0)))
            self.threshold = scores[idx]
        self.n_train = len(train)
        return self

    def _add(self, toks):
        n = len(toks)
        for i, t in enumerate(toks):
            slot = _slot(i, n)
            self.pos_counts.setdefault(slot, Counter())[t] += 1
            self.pos_tot[slot] += 1
            self.vocab.add(t)
        seq = [BOUNDARY] + list(toks) + [BOUNDARY]
        for p, c in zip(seq, seq[1:]):
            self.bg_counts[(p, c)] += 1
            self.from_counts[p] += 1

    # -- scoring --------------------------------------------------------
    def _pos_lp(self, tok, slot):
        v = len(self.vocab) + 1
        num = self.pos_counts.get(slot, {}).get(tok, 0) + SMOOTH_K
        den = self.pos_tot.get(slot, 0) + SMOOTH_K * v
        return math.log(num / den)

    def _bg_lp(self, prev, cur):
        v = len(self.vocab) + 1
        num = self.bg_counts.get((prev, cur), 0) + SMOOTH_K
        den = self.from_counts.get(prev, 0) + SMOOTH_K * v
        return math.log(num / den)

    def name_logprob(self, toks):
        """Mean per-token blended log-prob; higher = more name-like."""
        if not toks:
            return float("-inf")
        n = len(toks)
        pos = sum(self._pos_lp(t, _slot(i, n)) for i, t in enumerate(toks)) / n
        seq = [BOUNDARY] + list(toks) + [BOUNDARY]
        bg = sum(self._bg_lp(p, c) for p, c in zip(seq, seq[1:])) / (n + 1)
        return POS_WEIGHT * pos + (1 - POS_WEIGHT) * bg

    def anomalies(self, toks):
        """Structural flags as (type, detail) tuples; empty if name looks fine."""
        flags = []
        real = [t for t in toks if len(t) >= MIN_TOK_LEN]
        dupes = [t for t, c in Counter(real).items() if c >= 2]
        if dupes:
            flags.append(("duplicate", ",".join(sorted(dupes))))
        if self.threshold is not None and toks:
            lp = self.name_logprob(toks)
            if lp < self.threshold:
                flags.append(("low_prob", f"{lp:.2f}<{self.threshold:.2f}"))
        return flags

    def is_anomalous(self, toks):
        return bool(self.anomalies(toks))

    # -- persistence ----------------------------------------------------
    def to_dict(self):
        return {
            "pos_counts": {s: dict(c) for s, c in self.pos_counts.items()},
            "pos_tot": dict(self.pos_tot),
            "bg_counts": {f"{p}\t{c}": n for (p, c), n in self.bg_counts.items()},
            "from_counts": dict(self.from_counts),
            "vocab": sorted(self.vocab),
            "threshold": self.threshold,
            "n_train": self.n_train,
        }

    @classmethod
    def from_dict(cls, d):
        m = cls()
        m.pos_counts = {s: Counter(c) for s, c in d["pos_counts"].items()}
        m.pos_tot = Counter(d["pos_tot"])
        m.bg_counts = Counter()
        for k, n in d["bg_counts"].items():
            p, c = k.split("\t")
            m.bg_counts[(p, c)] = n
        m.from_counts = Counter(d["from_counts"])
        m.vocab = set(d["vocab"])
        m.threshold = d["threshold"]
        m.n_train = d["n_train"]
        return m

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
