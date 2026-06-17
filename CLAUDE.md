# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`namecheck` is a spell-checker / matcher for **romanized East & Southeast Asian names** (Indonesia, Thailand, Korea, Japan, Vietnam, Malaysia, Singapore, Philippines). The core insight driving the whole design: a mismatched Asian name is usually a *deterministic* artifact of competing romanization standards (`Choi`/`Choe`, `Nguyen`/`Nguyen`), not a random Western-style typo — so flat Levenshtein/Soundex fail, and the pipeline normalizes structure and romanization *before* scoring. See `DESIGN.md` for the full rationale and operations reference.

There is **no test framework or build step**. It is plain Python 3.9 run directly. External dependencies: `openpyxl` (corrections xlsx), `PyYAML` (config.yaml), and optionally `pykakasi` (JMnedict kana→romaji extraction). The `names-dataset` pip package is **no longer used** — its raw per-country CSVs live under `data/source/name_dataset/data/<CC>.csv`.

## Commands

```bash
# Build the per-country cache (data/cache/<country>/) for the countries/sources
# enabled in config.yaml. Dependency-ordered: token sources -> finalize ranks
# -> aliases/syllables/surnames -> confusions(1b)/name_models(1c).
python3 -m namecheck.data
python3 -m namecheck.data --config other.yaml   # alternate config

# Honest end-to-end evaluation: loads the cache (no building/mining at eval time),
# trains nothing — 1b/1c are read from cache. Trains were on 'good', scores 'test'.
python3 load_public.py
python3 load_public.py --serial           # single-process (debug; disables per-country parallelism)
python3 load_public.py --no-confusion     # skip loading 1b priors
python3 load_public.py --no-name-model    # skip loading 1c models
python3 load_public.py --optimize         # per-market SUSPECT_SCORE grid search (sampled, parallel)

# Per-name detection export (wrong/correct tabs) from the cache-built checker:
python3 export_test_results.py
```

`config.yaml` (repo root) drives everything: `enabled_countries`, the `sources` on/off map, `max_tokens_per_market`, `build_regional`. Only enabled countries are built and evaluated.

There is no single-test runner (no unit tests). Validate changes by rebuilding the cache (`python3 -m namecheck.data`) and running `load_public.py`, comparing the per-market coverage/detect/fpr table to the prior run.

## Architecture

### Two layers, two checkers

The `namecheck/` package is the algorithm + data pipeline. `namecheck/data/` is the config-driven cache builder (`DataManager` + one loader per source); `load_public.py` at repo root is now just the `TokenSpellChecker` + evaluation harness (it reads the cache, builds nothing).

**`namecheck/` — the 4-layer scoring pipeline** (numbered in module docstrings):
- `normalize.py` — **Layer 0 + 1**. Layer 0 is input triage: `is_plausible_name` (gate), `split_passengers` (multi-passenger `\\n` blobs), `extract_name` (pull a name out of CS prose), `classify_intent` (route a `(before, after)` pair to spelling / name_change / dob / document / gender / unroutable — non-spelling cases must never reach token checking). Layer 1 is `tokenize`/`fold` (title + particle stripping, diacritic folding, gender-marker stripping, adjacent-dedupe).
- `romanize.py` — **Layer 2**. `canonical(token, country)` collapses competing romanizations to one key per country (Korean surname equivalence table, Japanese Hepburn↔Kunrei, Indonesian Dutch/Arabic variants, Thai aspirates). Applied to *both* sides of any comparison, so over-merging only risks false-accepts.
- `features.py` — **Layer 3**. `NGramIndex`: inverted 3-gram index with Jaccard prefilter for fast candidate retrieval.
- `scorer.py` — **Layer 4**. `norm_score` = weighted Damerau-Levenshtein with phonetic substitution costs (cheap for `k/g`, `i/y`, silent `h`, etc.), normalized to [0,1].

