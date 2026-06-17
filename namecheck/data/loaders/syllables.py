"""2b. Closed-class syllable inventories (generated from phonotactics).

Vietnamese syllables (single-syllable reject test) and Korean syllables
(multi-syllable accept test) are enumerable; persist them to
data/cache/<country>/syllables.txt for the checker's closed-class logic.
"""
import os

from namecheck.closed_class import (
    generate_vietnamese_syllables, generate_korean_syllables,
    generate_japanese_mora,
)
from namecheck.data.config import cache_dir, cache_file
from namecheck.data.loaders.base import StageLoader

_GENERATORS = {
    "vietnam": generate_vietnamese_syllables,
    "korea": generate_korean_syllables,
    "japan": generate_japanese_mora,
}


class SyllablesLoader(StageLoader):
    name = "syllables"
    stage = 2
    scope = set(_GENERATORS)

    def build(self, country, ctx=None):
        gen = _GENERATORS.get(country)
        if gen is None:
            return
        syl = gen()
        os.makedirs(cache_dir(country), exist_ok=True)
        with open(cache_file(country, "syllables.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(syl)))
        print(f"    syllables[{country}]: {len(syl)} syllables")
