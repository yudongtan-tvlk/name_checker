"""Wikidata per-country labels. Frequency = sum of sitelinks.

Raw: data/source/wikidata/wikidata_<country>.csv (header `label,sitelinks`).
Sitelinks are a popularity proxy, so a token's frequency contribution is the
sum of sitelinks over every person whose label contains it. When the local CSV
is absent it is fetched from the WDQS SPARQL endpoint and saved (source-first,
then external).
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

from namecheck.data.config import source_dir
from namecheck.data.loaders.base import TokenLoader, valid_tokens

SITELINK_FLOOR = 1   # a label with 0 sitelinks still attests the name once

# --- WDQS fetch -----------------------------------------------------------
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = ("namecheck-dictionary-builder/0.2 "
              "(OTA name-validation project; contact: data-eng@example.com)")
PAGE_SIZE = 5000
COUNTRY_QID = {
    "indonesia": "Q252", "thailand": "Q869", "vietnam": "Q881",
    "malaysia": "Q833", "singapore": "Q334", "philippines": "Q928",
    "japan": "Q17", "korea": "Q884",
}
COUNTRY_LANG = {"vietnam": "vi"}   # native labels have better coverage for VN
_QUERY = """
SELECT ?label ?sitelinks WHERE {{
  ?person wdt:P31 wd:Q5 ;
          wdt:P27 wd:{qid} ;
          wikibase:sitelinks ?sitelinks ;
          rdfs:label ?label .
  FILTER(LANG(?label) = "{lang}")
}}
LIMIT {limit} OFFSET {offset}
"""


def _fetch_page(qid, lang, offset):
    url = (ENDPOINT + "?format=json&query="
           + urllib.parse.quote(_QUERY.format(qid=qid, lang=lang,
                                              limit=PAGE_SIZE, offset=offset)))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return [(b["label"]["value"], int(b["sitelinks"]["value"]))
                    for b in data["results"]["bindings"]]
        except json.JSONDecodeError:
            return None                      # malformed page -> skip
        except Exception:
            if attempt == 3:
                raise
            time.sleep(10 * (2 ** attempt))   # 10s, 20s, 40s


def _fetch_country(country, out_path, lang=None):
    qid = COUNTRY_QID.get(country)
    if not qid:
        return False
    if lang is None:
        lang = COUNTRY_LANG.get(country, "en")
    print(f"    wikidata: fetching {country} ({qid}, lang={lang}) from WDQS ...")
    rows, offset, consecutive_skips = [], 0, 0
    while True:
        page = _fetch_page(qid, lang, offset)
        if page is None:
            consecutive_skips += 1
            offset += PAGE_SIZE
            if consecutive_skips >= 5:
                break
            continue
        consecutive_skips = 0
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "sitelinks"])
        w.writerows(rows)
    print(f"    wikidata: fetched {len(rows)} people -> {out_path}")
    return True


class WikidataLoader(TokenLoader):
    name = "wikidata"
    stage = 0
    curated = False

    def _csv_path(self, country):
        return os.path.join(source_dir("wikidata"), f"wikidata_{country}.csv")

    def contribute(self, country):
        path = self._csv_path(country)
        if not os.path.exists(path):
            try:
                if not _fetch_country(country, path):
                    print(f"    wikidata: no QID for {country} -- skipped")
                    return {}
            except Exception as e:
                print(f"    wikidata: WDQS fetch failed for {country} ({e}) -- skipped")
                return {}
        freq = {}
        n_rows = 0
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                label = row.get("label") or ""
                try:
                    sl = int(row.get("sitelinks") or 0)
                except ValueError:
                    sl = 0
                weight = max(sl, SITELINK_FLOOR)
                n_rows += 1
                for tok in valid_tokens(label):
                    freq[tok] = freq.get(tok, 0) + weight
        print(f"    wikidata[{country}]: {n_rows} people -> {len(freq)} tokens "
              f"(freq = summed sitelinks)")
        return freq
