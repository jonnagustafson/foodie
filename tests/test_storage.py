"""Tests for integrations.storage."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

import integrations.storage as storage_module
from integrations.storage import save_receipt, update_item_category


def _make_parsed(
    *,
    date: str = "2026-04-27",
    store: str = "ICA Test",
    total: float = 50.0,
    items: list[dict[str, Any]] | None = None,
    savings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "date": date,
        "store": store,
        "total": total,
        "items": items
        or [
            {
                "name": "Broccoli",
                "price": 17.99,
                "quantity": 1.0,
                "deal": None,
                "category": "Grönsaker",
            },
        ],
        "savings": savings or [],
    }


def _patch_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all storage module paths to tmp_path."""
    monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(storage_module, "_ITEMS_CSV", tmp_path / "items.csv")
    monkeypatch.setattr(storage_module, "_RECEIPTS_CSV", tmp_path / "receipts.csv")
    monkeypatch.setattr(storage_module, "_SAVINGS_CSV", tmp_path / "savings.csv")
    return tmp_path


@pytest.fixture()
def tmp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Storage redirected to tmp_path, seeded with current schema."""
    _patch_storage(tmp_path, monkeypatch)
    new_fields = [
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
    with (tmp_path / "items.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        writer.writerows(
            [
                {
                    "id": "aaaa1111",
                    "receipt_id": "r1",
                    "date": "2026-04-27",
                    "name": "Broccoli",
                    "price": "17.99",
                    "quantity": "1.0",
                    "category": "Grönsaker",
                    "deal_name": "",
                    "deal_discount": "",
                },
                {
                    "id": "bbbb2222",
                    "receipt_id": "r1",
                    "date": "2026-04-27",
                    "name": "Arla Mjölk",
                    "price": "15.90",
                    "quantity": "1.0",
                    "category": "Mejeri & Ägg",
                    "deal_name": "",
                    "deal_discount": "",
                },
            ]
        )
    return tmp_path


@pytest.fixture()
def tmp_storage_old_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Storage redirected to tmp_path, seeded with pre-deal-column schema."""
    _patch_storage(tmp_path, monkeypatch)
    old_fields = ["id", "receipt_id", "date", "name", "price", "quantity", "category"]
    with (tmp_path / "items.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow(
            {
                "id": "aaaa1111",
                "receipt_id": "r1",
                "date": "2026-04-27",
                "name": "Broccoli",
                "price": "17.99",
                "quantity": "1.0",
                "category": "Grönsaker",
            }
        )
    return tmp_path


