"""Source: Traveloka traveller names (booking sample XLSX).

Real passenger names entered by Traveloka travellers, so this is NOT a curated
tier -- traveller-typed names are the very population namecheck must catch typos
in. curated=False keeps tokens subject to the min-frequency floor and eligible
for 2a alias/typo quarantine, so a misspelled name cannot whitelist itself.

Cleaning (applied here, not upstream):
  1. business_unit_id == FLIGHT
  2. user_setting_country_id in {KR, JP, VN}  (account country, mapped to market)
  3. both first_name and last_name present

Frequency = raw booking count (every qualifying row contributes), matching the
corrections/names_dataset occurrence-count convention. user_setting_country_id
is the account country, not the name's romanization market -- accepted as-is
(same basis as corrections' origin_country); the min_freq floor suppresses the
one-off foreign-token tail.

Swap fix (KR/VN only): some rows have first/last reversed. Detected by the
surname pattern -- a first_name token is a known KR/VN surname while no
last_name token is -> the fields are swapped and corrected before counting.
NOTE: tokens from both fields are pooled into one frequency counter, so the
swap does not change the dictionary; it is a data-quality fix and its count is
reported. JP has no surname inventory, so JP rows are not swap-checked.
"""
import os
from collections import Counter

from namecheck.data.config import TVLK_BOOKINGS_PATH, COUNTRY_CC, cache_file
from namecheck.data.loaders.base import TokenLoader, valid_tokens

SHEET = "PQP Samples - Product"
BUSINESS_UNIT = "FLIGHT"
# account-country code -> market; only the markets this source covers.
_CC_TO_COUNTRY = {"KR": "korea", "JP": "japan", "VN": "vietnam"}
# markets with a curated surname inventory -> eligible for swap detection.
_SWAP_MARKETS = ("korea", "vietnam")
# a last-position token must recur this many times to be an observed surname.
SURNAME_MIN_FREQ = 5
SWAP_REPORT_PATH = os.path.join(os.path.dirname(TVLK_BOOKINGS_PATH),
                                "tvlk_swap_report.txt")


def _load_surnames(country):
    """Folded surname set for a market, or empty if no inventory."""
    path = cache_file(country, "surnames.txt")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {ln.strip().lower() for ln in f if ln.strip()}


class TvlkBookingsLoader(TokenLoader):
    name = "tvlk_bookings"
    stage = 0
    curated = False

    def __init__(self):
        self._freq = None   # memoized {country: Counter}

    def _load_all(self):
        import openpyxl
        wb = openpyxl.load_workbook(TVLK_BOOKINGS_PATH, read_only=True)
        ws = wb[SHEET]
        it = ws.iter_rows(values_only=True)
        idx = {h: i for i, h in enumerate(next(it))}
        freq = {c: Counter() for c in COUNTRY_CC}
        surnames = {c: _load_surnames(c) for c in _SWAP_MARKETS}
        swapped = Counter()       # per-country swap fixes
        eligible = Counter()      # per-country rows that could be swap-checked
        obs_surnames = {c: Counter() for c in _SWAP_MARKETS}  # last-position tokens
        kept = skipped = 0
        for r in it:
            if str(r[idx["business_unit_id"]] or "").strip().upper() != BUSINESS_UNIT:
                skipped += 1
                continue
            cc = str(r[idx["user_setting_country_id"]] or "").strip().upper()
            country = _CC_TO_COUNTRY.get(cc)
            if not country:
                skipped += 1
                continue
            first = str(r[idx["first_name"]] or "").strip()
            last = str(r[idx["last_name"]] or "").strip()
            if not first or not last:           # rule 3: both names required
                skipped += 1
                continue
            # swap fix: surname in first, none in last -> fields reversed.
            sset = surnames.get(country)
            if sset:
                eligible[country] += 1
                first_toks = valid_tokens(first)
                last_toks = valid_tokens(last)
                first_has = any(t in sset for t in first_toks)
                last_has = any(t in sset for t in last_toks)
                if first_has and not last_has:
                    first, last = last, first
                    swapped[country] += 1
                # last position (post-swap) = surname slot -> observed surname.
                for tok in valid_tokens(last):
                    obs_surnames[country][tok] += 1
            for field in (first, last):
                for tok in valid_tokens(field):
                    freq[country][tok] += 1
            kept += 1
        wb.close()
        print(f"    tvlk_bookings: {kept} rows kept, {skipped} skipped")
        self._write_swap_report(swapped, eligible)
        self._write_observed_surnames(obs_surnames)
        self._freq = freq

    def _write_observed_surnames(self, obs_surnames):
        """Emit tvlk_surnames.txt (token<TAB>count, desc) per swap-market.

        Last-position tokens (after the swap fix) seen >= SURNAME_MIN_FREQ times.
        Separate from the curated surnames.txt -- 1a slot grammar is unchanged.
        """
        print("    tvlk_bookings observed surnames:")
        for country in _SWAP_MARKETS:
            kept = [(t, n) for t, n in obs_surnames[country].most_common()
                    if n >= SURNAME_MIN_FREQ]
            path = cache_file(country, "tvlk_surnames.txt")
            with open(path, "w", encoding="utf-8") as f:
                for t, n in kept:
                    f.write(f"{t}\t{n}\n")
            curated = _load_surnames(country)
            new = sum(1 for t, _ in kept if t not in curated)
            print(f"      {country:8s}: {len(kept)} surnames "
                  f"(>= {SURNAME_MIN_FREQ}), {new} not in curated list -> {path}")

    def _write_swap_report(self, swapped, eligible):
        lines = ["tvlk_bookings first/last swap-fix report",
                 "(rule: surname token in first_name, none in last_name -> swap)",
                 ""]
        total_sw = total_el = 0
        for country in _SWAP_MARKETS:
            el, sw = eligible[country], swapped[country]
            total_el += el
            total_sw += sw
            pct = (100.0 * sw / el) if el else 0.0
            lines.append(f"  {country:8s}: {sw} swapped / {el} eligible ({pct:.1f}%)")
        lines.append("  japan   : not checked (no surname inventory)")
        pct = (100.0 * total_sw / total_el) if total_el else 0.0
        lines.append("")
        lines.append(f"  TOTAL   : {total_sw} swapped / {total_el} eligible ({pct:.1f}%)")
        report = "\n".join(lines) + "\n"
        with open(SWAP_REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(report)
        print("    tvlk_bookings swap-fix:")
        for ln in lines[3:]:
            print(f"    {ln}")
        print(f"    (report written to {SWAP_REPORT_PATH})")

    def contribute(self, country):
        if self._freq is None:
            self._load_all()
        fr = dict(self._freq.get(country, {}))
        print(f"    tvlk_bookings[{country}]: {len(fr)} tokens")
        return fr
