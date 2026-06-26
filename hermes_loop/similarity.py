"""Text similarity for convergence detection (stdlib only)."""

import re

from .config import DEFAULT_CONVERGENCE_THRESHOLD, DEFAULT_CONVERGENCE_WINDOW


def text_similarity(a: str, b: str) -> float:
    """Compute similarity between two strings using word overlap (Jaccard).

    Returns a float 0.0 (completely different) to 1.0 (identical).
    Uses only Python stdlib — no numpy/scikit-learn dependency.
    Handles short strings gracefully.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    words_a = set(re.findall(r"\w+", a.lower()))
    words_b = set(re.findall(r"\w+", b.lower()))

    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def check_convergence(
    summaries: list[str],
    threshold: float = DEFAULT_CONVERGENCE_THRESHOLD,
    window: int = DEFAULT_CONVERGENCE_WINDOW,
) -> tuple[bool, float]:
    """Check if the last N summaries indicate convergence.

    Returns (is_converged, avg_similarity) where is_converged is True
    when ALL pairs in the window exceed the threshold.
    """
    if len(summaries) < window:
        return False, 0.0

    recent = summaries[-window:]
    similarities = []
    for i in range(len(recent)):
        for j in range(i + 1, len(recent)):
            similarities.append(text_similarity(recent[i], recent[j]))

    if not similarities:
        return False, 0.0

    avg_sim = sum(similarities) / len(similarities)
    return avg_sim >= threshold, avg_sim