@pytest.fixture()
def tmp_storage_with_extra_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Storage seeded with the canonical_name/subcategory columns but no unit.

    Mirrors the real data file's drifted schema to prove the name-based migration
    keeps values aligned (no positional shifting) when a new column is inserted.
    """
    _patch_storage(tmp_path, monkeypatch)
    drifted_fields = [
        "id",
        "receipt_id",
        "date",
        "name",
        "price",
        "quantity",
        "category",
        "deal_name",
        "deal_discount",
        "canonical_name",
        "subcategory",
    ]
    with (tmp_path / "items.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=drifted_fields)
        writer.writeheader()
        writer.writerow(
            {
                "id": "aaaa1111",
                "receipt_id": "r1",
                "date": "2026-04-27",
                "name": "Gul lök ICA",
                "price": "9.95",
                "quantity": "1.0",
                "category": "Grönsaker",
                "deal_name": "",
                "deal_discount": "",
                "canonical_name": "Lök",
                "subcategory": "Rotfrukter",
            }
        )
    return tmp_path


class TestUpdateItemCategory:
    def test_updates_correct_row(self, tmp_storage: Path) -> None:
        update_item_category("aaaa1111", "Fryst")
        df = storage_module.load_items()
        assert df.loc[df["id"] == "aaaa1111", "category"].iloc[0] == "Fryst"

    def test_does_not_affect_other_rows(self, tmp_storage: Path) -> None:
        update_item_category("aaaa1111", "Fryst")
        df = storage_module.load_items()
        assert df.loc[df["id"] == "bbbb2222", "category"].iloc[0] == "Mejeri & Ägg"

    def test_unknown_id_raises_key_error(self, tmp_storage: Path) -> None:
        with pytest.raises(KeyError):
            update_item_category("deadbeef", "Fryst")

    def test_invalid_id_format_raises_value_error(self, tmp_storage: Path) -> None:
        with pytest.raises(ValueError, match="Invalid item_id"):
            update_item_category("nonexistent", "Fryst")

    def test_invalid_category_raises_value_error(self, tmp_storage: Path) -> None:
        with pytest.raises(ValueError, match="Unknown category"):
            update_item_category("aaaa1111", "Nonsense")

    def test_update_is_persisted(self, tmp_storage: Path) -> None:
        update_item_category("bbbb2222", "Dryck")
        # Load fresh to confirm disk was written
        df = storage_module.load_items()
        assert df.loc[df["id"] == "bbbb2222", "category"].iloc[0] == "Dryck"

    def test_load_items_backfills_deal_columns(
        self, tmp_storage_old_schema: Path
    ) -> None:
        df = storage_module.load_items()
        assert "deal_name" in df.columns
        assert "deal_discount" in df.columns
        assert (df["deal_discount"] == 0.0).all()

    def test_updates_against_old_schema(self, tmp_storage_old_schema: Path) -> None:
        update_item_category("aaaa1111", "Fryst")
        df = storage_module.load_items()
        assert df.loc[df["id"] == "aaaa1111", "category"].iloc[0] == "Fryst"


class TestSaveReceipt:
    def test_saves_item_without_deal(self, tmp_storage: Path) -> None:
        save_receipt(_make_parsed(), "test.pdf")
        df = storage_module.load_items()
        broccoli = df[df["name"] == "Broccoli"]
        assert len(broccoli) >= 1
        assert broccoli.iloc[-1]["deal_name"] == ""
        assert broccoli.iloc[-1]["deal_discount"] == 0.0

    def test_saves_item_with_deal(self, tmp_storage: Path) -> None:
        items = [
            {
                "name": "Chorizo",
                "price": 35.86,
                "quantity": 1.0,
                "deal": {"name": "Vegankorv 29kr", "discount": -6.86},
                "category": "Kött & Chark",
            }
        ]
        save_receipt(_make_parsed(items=items), "test.pdf")
        df = storage_module.load_items()
        row = df[df["name"] == "Chorizo"].iloc[-1]
        assert row["deal_name"] == "Vegankorv 29kr"
        assert row["deal_discount"] == pytest.approx(-6.86)

    def test_saves_savings(self, tmp_storage: Path) -> None:
        savings = [{"name": "Storköpsrabatt", "amount": -27.90}]
        save_receipt(_make_parsed(savings=savings), "test.pdf")
        df = storage_module.load_savings()
        assert len(df) == 1
        assert df.iloc[0]["name"] == "Storköpsrabatt"
        assert df.iloc[0]["amount"] == pytest.approx(-27.90)

    def test_no_savings_produces_empty_savings_table(self, tmp_storage: Path) -> None:
        save_receipt(_make_parsed(), "test.pdf")
        df = storage_module.load_savings()
        assert df.empty

    def test_persists_unit_and_canonical_name(self, tmp_storage: Path) -> None:
        items = [
            {
                "name": "Gul lök ICA",
                "price": 9.95,
                "quantity": 1.0,
                "unit": "st",
                "deal": None,
                "category": "Grönsaker",
            }
        ]
        save_receipt(_make_parsed(items=items), "test.pdf")
        df = storage_module.load_items()
        row = df[df["name"] == "Gul lök ICA"].iloc[-1]
        assert row["unit"] == "st"
        assert row["canonical_name"] == "Lök"

    def test_defaults_unit_when_parser_omits_it(self, tmp_storage: Path) -> None:
        # Items constructed before the unit field existed must still save.
        save_receipt(_make_parsed(), "test.pdf")
        df = storage_module.load_items()
        assert df.iloc[-1]["unit"] == "st"


class TestSchemaMigration:
    def test_drifted_schema_keeps_values_aligned(
        self, tmp_storage_with_extra_columns: Path
    ) -> None:
        df = storage_module.load_items()
        row = df[df["id"] == "aaaa1111"].iloc[0]
        # The inserted unit column must not shift canonical_name/subcategory.
        assert row["canonical_name"] == "Lök"
        assert row["subcategory"] == "Rotfrukter"
        assert row["unit"] == "st"  # new column, back-filled
        assert row["category"] == "Grönsaker"

    def test_legacy_rows_get_derived_canonical_name(self, tmp_storage: Path) -> None:
        # tmp_storage has no canonical_name column; it must be derived from name.
        df = storage_module.load_items()
        lok = df[df["name"] == "Arla Mjölk"].iloc[0]
        assert lok["canonical_name"] != ""


class TestCsvInjection:
    def test_csv_injection_stripped_from_name(self, tmp_storage: Path) -> None:
        items = [
            {
                "name": "=HYPERLINK(evil)",
                "price": 10.0,
                "quantity": 1.0,
                "deal": None,
                "category": "Övrigt",
            }
        ]
        save_receipt(_make_parsed(items=items), "test.pdf")
        df = storage_module.load_items()
        injected = df[df["name"].str.contains("HYPERLINK", na=False)]
        assert all(not row.startswith("=") for row in injected["name"])
