"""Source: CS-verified gold corrections (XLSX 'good' tab).

nameAfter strings are gold by definition, so their tokens are curated. Frequency
= occurrence count across the 'good' tab (popular gold names recur). The 'test'
tab is never read here (it would leak into evaluation).
"""
from collections import Counter

from namecheck import split_passengers
from namecheck.data.config import XLSX_PATH, COUNTRY_CC
from namecheck.data.loaders.base import TokenLoader, valid_tokens


class CorrectionsLoader(TokenLoader):
    name = "corrections"
    stage = 0
    curated = True

    def __init__(self):
        self._freq = None   # memoized {country: Counter}

    def _load_all(self):
        import openpyxl
        wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
        ws = wb["good"]
        it = ws.iter_rows(values_only=True)
        idx = {h: i for i, h in enumerate(next(it))}
        freq = {c: Counter() for c in COUNTRY_CC}
        for r in it:
            a = str(r[idx["nameAfter"]] or "").strip()
            c = str(r[idx["origin_country"]] or "").strip().lower()
            if not a or c not in COUNTRY_CC:
                continue
            for name in (split_passengers(a) or [a]):
                for tok in valid_tokens(name):
                    freq[c][tok] += 1
        wb.close()
        self._freq = freq

    def contribute(self, country):
        if self._freq is None:
            self._load_all()
        fr = dict(self._freq.get(country, {}))
        print(f"    corrections[{country}]: {len(fr)} gold tokens")
        return fr
