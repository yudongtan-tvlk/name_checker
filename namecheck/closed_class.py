"""2b. Closed-class validation for closed-inventory languages.

Vietnamese is monosyllabic: every name token is a single syllable drawn
from an enumerable set (~a few thousand toneless, ASCII-folded forms).
A token that is not one valid syllable is structurally impossible as a
Vietnamese name token -- `thithuy` (two syllables jammed together) and
`kk` (no vowel nucleus) fail instantly, even if a public dump enshrined
them as "valid".

The syllable set is GENERATED from Vietnamese phonotactics (onset x rhyme)
rather than curated by hand. Generation is deliberately permissive: over-
generating a few impossible syllables only risks a false-accept of junk,
never a false-reject of a real name -- the same safe-direction philosophy
as romanize.py.
"""

# Initial consonants, ASCII-folded (đ -> d, so `d` covers d/đ). "" = vowel-initial.
VN_ONSETS = [
    "", "b", "c", "ch", "d", "g", "gh", "gi", "h", "k", "kh", "l", "m",
    "n", "ng", "ngh", "nh", "p", "ph", "qu", "r", "s", "t", "th", "tr",
    "v", "x",
]

# Vowel nuclei, ASCII-folded (ă/â->a, ê->e, ô/ơ->o, ư->u). Monophthongs +
# di/triphthongs. Over-inclusive on purpose.
VN_NUCLEI = [
    "a", "e", "i", "o", "u", "y",
    "ai", "ao", "au", "ay", "eo", "eu", "ia", "ie", "iu", "oa", "oe",
    "oi", "oo", "ua", "ue", "ui", "uo", "uu", "uy", "ya", "ye", "yu",
    "oai", "oay", "uai", "uay", "uoi", "uou", "uya", "uye", "ieu", "yeu",
    "uyu", "oeo", "ye", " uo",
]

# Final consonants. "" = open syllable.
VN_CODAS = ["", "c", "ch", "m", "n", "ng", "nh", "p", "t"]


def generate_vietnamese_syllables():
    """All onset x nucleus x coda combinations (permissive). -> set[str]."""
    out = set()
    for o in VN_ONSETS:
        for nuc in VN_NUCLEI:
            nuc = nuc.strip()
            if not nuc:
                continue
            for c in VN_CODAS:
                out.add(o + nuc + c)
    return out


def is_valid_vietnamese_token(token, syllables):
    """A Vietnamese name token must be exactly one valid syllable.

    Multi-syllable runs ('thithuy', 'vananh') are spacing errors, not names,
    so they are rejected even when each part is individually a real syllable.
    """
    return token in syllables


# --- Korean -----------------------------------------------------------------
# Korean given names are 1-2 hangul syllables glued into one romanized token
# (eunseob = eun+seob, gwangmin = gwang+min). The token space is combinatorial,
# but the SYLLABLE space is closed, so a given token is plausible if it
# decomposes into valid romanized syllables. Generated from Revised-Romanization
# phonotactics plus the common variant spellings that show up in bookings
# (eo/u, oo/u, hoon/hun, gwang/kwang, hee/hye) -- same safe, over-generating
# philosophy as the VN set: extra syllables only risk a false-accept of junk.
KR_ONSETS = [
    "", "g", "k", "kk", "n", "d", "t", "tt", "r", "l", "m", "b", "p", "pp",
    "s", "ss", "j", "jj", "ch", "c", "h",
]
KR_VOWELS = [
    "a", "ya", "eo", "yeo", "o", "yo", "u", "yu", "eu", "i",
    "ae", "yae", "e", "ye", "wa", "wae", "oe", "wo", "we", "wi", "ui",
    # common romanization variants (RR / McCune / ad-hoc booking spellings)
    "oo", "woo", "wu", "ou", "uh", "yoo", "oi", "ee", "ei", "eui", "yi", "eu",
]
KR_CODAS = ["", "k", "g", "n", "t", "d", "l", "m", "p", "b", "ng", "s"]


def generate_korean_syllables():
    """All onset x vowel x coda romanized syllables (permissive). -> set[str]."""
    out = set()
    for o in KR_ONSETS:
        for v in KR_VOWELS:
            for c in KR_CODAS:
                out.add(o + v + c)
    return out


def korean_decomposes(token, syllables, max_syll=3):
    """True if token splits into 1..max_syll valid romanized syllables."""
    n = len(token)
    if n < 2:
        return False
    maxlen = max((len(s) for s in syllables), default=0)
    INF = max_syll + 1
    dp = [INF] * (n + 1)
    dp[0] = 0
    for i in range(n):
        if dp[i] >= INF:
            continue
        for j in range(i + 1, min(n, i + maxlen) + 1):
            if token[i:j] in syllables and dp[i] + 1 < dp[j]:
                dp[j] = dp[i] + 1
    return dp[n] <= max_syll


# Generic registry: country -> validator. Vietnamese uses single-syllable
# membership as a REJECT test (a token that isn't one syllable is junk). Korean
# uses multi-syllable decomposition as an ACCEPT test (see korean_acceptor).
def closed_class_validator(country, syllables):
    if country == "vietnam":
        return lambda tok: is_valid_vietnamese_token(tok, syllables)
    return None


# --- Japanese ---------------------------------------------------------------
# Japanese romaji is tightly constrained: (C)V mora + syllabic 'n', no 'l',
# 'x', 'q', and no consonant clusters. A real Japanese name's tokens all
# decompose into mora; a foreign name (lumawan, rosmiyati, hengxu, pradini)
# does not. We use this as a ROUTING signal (the JP dictionary is too large --
# jmnedict ~242k -- to detect foreign names by membership). Sokuon and long
# vowels are handled by collapsing doubled letters before decomposing.
import re as _re

_JP_DOUBLE = _re.compile(r"(.)\1+")
JP_ONSETS = ["", "k", "g", "s", "sh", "z", "j", "t", "ch", "ts", "d",
             "n", "h", "f", "b", "p", "m", "y", "r", "w"]
JP_NUCLEI = ["a", "i", "u", "e", "o", "ya", "yu", "yo", "ou", "ei", "oh"]


def generate_japanese_mora():
    """Hepburn mora set (onset x nucleus) + syllabic 'n'. -> set[str]."""
    out = {"n"}
    for o in JP_ONSETS:
        for nuc in JP_NUCLEI:
            out.add(o + nuc)
    return out


def japanese_is_native(token, mora, max_mora=8):
    """True if token (doubled letters collapsed) splits into Japanese mora."""
    t = _JP_DOUBLE.sub(r"\1", token)
    return korean_decomposes(t, mora, max_syll=max_mora)


def japanese_native_checker(mora):
    """Returns fn(tok) -> True if tok looks like a native Japanese romaji token.
    Used by route() to detect foreign names on JP-market bookings."""
    return lambda tok: japanese_is_native(tok, mora)


def korean_acceptor(syllables, max_syll=2):
    """Returns fn(tok) -> True if tok is a plausible romanized Korean name token
    (decomposes into <=max_syll valid syllables). Used to ACCEPT dict-miss KR
    tokens. max_syll=2: a given name is 1-2 syllables once the surname is split
    off, so a stricter cap rejects long multi-name junk while still accepting
    real given names."""
    return lambda tok: korean_decomposes(tok, syllables, max_syll=max_syll)
