"""1b. Confusion-pair priors, mined on the 'good' tab.

Aligns (wrong, gold) token pairs from gold corrections and aggregates recurring
token-level and char-op confusions into a ConfusionModel, then writes each
country's slice to data/cache/<country>/confusions.tsv + confusion_ops.tsv.
Mining uses a checker (built from the finalized cache) for token alignment, so
this runs after tokens/aliases (stage 3).
"""
import os

from namecheck.data.config import cache_dir, cache_file
from namecheck.data.loaders.base import StageLoader


def _write_country(model, country):
    os.makedirs(cache_dir(country), exist_ok=True)
    tp = model.token_pairs.get(country, {})
    with open(cache_file(country, "confusions.tsv"), "w", encoding="utf-8") as f:
        for wrong in sorted(tp):
            for gold, n in tp[wrong].most_common():
                f.write(f"{wrong}\t{gold}\t{n}\n")
    co = model.char_ops.get(country)
    with open(cache_file(country, "confusion_ops.tsv"), "w", encoding="utf-8") as f:
        if co:
            for (kind, a, b), n in co.most_common():
                f.write(f"{kind}\t{a}\t{b}\t{n}\n")


class ConfusionsLoader(StageLoader):
    name = "confusions"
    stage = 3

    def __init__(self):
        self._model = None

    def _ensure_model(self, ctx):
        if self._model is None:
            import load_public  # lazy: avoids import cycle at module load
            self._model = load_public._mine_confusions(ctx["train_pairs"], ctx["checker"])
        return self._model

    def build(self, country, ctx=None):
        model = self._ensure_model(ctx)
        _write_country(model, country)
        n = sum(len(c) for c in model.token_pairs.get(country, {}).values())
        print(f"    confusions[{country}]: {n} token-pair rows")
