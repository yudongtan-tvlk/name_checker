"""C: Korean given names from Wikidata native (ko) labels.

The default wikidata loader fetches `en` labels; many Korean people only have a
hangul `ko` label. This loader fetches those, splits off the surname (the first
hangul syllable) and romanizes the GIVEN part with unidecode -> a romanized
given-name token, weighted by sitelinks. Korea only (hangul).

Raw: data/source/wikidata/wikidata_korea_ko.csv (label,sitelinks); fetched from
WDQS if absent.
"""
import csv
import os

from unidecode import unidecode

from namecheck.data.config import source_dir
from namecheck.data.loaders.base import TokenLoader, valid_tokens
from namecheck.data.loaders.wikidata import _fetch_country, SITELINK_FLOOR


def _is_hangul(ch):
    return "가" <= ch <= "힣"


class WikidataKoLoader(TokenLoader):
    name = "wikidata_ko"
    stage = 0
    curated = False
    scope = {"korea"}

    def _csv_path(self):
        return os.path.join(source_dir("wikidata"), "wikidata_korea_ko.csv")

    def contribute(self, country):
        if country != "korea":
            return {}
        path = self._csv_path()
        if not os.path.exists(path):
            try:
                if not _fetch_country("korea", path, lang="ko"):
                    return {}
            except Exception as e:
                print(f"    wikidata_ko: WDQS fetch failed ({e}) -- skipped")
                return {}
        freq = {}
        n = 0
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                label = (row.get("label") or "").replace(" ", "")
                try:
                    sl = int(row.get("sitelinks") or 0)
                except ValueError:
                    sl = 0
                weight = max(sl, SITELINK_FLOOR)
                # surname = first hangul syllable; given = the rest
                if len(label) < 2 or not _is_hangul(label[0]):
                    continue
                given = label[1:]
                if not given:
                    continue
                n += 1
                for tok in valid_tokens(unidecode(given)):
                    freq[tok] = freq.get(tok, 0) + weight
        print(f"    wikidata_ko[korea]: {n} ko labels -> {len(freq)} given tokens")
        return freq
