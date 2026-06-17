"""1a. Curated surname inventories (VN/KR) — passthrough.

These lists are hand-curated, not built; this loader only verifies the cache
file is present (migration / manual curation provides it). It never fetches or
generates, so a missing file is a warning, not an error.
"""
import os

from namecheck.data.config import cache_file
from namecheck.data.loaders.base import StageLoader


class SurnamesLoader(StageLoader):
    name = "surnames"
    stage = 2
    scope = {"vietnam", "korea"}

    def build(self, country, ctx=None):
        path = cache_file(country, "surnames.txt")
        if os.path.exists(path):
            n = sum(1 for ln in open(path, encoding="utf-8") if ln.strip())
            print(f"    surnames[{country}]: present ({n} surnames)")
        else:
            print(f"    surnames[{country}]: MISSING {path} -- curate or migrate it")
