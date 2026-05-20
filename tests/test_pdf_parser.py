"""Tests for integrations.pdf_parser (using synthetic text, no real PDFs)."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.pdf_parser import (
    _extract_date,
    _extract_items,
    _extract_store,
    _extract_total,
    _parse_price,
    _should_skip,
    parse_ica_receipt,
)

_REAL_RECEIPT = (
    Path(__file__).parent
    / "data"
    / "ICA Kvantum Malmborgs Caroli 530,03 kr 2026-04-27.pdf"
)


class TestParsePrice:
    def test_simple(self) -> None:
        assert _parse_price("12,90") == pytest.approx(12.90)

    def test_with_space(self) -> None:
        assert _parse_price("1 234,00") == pytest.approx(1234.00)

    def test_invalid(self) -> None:
        assert _parse_price("abc") == 0.0


class TestShouldSkip:
    def test_skips_summa(self) -> None:
        assert _should_skip("Summa    245,60") is True

    def test_skips_moms(self) -> None:
        assert _should_skip("Varav moms 12%  14,23") is True

    def test_skips_kort(self) -> None:
        assert _should_skip("Kort  245,60") is True

    def test_keeps_regular_item(self) -> None:
        assert _should_skip("Arla Mellanmjölk 1,5% 1l  15,90") is False

    def test_does_not_skip_storkoepsrabatt(self) -> None:
        assert _should_skip("Storköpsrabatt -27,90") is False


class TestExtractDate:
    def test_finds_iso_date(self) -> None:
        lines = ["ICA Supermarket", "2024-03-15 14:23", "Kassakvitto"]
        assert _extract_date(lines) == "2024-03-15"

    def test_returns_today_if_missing(self) -> None:
        from datetime import datetime

        result = _extract_date(["Ingen datum här"])
        datetime.strptime(result, "%Y-%m-%d")


class TestExtractStore:
    def test_finds_ica_in_header(self) -> None:
        lines = ["ICA Supermarket Centrum", "Storgatan 1"]
        assert _extract_store(lines) == "ICA Supermarket Centrum"

    def test_falls_back_to_ica(self) -> None:
        lines = ["Ingen butik här"]
        assert _extract_store(lines) == "ICA"


class TestExtractTotal:
    def test_finds_summa(self) -> None:
        lines = ["Arla Mjölk  15,90", "Summa  245,60"]
        assert _extract_total(lines) == pytest.approx(245.60)

    def test_returns_zero_if_missing(self) -> None:
        assert _extract_total(["Bara vanliga rader"]) == 0.0


class TestExtractItems:
    def test_parses_simple_items(self) -> None:
        lines = [
            "ICA Supermarket",
            "2024-01-15",
            "Arla Mellanmjölk 1,5% 1l  15,90",
            "Kycklingfilé 700g  89,90",
            "Summa  105,80",
        ]
        items, savings = _extract_items(lines)
        assert len(items) == 2
        assert items[0]["name"] == "Arla Mellanmjölk 1,5% 1l"
        assert items[0]["price"] == pytest.approx(15.90)
        assert items[0]["quantity"] == pytest.approx(1.0)
        assert items[0]["deal"] is None
        assert savings == []

    def test_strips_asterisk_from_name(self) -> None:
        items, _ = _extract_items(["*Chorizo vegan  35,86"])
        assert items[0]["name"] == "Chorizo vegan"

    def test_strips_embedded_article_detail(self) -> None:
        items, _ = _extract_items(["Broccoli 1318857 17,99 1,00 st 17,99"])
        assert items[0]["name"] == "Broccoli"

    def test_parses_quantity_line(self) -> None:
        lines = [
            "Bregott Entre 500g  79,80",
            "2 x 39,90",
        ]
        items, _ = _extract_items(lines)
        assert len(items) == 1
        assert items[0]["quantity"] == pytest.approx(2.0)

    def test_attaches_deal_to_parent_item(self) -> None:
        lines = [
            "*Chorizo vegan  35,86",
            "Vegankorv, 29kr/st -6,86",
            "Broccoli  17,99",
        ]
        items, savings = _extract_items(lines)
        assert len(items) == 2
        assert items[0]["deal"] is not None
        assert items[0]["deal"]["name"] == "Vegankorv, 29kr/st"
        assert items[0]["deal"]["discount"] == pytest.approx(-6.86)
        assert items[1]["deal"] is None
        assert savings == []

    def test_deal_line_not_added_as_separate_item(self) -> None:
        lines = [
            "*Chorizo vegan  35,86",
            "Vegankorv, 29kr/st -6,86",
        ]
        items, _ = _extract_items(lines)
        assert len(items) == 1

    def test_standalone_negative_line_goes_to_savings(self) -> None:
        lines = [
            "Broccoli  17,99",
            "Storköpsrabatt -27,90",
        ]
        items, savings = _extract_items(lines)
        assert len(items) == 1
        assert len(savings) == 1
        assert savings[0]["name"] == "Storköpsrabatt"
        assert savings[0]["amount"] == pytest.approx(-27.90)

    def test_skips_summary_lines(self) -> None:
        lines = [
            "Summa  100,00",
            "Varav moms 12%  10,71",
            "Kort  100,00",
        ]
        items, savings = _extract_items(lines)
        assert items == []
        assert savings == []

    def test_skips_zero_price(self) -> None:
        lines = ["Märklig rad utan pris"]
        items, _ = _extract_items(lines)
        assert items == []


class TestParseIcaReceiptRealFile:
    def test_date(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        assert result["date"] == "2026-04-27"

    def test_store(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        assert result["store"] == "ICA Kvantum Malmborgs Caroli"

    def test_total(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        assert result["total"] == pytest.approx(530.03)

    def test_item_count(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        assert len(result["items"]) == 19

    def test_items_have_required_keys(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        for item in result["items"]:
            assert "name" in item
            assert "price" in item
            assert "quantity" in item
            assert "deal" in item

    def test_item_names_are_clean(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        for item in result["items"]:
            assert not item["name"].startswith("*")
            # No embedded article number (7+ digit code)
            assert not any(
                part.isdigit() and len(part) >= 7
                for part in item["name"].split()
            )

    def test_known_item_present(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        names = [item["name"] for item in result["items"]]
        assert "Broccoli" in names

    def test_items_with_deals(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        deals = [item for item in result["items"] if item["deal"] is not None]
        assert len(deals) == 4

    def test_deal_structure(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        deals = [item for item in result["items"] if item["deal"] is not None]
        for item in deals:
            assert "name" in item["deal"]
            assert "discount" in item["deal"]
            assert item["deal"]["discount"] < 0

    def test_no_asterisk_in_item_names(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        for item in result["items"]:
            assert "*" not in item["name"]

    def test_savings_list(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        assert len(result["savings"]) == 1
        assert result["savings"][0]["name"] == "Storköpsrabatt"
        assert result["savings"][0]["amount"] == pytest.approx(-27.90)

    def test_savings_have_required_keys(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        for s in result["savings"]:
            assert "name" in s
            assert "amount" in s
            assert s["amount"] < 0

    def test_item_sum_matches_total(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        item_sum = sum(
            item["price"] * item["quantity"] + (item["deal"]["discount"] if item["deal"] else 0)
            for item in result["items"]
        )
        savings_sum = sum(s["amount"] for s in result["savings"])
        assert item_sum + savings_sum == pytest.approx(result["total"], abs=0.01)

    @pytest.mark.parametrize("bad_name", ["poäng", "rabatt", "Betalat", "Köp", "6,00 25,40 423,", "25,00 16,30 65,"])
    def test_payment_and_vat_lines_excluded(self, bad_name: str) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        names = [item["name"] for item in result["items"]]
        assert not any(bad_name in name for name in names)

    def test_deal_lines_not_separate_items(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        names = [item["name"] for item in result["items"]]
        assert not any("Vegankorv" in name for name in names)
        assert not any("2f28kr" in name for name in names)
        assert not any("2f25kr" in name for name in names)

    def test_storkoepsrabatt_not_an_item(self) -> None:
        result = parse_ica_receipt(_REAL_RECEIPT)
        names = [item["name"] for item in result["items"]]
        assert not any("Storköpsrabatt" in name for name in names)

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_ica_receipt("nonexistent.pdf")
