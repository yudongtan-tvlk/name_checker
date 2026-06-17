"""Layer 0 + 1: input cleanup and structural standardization."""
import re
import unicodedata

TITLES = {
    "mr", "mrs", "ms", "miss", "mstr", "master", "dr", "tn", "pn",
    "tuan", "puan", "encik", "cik", "bapak", "ibu", "bpk", "sdr", "sdri",
}
# Relational particles that customers include/omit inconsistently.
PARTICLES = {
    "bin", "binti", "binte", "bte", "bt", "al", "ap",  # MY/SG/ID
    "van", "thi",  # VN middle markers (ASCII-folded forms of Văn/Thị)
}


def fold(text: str) -> str:
    """NFKC + strip diacritics -> lowercase ASCII letters/spaces."""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Vietnamese đ/Đ survives NFKD
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^A-Za-z ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def is_plausible_name(raw: str, max_tokens: int = 6) -> bool:
    """Layer 0 gate: reject free text / multi-passenger blobs / non-Latin."""
    if not raw or "\\n" in raw or "\n" in raw:
        return False
    if re.search(r"[0-9@/:]", raw):
        return False
    if re.search(r"[^\x00-\x7fÀ-ɏḀ-ỿ\s]", raw):
        return False  # CJK etc. -> route to transliteration, not this checker
    folded = fold(raw)
    return bool(folded) and len(folded.split()) <= max_tokens and len(folded) <= 60


# 3b: parenthesized gender/title markers like "(Nữ)", "(Mr)" are metadata,
# not name tokens. Stripped on the RAW string (before folding) so that a
# genuine given name "Nam" without parentheses is never touched.
_GENDER_MARKERS = re.compile(
    r"\(\s*(?:n[ữu]|nam|male|female|mr?s?|f|m)\s*\.?\s*\)", re.I)


def strip_gender_markers(raw: str) -> str:
    return _GENDER_MARKERS.sub(" ", raw)


def dedupe_adjacent(tokens):
    """3b: collapse accidentally duplicated adjacent tokens
    ('Nguyen Nguyen thi hai yen' -> 'Nguyen thi hai yen')."""
    out = []
    for t in tokens:
        if not out or out[-1] != t:
            out.append(t)
    return out


def tokenize(raw: str, strip_particles: bool = True):
    """Return content tokens after title/particle removal."""
    toks = fold(strip_gender_markers(raw)).split()
    while toks and toks[0] in TITLES:
        toks = toks[1:]
    if strip_particles:
        toks = [t for t in toks if t not in PARTICLES]
    return toks


# ---------------------------------------------------------------------------
# Layer 0: input extraction & intent routing
# ---------------------------------------------------------------------------

# Patterns that signal non-spelling intents; matched against folded text.
_DOB_SIGNALS = re.compile(
    r"\b(tgl|tanggal|lahir|date.of.birth|dob|born|ngay.sinh"
    r"|kewarganegaraan|nationality|citizenship)\b",
    re.I,
)
_DOCNUM_SIGNALS = re.compile(
    r"\b(ktp|nik|cccd|pnr|passport|paspor|ccid|id.card)\b",
    re.I,
)
# Strong free-text markers (prose, not a name)
_PROSE_SIGNALS = re.compile(
    r"\b(saya|kami|kak|nama|tiket|ingin|tolong|please|mohon|want|change"
    r"|correct|koreksi|perbaiki|salah|wrong|sorry|help|thank|regards"
    r"|dear|hello|hi\b|muon|sua|thanh|doi)\b",
    re.I,
)
# Separator arrow variants like "→", "->", "=>"
_ARROW = re.compile(r"\s*(?:→|->|=>|=)\s*")

# Newline variants produced by various CSV escaping layers
_NEWLINE = re.compile(r"(?:\\{1,8}n|\n|\r)")


def split_passengers(raw: str) -> list:
    """Split a multi-passenger blob into individual name strings.

    Handles:
    - Actual newlines and heavily-escaped \\\\\\\\n variants
    - Numbered lists: "1. Name  2. Name"
    - Comma-separated blobs (≥3 names in one field)

    Returns a list of candidate strings (may still need extract_name).
    """
    if not raw:
        return []

    # Normalise all newline escaping variants to real newline
    text = _NEWLINE.sub("\n", raw)

    # Split on newlines first
    parts = [p.strip() for p in text.split("\n") if p.strip()]

    # If still one part, try numbered-list split: "1. X  2. Y"
    if len(parts) == 1:
        numbered = re.split(r"\s*\d+\.\s+", parts[0])
        numbered = [p.strip() for p in numbered if p.strip()]
        if len(numbered) > 1:
            parts = numbered

    # If still one part with commas and multiple long tokens, try comma split
    if len(parts) == 1 and "," in parts[0]:
        by_comma = [p.strip() for p in parts[0].split(",") if p.strip()]
        # Only split if each segment looks name-like (no digits, not too short)
        if len(by_comma) >= 2 and all(
            re.match(r"^[A-Za-zÀ-ỿ .'-]+$", s) and len(s) > 2
            for s in by_comma
        ):
            parts = by_comma

    return parts


