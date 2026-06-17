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


def compute_category_breakdown(items_df: pd.DataFrame) -> pd.DataFrame:
    """Compute spending per category and subcategory for a hierarchical view.

    When subcategory is empty, falls back to canonical_name (the generic
    product label produced by the LLM, e.g. "Morot" or "Spagetti"), then to
    the raw item name, so every leaf in the chart carries a meaningful label
    instead of "Övrigt".

    Args:
        items_df: DataFrame with columns [category, price, quantity] and
            optionally [subcategory], [canonical_name], [name].

    Returns:
        DataFrame with columns [category, subcategory, total] sorted by total
        descending.
    """
    if items_df.empty:
        return pd.DataFrame(columns=["category", "subcategory", "total"])

    df = items_df.copy()
    if "subcategory" not in df.columns:
        df["subcategory"] = ""
    df["subcategory"] = df["subcategory"].fillna("").str.strip()

    # Fill missing subcategory with canonical_name, then raw name, then "Övrigt".
    if "canonical_name" in df.columns:
        mask = df["subcategory"] == ""
        df.loc[mask, "subcategory"] = df.loc[mask, "canonical_name"].fillna("")
    if "name" in df.columns:
        mask = df["subcategory"] == ""
        df.loc[mask, "subcategory"] = df.loc[mask, "name"].fillna("")
    df["subcategory"] = df["subcategory"].replace("", "Övrigt")

    df["total"] = df["price"] * df["quantity"]
    result = (
        df.groupby(["category", "subcategory"])["total"].sum().reset_index()
    )
    return result.sort_values("total", ascending=False)


def compute_top_items(items_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Compute the most frequently purchased items by total quantity.

    Items are grouped by their canonical name when available, so brand and size
    variants of the same product (e.g. different egg brands) count together.
    Falls back to the raw name column when no canonical name is present.

    Args:
        items_df: DataFrame with columns [quantity] plus [canonical_name] or [name].
        n: Number of top items to return.

    Returns:
        DataFrame with columns [name, count] sorted by count descending.
    """
    if items_df.empty:
        return pd.DataFrame(columns=["name", "count"])

    group_col = "canonical_name" if "canonical_name" in items_df.columns else "name"
    result = (
        items_df.groupby(group_col)["quantity"]
        .sum()
        .reset_index()
        .rename(columns={group_col: "name", "quantity": "count"})
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
