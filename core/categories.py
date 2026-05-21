"""Food categorization logic for Swedish grocery items."""

from __future__ import annotations

import re

# Category order matters — first match wins.
# Ordering rules:
#   - Mejeri before Dryck: "mjölk" must match before "öl" (removed) causes issues.
#   - Dryck before Frukt: "juice" must match "apelsinjuice" before "apelsin" does.
#   - Snacks before Bröd: "choklad" must match "chokladkaka" before Bröd's "bulle" etc.
#   - Fisk before Fryst: "lax" beats "fryst" for frozen fish items.
#
# Removed ambiguous short-form keywords that are substrings of unrelated words:
#   "te"  → substring of "tomater", "butter" etc.
#   "öl"  → substring of "mjölk"
#   "ost" → substring of "mellanrost", "frukost"
#   "bar" → substring of many words
#   "kaka"→ substring of "chokladkaka" — Snacks handles "choklad" instead
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Mejeri & Ägg": [
        "mjölk", "yoghurt", "smör", "grädde", "ägg", "kvarg",
        "filmjölk", "crème fraîche", "bregott", "skyr", "keso", "kesella",
        "mozzarella", "halloumi", "feta", "ricotta", "mascarpone",
        "herrgård", "prästost", "grevé", "lagrad ost",
    ],
    "Dryck": [
        "juice", "kaffe", "vatten", "läsk", "cider",
        "saft", "smoothie", "energidryck", "mineralvatten", "lemonad",
        "kakao", "cola", "fanta", "sprite", "lättöl", "folköl",
    ],
    "Kött & Chark": [
        "kyckling", "nötkött", "fläsk", "köttfärs", "biff", "entrecôte",
        "skinka", "bacon", "korv", "falukorv", "leverpastej", "salami",
        "kalkon", "lamm", "kotlett", "karré", "filé", "kycklingfilé",
        "köttbullar", "pannbiff", "chorizo", "salsiccia", "serrano",
        "parmaskinka", "prosciutto", "mortadella", "pastrami",
    ],
    "Fisk & Skaldjur": [
        "lax", "torsk", "räkor", "tonfisk", "makrill", "sill",
        "strömming", "hummer", "krabba", "musslor", "kaviar",
        "abborre", "piggvar", "fiskfilé",
    ],
    "Frukt": [
        "äpple", "banan", "apelsin", "päron", "druvor", "jordgubbe",
        "hallon", "blåbär", "mango", "ananas", "citron", "lime",
        "mandarin", "persika", "melon", "kiwi", "plommon", "nektarin",
        "clementin",
    ],
    "Grönsaker": [
        "tomat", "gurka", "sallad", "morot", "lök", "paprika", "broccoli",
        "blomkål", "zucchini", "aubergine", "spenat", "kål", "purjolök",
        "selleri", "majs", "ärtor", "potatis", "avokado",
        "rödlök", "vitlök", "squash", "rädisa", "svamp", "rabarber",
        "fänkål", "ruccola",
    ],
    "Snacks & Godis": [
        "chips", "godis", "choklad", "popcorn", "lakrits",
        "gelé", "skumgodis", "kex", "nötmix",
    ],
    "Bröd & Bakverk": [
        # "kaka" excluded — ambiguous substring in "chokladkaka", "havrekaka"
        # "kex" excluded — already matched by Snacks & Godis (first-match wins)
        "bröd", "knäckebröd", "bulle", "croissant", "bagel",
        "pita", "tortilla", "levain", "rieska", "fralla", "limpa",
        "wienerbröd", "muffin", "ciabatta", "focaccia",
    ],
    "Skafferi": [
        "havre", "müsli", "granola", "cornflakes", "flingor", "gryn",
        "pasta", "ris", "couscous", "bulgur", "quinoa", "mjöl",
        "konserv", "sås", "olja", "olivolja", "socker", "salt", "krydda",
        "senap", "ketchup", "majonäs", "vinäger", "buljong", "tomatsås",
        "honung", "sylt", "marmelad", "mandel", "cashew", "nötter",
        "kikärtor", "linser", "bambu", "bön", "gemelli", "fusilli", "penne",
        "spaghetti", "tagliatelle", "farfalle", "orzo", "risoni", "canneloni",
        "gnocchi", "lasagneplattor", "tortellini", "ravioli", "linguine", "tapenade", "pesto",
        "oliv", "krossade tomater", "kokosmjölk", "soja", "teriyakisås", "sriracha",
        "gochujang", "harissa", "chipotlesås", "sambal oelek", "wasabi", "miso",
        "peppar", "paprikapulver", "curry", "kanel",
    ],
    "Fryst": [
        "fryst", "glass", "frysta",
    ],
    "Hygien & Rengöring": [
        "tvål", "schampo", "tandkräm", "tandk", "toapapper", "diskmedel",
        "tvättmedel", "balsam", "deodorant", "rakhyvel", "blöja", 
        "rengöring", "tandborsta", "solkräm", "nivea", "lotion",
        "hudkräm", "hårspray", "intim", "toa"
    ],
}

UNCATEGORIZED = "Övrigt"

# Precompiled per-category patterns. Keywords are sorted longest-first within each
# alternation so that more specific terms match before shorter ones.
# Word-boundary anchors were considered but ruled out: Swedish compound nouns are
# written without spaces (e.g. "Mellanmjölk", "Apelsinjuice"), so a left-boundary
# lookbehind would silently reject valid matches.
_CATEGORY_PATTERNS: dict[str, re.Pattern[str]] = {
    category: re.compile(
        "|".join(re.escape(kw) for kw in sorted(keywords, key=len, reverse=True)),
        re.IGNORECASE,
    )
    for category, keywords in _CATEGORY_KEYWORDS.items()
}


def categorize_item(name: str) -> str:
    """Categorize a grocery item by name using substring keyword matching.

    Uses precompiled patterns (longest keyword first) for performance. Category
    order in _CATEGORY_KEYWORDS determines priority when multiple categories match.

    Args:
        name: The item name from the receipt.

    Returns:
        The category name, or 'Övrigt' if no match is found.
    """
    for category, pattern in _CATEGORY_PATTERNS.items():
        if pattern.search(name):
            return category
    return UNCATEGORIZED


def all_categories() -> list[str]:
    """Return all known category names plus the uncategorized label.

    Returns:
        Sorted list of category names.
    """
    return sorted(_CATEGORY_KEYWORDS.keys()) + [UNCATEGORIZED]
