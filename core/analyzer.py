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
        Rows whose date cannot be parsed are dropped; if no row has a valid
        date an empty DataFrame is returned.
    """
    if items_df.empty:
        return pd.DataFrame(columns=["month", "total"])

    df = items_df.copy()
    df["total"] = df["price"] * df["quantity"]
    parsed_dates = pd.to_datetime(df["date"], errors="coerce")
    df = df[parsed_dates.notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=["month", "total"])
    df["month"] = parsed_dates.dropna().dt.to_period("M").astype(str)
    result = df.groupby("month")["total"].sum().reset_index()
    return result.sort_values("month")


def list_trackable_products(items_df: pd.DataFrame) -> list[str]:
    """List canonical products that appear on at least two distinct dates.

    A price trend needs more than one data point, so single-purchase products
    are excluded from the selector.

    Args:
        items_df: DataFrame with columns [canonical_name, date].

    Returns:
        Canonical product names sorted alphabetically.
    """
    if items_df.empty or "canonical_name" not in items_df.columns:
        return []

    dates_per_product = items_df.groupby("canonical_name")["date"].nunique()
    trackable = dates_per_product[dates_per_product >= 2].index
    return sorted(trackable)


def compute_price_over_time(
    items_df: pd.DataFrame, canonical_name: str
) -> pd.DataFrame:
    """Compute the unit price of a single product over time.

    Args:
        items_df: DataFrame with columns [canonical_name, date, price].
        canonical_name: The canonical product to track.

    Returns:
        DataFrame with columns [date, price] sorted by date ascending. When a
        product was bought more than once on the same date, prices are averaged.
        Empty if the product is not present.
    """
    if items_df.empty or "canonical_name" not in items_df.columns:
        return pd.DataFrame(columns=["date", "price"])

    product = items_df[items_df["canonical_name"] == canonical_name]
    if product.empty:
        return pd.DataFrame(columns=["date", "price"])

    result = product.groupby("date")["price"].mean().reset_index()
    return result.sort_values("date")


def compute_price_per_kg(items_df: pd.DataFrame) -> pd.DataFrame:
    """Compute price per kilogram/litre for weight- and volume-sold products.

    Only items whose selling unit is 'kg' or 'l' carry a meaningful price per
    unit; per-piece items are excluded because their package weight is unknown.

    Args:
        items_df: DataFrame with columns [canonical_name, unit, price, date].

    Returns:
        DataFrame with columns [canonical_name, unit, avg_price, latest_price]
        sorted by avg_price descending. Empty if no weight-sold items exist.
    """
    expected = ["canonical_name", "unit", "avg_price", "latest_price"]
    if items_df.empty or not {"unit", "canonical_name"}.issubset(items_df.columns):
        return pd.DataFrame(columns=expected)

    weighed = items_df[items_df["unit"].isin(["kg", "l"])]
    if weighed.empty:
        return pd.DataFrame(columns=expected)

    latest = (
        weighed.sort_values("date")
        .groupby(["canonical_name", "unit"])["price"]
        .last()
        .rename("latest_price")
    )
    avg = (
        weighed.groupby(["canonical_name", "unit"])["price"].mean().rename("avg_price")
    )
    result = pd.concat([avg, latest], axis=1).reset_index()
    return result.sort_values("avg_price", ascending=False)


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
