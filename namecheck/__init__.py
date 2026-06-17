"""namecheck — spell checker for romanized East/Southeast Asian names.

Usage:
    from namecheck import score_pair, verdict, NameChecker

    score_pair("GWANGEUN JEONG", "KWANGEUN JEONG", "korea")  # ~0.02 -> accept

    nc = NameChecker()
    nc.add_reference("NGUYEN THI SU", "vietnam")
    nc.check("NGUYE THI SU", "vietnam")
    # {'status': 'accept', 'suggestions': [{'name': 'NGUYEN THI SU', ...}]}
"""
from .checker import NameChecker, score_pair, verdict, AUTO_ACCEPT, REVIEW
from .normalize import is_plausible_name, tokenize, split_passengers, extract_name, classify_intent
from .scorer import norm_score

__all__ = [
    "NameChecker", "score_pair", "verdict", "AUTO_ACCEPT", "REVIEW",
    "is_plausible_name", "tokenize", "norm_score",
    "split_passengers", "extract_name", "classify_intent",
]
