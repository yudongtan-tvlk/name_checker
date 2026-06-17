"""Shared constants, paths, and config.yaml loader for the data pipeline.

This module is the single source of truth for the constants that used to live
in load_public.py (COUNTRY_CC, ranks, scoring thresholds, surname/evidence
tables) plus the cache/source path helpers. Both the data loaders and the
checker/eval (load_public.py) import from here, so the layout and tuning live
in one place.
"""
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --------------------------------------------------------------------------
# Filesystem layout
# --------------------------------------------------------------------------
SOURCE_ROOT = os.path.join(ROOT, "data", "source")   # raw downloads / inputs
CACHE_ROOT = os.path.join(ROOT, "data", "cache")      # processed per-country cache
CONFIG_PATH = os.path.join(ROOT, "config.yaml")

# The CS-corrections workbook (disjoint 'good' train / 'test' eval tabs).
XLSX_PATH = os.path.join(SOURCE_ROOT, "Correction Name 20250101-20260611 filtered.xlsx")

# Traveloka traveller-name booking sample (tvlk_bookings token source).
TVLK_BOOKINGS_PATH = os.path.join(SOURCE_ROOT, "tvlk_bookings.xlsx")


def cache_dir(country):
    """data/cache/<country>/ — also accepts 'regional'."""
    return os.path.join(CACHE_ROOT, country)


def cache_file(country, name):
    """e.g. cache_file('vietnam', 'tokens.txt') -> data/cache/vietnam/tokens.txt"""
    return os.path.join(CACHE_ROOT, country, name)


def source_dir(name=""):
    return os.path.join(SOURCE_ROOT, name) if name else SOURCE_ROOT


# --------------------------------------------------------------------------
# Country tables
# --------------------------------------------------------------------------
COUNTRY_CC = {
    "indonesia": "ID", "thailand": "TH", "korea": "KR", "japan": "JP",
    "vietnam": "VN", "malaysia": "MY", "singapore": "SG", "philippines": "PH",
}
# Regional fallback pool: names-dataset has NO country tags for TH/VN, and
# diaspora names (e.g. Nguyen) are tagged under MY/SG/US. The regional pool is
# the union of these Asian country tags.
REGIONAL_CCS = {"ID", "TH", "KR", "JP", "VN", "MY", "SG", "PH",
                "CN", "HK", "TW", "MO", "BN", "KH"}

# --------------------------------------------------------------------------
# Rank / scoring constants
# --------------------------------------------------------------------------
# rank: lower = more common (a dense rank derived from summed frequency).
NO_RANK = 1_000_000        # sentinel: present but no frequency signal
CURATED_RANK = 5_000       # legacy sentinel (pre-refactor caches); superseded
                           # by the is_curated provenance flag for new builds.
LAMBDA = 0.15              # weight of popularity prior in suggestion ranking
SUSPECT_SCORE = 10.0       # default: tokens below this percentile can be 'suspect'
COMMON_SCORE = 80.0        # anchor must be above this percentile to trigger suspect
SUSPECT_EDIT = 0.20        # ...within this canonical edit distance
SUSPECT_NEAR_EDIT = 0.12   # tighter bound for the bottom-percentile "rare in-dict
                           # token is a typo of a close common name" path -- 0.20
                           # over-fires on rare-but-valid multi-ethnic names (SG)

# Per-market optimal SUSPECT_SCORE (grid search, --optimize). Objective:
# detect + corr@1-all - fpr (name-level false-positive rate penalized).
SUSPECT_SCORES_BY_COUNTRY = {
    "indonesia":    1,
    "thailand":     1,
    "korea":        2,
    "japan":        1,
    "vietnam":      1,
    "malaysia":     1,
    "singapore":   10,
    "philippines":  1,
}

# 1a. Positional slot grammar surname inventories (filename within a cache dir).
SURNAME_FILES = {
    "vietnam": "surnames.txt",
    "korea":   "surnames.txt",
}

# 1b. char-level confusion partner must beat the token's percentile by this margin.
CONFUSION_SCORE_GAP = 15.0

# 3c. below this fraction of native-fitting tokens, a name on a closed-class
# (VN/KR) booking is treated as foreign -> neutral 'regional' rule-set.
ROUTE_NATIVE_MIN = 0.5

# 2c (read-time, legacy/back-compat): drop tokens whose rank is >= cutoff at
# _ensure time. With the new dense-rank scheme nothing here is >= NO_RANK, so
# this is a no-op on fresh caches and preserves old-cache behavior.
EVIDENCE_CUTOFF_BY_COUNTRY = {
    "indonesia": NO_RANK,
    "japan":     NO_RANK,
    "korea":     NO_RANK,
}

# 2c (build-time): drop NON-curated tokens whose summed frequency is below this
# floor before dense-ranking, so unverified long-tail singletons stop being
# silently accepted (a token seen once in millions of name_dataset rows is
# almost certainly a typo/OCR artifact). Curated tokens are never dropped.
# Default floor = 2 (drop pure singletons). Wikidata-only markets (TH/VN have no
# name_dataset file) stay at 1: their data is sparse and sitelink-weighted, so a
# floor would gut coverage.
EVIDENCE_MIN_FREQ_DEFAULT = 2
EVIDENCE_MIN_FREQ_BY_COUNTRY = {
    "thailand": 1,
    "vietnam":  1,
}

# Cap per-market dictionary size: keep the most-frequent MAX_TOKENS_PER_MARKET
# tokens (+ all curated). Bounds the raw name_dataset tail (MY/SG/PH balloon to
# 100k-630k otherwise) so the NGram index / alias quarantine / suggestion stay
# tractable. A token ranked beyond this is negligibly common.
MAX_TOKENS_PER_MARKET = 150_000

# --------------------------------------------------------------------------
# config.yaml
# --------------------------------------------------------------------------
_DEFAULT_CONFIG = {
    "enabled_countries": list(COUNTRY_CC),
    "sources": {
        "names_dataset": True, "popular_names": True, "jmnedict": True,
        "wikidata": True, "corrections": True, "tvlk_bookings": True,
        "aliases": True, "syllables": True, "confusions": True,
        "name_models": True, "surnames": True,
    },
    "build_regional": False,
}


class Config:
    def __init__(self, data):
        self.enabled_countries = [c.lower() for c in data.get("enabled_countries", [])]
        self.sources = dict(_DEFAULT_CONFIG["sources"])
        self.sources.update(data.get("sources", {}))
        self.build_regional = bool(data.get("build_regional", False))
        self.max_tokens_per_market = int(
            data.get("max_tokens_per_market", MAX_TOKENS_PER_MARKET))

    def source_on(self, name):
        return bool(self.sources.get(name, False))

    def buckets(self):
        """Countries to process, plus 'regional' when build_regional is set."""
        b = list(self.enabled_countries)
        if self.build_regional and "regional" not in b:
            b.append("regional")
        return b


def load_config(path=CONFIG_PATH):
    """Parse config.yaml; fall back to defaults if absent."""
    if not os.path.exists(path):
        return Config(_DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config(data)
