"""Tests for integrations.llm_categorizer."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import integrations.llm_categorizer as llm
from integrations.llm_categorizer import (
    LLMCategorizationError,
    enrich_items,
    load_cache,
)


def _patch_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the cache file and data dir to a temp location."""
    monkeypatch.setattr(llm, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(llm, "_CACHE_CSV", tmp_path / "item_cache.csv")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _tool_response(entries: list[dict[str, Any]]) -> SimpleNamespace:
    """Build a fake Messages API response carrying a single tool_use block."""
    block = SimpleNamespace(type="tool_use", input={"items": entries})
    return SimpleNamespace(content=[block])


class _FakeClient:
    """Minimal stand-in for anthropic.Anthropic recording calls and replying."""

    def __init__(self, entries: list[dict[str, Any]] | Exception) -> None:
        self._entries = entries
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls += 1
        if isinstance(self._entries, Exception):
            raise self._entries
        return _tool_response(self._entries)


def test_enrich_items_uses_llm_and_canonicalizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_cache(tmp_path, monkeypatch)
    client = _FakeClient(
        [
            {
                "raw_name": "*Garant Ägg Frigående 12-p",
                "canonical_name": "Ägg",
                "category": "Mejeri & Ägg",
                "subcategory": "Ägg",
            },
            {
                "raw_name": "Eko Ägg Stora 6-p",
                "canonical_name": "Ägg",
                "category": "Mejeri & Ägg",
                "subcategory": "Ägg",
            },
        ]
    )

    result = enrich_items(
        ["*Garant Ägg Frigående 12-p", "Eko Ägg Stora 6-p"], client=client
    )

    assert result["*Garant Ägg Frigående 12-p"]["canonical_name"] == "Ägg"
    assert result["Eko Ägg Stora 6-p"]["canonical_name"] == "Ägg"
    assert result["Eko Ägg Stora 6-p"]["source"] == "llm"


def test_enrich_items_caches_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_cache(tmp_path, monkeypatch)
    entries = [
        {
            "raw_name": "Arla Mellanmjölk 1l",
            "canonical_name": "Mjölk",
            "category": "Mejeri & Ägg",
            "subcategory": "Mjölk",
        }
    ]
    client = _FakeClient(entries)

    enrich_items(["Arla Mellanmjölk 1l"], client=client)
    assert client.calls == 1

    # Second call for the same name must hit the cache, not the API.
    again = enrich_items(["Arla Mellanmjölk 1l"], client=client)
    assert client.calls == 1
    assert again["Arla Mellanmjölk 1l"]["canonical_name"] == "Mjölk"
    assert again["Arla Mellanmjölk 1l"]["source"] == "cache"
    assert "Arla Mellanmjölk 1l" in load_cache()


def test_enrich_items_falls_back_on_api_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_cache(tmp_path, monkeypatch)
    client = _FakeClient(RuntimeError("boom"))

    result = enrich_items(["Kycklingfilé 700g"], client=client)

    assert result["Kycklingfilé 700g"]["category"] == "Kött & Chark"
    assert result["Kycklingfilé 700g"]["canonical_name"] == "Kycklingfilé 700g"
    assert result["Kycklingfilé 700g"]["source"] == "keyword"
    # Fallback results are not cached, so a transient failure self-heals.
    assert load_cache() == {}


def test_enrich_items_without_client_uses_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_cache(tmp_path, monkeypatch)

    result = enrich_items(["Äpple Gala 1kg"])

    assert result["Äpple Gala 1kg"]["category"] == "Frukt"
    assert result["Äpple Gala 1kg"]["source"] == "keyword"


def test_enrich_items_rejects_unknown_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_cache(tmp_path, monkeypatch)
    # The model returns a category outside the allowed enum — it must be ignored
    # and the item must fall back to keyword categorization.
    client = _FakeClient(
        [
            {
                "raw_name": "Tomat Kvisttomater",
                "canonical_name": "Tomat",
                "category": "Not A Real Category",
                "subcategory": "",
            }
        ]
    )

    result = enrich_items(["Tomat Kvisttomater"], client=client)

    assert result["Tomat Kvisttomater"]["category"] == "Grönsaker"
    assert result["Tomat Kvisttomater"]["source"] == "keyword"


def test_categorize_names_llm_raises_without_tool_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_cache(tmp_path, monkeypatch)
    client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                content=[SimpleNamespace(type="text", text="no tool here")]
            )
        )
    )

    with pytest.raises(LLMCategorizationError):
        llm.categorize_names_llm(["whatever"], client)
