"""Loader contract + registry.

Two kinds of loader:

- **TokenLoader** (stage 0): contributes per-country token *frequencies* that
  the manager sums across sources before dense-ranking. `curated` marks whether
  its tokens are gold/curated provenance. `contribute(country) -> {token: freq}`.

- **StageLoader** (stage >= 2): a derived/mined/generated step that reads
  upstream cache and writes its own artifact. `build(country)`.

`stage` orders execution (manager runs ascending). `scope` limits which buckets
a loader applies to.
"""
from namecheck.normalize import tokenize
from namecheck.data.config import COUNTRY_CC


def valid_tokens(text):
    """Folded name -> dictionary-eligible tokens (len>=2, ascii letters).

    Same filter the legacy builders used, so migrated and rebuilt caches agree
    on what counts as a token."""
    return [t for t in tokenize(text)
            if len(t) >= 2 and t.isalpha() and t.isascii()]


class Loader:
    name = "loader"
    stage = 0
    curated = False
    # scope: set of buckets this loader applies to, or None = all enabled countries
    scope = None

    def applies_to(self, country):
        return self.scope is None or country in self.scope


class TokenLoader(Loader):
    """Contributes {token: freq} for a country. Does not write tokens.txt."""
    is_token_source = True

    def contribute(self, country):  # pragma: no cover - interface
        raise NotImplementedError


class StageLoader(Loader):
    """Reads upstream cache, writes its own artifact for a country."""
    is_token_source = False

    def build(self, country):  # pragma: no cover - interface
        raise NotImplementedError


def cc_for(country):
    return COUNTRY_CC.get(country)
