"""DataManager: config-driven, dependency-ordered cache builder.

Pipeline (ascending stage), over the config's enabled countries:
  stage 0  token sources contribute per-country {token: freq} (+curated flag)
  stage 1  finalize: sum freq across sources -> dense rank -> write tokens.txt
  stage 2  aliases (quarantine), syllables, surnames
  stage 3  confusions (1b) + name_models (1c), mined on the 'good' tab

Only `enabled_countries` are processed. The regional pool is NOT rebuilt here
(reused from the migrated cache) unless `build_regional` is set, in which case
only its derived stages (aliases) run over the existing regional tokens.
"""
from collections import Counter

from namecheck.data.config import (
    load_config, EVIDENCE_MIN_FREQ_BY_COUNTRY, EVIDENCE_MIN_FREQ_DEFAULT,
    COUNTRY_CC, cache_file,
)
from namecheck.data.tokens_io import finalize_ranks, write_tokens, read_tokens
from namecheck.data.loaders import REGISTRY, TOKEN_SOURCES


class DataManager:
    def __init__(self, config=None):
        self.config = config or load_config()
        # instantiate only enabled loaders once (memoized state e.g. XLSX reads)
        self.loaders = {name: REGISTRY[name]()
                        for name in REGISTRY if self.config.source_on(name)}

    # -- stage 0 + 1 -------------------------------------------------------
    def build_tokens(self, country):
        freq, curated = Counter(), set()
        for name in TOKEN_SOURCES:
            ld = self.loaders.get(name)
            if not ld or not ld.applies_to(country):
                continue
            contrib = ld.contribute(country)
            for tok, fr in contrib.items():
                freq[tok] += fr
            if ld.curated:
                curated.update(contrib.keys())
        if not freq:
            print(f"  {country}: no token contributions -- tokens.txt not written")
            return 0
        min_freq = EVIDENCE_MIN_FREQ_BY_COUNTRY.get(country, EVIDENCE_MIN_FREQ_DEFAULT)
        ranks, curated_kept = finalize_ranks(
            freq, curated, min_freq=min_freq,
            max_tokens=self.config.max_tokens_per_market)
        write_tokens(cache_file(country, "tokens.txt"), ranks, curated_kept)
        print(f"  {country}: {len(ranks)} tokens finalized "
              f"({len(curated_kept)} curated, min_freq={min_freq}, "
              f"cap={self.config.max_tokens_per_market})")
        return len(ranks)

    # -- stage 2 -----------------------------------------------------------
    def run_derived(self, country):
        for name in ("aliases", "syllables", "surnames"):
            ld = self.loaders.get(name)
            if ld and ld.applies_to(country):
                ld.build(country)

    # -- stage 3 -----------------------------------------------------------
    def _stage3_ctx(self):
        import load_public
        checker = load_public.build_checker_from_cache(
            self.config, with_confusions=False, with_name_models=False)
        train_pairs, _ = load_public._load_pairs("good")
        gold = load_public._load_gold_names("good")
        return {"checker": checker, "train_pairs": train_pairs, "gold": gold}

    def run_models(self, countries):
        names = [n for n in ("confusions", "name_models") if n in self.loaders]
        if not names:
            return
        ctx = self._stage3_ctx()
        for name in names:
            ld = self.loaders[name]
            for country in countries:
                if country in COUNTRY_CC and ld.applies_to(country):
                    ld.build(country, ctx)

    # -- orchestration -----------------------------------------------------
    def run(self):
        cfg = self.config
        countries = [c for c in cfg.enabled_countries]   # token build: countries only
        print(f"=== DataManager: building cache for {countries} ===")
        print(f"sources on: {[n for n in self.loaders]}")

        print("\n[stage 0+1] token sources -> finalize ranks")
        for c in countries:
            self.build_tokens(c)

        print("\n[stage 2] derived (aliases / syllables / surnames)")
        buckets = list(countries)
        if cfg.build_regional:
            buckets.append("regional")
        for c in buckets:
            self.run_derived(c)

        print("\n[stage 3] mined models (confusions / name_models)")
        self.run_models(countries)
        print("\n=== build complete ===")


def build(config=None):
    DataManager(config).run()
