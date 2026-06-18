"""Tests for core.canonical."""

from __future__ import annotations

import pytest

from core.canonical import canonical_name


class TestCanonicalName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Gul lök ICA", "Lök"),
            ("Lök vit Morado ICA", "Lök"),
            ("Salladslök", "Lök"),
            ("Snackmorot ICA200g", "Morot"),
            ("Kål Spets", "Kål"),
            ("Pak Choi", "Kål"),
            ("Vispgrädde 36%", "Grädde"),
            ("Banan Eko", "Banan"),
            ("Blodapelsin", "Apelsin"),
            ("Coca-Cola Zero", "Läsk"),
            ("Shimeji brun 150g", "Svamp"),
        ],
    )
    def test_known_variants_map_to_canonical(self, raw: str, expected: str) -> None:
        assert canonical_name(raw) == expected

    def test_unmapped_item_falls_back_to_cleaned_name(self) -> None:
        # No keyword matches; brand/eco/size noise is stripped.
        assert canonical_name("Rotselleri ICA Eko 500g") == "Rotselleri"

    def test_fallback_never_returns_empty(self) -> None:
        assert canonical_name("ICA") == "ICA"

    def test_is_case_insensitive(self) -> None:
        assert canonical_name("GUL LÖK") == "Lök"

    def test_specific_keyword_beats_generic(self) -> None:
        # "krispsallat" must resolve to Sallad, not be shadowed by a shorter term.
        assert canonical_name("Krispsallat") == "Sallad"
