"""B: curated romanized Korean given-name list (korea only, curated tier).

Reads a hand-supplied given-name list from data/source/kr_given_names/ (any
.csv/.txt files). Each line is a given name in hangul or already romanized,
optionally `name,count`. Hangul is romanized with unidecode; frequency = count
if given else 1. Curated, so these gain real ranks and protection — they sharpen
suggestion/ranking quality for common given names (complements the syllable
acceptor, which only validates plausibility).

No reliable public auto-fetch source, so this is manual-populate: drop a list
(e.g. romanized KOSIS / court baby-name statistics) into the directory. Absent
directory -> contributes nothing.
"""
import csv
import os

from unidecode import unidecode

from namecheck.data.config import source_dir
from namecheck.data.loaders.base import TokenLoader, valid_tokens


def _is_hangul(ch):
    return "가" <= ch <= "힣"


class KrGivenNamesLoader(TokenLoader):
    name = "kr_given_names"
    stage = 0
    curated = True
    scope = {"korea"}

    def _dir(self):
        return source_dir("kr_given_names")

    def contribute(self, country):
        if country != "korea":
            return {}
        d = self._dir()
        if not os.path.isdir(d):
            print(f"    kr_given_names: no {d} -- skipped (manual-populate)")
            return {}
        freq = {}
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".csv", ".txt")):
                continue
            with open(os.path.join(d, fn), encoding="utf-8-sig", newline="") as f:
                for row in csv.reader(f):
                    if not row or not row[0].strip():
                        continue
                    name = row[0].strip()
                    try:
                        cnt = int(row[1]) if len(row) > 1 and row[1] else 1
                    except ValueError:
                        cnt = 1
                    if any(_is_hangul(c) for c in name):
                        name = unidecode(name)
                    for tok in valid_tokens(name):
                        freq[tok] = freq.get(tok, 0) + cnt
        print(f"    kr_given_names[korea]: {len(freq)} curated given tokens")
        return freq
