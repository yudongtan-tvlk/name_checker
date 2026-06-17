# namecheck — Design & Operations

Single consolidated reference for the romanized Asian-name spell checker.
Supersedes the original working notes: `asian_name_validation_pipeline_blueprint.md`,
`EXECUTION_PLAN.md`, `PLAN_KR_FALSE_POSITIVES.md`, `PLAN_KR_GIVEN_NAME_COVERAGE.md`,
`PROPOSAL_DETECTION_IMPROVEMENTS.md`, `PUBLIC_DATA_GUIDE.md`, and `TEST_REPORT.md`
(all folded in here; the originals are removed).

---

## 1. Goal

Validate, spell-check, and correct **romanized East & Southeast Asian names**
(Indonesia, Thailand, Korea, Japan, Vietnam, Malaysia, Singapore, Philippines)
for an OTA's booking and CS-correction flows.

**Core thesis.** A mismatched Asian name is usually a *deterministic* artifact of
competing romanization standards or regional linguistics — not a random Western
typo. `John→Jonh` is stochastic; `Choi↔Choe`, `Nguyen↔Ngyuen`, `Mohamad↔Muhamad`,
`GWANGEUN↔KWANGEUN` are systemic. Flat Levenshtein / Soundex / Metaphone assume
Anglo-Saxon phonetics and fail on these. The pipeline therefore normalizes
*structure* and *romanization* before scoring.

**Two operating modes** share the pipeline:
- **(a) Pair verification** — score an entered name against a reference (passport
  OCR/API, prior booking). Highest-value; catches ~91% of VN errors at <0.15.
- **(b) Spell suggestion** — no reference; retrieve nearest dictionary names per
  token and return ok / variant / suspect / misspelled. The production-shaped
  path where the detection-improvement research lives.

**Outcome bands** (calibrated on real data, tighter than the original blueprint's
0.3/0.7 because real negatives score lower than assumed):
- `< 0.15` accept / silent normalize
- `0.15–0.40` "Did you mean …?" review prompt
- `> 0.40` mismatch → route to name-change flow, not spelling correction

---

## 2. System architecture

A sequential pipeline that isolates structural inconsistency *before* algorithmic
scoring. Numbered layers map to module docstrings.

```
[ Raw input ]
     │
 L0  Input triage & intent routing  (normalize.py)
     │   is_plausible_name · split_passengers · extract_name · classify_intent
     ▼
 L1  Structural standardization     (normalize.py)
     │   tokenize/fold · title+particle strip · diacritic fold · gender-marker
     │   strip · adjacent-dedupe · token-order permutations · join/split variants
     ▼
 L2  Romanization canonicalizer     (romanize.py)
     │   per-country equivalence: KR surname/vowel maps, JP Hepburn↔Kunrei,
     │   ID/MY old-Dutch+Arabic, TH aspirates. Applied to BOTH sides.
     ▼
 L3  Feature extraction             (features.py)
     │   char 3-gram inverted index + Jaccard prefilter for candidate retrieval
     ▼
 L4  Weighted scoring               (scorer.py)
     │   weighted Damerau-Levenshtein, phonetic substitution costs, → [0,1]
     ▼
[ accept / review / mismatch ]  or  [ per-token ok/variant/suspect/misspelled ]
```

### Layer detail

**L1 — structural standardization.** Resolves variance from form-fills, passport
standards, and naming customs:
- **Name inversion.** JP/KR/VN put family name first domestically but invert on
  international docs. Pair mode generates both `(first+last)` and `(last+first)`
  permutations for matching.
- **Particle / title elimination.** Strip inconsistently-included relational
  particles: MY/ID `bin`/`binti`/`binte`/`a/l`/`a/p`; VN `Văn` (male) / `Thị`
  (female). Particles strippable on *both* sides before scoring
  (`LE PHUONG THUY ↔ LE THI PHUONG THUY`).
- **Token aggregation.** Hyphenated/split given names collapse:
  `Min Seok` → `Minseok`; comparison runs on the *joined* string so split/merge
  errors (`Jun Kyu ↔ JunKyu`, `SAFEEIE ↔ SAFEE IE`) match.
- **NFKC + whitespace canonicalization** first (~3.5% of "corrections" are
  whitespace/case-only).

