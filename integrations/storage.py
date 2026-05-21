"""CSV-based persistence for receipts and line items."""

from __future__ import annotations

import csv
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from core.categories import all_categories

_DATA_DIR = Path(__file__).parent.parent / "data"
_RECEIPTS_CSV = _DATA_DIR / "receipts.csv"
_ITEMS_CSV = _DATA_DIR / "items.csv"
_SAVINGS_CSV = _DATA_DIR / "savings.csv"

_RECEIPT_FIELDS = ["receipt_id", "date", "store", "total", "filename"]
_ITEM_FIELDS = [
    "id", "receipt_id", "date", "name", "price", "quantity", "category",
    "deal_name", "deal_discount",
]
_SAVINGS_FIELDS = ["id", "receipt_id", "date", "name", "amount"]


_CSV_INJECT_RE = re.compile(r"^[=+\-@\t\r]")


def _sanitize(value: str) -> str:
    """Strip leading characters that spreadsheet apps interpret as formula prefixes."""
    return _CSV_INJECT_RE.sub("", value).strip()


def ensure_data_dir() -> None:
    """Create the data directory and CSV files with headers if absent."""
    _DATA_DIR.mkdir(exist_ok=True)
    _ensure_csv(_RECEIPTS_CSV, _RECEIPT_FIELDS)
    _ensure_csv(_ITEMS_CSV, _ITEM_FIELDS)
    _ensure_csv(_SAVINGS_CSV, _SAVINGS_FIELDS)


def save_receipt(parsed: dict[str, Any], filename: str) -> str:
    """Persist a parsed receipt and its items to CSV.

    Args:
        parsed: Output from pdf_parser.parse_ica_receipt, with items
            already enriched with a 'category' field.
        filename: Original filename of the uploaded PDF.

    Returns:
        The generated receipt_id (8-character hex string).

    Raises:
        IOError: If writing to the CSV files fails.
    """
    ensure_data_dir()
    receipt_id = uuid.uuid4().hex[:8]

    with _RECEIPTS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_RECEIPT_FIELDS)
        writer.writerow(
            {
                "receipt_id": receipt_id,
                "date": parsed["date"],
                "store": _sanitize(parsed["store"]),
                "total": parsed["total"],
                "filename": _sanitize(filename),
            }
        )

    with _ITEMS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_ITEM_FIELDS)
        for item in parsed["items"]:
            deal = item.get("deal") or {}
            writer.writerow(
                {
                    "id": uuid.uuid4().hex[:8],
                    "receipt_id": receipt_id,
                    "date": parsed["date"],
                    "name": _sanitize(item["name"]),
                    "price": item["price"],
                    "quantity": item["quantity"],
                    "category": _sanitize(item.get("category", "Övrigt")),
                    "deal_name": _sanitize(deal.get("name", "")),
                    "deal_discount": deal.get("discount", ""),
                }
            )

    with _SAVINGS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SAVINGS_FIELDS)
        for saving in parsed.get("savings", []):
            writer.writerow(
                {
                    "id": uuid.uuid4().hex[:8],
                    "receipt_id": receipt_id,
                    "date": parsed["date"],
                    "name": _sanitize(saving["name"]),
                    "amount": saving["amount"],
                }
            )

    return receipt_id


def load_receipts() -> pd.DataFrame:
    """Load all receipts from CSV.

    Returns:
        DataFrame with receipt data, empty if none exist.
    """
    ensure_data_dir()
    if _RECEIPTS_CSV.stat().st_size == 0:
        return pd.DataFrame(columns=_RECEIPT_FIELDS)
    df = pd.read_csv(_RECEIPTS_CSV, dtype=str)
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0.0)
    return df


def load_items() -> pd.DataFrame:
    """Load all line items from CSV.

    Returns:
        DataFrame with item data, empty if none exist.
    """
    ensure_data_dir()
    if _ITEMS_CSV.stat().st_size == 0:
        return pd.DataFrame(columns=_ITEM_FIELDS)
    df = pd.read_csv(
        _ITEMS_CSV,
        dtype={"name": str, "category": str, "date": str, "deal_name": str},
    )
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1.0)
    # Back-fill columns added after initial release so old CSV files still load.
    if "deal_name" not in df.columns:
        df["deal_name"] = ""
    if "deal_discount" not in df.columns:
        df["deal_discount"] = 0.0
    df["deal_name"] = df["deal_name"].fillna("")
    df["deal_discount"] = pd.to_numeric(df["deal_discount"], errors="coerce").fillna(0.0)
    return df


def load_savings() -> pd.DataFrame:
    """Load all cart-level savings from CSV.

    Returns:
        DataFrame with savings data, empty if none exist.
    """
    ensure_data_dir()
    if _SAVINGS_CSV.stat().st_size == 0:
        return pd.DataFrame(columns=_SAVINGS_FIELDS)
    df = pd.read_csv(_SAVINGS_CSV, dtype={"name": str, "date": str})
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    return df


def update_item_category(item_id: str, category: str) -> None:
    """Update the category for a single item in storage.

    Args:
        item_id: The 8-character hex item ID.
        category: The new category name.

    Raises:
        KeyError: If no item with the given ID exists.
        IOError: If reading or writing the CSV fails.
    """
    if not re.fullmatch(r"[0-9a-f]{8}", item_id):
        raise ValueError(f"Invalid item_id format: {item_id!r}")
    if category not in all_categories():
        raise ValueError(f"Unknown category: {category!r}")
    ensure_data_dir()
    df = pd.read_csv(_ITEMS_CSV, dtype=str)
    if item_id not in df["id"].values:
        raise KeyError(f"Item not found: {item_id}")
    df.loc[df["id"] == item_id, "category"] = category
    df.to_csv(_ITEMS_CSV, index=False)


def receipt_already_saved(filename: str) -> bool:
    """Check whether a receipt file has already been imported.

    Args:
        filename: The PDF filename to look up.

    Returns:
        True if a receipt with this filename exists in storage.
    """
    receipts = load_receipts()
    if receipts.empty:
        return False
    return filename in receipts["filename"].values


def _ensure_csv(path: Path, fields: list[str]) -> None:
    """Create a CSV with headers if the file is missing or empty."""
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
