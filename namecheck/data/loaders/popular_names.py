"""Source B: sigpwned/popular-names-by-country-dataset.

Curated CC-licensed lists (~4.6k names incl. romanizations) = a high-precision
"definitely valid" tier, so tokens are curated. Frequency = 1 per listing.
Raw: data/source/popular_names/common-{forenames,surnames}-by-country.csv;
fetched from GitHub if absent.
"""
import csv
import os
import urllib.request
from collections import Counter

from namecheck.data.config import source_dir, COUNTRY_CC
from namecheck.data.loaders.base import TokenLoader, valid_tokens

_FILES = ("common-forenames-by-country.csv", "common-surnames-by-country.csv")
_BASE_URLS = (
    "https://raw.githubusercontent.com/sigpwned/popular-names-by-country-dataset/master/",
    "https://raw.githubusercontent.com/sigpwned/popular-names-by-country-dataset/main/",
)


class PopularNamesLoader(TokenLoader):
    name = "popular_names"
    stage = 0
    curated = True

    def __init__(self):
        self._freq = None

    def _dir(self):
        return source_dir("popular_names")

    def _ensure_files(self):
        d = self._dir()
        os.makedirs(d, exist_ok=True)
        for fn in _FILES:
            path = os.path.join(d, fn)
            if os.path.exists(path):
                continue
            for base in _BASE_URLS:
                try:
                    print(f"    popular_names: fetching {fn} ...")
                    urllib.request.urlretrieve(base + fn, path)
                    break
                except Exception as e:           # try next branch / give up
                    last = e
            else:
                print(f"    popular_names: could not fetch {fn} ({last}) -- skipped")

    def _load_all(self):
        self._ensure_files()
        cc_to_country = {v: k for k, v in COUNTRY_CC.items()}
        freq = {c: Counter() for c in COUNTRY_CC}
        for fn in _FILES:
            path = os.path.join(self._dir(), fn)
            if not os.path.exists(path):
                continue
            # utf-8-sig: the upstream CSVs carry a BOM on the first header.
            with open(path, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    cc = (row.get("Country") or row.get("Country Code")
                          or row.get("country_code") or "").upper()
                    country = cc_to_country.get(cc)
                    if not country:
                        continue
                    name = row.get("Romanized Name") or row.get("Localized Name") or ""
                    for tok in valid_tokens(name):
                        freq[country][tok] += 1
        self._freq = freq

    def contribute(self, country):
        if self._freq is None:
            self._load_all()
        fr = dict(self._freq.get(country, {}))
        print(f"    popular_names[{country}]: {len(fr)} curated tokens")
        return fr