**L2 — regional romanization mapping matrix.** Collapses historical, colonial, and
orthographic conflicts to one canonical key. Applied to *both* sides, so
over-merging only risks a false-accept (never a false-reject):

| Region | Root | Variations collapsed |
|---|---|---|
| **Korea** | ㅓ (eo) | `eo ↔ u ↔ o` (Seong/Sung/Song) |
| | ㅡ (eu) | `eu ↔ u` (Eun/Un) |
| | surnames | `Lee↔Yi↔Rhee↔I`, `Kim↔Gim`, `Park↔Bak`, `Choi↔Choe` (equivalence array) |
| **Japan** | long vowels | `oo`/`ou`/`oh`/`ō` → collapse to single root |
| | consonants | `si↔shi`, `tu↔tsu`, `ti↔chi`, `hu↔fu` (Kunrei → Hepburn) |
| **Indonesia / MY** | old Dutch | `oe↔u` (Soekarno/Sukarno), `dj↔j`, `tj↔c`, `ch↔kh` |
| **Vietnam** | vowel slide | `uy↔yu` transposition (Nguyen/Ngyuen) |

**L4 — weighted substitution costs.** Flat Levenshtein charges 1.0 for any
substitution; here cost reflects phonetic/linguistic probability — `C(k,g)≈0.2`
(KR/ID shift), `C(p,b)≈0.2` (KR/TH), `C(m,n)≈0.3` (JP nasal), vs `C(k,x)=1.0`
(unrelated). Cheap indels for silent `h` and dropped vowels; transposition is cheap
(`Nguyen/Ngyuen`). So common regional variation doesn't inflate the score. (The
original blueprint also proposed Beider-Morse phonetic matching as an L3 fallback;
the implementation uses the char-3-gram index instead — simpler, no extra dep, and
sufficient given L2 canonicalization already collapses phonetic variants.)

### Two layers, two checkers — do not confuse them

| | `checker.NameChecker` / `score_pair` | `load_public.TokenSpellChecker` |
|---|---|---|
| Basis | reference-based (compares to known name) | dictionary-based (no reference) |
| Output | score 0..1 → accept/review/mismatch | per-token ok/variant/suspect/misspelled |
| Use | when a correct reference exists | production-shaped detection path |
| Houses | pair scoring, inversion, subset handling | all of 1a/1b/1c/2a/2b/3c |

### Package layout

```
namecheck/
  __init__.py      public API: score_pair, verdict, NameChecker, classify_intent…
  normalize.py     L0+L1: NFKC, titles, particles, tokenization, intent routing
  romanize.py      L2: per-country canonicalization rules
  features.py      L3: n-grams, candidate-retrieval index
  scorer.py        L4: weighted Damerau-Levenshtein + cost matrix
  checker.py       pair-mode orchestration, thresholds, suggestions
  confusion.py     1b: confusion-pair prior model (mine + apply)
  name_model.py    1c: positional-unigram+bigram full-name model
  closed_class.py  2b: VN/KR/JP syllable & mora generators + validators
  data/            config-driven cache builder (DataManager + one loader/source)
load_public.py     TokenSpellChecker + honest evaluation harness (reads cache)
evaluate.py        legacy upper-bound benchmark (old BQ CSV)
export_test_results.py   per-name detection export (wrong/correct tabs)
```

### Dictionary cache & rank semantics

- Runtime dictionaries: `data/cache/<country>/tokens.txt` (+ `regional/tokens.txt`),
  format `token<TAB>rank<TAB>is_curated`. **Lower rank = more common.** Legacy
  2-col `token<TAB>rank` tolerated on read.
- **Rank = dense rank over summed cross-source frequency** (1 = most common). Each
  source contributes a per-country frequency; the manager sums, drops non-curated
  tokens below a min-freq floor, caps to `max_tokens_per_market` (curated always
  kept), then dense-ranks.
- **`is_curated`** marks gold-source tokens (corrections, popular_names,
  kr_given_names) — protects them from alias quarantine. Replaces the retired
  `CURATED_RANK`/`NO_RANK` sentinels.
- **Per-market percentile scoring** (`_compute_scores`): a token's score is its
  frequency percentile *within its own market*, so one global threshold is
  comparable across markets. Per-market overrides in `SUSPECT_SCORES_BY_COUNTRY`
  (tuned via `--optimize`).
