"""Business logic for analyzing grocery receipt data."""

from __future__ import annotations

import pandas as pd


def compute_spending_by_category(items_df: pd.DataFrame) -> pd.DataFrame:
    """Compute total spending per food category.

    Args:
        items_df: DataFrame with columns [category, price, quantity].

    Returns:
        DataFrame with columns [category, total] sorted by total descending.
    """
    if items_df.empty:
        return pd.DataFrame(columns=["category", "total"])

    df = items_df.copy()
    df["total"] = df["price"] * df["quantity"]
    result = df.groupby("category")["total"].sum().reset_index()
    return result.sort_values("total", ascending=False)


def compute_top_items(items_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Compute the most frequently purchased items by total quantity.

    Args:
        items_df: DataFrame with columns [name, quantity].
        n: Number of top items to return.

    Returns:
        DataFrame with columns [name, count] sorted by count descending.
    """
    if items_df.empty:
        return pd.DataFrame(columns=["name", "count"])

    result = (
        items_df.groupby("name")["quantity"]
        .sum()
        .reset_index()
        .rename(columns={"quantity": "count"})
        .sort_values("count", ascending=False)
        .head(n)
    )
    return result


def compute_monthly_summary(items_df: pd.DataFrame) -> pd.DataFrame:
    """Compute total spending grouped by calendar month.

    Args:
        items_df: DataFrame with columns [date, price, quantity].

    Returns:
        DataFrame with columns [month, total] sorted by month ascending.
    """
    if items_df.empty:
        return pd.DataFrame(columns=["month", "total"])

    df = items_df.copy()
    df["total"] = df["price"] * df["quantity"]
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    result = df.groupby("month")["total"].sum().reset_index()
    return result.sort_values("month")


def compute_summary_metrics(items_df: pd.DataFrame) -> dict[str, float | int]:
    """Compute high-level summary metrics from items.

    Args:
        items_df: DataFrame with columns [price, quantity, receipt_id].

    Returns:
        Dictionary with keys: total_spent, num_receipts, num_items.
    """
    if items_df.empty:
        return {"total_spent": 0.0, "num_receipts": 0, "num_items": 0}

    return {
        "total_spent": (items_df["price"] * items_df["quantity"]).sum(),
        "num_receipts": items_df["receipt_id"].nunique(),
        "num_items": len(items_df),
    }
