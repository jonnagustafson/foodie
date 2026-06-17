"""CSV-based persistence for receipts and line items."""

from __future__ import annotations

import csv
import os
import re
import tempfile
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
    "id",
    "receipt_id",
    "date",
    "name",
    "price",
    "quantity",
    "category",
    "deal_name",
    "deal_discount",
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


def _append_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    """Append rows to a CSV file, raising a clear error on failure.

    Args:
        path: Target CSV file (must already have a header).
        fields: Column order for the DictWriter.
        rows: Rows to append; nothing is written if empty.

    Raises:
        IOError: If the file cannot be opened or written.
    """
    if not rows:
        return
    try:
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writerows(rows)
    except OSError as exc:
        raise IOError(f"Could not write to {path.name}: {exc}") from exc


def save_receipt(parsed: dict[str, Any], filename: str) -> str:
    """Persist a parsed receipt and its items to CSV.

    Rows are written receipt-first; if a later write fails the receipt row may
    already be on disk. Callers should surface the raised IOError rather than
    assume a clean rollback.

    Args:
        parsed: Output from pdf_parser.parse_ica_receipt, with items
            already enriched with a 'category' field.
        filename: Original filename of the uploaded PDF.

    Returns:
        The generated receipt_id (8-character hex string).

    Raises:
        IOError: If writing to any of the CSV files fails.
    """
    ensure_data_dir()
    receipt_id = uuid.uuid4().hex[:8]

    receipt_row = {
        "receipt_id": receipt_id,
        "date": parsed["date"],
        "store": _sanitize(parsed["store"]),
        "total": parsed["total"],
        "filename": _sanitize(filename),
    }
    item_rows = [
        {
            "id": uuid.uuid4().hex[:8],
            "receipt_id": receipt_id,
            "date": parsed["date"],
            "name": _sanitize(item["name"]),
            "price": item["price"],
            "quantity": item["quantity"],
            "category": _sanitize(item.get("category", "Övrigt")),
            "deal_name": _sanitize((item.get("deal") or {}).get("name", "")),
            "deal_discount": (item.get("deal") or {}).get("discount", ""),
        }
        for item in parsed["items"]
    ]
    savings_rows = [
        {
            "id": uuid.uuid4().hex[:8],
            "receipt_id": receipt_id,
            "date": parsed["date"],
            "name": _sanitize(saving["name"]),
            "amount": saving["amount"],
        }
        for saving in parsed.get("savings", [])
    ]

    _append_rows(_RECEIPTS_CSV, _RECEIPT_FIELDS, [receipt_row])
    _append_rows(_ITEMS_CSV, _ITEM_FIELDS, item_rows)
    _append_rows(_SAVINGS_CSV, _SAVINGS_FIELDS, savings_rows)

    return receipt_id


def _load_csv(
    path: Path,
    fields: list[str],
    str_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Read a CSV file, returning an empty DataFrame if absent or header-only.

    Raises:
        IOError: If the file exists but cannot be parsed (e.g. corrupt data).
    """
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=fields)
    dtype = {col: str for col in (str_cols or [])}
    try:
        return pd.read_csv(path, dtype=dtype or None)
    except pd.errors.ParserError as exc:
        raise IOError(
            f"Could not parse {path.name}: {exc}. "
            "The file may be corrupt or written with an incompatible schema."
        ) from exc


def load_receipts() -> pd.DataFrame:
    """Load all receipts from CSV.

    Returns:
        DataFrame with receipt data, empty if none exist.
    """
    df = _load_csv(_RECEIPTS_CSV, _RECEIPT_FIELDS, str_cols=list(_RECEIPT_FIELDS))
    if not df.empty:
        df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0.0)
    return df


def load_items() -> pd.DataFrame:
    """Load all line items from CSV.

    Returns:
        DataFrame with item data, empty if none exist.
    """
    _migrate_csv_schema(_ITEMS_CSV, _ITEM_FIELDS)
    df = _load_csv(
        _ITEMS_CSV,
        _ITEM_FIELDS,
        str_cols=["name", "category", "date", "deal_name"],
    )
    if df.empty:
        return df
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1.0)
    # Back-fill columns added after initial release so old CSV files still load.
    if "deal_name" not in df.columns:
        df["deal_name"] = ""
    if "deal_discount" not in df.columns:
        df["deal_discount"] = 0.0
    df["deal_name"] = df["deal_name"].fillna("")
    df["deal_discount"] = pd.to_numeric(df["deal_discount"], errors="coerce").fillna(
        0.0
    )
    return df


def load_savings() -> pd.DataFrame:
    """Load all cart-level savings from CSV.

    Returns:
        DataFrame with savings data, empty if none exist.
    """
    df = _load_csv(_SAVINGS_CSV, _SAVINGS_FIELDS, str_cols=["name", "date"])
    if not df.empty:
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
    _migrate_csv_schema(_ITEMS_CSV, _ITEM_FIELDS)
    try:
        df = pd.read_csv(_ITEMS_CSV, dtype=str)
    except (OSError, pd.errors.ParserError) as exc:
        raise IOError(f"Could not read {_ITEMS_CSV.name}: {exc}") from exc
    if item_id not in df["id"].values:
        raise KeyError(f"Item not found: {item_id}")
    df.loc[df["id"] == item_id, "category"] = category
    _write_csv_atomic(_ITEMS_CSV, df)


def receipt_already_saved(filename: str) -> bool:
    """Check whether a receipt file has already been imported.

    Args:
        filename: The PDF filename to look up.

    Returns:
        True if a receipt with this filename exists in storage.

    Raises:
        IOError: If the receipts file exists but cannot be read or parsed.
    """
    if not _RECEIPTS_CSV.exists() or _RECEIPTS_CSV.stat().st_size == 0:
        return False
    try:
        filenames = pd.read_csv(_RECEIPTS_CSV, usecols=["filename"], dtype=str)[
            "filename"
        ]
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise IOError(f"Could not read {_RECEIPTS_CSV.name}: {exc}") from exc
    return filename in filenames.values


def _write_csv_atomic(path: Path, df: pd.DataFrame) -> None:
    """Write a DataFrame to *path* atomically via a temp file and os.replace.

    A crash mid-write leaves the original file intact instead of a truncated,
    corrupt CSV.

    Raises:
        IOError: If the temporary file cannot be written or moved into place.
    """
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp_name)
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, path)
    except OSError as exc:
        raise IOError(f"Could not write to {path.name}: {exc}") from exc


def _ensure_csv(path: Path, fields: list[str]) -> None:
    """Create a CSV with headers if the file is missing or empty."""
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()


def _migrate_csv_schema(path: Path, fields: list[str]) -> None:
    """Rewrite the CSV header to match *fields* if the column count has changed.

    Handles forward migrations (columns added). Existing data rows with fewer
    fields than the new header are left as-is; pandas fills the missing columns
    with NaN on the next read. Rows that already carry the new fields are
    unaffected.

    Args:
        path: Path to the CSV file to inspect and potentially rewrite.
        fields: The authoritative list of column names for this file.
    """
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            existing_header = next(reader)
        except StopIteration:
            return
        if existing_header == fields:
            return  # Already current — nothing to do.
        rows = list(reader)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)
