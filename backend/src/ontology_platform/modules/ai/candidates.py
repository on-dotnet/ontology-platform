"""Shortlisting alignment candidates by name (spec 004, 4.1). Pure: no model, no database.

A new object type is compared with every type it could be by its names alone. Those that score
high enough become candidates, and a model judges whether they are the same concept; the names
themselves decide nothing beyond that (apart from equal main names, guardrail G1). Local names
take no part: the model makes them up.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

# Initial values (spec 004, 4.1); the evaluation weighs 0.5 against 0.6.
THRESHOLD = 0.5
PER_TYPE = 3
# Weights of a pair of names. English labels count as main names.
MAIN_WEIGHT = 1.0
MAIN_SYNONYM_WEIGHT = 0.9
SYNONYM_WEIGHT = 0.8


def normalize(text: str) -> str:
    """Comparison key: NFKC (full-width → half-width), lowercase, no whitespace."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def main_name(label_zh: str | None, label_en: str | None) -> str:
    """The Chinese label, or the English one when there is none (normalized)."""
    return normalize(label_zh or "") or normalize(label_en or "")


def same_main_name(a_zh: str | None, a_en: str | None, b_zh: str | None, b_en: str | None) -> bool:
    """Guardrail G1: the Chinese labels decide; when either side has none, the English ones."""
    a, b = normalize(a_zh or ""), normalize(b_zh or "")
    if a and b:
        return a == b
    a, b = normalize(a_en or ""), normalize(b_en or "")
    return bool(a) and a == b


@dataclass(frozen=True, slots=True)
class Names:
    """Normalized names of a type: labels (main names) and synonyms, without empty ones."""

    main: tuple[str, ...]
    synonyms: tuple[str, ...]

    @classmethod
    def of(cls, label_zh: str | None, label_en: str | None, synonyms: Iterable[str]) -> "Names":
        main = _distinct(normalize(name) for name in (label_zh or "", label_en or ""))
        rest = _distinct(normalize(name) for name in synonyms)
        return cls(main, tuple(name for name in rest if name not in main))


def _distinct(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(name for name in names if name))


def similarity(a: str, b: str) -> float:
    """Of two normalized names (spec 004, 4.1)."""
    if a == b:
        return 1.0 if a else 0.0
    if len(a) <= 1 or len(b) <= 1:
        return 0.0
    short, long_ = sorted((a, b), key=len)
    if short in long_:
        return 0.6 + 0.4 * len(short) / len(long_)
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


@dataclass(frozen=True, slots=True)
class Score:
    value: float
    # The pair reaches the threshold only through a one-character name (guardrail G4).
    one_character: bool = False


def score(a: Names, b: Names, threshold: float = THRESHOLD) -> Score:
    """The best weighted similarity of any two names of the two types."""
    best = longer = 0.0
    pairs = (
        (a.main, b.main, MAIN_WEIGHT),
        (a.main, b.synonyms, MAIN_SYNONYM_WEIGHT),
        (a.synonyms, b.main, MAIN_SYNONYM_WEIGHT),
        (a.synonyms, b.synonyms, SYNONYM_WEIGHT),
    )
    for left, right, weight in pairs:
        for x in left:
            for y in right:
                value = similarity(x, y) * weight
                best = max(best, value)
                if len(x) > 1 and len(y) > 1:
                    longer = max(longer, value)
    return Score(round(best, 4), best >= threshold > longer)


def shortlist[K](
    names: Names,
    pool: Sequence[tuple[K, Names]],
    *,
    threshold: float = THRESHOLD,
    limit: int = PER_TYPE,
) -> list[tuple[K, Score]]:
    """The candidates of a type among `pool`: the best `limit` scoring at least `threshold`.

    Ties keep the order of the pool, so the result does not depend on anything else.
    """
    scored = [(key, score(names, other, threshold)) for key, other in pool]
    kept = [(key, found) for key, found in scored if found.value >= threshold]
    kept.sort(key=lambda entry: -entry[1].value)
    return kept[:limit]


def group_recall(groups: Sequence[Sequence[str]], threshold: float = THRESHOLD) -> tuple[int, int]:
    """Pairs of names within each group that would be candidates, and all such pairs.

    The free, deterministic lower bound of the shortlist's recall (spec 004, 4.1): names of one
    expected concept, each taken as a main name, without the synonyms a model would add.
    """
    hits = total = 0
    for group in groups:
        names = list(_distinct(normalize(name) for name in group))
        for index, a in enumerate(names):
            for b in names[index + 1 :]:
                total += 1
                hits += similarity(a, b) * MAIN_WEIGHT >= threshold
    return hits, total
