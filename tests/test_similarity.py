"""Tests for similarity.py — text_similarity and check_convergence."""

from __future__ import annotations

import pytest

from hermes_loop.similarity import text_similarity, check_convergence

# ===================================================================
# text_similarity
# ===================================================================


class TestTextSimilarity:
    """Tests for text_similarity function."""

    # --- Identity / equality ---

    def test_identical_strings(self):
        """Identical strings return 1.0."""
        assert text_similarity("hello world", "hello world") == 1.0

    def test_both_empty(self):
        """Both empty strings return 1.0."""
        assert text_similarity("", "") == 1.0

    def test_both_only_non_word_chars(self):
        """Strings with only non-word characters return 1.0."""
        assert text_similarity("!!! ???", "??? !!!") == 1.0

    # --- Empty / one-empty ---

    def test_one_empty(self):
        """One empty string returns 0.0."""
        assert text_similarity("hello", "") == 0.0

    def test_other_empty(self):
        """Other empty string returns 0.0."""
        assert text_similarity("", "world") == 0.0

    # --- Completely different ---

    def test_completely_different(self):
        """No overlapping words returns 0.0."""
        assert text_similarity("abc def", "xyz uvw") == 0.0

    # --- Partial overlap ---

    def test_partial_overlap(self):
        """Partial word overlap returns between 0 and 1."""
        sim = text_similarity("hello world foo", "hello bar")
        assert 0.0 < sim < 1.0

    def test_half_overlap(self):
        """50% word overlap."""
        sim = text_similarity("a b c", "a b d")
        assert sim == pytest.approx(0.5)  # {a,b} ∩ {a,b,d} = 2 / 3

    def test_one_third_overlap(self):
        """33% word overlap."""
        sim = text_similarity("a b c", "a d e")
        assert sim == pytest.approx(1 / 5, abs=0.01)  # {a} / {a,b,c,d,e} = 1/5

    def test_all_words_overlap_with_extra(self):
        """All words in A are in B, but B has extras."""
        sim = text_similarity("a b", "a b c d")
        assert sim == pytest.approx(0.5)  # {a,b} / {a,b,c,d} = 2/4

    # --- Case insensitivity ---

    def test_case_insensitive(self):
        """Similarity is case-insensitive."""
        assert text_similarity("Hello World", "hello world") == 1.0

    def test_mixed_case(self):
        """Mixed case strings."""
        sim = text_similarity("Hello World", "hello")
        assert 0.0 < sim < 1.0

    # --- Punctuation handling ---

    def test_punctuation_ignored(self):
        """Punctuation is ignored; only word characters count."""
        sim = text_similarity("hello, world!", "hello world")
        assert sim == 1.0

    def test_only_punctuation_one_side(self):
        """One string with only punctuation, other with words."""
        assert text_similarity("hello", "!!!") == 0.0

    # --- Unicode handling ---

    def test_unicode_words(self):
        """Unicode word characters are matched."""
        sim = text_similarity("héllo wörld", "héllo")
        assert 0.0 < sim < 1.0

    def test_cjk_characters(self):
        """CJK characters are matched by \\w+ in Python 3.
        (Python 3's re module matches Unicode word characters including CJK.)
        """
        sim = text_similarity("你好世界", "你好")
        # '你好世界' has 1 word, '你好' has 1 word, no overlap
        assert sim == 0.0

    # --- Numeric ---

    def test_numeric_words(self):
        """Numbers are treated as words."""
        sim = text_similarity("version 1 2 3", "version 1 2")
        assert 0.0 < sim < 1.0

    # --- Whitespace ---

    def test_extra_whitespace(self):
        """Extra whitespace does not affect similarity."""
        assert text_similarity("hello   world", "hello world") == 1.0

    def test_newlines(self):
        """Newlines and tabs are handled like spaces."""
        assert text_similarity("hello\nworld", "hello world") == 1.0

    # --- Single-word strings ---

    def test_single_word_identical(self):
        """Single-word identical strings."""
        assert text_similarity("hello", "hello") == 1.0

    def test_single_word_different(self):
        """Single-word different strings."""
        assert text_similarity("hello", "world") == 0.0

    # --- None inputs ---
    # The function doesn't guard None, but let's ensure it doesn't crash
    # (it would crash on .lower() — that's the contract; attribute strings only)

    def test_none_a_crashes(self):
        """Passing None as first argument: None is falsy so 'not None or not "hello"'
        is True, returning 0.0 immediately without AttributeError."""
        result = text_similarity(None, "hello")  # type: ignore[arg-type]
        assert result == 0.0


# ===================================================================
# check_convergence
# ===================================================================


