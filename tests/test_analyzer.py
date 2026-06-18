"""Tests for core.analyzer."""

import pandas as pd
import pytest

from core.analyzer import (
    compute_monthly_summary,
    compute_price_over_time,
    compute_price_per_kg,
    compute_spending_by_category,
    compute_summary_metrics,
    compute_top_items,
    list_trackable_products,
)


@pytest.fixture()
def sample_items() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "receipt_id": "a1",
                "date": "2024-01-10",
                "name": "Mjölk",
                "price": 15.0,
                "quantity": 2.0,
                "category": "Mejeri & Ägg",
            },
            {
                "receipt_id": "a1",
                "date": "2024-01-10",
                "name": "Bröd",
                "price": 30.0,
                "quantity": 1.0,
                "category": "Bröd & Bakverk",
            },
            {
                "receipt_id": "b2",
                "date": "2024-02-05",
                "name": "Mjölk",
                "price": 15.0,
                "quantity": 1.0,
                "category": "Mejeri & Ägg",
            },
            {
                "receipt_id": "b2",
                "date": "2024-02-05",
                "name": "Chips",
                "price": 25.0,
                "quantity": 1.0,
                "category": "Snacks & Godis",
            },
        ]
    )


class TestComputeSpendingByCategory:
    def test_returns_correct_totals(self, sample_items: pd.DataFrame) -> None:
        result = compute_spending_by_category(sample_items)
        totals = dict(zip(result["category"], result["total"]))
        assert totals["Mejeri & Ägg"] == pytest.approx(45.0)  # 15*2 + 15*1
        assert totals["Bröd & Bakverk"] == pytest.approx(30.0)
        assert totals["Snacks & Godis"] == pytest.approx(25.0)

    def test_sorted_descending(self, sample_items: pd.DataFrame) -> None:
        result = compute_spending_by_category(sample_items)
        assert result["total"].is_monotonic_decreasing

    def test_empty_input(self) -> None:
        result = compute_spending_by_category(pd.DataFrame())
        assert result.empty


class TestComputeTopItems:
    def test_most_purchased_first(self, sample_items: pd.DataFrame) -> None:
        result = compute_top_items(sample_items)
        assert result.iloc[0]["name"] == "Mjölk"
        assert result.iloc[0]["count"] == pytest.approx(3.0)

    def test_respects_n_limit(self, sample_items: pd.DataFrame) -> None:
        result = compute_top_items(sample_items, n=1)
        assert len(result) == 1

    def test_empty_input(self) -> None:
        result = compute_top_items(pd.DataFrame())
        assert result.empty


class TestComputeMonthlySummary:
    def test_groups_by_month(self, sample_items: pd.DataFrame) -> None:
        result = compute_monthly_summary(sample_items)
        assert set(result["month"]) == {"2024-01", "2024-02"}

    def test_sorted_ascending(self, sample_items: pd.DataFrame) -> None:
        result = compute_monthly_summary(sample_items)
        assert list(result["month"]) == sorted(result["month"])

    def test_empty_input(self) -> None:
        result = compute_monthly_summary(pd.DataFrame())
        assert result.empty

    def test_drops_unparseable_dates(self, sample_items: pd.DataFrame) -> None:
        bad_row = pd.DataFrame(
            [
                {
                    "receipt_id": "c3",
                    "date": "not-a-date",
                    "name": "Mystisk vara",
                    "price": 99.0,
                    "quantity": 1.0,
                    "category": "Övrigt",
                }
            ]
        )
        result = compute_monthly_summary(pd.concat([sample_items, bad_row]))
        assert set(result["month"]) == {"2024-01", "2024-02"}

    def test_all_dates_unparseable_returns_empty(self) -> None:
        df = pd.DataFrame([{"date": "bad", "price": 10.0, "quantity": 1.0}])
        assert compute_monthly_summary(df).empty


@pytest.fixture()
def price_items() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "canonical_name": "Banan",
                "date": "2024-01-10",
                "price": 20.0,
                "unit": "kg",
            },
            {
                "canonical_name": "Banan",
                "date": "2024-02-10",
                "price": 24.0,
                "unit": "kg",
            },
            {
                "canonical_name": "Banan",
                "date": "2024-02-10",
                "price": 26.0,
                "unit": "kg",
            },
            {
                "canonical_name": "Mjölk",
                "date": "2024-01-10",
                "price": 15.0,
                "unit": "st",
            },
            {
                "canonical_name": "Räkor",
                "date": "2024-01-10",
                "price": 200.0,
                "unit": "kg",
            },
        ]
    )


class TestListTrackableProducts:
    def test_only_products_with_multiple_dates(self, price_items: pd.DataFrame) -> None:
        # Banan has two distinct dates; Mjölk and Räkor have one each.
        assert list_trackable_products(price_items) == ["Banan"]

    def test_empty_input(self) -> None:
        assert list_trackable_products(pd.DataFrame()) == []


class TestComputePriceOverTime:
    def test_returns_price_by_date(self, price_items: pd.DataFrame) -> None:
        result = compute_price_over_time(price_items, "Banan")
        assert list(result["date"]) == ["2024-01-10", "2024-02-10"]
        assert result.iloc[0]["price"] == pytest.approx(20.0)
        # Two prices on the same date are averaged: (24 + 26) / 2.
        assert result.iloc[1]["price"] == pytest.approx(25.0)

    def test_unknown_product_returns_empty(self, price_items: pd.DataFrame) -> None:
        assert compute_price_over_time(price_items, "Saknas").empty

    def test_empty_input(self) -> None:
        assert compute_price_over_time(pd.DataFrame(), "Banan").empty


class TestComputePricePerKg:
    def test_only_weight_sold_items(self, price_items: pd.DataFrame) -> None:
        result = compute_price_per_kg(price_items)
        names = set(result["canonical_name"])
        assert "Mjölk" not in names  # sold per piece
        assert {"Banan", "Räkor"} <= names

    def test_avg_and_latest_price(self, price_items: pd.DataFrame) -> None:
        result = compute_price_per_kg(price_items)
        banan = result[result["canonical_name"] == "Banan"].iloc[0]
        assert banan["avg_price"] == pytest.approx((20.0 + 24.0 + 26.0) / 3)
        assert banan["latest_price"] == pytest.approx(26.0)  # last by date

    def test_sorted_by_avg_price_descending(self, price_items: pd.DataFrame) -> None:
        result = compute_price_per_kg(price_items)
        assert result["avg_price"].is_monotonic_decreasing

    def test_empty_when_no_weight_items(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "canonical_name": "Mjölk",
                    "unit": "st",
                    "price": 15.0,
                    "date": "2024-01-10",
                }
            ]
        )
        assert compute_price_per_kg(df).empty

    def test_empty_input(self) -> None:
        assert compute_price_per_kg(pd.DataFrame()).empty


class TestComputeSummaryMetrics:
    def test_correct_totals(self, sample_items: pd.DataFrame) -> None:
        metrics = compute_summary_metrics(sample_items)
        assert metrics["total_spent"] == pytest.approx(100.0)  # 30+30+15+25
        assert metrics["num_receipts"] == 2
        assert metrics["num_items"] == 4

    def test_empty_input(self) -> None:
        metrics = compute_summary_metrics(pd.DataFrame())
        assert metrics["total_spent"] == 0.0
        assert metrics["num_receipts"] == 0