- Cache is built by `DataManager`, **not at eval time**. `data/source/` holds raw
  inputs; `data/cache/<country>/` holds processed caches the checker reads.

---

## 3. Data sources

All sources resolve to per-country token frequencies summed into the cache.
"curated" = high-precision gold tier, protected from quarantine.

| # | Source | Markets | Curated | Freq basis | Notes |
|---|---|---|---|---|---|
| A | **names-dataset** (philipperemy, FB-derived) | ID/KR/JP/MY/SG/PH + regional | no | occurrence count | Primary. **Zero TH/VN entries** — VN covered via diaspora tags (MY/SG/US), TH largely absent. Review provenance with legal before prod. |
| B | **popular-names-by-country** (sigpwned) | all | yes | 1 / listing | ~4.6k CC-licensed names incl. romanizations; "definitely valid" tier. Auto-fetched. |
| C | **JMnedict** (EDRDG) | japan | no | count | ~740k kana readings → ~242k Hepburn romaji via pykakasi; Japan dict only (kept out of regional pool). Grows JP 21.6k→258k tokens. |
| D | **Wikidata SPARQL** (en + ko labels) | all (QID per country) | no | summed sitelinks | Fills empty TH/VN. CC0, refreshable. WDQS blocked from sandbox — run on open internet. Plausibility tier, skews to notable people. |
| E | **CS corrections** (`good` tab) | all | yes | count | `nameAfter` tokens are gold; also the 1b/1c training corpus. `test` tab never read here (leakage). |
| F | **tvlk_bookings** (Traveloka travellers) | KR/JP/VN | **no** | booking count | Real traveller-typed names — the population we must catch typos in, so non-curated (stays subject to floor + quarantine). 23,982 rows kept. Includes first/last swap-fix. |
| G | **kr_given_names** (manual) | korea | yes | count | Curated romanized KR given-name list (manual-populate); sharpens ranking, complements the syllable acceptor. |

**Recommended primary (not yet wired): internal verified booking corpus.** Public
data alone is a *plausibility* tier; the *correction* tier should be
passport-matched names from completed bookings — same format, same markets, real
frequencies. See §7.

---

## 4. Per-market techniques

The detection-improvement work was driven by a failure-mode analysis (originally
the VN miss study: 31/39 misspelled tokens undetected). Three root causes, each
with targeted mechanisms. **Most fixes are global** (keyed on percentile /
`COMMON_SCORE`), not country special-cases.

### Issue 1 — dense valid-name space (a 1-letter error lands on another valid name)

Membership cannot catch `an→anh`, `tan→tam`, `lai→mai`. Stop asking "is this a
name?" and ask "is this plausible *here, for this person*?"

- **1a positional slot grammar** (`TokenSpellChecker.slots`, `surnames_{vn,kr}.txt`).
  First token of a multi-token VN/KR name must be a valid surname; stands down
  when a later token is the surname (given-first order, e.g. KR `jihun lee`).
  Single-letter first token (initial) is exempt.
- **1b confusion-pair priors** (`confusion.py`, `confusions_*.tsv`,
  `confusion_ops_*.tsv`). Mined from `good` corrections at two granularities:
  token-level (`an→anh` seen verbatim) and char-level (`i→y`, inserted-h). An
  in-dict token on the high-risk side of a frequent confusion → soft `suspect`
  with the partner as suggestion. **The single biggest lever** (detect +3.7pp,
  corr@1-all +3.3pp). Critical guard: never downgrade a token that is itself
  COMMON (`score ≥ COMMON_SCORE`) — CS logs corrections both directions, so
  without the guard `token_hit` flags the *most common* names (VN `anh`/`tran`).
- **1c full-name probability model** (`name_model.py`, `namemodel_*.json`).
  Positional-unigram + bigram, add-k smoothing. Flags structural anomalies
  membership can't: duplicated surname (`Nguyen Nguyen thi hai yen`), improbable
  sequence. **Threshold calibrated on held-out gold**, not training names
  (training calibration false-flags ~84%). Common-reduplication exemption: a
  duplicated *common* token (Sikh `Singh…Singh`, VN `Nguyen…Nguyen`) is legit.
