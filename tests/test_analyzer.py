"""Tests for core.analyzer."""

import pandas as pd
import pytest

from core.analyzer import (
    compute_monthly_summary,
    compute_spending_by_category,
    compute_summary_metrics,
    compute_top_items,
)


@pytest.fixture()
def sample_items() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"receipt_id": "a1", "date": "2024-01-10", "name": "Mjölk", "price": 15.0, "quantity": 2.0, "category": "Mejeri & Ägg"},
            {"receipt_id": "a1", "date": "2024-01-10", "name": "Bröd", "price": 30.0, "quantity": 1.0, "category": "Bröd & Bakverk"},
            {"receipt_id": "b2", "date": "2024-02-05", "name": "Mjölk", "price": 15.0, "quantity": 1.0, "category": "Mejeri & Ägg"},
            {"receipt_id": "b2", "date": "2024-02-05", "name": "Chips", "price": 25.0, "quantity": 1.0, "category": "Snacks & Godis"},
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
