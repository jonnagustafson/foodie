"""Tests for integrations.storage."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import integrations.storage as storage_module
from integrations.storage import update_item_category


@pytest.fixture()
def tmp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect storage to a temp directory and seed a minimal items.csv."""
    monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
    items_csv = tmp_path / "items.csv"
    receipts_csv = tmp_path / "receipts.csv"
    monkeypatch.setattr(storage_module, "_ITEMS_CSV", items_csv)
    monkeypatch.setattr(storage_module, "_RECEIPTS_CSV", receipts_csv)

    fields = ["id", "receipt_id", "date", "name", "price", "quantity", "category"]
    with items_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
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
                },
                {
                    "id": "bbbb2222",
                    "receipt_id": "r1",
                    "date": "2026-04-27",
                    "name": "Arla Mjölk",
                    "price": "15.90",
                    "quantity": "1.0",
                    "category": "Mejeri & Ägg",
                },
            ]
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
            update_item_category("nonexistent", "Fryst")

    def test_update_is_persisted(self, tmp_storage: Path) -> None:
        update_item_category("bbbb2222", "Dryck")
        # Load fresh to confirm disk was written
        df = storage_module.load_items()
        assert df.loc[df["id"] == "bbbb2222", "category"].iloc[0] == "Dryck"