def extract_name(raw: str) -> str:
    """Extract the candidate name string from a free-text field.

    Strategy (ordered by precision):
    1. ALL-CAPS run of ≥2 words — reliable in ID/TH/VN agent notes
    2. Arrow pattern "wrong → correct": take the right-hand side
    3. Longest run of Title-Case words (≥2 consecutive)
    4. Return raw stripped if nothing better found

    Returns the extracted string, or empty string if extraction fails.
    """
    raw = raw.strip()
    if not raw:
        return ""

    # Arrow: "WRONG NAME → CORRECT NAME"
    arrow_parts = _ARROW.split(raw)
    if len(arrow_parts) >= 2:
        candidate = arrow_parts[-1].strip()
        if is_plausible_name(candidate):
            return candidate

    # ALL-CAPS run — exclude known non-name uppercase words before matching
    _CAPS_NOISE = re.compile(
        r"\b(NAMA|SAAT|INI|TIKET|YANG|DI|DARI|KE|DAN|ATAU|DENGAN|MENJADI"
        r"|UNTUK|SESUAI|ADA|THE|AND|OR|TO|FROM|FOR|ON|IN|IS|IT|AS|AT|BY)\b"
    )
    stripped = _CAPS_NOISE.sub(" ", raw)
    caps_runs = re.findall(r"\b([A-Z][A-Z]+(?:\s+[A-Z][A-Z]+)*)\b", stripped)
    # prefer multi-word, fall back to single long token (≥5 chars)
    multi_caps = [r for r in caps_runs if " " in r]
    single_caps = [r for r in caps_runs if " " not in r and len(r) >= 5]
    for pool in (multi_caps, single_caps):
        if pool:
            best = max(pool, key=len)
            if is_plausible_name(best):
                return best

    # Title-Case run (≥2 consecutive words starting with uppercase)
    title_runs = re.findall(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\b", raw)
    if title_runs:
        best = max(title_runs, key=len)
        if is_plausible_name(best):
            return best

    # Fallback: return raw if already plausible
    if is_plausible_name(raw):
        return raw
    return ""


_INTENT_SPELLING = "spelling"
_INTENT_NAME_CHANGE = "name_change"
_INTENT_DOB = "dob"
_INTENT_DOC = "document"
_INTENT_GENDER = "gender"
_INTENT_UNROUTABLE = "unroutable"


def classify_intent(before: str, after: str, country: str = "") -> str:
    """Classify the correction intent from a (nameBefore, nameAfter) pair.

    Returns one of:
        'spelling'    — same person, romanization/typo variant → route to spell checker
        'name_change' — different person or full name replacement
        'dob'         — date-of-birth correction
        'document'    — document number / booking ref change
        'gender'      — title/gender change only
        'unroutable'  — cannot determine intent (native script only, junk, etc.)
    """
    combined = before + " " + after

    # Native-script-only: cannot process without transliteration
    latin_chars = re.sub(r"[^A-Za-zÀ-ỿ]", "", combined)
    if not latin_chars:
        return _INTENT_UNROUTABLE

    # DOB signals
    if _DOB_SIGNALS.search(combined):
        return _INTENT_DOB

    # Document number signals
    if _DOCNUM_SIGNALS.search(combined):
        return _INTENT_DOC

    # Gender/title-only change: both sides resolve to same name tokens.
    # Tokenize the RAW strings so strip_gender_markers sees "(Nữ)" intact.
    toks_b = tokenize(before, strip_particles=False)
    toks_a = tokenize(after, strip_particles=False)
    # Strip titles and check if remaining tokens identical
    def _no_title(toks):
        return [t for t in toks if t not in TITLES]
    if _no_title(toks_b) and _no_title(toks_a) and _no_title(toks_b) == _no_title(toks_a):
        return _INTENT_GENDER

    # Free-text prose in either field — route if we can extract names from both
    if _PROSE_SIGNALS.search(combined):
        # If after is already a clean name, before must contain the misspelling
        if is_plausible_name(after):
            name_b = extract_name(before)
            if name_b:
                return _INTENT_SPELLING
        name_a = extract_name(after)
        name_b = extract_name(before)
        if name_a and name_b:
            return _INTENT_SPELLING
        return _INTENT_UNROUTABLE

    # Both sides look like plausible names → spelling correction,
    # unless the pair score says this is a different name entirely (3a)
    if is_plausible_name(before) and is_plausible_name(after):
        return _spelling_or_name_change(before, after, country)

    # One side extractable
    name_b = extract_name(before)
    name_a = extract_name(after)
    if name_b and name_a:
        return _spelling_or_name_change(name_b, name_a, country)

    return _INTENT_UNROUTABLE


def _spelling_or_name_change(before: str, after: str, country: str) -> str:
    """3a: distinguish a misspelling from a full name replacement using the
    pair scorer. Lazy import avoids a circular dependency."""
    from .checker import score_pair, REVIEW
    if score_pair(before, after, country) > REVIEW:
        return _INTENT_NAME_CHANGE
    return _INTENT_SPELLING
