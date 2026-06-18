"""Canonical product names for grouping receipt items across purchases.

Raw receipt names vary by brand, size, and store label ("Gul lök ICA",
"Lök vit Morado ICA", "Salladslök" are all onions). Canonical names collapse
those variants to a single product so price can be tracked over time.

This is a deterministic, keyword-based mapping. Items that match no keyword
fall back to a cleaned version of their raw name, so an unmapped product still
groups with its exact-name twins.
"""

from __future__ import annotations

import re

# Canonical product name -> substring keywords that map to it. Mirrors the
# structure of core.categories: dict order sets priority (first match wins) and
# keywords within a group are matched longest-first so specific terms beat their
# substrings. Keep the most specific groups earlier.
_CANONICAL_KEYWORDS: dict[str, list[str]] = {
    "Crème Fraîche": ["crème fraîche", "creme fraiche", "creme fr", "cr fr"],
    "Grädde": ["vispgrädde", "matlagn grädde", "grädde"],
    "Yoghurt": ["yoghurt", "yogh", "fil naturell", "kvarg"],
    "Smör": ["bregott", "smör"],
    "Ägg": ["ägg"],
    "Mozzarella": ["mozzarella"],
    "Halloumi": ["halloumi", "grillost", "nablus"],
    "Fetaost": ["fetaost", "feta"],
    "Burrata": ["burrata"],
    "Parmesan": ["parmesan", "grana padano", "parmigiano"],
    "Färskost": ["cream ch", "cr cheese", "cream cheese", "färskost"],
    "Banan": ["banan"],
    "Apelsin": ["blodapelsin", "apelsin"],
    "Citron": ["citron"],
    "Päron": ["päron"],
    "Bär": ["blåbär", "björnbär", "hallon", "jordgubb"],
    "Melon": ["cantaloupe", "melon"],
    "Lök": ["salladslök", "rödlök", "vitlök", "purjolök", "lök"],
    "Kål": ["brysselkål", "grönkål", "savoy", "spetskål", "pak choi", "kål"],
    "Morot": ["snackmorot", "morot"],
    "Potatis": ["potatis"],
    "Tomat": ["körsbärstomat", "babyplommontom", "tomat"],
    "Gurka": ["gurka"],
    "Paprika": ["paprika"],
    "Avokado": ["avokado"],
    "Sparris": ["sparris"],
    "Spenat": ["spenat"],
    "Svamp": ["champinjon", "portabello", "portabella", "shitake", "shimeji", "svamp"],
    "Sallad": ["krispsallat", "ruccola", "rucola", "sallad", "sallat", "spenat"],
    "Rädisa": ["rädisa"],
    "Färska Kryddor": [
        "basilika",
        "persilja",
        "koriander",
        "gräslök",
        "dill",
        "timjan",
    ],
    "Pasta": [
        "spaghetti",
        "penne",
        "fusill",
        "tortiglioni",
        "radiatori",
        "mezze",
        "pasta",
    ],
    "Nudlar": ["udon", "nudlar", "noodle"],
    "Oliver": ["oliv"],
    "Salt": ["flingsalt", "salt"],
    "Mjöl": ["vetemjöl", "mjöl"],
    "Kaffe": ["kaffe", "mörkrost", "bryggmalet"],
    "Chips": ["chips"],
    "Godis": ["lösgodis", "naturgodis", "godis", "skum"],
    "Proteinbar": ["proteinbar", "barebells", "bar caramell", "bar cookies"],
    "Tuggummi": ["tuggummi", "spearm"],
    "Läsk": ["coca-cola", "cola", "läsk", "zero"],
    "Bubbelvatten": ["loka", "ramlösa", "bubbelvatten"],
    "Tofu": ["tofu"],
    "Tomatpuré": ["tomatpuré", "tomatpure"],
    "Deodorant": ["deodorant", "deo "],
    "Tandborste": ["tandborste", "tandb "],
    "Toapapper": ["toapapper", "bad&toa"],
    "Batteri": ["batteri"],
}

# Tokens stripped from the fallback name: store/brand labels, eco markers, and
# size/percentage suffixes that do not identify the product.
_FALLBACK_NOISE_RE = re.compile(
    r"\b(?:ica|eko|ekologisk|naturell|original|"
    r"\d+(?:[,.]\d+)?\s*(?:g|kg|l|ml|cl|st|p|pack|%))\b",
    re.IGNORECASE,
)

_CANONICAL_PATTERNS: dict[str, re.Pattern[str]] = {
    canonical: re.compile(
        "|".join(re.escape(kw) for kw in sorted(keywords, key=len, reverse=True)),
        re.IGNORECASE,
    )
    for canonical, keywords in _CANONICAL_KEYWORDS.items()
}


def _fallback_name(name: str) -> str:
    """Return a cleaned form of *name* for products with no keyword match."""
    cleaned = _FALLBACK_NOISE_RE.sub(" ", name)
    cleaned = " ".join(cleaned.split())
    return cleaned or name.strip()


def canonical_name(name: str) -> str:
    """Map a raw receipt item name to a canonical product name.

    Args:
        name: The raw item name from the receipt.

    Returns:
        The canonical product name if a keyword matches, otherwise a cleaned
        version of the raw name (brand, eco markers, and sizes removed).
    """
    for canonical, pattern in _CANONICAL_PATTERNS.items():
        if pattern.search(name):
            return canonical
    return _fallback_name(name)
