"""Source A: philipperemy/name-dataset raw per-country CSVs.

Raw: data/source/name_dataset/data/<CC>.csv, rows `first,last,gender,cc`
(no header, duplicates kept). Frequency = token occurrence count across first
and last names. NOTE: the dump has no TH/VN files (those markets rely on
wikidata + corrections); a missing CC contributes nothing.
"""
import csv
import os
from collections import Counter

from namecheck.data.config import source_dir
from namecheck.data.loaders.base import TokenLoader, valid_tokens, cc_for


class NamesDatasetLoader(TokenLoader):
    name = "names_dataset"
    stage = 0
    curated = False

    def _csv_path(self, country):
        cc = cc_for(country)
        return os.path.join(source_dir("name_dataset"), "data", f"{cc}.csv") if cc else None

    def contribute(self, country):
        path = self._csv_path(country)
        if not path or not os.path.exists(path):
            print(f"    names_dataset: no raw CSV for {country} ({path}) -- skipped")
            return {}
        freq = Counter()
        n_rows = 0
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                n_rows += 1
                for field in (row[0], row[1]):   # first, last
                    for tok in valid_tokens(field):
                        freq[tok] += 1
        print(f"    names_dataset[{country}]: {n_rows} rows -> {len(freq)} tokens")
        return dict(freq)