- **1d reference comparison** — *not implemented*; highest-value item (see §7).

### Issue 2 — typo-polluted public dictionary (FB-dump typos enshrined as names)

`nguen`, `nguye`, `thithuy`, `kk` absorb both membership and suspect checks.

- **2a typo-alias quarantine** (`aliases.py`, `aliases_*.txt`). At build time, for
  token T with neighbor C where `edit(T,C) ≤ 0.15` and `freq(C)/freq(T) ≥ 50`:
  remove T, record `T→C`. Checker returns `misspelled` with C. Curated tokens
  protected. Turns pollution into detection.
- **2b closed-class validation** (`closed_class.py`, `syllables.txt`). VN is
  monosyllabic — a token is valid only if it's exactly one generated syllable
  (`thithuy`/`kk` fail). Used as a **reject** test for VN. KR given names are 1-2
  syllables glued — used as an **accept** test (a dict-miss token that decomposes
  into valid romanized syllables is a plausible KR name, unless a close common
  anchor exists → then it's a typo of that anchor). JP mora used for routing (see
  3c). Syllable sets are *generated* from phonotactics, deliberately permissive
  (over-generation only risks false-accept, same safe direction as L2).
- **2c minimum-evidence threshold.** Build-time: drop non-curated tokens below the
  per-country freq floor before ranking. Read-time legacy cutoff is a no-op on
  fresh dense-ranked caches.

### Issue 3 — non-spelling cases entering the pipeline

Name changes, gender markers, DOB/doc changes, foreign passengers under wrong
origin — counting these as detection misses is a measurement error.

- **3a intent routing** — `classify_intent` runs in front of evaluation; only
  `spelling` reaches token checking. Adds `name_change` (pair score > 0.40 when
  both sides plausible).
- **3b normalization pre-checks** — duplicate-adjacent-token collapse + gender-
  marker stripping (`(Nữ)`, `(MR)`) in L1.
- **3c rule-set by name, not booking origin** (`route`). `origin_country` is the
  market, not nationality. A foreign name on a VN/KR/JP booking routes to neutral
  `regional` rules (no closed-class / surname slot). VN: native-syllable fraction
  < 0.5. KR: no recognized surname + low in-own-dict fraction. JP: native-mora
  fraction < 0.5 (membership useless — the 242k jmnedict dict "contains"
  everything, so mora phonotactics detect foreign names instead).

### Market-specific notes

- **Korea** — name segmentation splits space-less names via the surname inventory
  (`limkunhee`→`lim`+`kunhee`) so slot grammar + dict checks work; syllable
  acceptor covers the combinatorial given-name space (no list can enumerate
  ~160k 2-syllable combos); `li` surname variant added. `wikidata_ko` /
  `kr_given_names` built but left **off** — the syllable acceptor already covers
  given names, and the 10k low-freq ko tokens diluted detection.
- **Japan** — Hepburn-mora foreign-name routing; zero detection loss (only
  re-routes non-Japanese names, which were pure FPs).
- **Vietnam** — 1b common-token guard + foreign-leniency are the big VN levers
  (fpr 58.6→8.6).
- **Singapore — coverage-bound, not tuning-bound.** Held-out FPs are dict-miss
  Malay/Indian/Chinese names (`fazulee`, `mossammat`) absent from a thin
  multi-ethnic dictionary. The real lever is **data** (a romanized Malay+Tamil
  given-name source), not heuristics.
- **Thailand — data-bound at ~32% coverage.** names-dataset has no TH file; the
  dictionary is too sparse to accept real Thai names regardless of pipeline, so
  its 89% detect is meaningless.

---

## 5. Evaluation methodology

### Honesty discipline (load-bearing)

The corrections xlsx is **both** the mining corpus and the eval set, so
train/test isolation is mandatory. `good` (18.8k rows) and `test` (727 rows) tabs
are **verified disjoint** by `case_number`/`booking_id`. Priors (1b), gold-merge,
and name models (1c) train on `good`; `evaluate()` scores `test` only. When mining
and eval share a corpus, use k-fold cross-validation (`confusion_cv`) — never
report numbers where the model saw the test rows.

