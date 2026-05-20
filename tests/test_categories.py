"""Tests for core.categories."""

import pytest

from core.categories import UNCATEGORIZED, categorize_item


@pytest.mark.parametrize(
    "name, expected_category",
    [
        ("Arla Mellanmjölk 1,5% 1l", "Mejeri & Ägg"),
        ("Ägg 12-pack", "Mejeri & Ägg"),
        ("Kycklingfilé 700g", "Kött & Chark"),
        ("Köttfärs 500g", "Kött & Chark"),
        ("Lax Fryst 400g", "Fisk & Skaldjur"),
        ("Äpple Gala 1kg", "Frukt"),
        ("Banan Eko", "Frukt"),
        ("Tomat Kvisttomater", "Grönsaker"),
        ("Potatis Mandelpotatis 1kg", "Grönsaker"),
        ("Levain Surdegsbröd", "Bröd & Bakverk"),
        ("Havregryn 1kg", "Skafferi"),
        ("Pasta Penne 500g", "Skafferi"),
        ("Apelsinjuice 1l", "Dryck"),
        ("Kaffe Mellanrost 500g", "Dryck"),
        ("Olivolja Extra Virgin", "Skafferi"),
        ("Chips Sourcream & Onion", "Snacks & Godis"),
        ("Chokladkaka 200g", "Snacks & Godis"),
        ("Fryst Pizza", "Fryst"),
        ("Diskmedel Fairy", "Hygien & Rengöring"),
        ("Toapapper 8-pack", "Hygien & Rengöring"),
        ("Okänd Produkt XYZ", UNCATEGORIZED),
    ],
)
def test_categorize_item(name: str, expected_category: str) -> None:
    assert categorize_item(name) == expected_category


def test_categorize_item_case_insensitive() -> None:
    assert categorize_item("MJÖLK") == categorize_item("mjölk")


def test_categorize_item_empty_string() -> None:
    assert categorize_item("") == UNCATEGORIZED
