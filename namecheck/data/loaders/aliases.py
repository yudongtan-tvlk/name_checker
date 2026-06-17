"""2a. Typo-alias quarantine (derived from the finalized token cache).

For each token T with a much-more-common near neighbor C, remove T from the
valid set and record `T -> C` in aliases.txt; the checker then returns
'misspelled' with C as the suggestion. Curated tokens (is_curated=1) are
protected, replacing the old rank==CURATED_RANK guard.
"""
import os

from namecheck.romanize import canonical
from namecheck.scorer import norm_score
from namecheck.features import NGramIndex
from namecheck.data.config import COUNTRY_CC, NO_RANK, cache_file
from namecheck.data.tokens_io import read_tokens, write_tokens
from namecheck.data.loaders.base import StageLoader

TYPO_RATIO = 50        # C must be >= 50x more frequent than T (rank ratio)
TYPO_EDIT = 0.15       # ...and within this canonical edit distance
TYPO_MIN_RANK = 200    # don't quarantine top-common tokens
CAND_K = 25


class AliasesLoader(StageLoader):
    name = "aliases"
    stage = 2

    def build(self, country, ctx=None):
        tok_path = cache_file(country, "tokens.txt")
        ranks, curated = read_tokens(tok_path)
        if not ranks:
            print(f"    aliases[{country}]: no tokens -- skipped")
            return
        rom_country = country if country in COUNTRY_CC else "indonesia"
        idx = NGramIndex()
        for t in ranks:
            idx.add(t)
        aliases = {}
        for tok, rank in ranks.items():
            if rank < TYPO_MIN_RANK or tok in curated or rank >= NO_RANK:
                continue
            ctok = canonical(tok, rom_country)
            best_c, best_rank = None, rank
            for c in idx.candidates(tok, top_k=CAND_K):
                if c == tok:
                    continue
                rc = ranks.get(c)
                if rc is None or rc >= best_rank:
                    continue
                if rank < TYPO_RATIO * rc:          # C not dominant enough
                    continue
                if norm_score(ctok, canonical(c, rom_country)) > TYPO_EDIT:
                    continue
                best_c, best_rank = c, rc
            if best_c is not None:
                aliases[tok] = best_c
        if aliases:
            apath = cache_file(country, "aliases.txt")
            os.makedirs(os.path.dirname(apath), exist_ok=True)
            with open(apath, "w", encoding="utf-8") as f:
                f.write("\n".join(f"{t}\t{c}" for t, c in sorted(aliases.items())))
            for t in aliases:
                del ranks[t]
            write_tokens(tok_path, ranks, curated)
        print(f"    aliases[{country}]: quarantined {len(aliases)} typos "
              f"({len(ranks)} tokens remain)")