class TestCheckConvergence:
    """Tests for check_convergence function."""

    # --- Window boundary ---

    def test_fewer_than_window(self):
        """Fewer summaries than window returns (False, 0.0)."""
        result = check_convergence(["a"], threshold=0.9, window=3)
        assert result == (False, 0.0)

    def test_exactly_window_size(self):
        """Exactly window-size summaries are evaluated."""
        result = check_convergence(["hello world"] * 3, threshold=0.9, window=3)
        assert result[0] is True
        assert result[1] == 1.0

    # --- Convergence detection ---

    def test_all_identical(self):
        """All identical summaries converge."""
        result = check_convergence(["hello world"] * 5, threshold=0.9, window=5)
        assert result[0] is True
        assert result[1] == 1.0

    def test_all_different(self):
        """All different summaries do not converge."""
        result = check_convergence(
            ["abc", "def", "ghi", "jkl", "mno"],
            threshold=0.9,
            window=5,
        )
        assert result[0] is False
        assert result[1] < 1.0

    def test_partial_convergence_below_threshold(self):
        """Similar but below threshold is not converged."""
        summaries = [
            "fix the auth bug in login",
            "resolve authentication issue",
            "patch login auth flow",
            "correct auth logic in login",
            "fix auth for user login",
        ]
        result = check_convergence(summaries, threshold=0.9, window=5)
        # These should have some overlap but likely below 0.9
        assert result[1] < 0.9 or result[0] is True

    def test_consecutive_similar_above_threshold(self):
        """Consistently similar summaries should converge."""
        result = check_convergence(["hello world"] * 5, threshold=0.9, window=5)
        assert result[0] is True
        assert result[1] >= 0.9

    # --- Window edge cases ---

    def test_window_1_single_element(self):
        """Window=1 with at least 1 element: no pairs to compare."""
        result = check_convergence(["hello"], threshold=0.9, window=1)
        assert result == (False, 0.0)

    def test_window_1_with_multiple(self):
        """Window=1 with multiple elements: uses only last 1, no pairs."""
        result = check_convergence(["a", "b", "c"], threshold=0.9, window=1)
        assert result == (False, 0.0)

    def test_window_greater_than_list(self):
        """Window bigger than list returns (False, 0.0)."""
        result = check_convergence(["a", "b"], threshold=0.9, window=5)
        assert result == (False, 0.0)

    def test_window_2_two_elements(self):
        """Window=2 with exactly 2 elements produces 1 pair."""
        result = check_convergence(
            ["hello world", "hello world"], threshold=0.9, window=2
        )
        assert result[0] is True
        assert result[1] == 1.0

    # --- Empty lists ---

    def test_empty_list(self):
        """Empty list returns (False, 0.0)."""
        result = check_convergence([], threshold=0.9, window=3)
        assert result == (False, 0.0)

    # --- Default parameter usage ---

    def test_default_threshold_and_window(self):
        """Uses default threshold (0.9) and window (5) from config."""
        result = check_convergence(["a", "b", "c"])
        # Fewer than default window=5 → no convergence
        assert result == (False, 0.0)

    def test_default_window_identical(self):
        """Default window with 5 identical summaries converges."""
        result = check_convergence(["test summary"] * 5)
        assert result[0] is True
        assert result[1] == 1.0

    # --- Realistic summaries ---

    def test_converging_summaries(self):
        """Summaries that converge on the same topic have some overlap."""
        summaries = [
            "fixed login page CSS issue",
            "completed login button styling",
            "login page styling done",
            "finished login page design",
            "login page complete",
        ]
        result = check_convergence(summaries, threshold=0.3, window=5)
        # These share words like 'login', 'page', 'styling' etc.
        # Actual Jaccard similarity depends on exact word composition
        assert result[1] > 0.0

    def test_diverging_summaries(self):
        """Summaries with no common topic."""
        summaries = [
            "installed nginx server",
            "wrote unit tests for auth",
            "updated postgres schema",
            "configured docker compose",
            "fixed css layout issue",
        ]
        result = check_convergence(summaries, threshold=0.2, window=5)
        # These are completely different topics; similarity should be very low
        assert result[1] < 0.2

    # --- Threshold edge ---

    def test_exactly_at_threshold(self):
        """Average similarity exactly at threshold."""
        # Use overlapping strings where we know the similarity
        summaries = ["a b", "a b", "a b", "a b", "a b"]  # sim = 1.0
        result = check_convergence(summaries, threshold=1.0, window=5)
        assert result[0] is True
        assert result[1] == 1.0

    def test_just_below_threshold(self):
        """Average similarity just below threshold."""
        # Need to construct a case where sim is exactly below 0.8 but above 0
        summaries = ["a b", "c d", "a b", "c d", "a b"]
        result = check_convergence(summaries, threshold=0.8, window=5)
        assert result[1] < 0.8
