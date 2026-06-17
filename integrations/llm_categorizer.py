"""LLM-backed item categorization and canonicalization.

This module turns noisy receipt item names (e.g. ``*Garant Ägg Frigående M 12-p``)
into a stable identity: a canonical product name shared across brands and sizes
(``Ägg``), a top-level category, and a finer subcategory. All network I/O lives
here, never in ``core`` — ``core.categories`` stays a pure, deterministic fallback.

Results are cached on disk by raw item name, so each distinct string costs at most
one API call over the lifetime of the data set. When no API key is configured, or
the API call fails, the keyword categorizer in ``core.categories`` is used instead
and the ``source`` field records that a fallback was taken (the failure is never
swallowed silently).
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

from core.categories import all_categories, categorize_item

_DATA_DIR = Path(__file__).parent.parent / "data"
_CACHE_CSV = _DATA_DIR / "item_cache.csv"
_CACHE_FIELDS = ["raw_name", "canonical_name", "category", "subcategory"]

# Default model. Haiku is the cheapest tier and fast enough for classification.
_DEFAULT_MODEL = "claude-haiku-4-5"
# Names sent per API call. Bounds output size and keeps each request cheap.
_BATCH_SIZE = 40


class LLMCategorizationError(RuntimeError):
    """Raised when the categorization API call fails or returns no usable result."""


def _default_model() -> str:
    """Return the configured categorizer model, or the Haiku default.

    Returns:
        The model id from the ``FOODIE_CATEGORIZER_MODEL`` environment variable,
        falling back to the cheapest suitable model.
    """
    return os.environ.get("FOODIE_CATEGORIZER_MODEL") or _DEFAULT_MODEL


def _system_prompt() -> str:
    """Build the fixed system prompt listing the allowed categories.

    Returns:
        The system prompt text. Stable across requests so it can be prompt-cached.
    """
    categories = "\n".join(f"- {name}" for name in all_categories())
    return (
        "You categorize Swedish grocery receipt items. For each item name you "
        "receive, determine three things:\n"
        "1. canonical_name: the bare generic product as a singular Swedish noun, "
        "capitalized. Strip ALL of the following — nothing else survives:\n"
        "   - Store/retailer brands: ICA, Coop, Garant, Eldorado, Xtra, Signum, "
        "Hemköp, Willys, Axfood\n"
        "   - Manufacturer brands: Arla, Valio, Findus, Felix, Barilla, Knorr, "
        "Heinz, Alpro, Oatly, and any other brand name\n"
        "   - Quality/certification labels: Eko, KRAV, Fairtrade, Organic, "
        "Ekologisk, Ursprung, MSC\n"
        "   - Variety/cut descriptors: Frigående, Mellanmjölk, Lättyoghurt, "
        "Filet, Strimlad, Riven, Krossad, Rökt, Gravad\n"
        "   - Color and variety adjectives: Gul, Röd, Vit, Grön, Gröna, Röda, "
        "Vita, Gula, Söt, Söta, Tidig, and any other color or variety adjective\n"
        "   - Size, weight, volume, count: 500g, 1l, 12-p, 6-pack, stor, liten\n"
        "   - Leading asterisks and store codes\n"
        "Examples: 'Arla Mellanmjölk 1,5% 1l' -> 'Mjölk'; "
        "'*Garant Ägg Frigående 12-p' -> 'Ägg'; "
        "'Morot ICA Eko 1kg' -> 'Morot'; "
        "'Barilla Spaghetti 500g' -> 'Pasta'; "
        "'ICA Kycklingfilé Strimlad 400g' -> 'Kyckling'; "
        "'Gul lök ICA' -> 'Lök'; "
        "'Röd paprika' -> 'Paprika'. "
        "Items that are the same product MUST get the exact same canonical_name "
        "regardless of brand or variant.\n"
        "2. category: the single best-fitting top-level category, chosen ONLY "
        "from this list:\n"
        f"{categories}\n"
        "3. subcategory: a short, more specific group within the category "
        "(e.g. category 'Mejeri & Ägg' -> subcategory 'Ägg'). Use an empty "
        "string if no finer grouping applies.\n"
        "Return one entry per input item via the categorize_items tool."
    )


def _build_tool() -> dict[str, Any]:
    """Build the strict tool schema constraining category to known values.

    Returns:
        A tool definition for the Messages API. ``strict`` plus the ``enum`` on
        ``category`` guarantees the model can only return a known category.
    """
    return {
        "name": "categorize_items",
        "description": "Return the canonical name, category, and subcategory "
        "for each grocery item.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "raw_name": {"type": "string"},
                            "canonical_name": {"type": "string"},
                            "category": {"type": "string", "enum": all_categories()},
                            "subcategory": {"type": "string"},
                        },
                        "required": [
                            "raw_name",
                            "canonical_name",
                            "category",
                            "subcategory",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    }


def _keyword_enrichment(name: str) -> dict[str, str]:
    """Build a fallback enrichment using the deterministic keyword categorizer.

    Args:
        name: The raw item name.

    Returns:
        An enrichment dict. ``canonical_name`` falls back to the raw name (no
        cross-brand grouping without the LLM) and ``source`` records the fallback.
    """
    return {
        "canonical_name": name,
        "category": categorize_item(name),
        "subcategory": "",
        "source": "keyword",
    }


def _call_api(names: list[str], client: Any, model: str) -> list[dict[str, Any]]:
    """Send one batch of names to the Messages API and return parsed entries.

    Args:
        names: Raw item names for this batch.
        client: An ``anthropic.Anthropic`` client (or compatible).
        model: The model id to use.

    Returns:
        The list of entry dicts from the tool call.

    Raises:
        LLMCategorizationError: If the request fails or returns no tool call.
    """
    tool = _build_tool()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[
                {
                    "role": "user",
                    "content": "Categorize these items:\n"
                    + "\n".join(names),
                }
            ],
        )
    except Exception as exc:  # I/O boundary: wrap and re-raise, never swallow
        raise LLMCategorizationError(
            f"Categorization request failed for {len(names)} item(s): {exc}"
        ) from exc

    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return list(block.input.get("items", []))
    raise LLMCategorizationError("Model response contained no tool call.")


def categorize_names_llm(
    names: list[str], client: Any, model: str | None = None
) -> dict[str, dict[str, str]]:
    """Categorize raw item names via the LLM, batching across requests.

    Args:
        names: Distinct raw item names to categorize.
        client: An ``anthropic.Anthropic`` client (or compatible).
        model: Optional model id; defaults to the configured categorizer model.

    Returns:
        Mapping of raw name to an enrichment dict with keys ``canonical_name``,
        ``category``, ``subcategory``, and ``source`` ("llm"). Names the model
        omits are not included in the result.

    Raises:
        LLMCategorizationError: If any batch request fails.
    """
    resolved_model = model or _default_model()
    allowed = set(all_categories())
    result: dict[str, dict[str, str]] = {}

    for start in range(0, len(names), _BATCH_SIZE):
        batch = names[start : start + _BATCH_SIZE]
        for entry in _call_api(batch, client, resolved_model):
            raw = entry.get("raw_name")
            category = entry.get("category")
            if not raw or category not in allowed:
                continue
            result[raw] = {
                "canonical_name": (entry.get("canonical_name") or raw).strip(),
                "category": category,
                "subcategory": (entry.get("subcategory") or "").strip(),
                "source": "llm",
            }
    return result


def load_cache() -> dict[str, dict[str, str]]:
    """Load the on-disk categorization cache.

    Returns:
        Mapping of raw name to its cached enrichment dict (with ``source``
        "cache"). Empty if the cache file does not yet exist.
    """
    if not _CACHE_CSV.exists() or _CACHE_CSV.stat().st_size == 0:
        return {}
    cache: dict[str, dict[str, str]] = {}
    with _CACHE_CSV.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row.get("raw_name")
            if not raw:
                continue
            cache[raw] = {
                "canonical_name": row.get("canonical_name", raw),
                "category": row.get("category", ""),
                "subcategory": row.get("subcategory", ""),
                "source": "cache",
            }
    return cache


def _append_cache(entries: dict[str, dict[str, str]]) -> None:
    """Append newly categorized entries to the on-disk cache.

    Args:
        entries: Mapping of raw name to enrichment dict to persist.

    Raises:
        IOError: If writing to the cache file fails.
    """
    if not entries:
        return
    _DATA_DIR.mkdir(exist_ok=True)
    write_header = not _CACHE_CSV.exists() or _CACHE_CSV.stat().st_size == 0
    with _CACHE_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CACHE_FIELDS)
        if write_header:
            writer.writeheader()
        for raw, enrichment in entries.items():
            writer.writerow(
                {
                    "raw_name": raw,
                    "canonical_name": enrichment["canonical_name"],
                    "category": enrichment["category"],
                    "subcategory": enrichment["subcategory"],
                }
            )


def enrich_items(
    names: list[str], client: Any | None = None, model: str | None = None
) -> dict[str, dict[str, str]]:
    """Resolve canonical name, category, and subcategory for each item name.

    Cached names are served from disk; uncached names are sent to the LLM in
    batches and the results persisted. If no API key is configured or the API
    call fails, uncached names fall back to the deterministic keyword
    categorizer (and the ``source`` field records "keyword"). Fallback results
    are not cached, so a transient failure self-heals on the next run.

    Args:
        names: Raw item names (duplicates allowed).
        client: Optional ``anthropic.Anthropic`` client; created from the
            environment when omitted and an API key is present.
        model: Optional model id; defaults to the configured categorizer model.

    Returns:
        Mapping of every input name to an enrichment dict with keys
        ``canonical_name``, ``category``, ``subcategory``, and ``source``.
    """
    distinct = list(dict.fromkeys(n for n in names if n))
    cache = load_cache()
    result: dict[str, dict[str, str]] = {
        name: cache[name] for name in distinct if name in cache
    }
    missing = [name for name in distinct if name not in cache]
    if not missing:
        return result

    if client is None and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        client = anthropic.Anthropic()

    if client is not None:
        try:
            enriched = categorize_names_llm(missing, client, model)
        except LLMCategorizationError:
            enriched = {}
        _append_cache(enriched)
        result.update(enriched)
        missing = [name for name in missing if name not in enriched]

    for name in missing:
        result[name] = _keyword_enrichment(name)
    return result
