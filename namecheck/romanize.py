"""Layer 2: deterministic romanization canonicalization.

Each function maps a folded token to a canonical internal form so that
competing romanization standards collapse to the same key. Rules are applied
to BOTH sides of a comparison, so over-merging only risks false accepts
(measured by negative controls in evaluate.py).
"""
import re
from functools import lru_cache

# --- Korean ----------------------------------------------------------------
KR_SURNAME_EQUIV = {
    "lee": "i", "yi": "i", "rhee": "i", "rie": "i", "ri": "i", "li": "i", "i": "i",
    "kim": "kim", "gim": "kim", "ghim": "kim",
    "park": "bak", "pak": "bak", "bak": "bak", "bahk": "bak",
    "choi": "choe", "choe": "choe", "chwe": "choe",
    "jung": "jeong", "jeong": "jeong", "chung": "jeong", "cheong": "jeong",
    "kang": "gang", "gang": "gang",
    "cho": "jo", "jo": "jo", "joe": "jo",
    "yun": "yun", "yoon": "yun",
    "lim": "im", "im": "im", "rim": "im",
    "shin": "sin", "sin": "sin",
    "suh": "seo", "seo": "seo", "so": "seo",
    "moon": "mun", "mun": "mun",
    "woo": "u", "wu": "u",
    "yu": "yu", "yoo": "yu", "ryu": "yu", "ryoo": "yu",
    "jang": "jang", "chang": "jang",
    "baek": "baek", "paik": "baek", "back": "baek", "paek": "baek",
    "oh": "o", "o": "o",
    "noh": "no", "no": "no", "roh": "no",
}
_KR_SEQ = [("eo", "u"), ("eu", "u"), ("oo", "u"), ("ou", "u"),
           ("wo", "wu"), ("ck", "k")]

# --- Japanese ----------------------------------------------------------------
_JP_SEQ = [
    ("tsu", "tu"), ("shi", "si"), ("chi", "ti"), ("sha", "sya"), ("shu", "syu"),
    ("sho", "syo"), ("cha", "tya"), ("chu", "tyu"), ("cho", "tyo"),
    ("ji", "zi"), ("fu", "hu"),
    ("ou", "o"), ("oo", "o"), ("uu", "u"), ("ei", "e"), ("ee", "e"),
]
_JP_OH = re.compile(r"oh(?=[bcdfghjklmnpqrstvwxyz]|$)")

# --- Indonesian / Malay (old Dutch & Arabic-transliteration variants) -------
_ID_SEQ = [
    ("oe", "u"), ("dj", "j"), ("tj", "c"), ("sj", "sy"), ("nj", "ny"),
    ("kh", "k"), ("ch", "k"), ("sh", "sy"), ("dh", "d"), ("th", "t"),
    ("q", "k"), ("f", "p"), ("v", "p"), ("z", "j"),
    ("ie", "i"),
]

# --- Thai --------------------------------------------------------------------
_TH_SEQ = [("bh", "p"), ("ph", "p"), ("th", "t"), ("kh", "k"), ("dh", "d"),
           ("ck", "k"), ("x", "s")]

# --- Generic (all countries) -------------------------------------------------
_GEN_SEQ = [("ck", "k")]


def _apply(token: str, seq) -> str:
    for a, b in seq:
        token = token.replace(a, b)
    return token


def _squeeze(token: str) -> str:
    """Collapse doubled letters: radhiyya->radhiya, keettahn->ketahn."""
    return re.sub(r"(.)\1+", r"\1", token)


@lru_cache(maxsize=None)
def canonical(token: str, country: str, is_first_token: bool = False) -> str:
    c = (country or "").lower()
    t = token
    if c in ("korea", "south korea", "kr"):
        if is_first_token and t in KR_SURNAME_EQUIV:
            t = KR_SURNAME_EQUIV[t]
        t = _apply(t, _KR_SEQ)
    elif c in ("japan", "jp"):
        t = _JP_OH.sub("o", t)
        t = _apply(t, _JP_SEQ)
    elif c in ("indonesia", "malaysia", "singapore", "brunei", "id", "my", "sg"):
        t = _apply(t, _ID_SEQ)
    elif c in ("thailand", "th"):
        t = _apply(t, _TH_SEQ)
    else:
        t = _apply(t, _GEN_SEQ)
    return _squeeze(t)


def canonical_tokens(tokens, country: str):
    out = []
    for i, t in enumerate(tokens):
        # surname equivalence tried on first AND last token (order unknown)
        is_edge = i == 0 or i == len(tokens) - 1
        out.append(canonical(t, country, is_first_token=is_edge))
    return out
