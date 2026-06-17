"""1c. Per-country positional name models, built on the 'good' tab.

Fits a positional-unigram + bigram NameModel per country on gold nameAfter
token sequences and writes data/cache/<country>/namemodel.json. Threshold is
calibrated inside NameModel.fit on held-out gold.
"""
import os

from namecheck.data.config import cache_dir, cache_file
from namecheck.data.loaders.base import StageLoader


class NameModelsLoader(StageLoader):
    name = "name_models"
    stage = 3

    def __init__(self):
        self._models = None

    def _ensure_models(self, ctx):
        if self._models is None:
            import load_public  # lazy
            self._models = load_public.build_name_models(ctx["gold"])
        return self._models

    def build(self, country, ctx=None):
        models = self._ensure_models(ctx)
        m = models.get(country)
        if not m:
            print(f"    name_models[{country}]: too few gold names -- skipped")
            return
        os.makedirs(cache_dir(country), exist_ok=True)
        m.save(cache_file(country, "namemodel.json"))
        print(f"    name_models[{country}]: fit on {m.n_train} names")