The `good` tab is the **training** corpus: its `nameAfter` tokens were merged into
the dict (curated) and trained 1b/1c, so coverage/detect on `good` are optimistic.
Use it for dev signal (correct-name FPs + case review); reserve `test` for final
numbers.

### Metrics

- **Coverage** — % of correct (gold) name tokens accepted (ok/variant).
  `1 − coverage` = token-level false-flag rate.
- **Detect** — % of misspelled tokens flagged (incl. rare-but-in-dict `suspect`).
- **FPR** — name-level false-positive rate: % of *unique* corrected names
  (nameAfter) flagged (any token suspect/misspelled, or a 1c structural flag).
  Deduped per country; not simply `1 − coverage`. Most flags are *soft* `suspect`
  (an inline "did you mean?", not a block) — a multi-token name trips if any one
  token is rare, so high FPR ≠ broken.
- **corr@1\*** — top-1 correction accuracy when the gold token is in the dict.
- **corr@1-all** — top-1 accuracy over all misspelled tokens.

`--optimize` grid-searches `SUSPECT_SCORE` per market on the objective
`detect + corr@1-all − fpr`.

### Legacy benchmark (`evaluate.py`)

Uses the CSV's own corrected names as the dictionary — an **upper bound** (the
right answer is always retrievable; reported 94% top-1). Useful for pair-mode +
negative-control calibration, not for production-realistic detection numbers.

---

## 6. Latest evaluation results

Honest eval on `test`, all 8 markets, cache-only (no training at eval time), KR/JP/VN
dictionaries including `tvlk_bookings` (`python3 load_public.py`):

| country | gold tokens | coverage | detect | fpr | corr@1* | corr@1-all |
|---|---|---|---|---|---|---|
| indonesia | 677 | 71.9% | 58.1% | 59.0% | 16.2% | 12.8% |
| thailand | 225 | 32.9% | 89.5% | 90.3% | 44.4% | 11.4% |
| korea | 197 | 93.4% | 44.2% | 13.2% | 14.5% | 12.6% |
| japan | 58 | 94.8% | 71.4% | 8.7% | 22.2% | 19.0% |
| vietnam | 211 | 95.7% | 51.4% | 8.6% | 16.7% | 14.3% |
| malaysia | 217 | 90.3% | 43.3% | 27.7% | 23.1% | 20.0% |
| singapore | 50 | 90.0% | 45.5% | 33.3% | 11.1% | 9.1% |
| philippines | 40 | 80.0% | 40.0% | 42.9% | 0.0% | 0.0% |
| **TOTAL** | **1675** | **76.1%** | **61.2%** | **45.5%** | **18.5%** | **12.9%** |

1c structural model (TOTAL): struct-detect 10.1%, struct-FP 2.9% (552 pairs).

**Tuned markets — false-positive reduction (`test`, token-level):**

| market | baseline cov/detect/fpr | final cov/detect/fpr | key change |
|---|---|---|---|
| vietnam | 73.9 / 57.1 / 58.6 | **95.7 / 51.4 / 8.6** | 1b common-token guard + foreign-leniency |
| korea | 81.0 / 58.5 / 35.2 | **93.4 / 44.2 / 13.2** | segmentation + syllable acceptor + `li` |
| japan | 89.7 / 71.4 / 21.7 | **94.8 / 71.4 / 8.7** | Japanese-mora foreign-name routing |
| singapore | 90.0 / 45.5 / 33.3 | 90.0 / 45.5 / 33.3 | coverage-bound (data, not tuning) |

**Cumulative item impact** (TOTAL on `test`, pre-tvlk final pipeline):

| item | coverage | detect | corr@1-all |
|---|---|---|---|
| baseline (membership + percentile suspect) | 74.9% | 62.2% | 11.6% |
| + 1a slot grammar | — | 63.5% | 11.8% |
| + 1b confusion priors | ~ | 67.2% | 15.1% |
| + gold merge | 66.5% | 68.2% | 14.4% |
| + 1c name model | 64.7% | 69.2% | 14.4% |
| + 2a alias quarantine | 64.4% | 69.4% | 14.6% |
| + 2b closed-class (VN) | 64.3% | 69.6% | 14.4% |
| + 3c route-by-name | 65.0% | 69.4% | 14.6% |
| + 2c evidence cutoff | 64.7% | 69.8% | 14.8% |