**Two distinct checkers** — do not confuse them:
- `checker.NameChecker` / `score_pair` — **reference-based**. Compares a name against known references (or two names directly). Used when a correct reference exists. `score_pair` returns 0..1; `verdict` bands it accept(<0.15)/review(<0.40)/mismatch.
- `load_public.TokenSpellChecker` — **dictionary-based, no reference**. The production-shaped path: per-country token dictionaries with frequency ranks, returns `ok`/`variant`/`suspect`/`misspelled` per token. This is where the detection-improvement work (1a/1b/1c/2a) lives.

### Dictionary cache and rank semantics

`data/cache/<country>/tokens.txt` (and `data/cache/regional/tokens.txt`) are the runtime dictionaries: `token<TAB>rank<TAB>is_curated`, **lower rank = more common** (legacy 2-col `token<TAB>rank` is tolerated on read). Rank semantics (post unified-frequency refactor):
- **Rank is a dense rank derived from summed cross-source frequency** (1 = most common). Each token source contributes a per-country frequency (`names_dataset` = occurrence count, `wikidata` = summed sitelinks, `corrections`/`jmnedict` = count, `popular_names` = 1/listing); the manager sums them, drops non-curated tokens below a min-frequency floor (`EVIDENCE_MIN_FREQ_*`), caps to `max_tokens_per_market` (curated always kept), then dense-ranks.
- **`is_curated`** (3rd column) marks tokens from a gold/curated source (`corrections`, `popular_names`). It — not a `CURATED_RANK` sentinel — protects tokens from alias quarantine. The old `CURATED_RANK`/`NO_RANK` sentinels are retired from token ranking.
- Per-market scoring is **percentile-based** (`_compute_scores`): a token's score is its frequency percentile *within its own market*, so one global `SUSPECT_SCORE` threshold is comparable across markets. Per-market overrides live in `SUSPECT_SCORES_BY_COUNTRY` in `namecheck/data/config.py` (tuned via `--optimize`).

The cache is built by `DataManager` (`namecheck/data/`), not at eval time. `data/source/` holds the raw inputs (`name_dataset/data/<CC>.csv`, `wikidata/`, `JMnedict.xml`, the corrections xlsx, fetched `popular_names/`); `data/cache/<country>/` holds the processed per-country caches the checker reads. All shared constants/paths live in `namecheck/data/config.py`.

### Detection-improvement work (the active research track)

`DESIGN.md` (§4 techniques, §7 opportunities) is the roadmap; implemented pieces:
- **1a positional slot grammar** (`TokenSpellChecker.slots`, `surnames_{vietnam,korea}.txt`) — first token of a multi-token VN/KR name must be a valid surname; stands down when a later token is the surname (given-first order).
- **1b confusion-pair priors** (`namecheck/confusion.py`, `confusions_*.tsv`, `confusion_ops_*.tsv`) — mined from CS correction logs; an in-dict token on the high-risk side of a frequent confusion is downgraded to soft `suspect`.
- **1c full-name probability model** (`namecheck/name_model.py`, `namemodel_*.json`) — per-country positional-unigram + bigram model flagging structural anomalies (duplicated surname, improbable sequence). **Threshold is calibrated on held-out gold names**, not training names — calibrating on training data false-flags ~84% of real names.
- **2a typo-alias quarantine** (`load_aliases.py`, `aliases_*.txt`) — removes typo tokens that pollute the dictionary and records them as `typo -> name`; checker returns `misspelled` with the real name.
- **3a intent routing** — `classify_intent` wired in front of evaluation.

Not yet implemented: 2b (closed-class syllable validation), 2c (minimum-evidence threshold), 3c (rule-set by name not booking origin).

### Honesty discipline in evaluation

The corrections xlsx is both the mining corpus and the eval set, so **train/test isolation is load-bearing**. The `good` and `test` tabs are verified disjoint (checked by `case_number`/`booking_id`). Priors (1b), gold-merge (`load_corrections.py`), and name models (1c) train on `good`; `evaluate()` scores `test` only. When mining and eval share a corpus, use k-fold cross-validation (`confusion_cv` in `evaluate`) — never report numbers where the model saw the test rows.
```