Net vs baseline: **detect +7.6pp, corr@1-all +3.2pp, coverage −10.2pp** — the
coverage cost is deliberate (1b/1c/2b trade silent-accept for soft flagging).

**Three structural problems (not tuning problems):**
1. Coverage gaps → false flags (TH 77% of correct tokens missing).
2. Weak detection — 44% of misspellings are themselves valid names in a 261k pool
   (`ERNI`/`ERNY` both real).
3. Poor ranking — 261k candidates, only ~half with real frequency info.

---

## 7. Opportunities for improvement

Ranked by leverage. Items 1a–3c are implemented (§4).

1. **1d reference comparison — highest value, unimplemented.** Where a reference
   exists (passport OCR/API, repeat-customer profile, other booking fields), use
   `score_pair` directly instead of dictionary lookup. No algorithm work — needs a
   reference data source to wire against.
2. **Internal verified booking corpus as primary dictionary.** Public data is a
   plausibility tier only. Export distinct verified name tokens per origin-country
   into the cache; gives real frequencies for ranking and the actual correct names
   for correction. The single biggest quality lever.
3. **Thailand dictionary (data-bound at 32%).** Source a Thai romanized-name list
   or internal TH booking corpus.
4. **Singapore multi-ethnic coverage.** Romanized Malay + Tamil given-name source
   (analogous to the curated KR-B loader). Heuristics can't fix dict-miss names.
5. **Indonesia / Philippines FPR** (59% / 43%) — next-weakest after TH; a
   tvlk-style real-traveller source for those markets.
6. **KR detection dip from non-curated tvlk data** — lever: raise
   `EVIDENCE_MIN_FREQ_BY_COUNTRY["korea"]` above the default 2.
7. **Shadow-mode deployment** against live CS tickets before enabling auto-correct;
   treat `suspect` as an inline confirm, not a block.

Not yet implemented from the original proposal: KR-given list expansion via
`kr_given_names`/`wikidata_ko` (built, left off — syllable acceptor already
covers it).

---

## 8. Running the scripts

`config.yaml` (repo root) drives everything: `enabled_countries`, the `sources`
on/off map, `max_tokens_per_market`, `build_regional`. Only enabled countries are
built and evaluated. No test framework / build step — plain Python 3.9. Deps:
`openpyxl`, `PyYAML`, optionally `pykakasi` (JMnedict) and `unidecode` (KR ko).

### Build the cache

```bash
# Build per-country cache (data/cache/<country>/) for enabled countries/sources.
# Dependency-ordered: token sources → finalize ranks → aliases/syllables/surnames
# → confusions(1b)/name_models(1c).
python3 -m namecheck.data
python3 -m namecheck.data --config other.yaml    # alternate config
```

### Honest evaluation

```bash
python3 load_public.py                 # load cache, train nothing, score 'test'
python3 load_public.py --serial        # single-process (debug)
python3 load_public.py --no-confusion  # skip loading 1b priors
python3 load_public.py --no-name-model # skip loading 1c models
python3 load_public.py --optimize      # per-market SUSPECT_SCORE grid search
```

Validate any change by rebuilding the cache then re-running `load_public.py`,
comparing the per-market coverage/detect/fpr table to the prior run.

### Per-name detection export

```bash
python3 export_test_results.py                # default --tab good (dev signal)
python3 export_test_results.py --tab test     # unbiased final numbers
python3 export_test_results.py out.xlsx       # override output filename
```

Two tabs ("wrong names" / "correct names"), 5 columns: input, detect result,
country, correction suggestion, gold corrected name. Runs at the production
operating point (baked suspect scores + 1b + 1c).

### Legacy upper-bound benchmark

```bash
python3 evaluate.py    # pair + negative-control + suggestion on the old BQ CSV
```

### Programmatic use

```python
from load_public import build_checker_from_cache
checker = build_checker_from_cache()
checker.check("Mohamad Husnul Hitami", "indonesia")
# → {"status": "...", "tokens": [{"token","status","suggestions"}, ...]}

from namecheck import score_pair, verdict
score_pair("GWANGEUN JEONG", "KWANGEUN JEONG", "korea")  # ~0.02 → accept
```
