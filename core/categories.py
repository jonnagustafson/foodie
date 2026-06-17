"""Food categorization logic for Swedish grocery items."""

from __future__ import annotations

import re

# Category order matters — first match wins.
# Ordering rules:
#   - Mejeri before Dryck: "mjölk" must match before "öl" (removed) causes issues.
#   - Dryck before Frukt: "juice" must match "apelsinjuice" before "apelsin" does.
#   - Snacks before Bröd: "choklad" must match "chokladkaka" before Bröd's "bulle" etc.
#   - Fisk before Fryst: "lax" beats "fryst" for frozen fish items.
#   - Fryst before Deli: "fryst" marks frozen ready-meals (e.g. "Fryst Pizza")
#     over Deli's "pizza". Fresh veg/fruit categories stay earlier, so frozen
#     produce keeps its produce category.
#
# Removed ambiguous short-form keywords that are substrings of unrelated words:
#   "te"  → substring of "tomater", "butter" etc.
#   "öl"  → substring of "mjölk"
#   "ost" → substring of "mellanrost", "frukost"
#   "bar" → substring of many words
#   "kaka"→ substring of "chokladkaka" — Snacks handles "choklad" instead
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Mejeri & Ägg": [
        "mjölk",
        "yoghurt",
        "yogh",
        "smör",
        "grädde",
        "ägg",
        "kvarg",
        "filmjölk",
        "crème fraîche",
        "creme fraiche",
        "bregott",
        "skyr",
        "keso",
        "kesella",
    ],
    "Ost": [
        "mozzarella",
        "halloumi",
        "feta",
        "ricotta",
        "mascarpone",
        "herrgård",
        "prästost",
        "präst",
        "grevé",
        "lagrad ost",
        "manchego",
        "gammelknas",
        "gruyere",
        "saint agur",
        "burrata",
        "danablu",
        "castello",
        "gouda",
        "brie",
        "camembert",
        "cheddar",
        "emmentaler",
        "parmigiano",
        "pecorino",
        "stilton",
        "roquefort",
        "havarti",
    ],
    "Dryck": [
        "juice",
        "kaffe",
        "vatten",
        "läsk",
        "cider",
        "vitaminwell" "saft",
        "smoothie",
        "energidryck",
        "mineralvatten",
        "lemonad",
        "kakao",
        "cola",
        "fanta",
        "sprite",
        "lättöl",
        "folköl",
        "loka",
        "ramlösa",
    ],
    "Kött & Chark": [
        "kyckling",
        "nötkött",
        "fläsk",
        "köttfärs",
        "biff",
        "entrecôte",
        "skinka",
        "bacon",
        "korv",
        "falukorv",
        "leverpastej",
        "salami",
        "kalkon",
        "lamm",
        "kotlett",
        "karré",
        "filé",
        "kycklingfilé",
        "köttbullar",
        "pannbiff",
        "chorizo",
        "salsiccia",
        "serrano",
        "parmaskinka",
        "prosciutto",
        "mortadella",
        "pastrami",
    ],
    "Vego": [
        "tofu",
        "tempeh",
        "seitan",
        "quorn",
        "oumph",
        "beyond meat",
        "impossible",
        "vego",
        "vegan",
        "vegansk",
        "vegetarisk",
        "sojafärs",
        "ärtfärs",
        "linsfärs",
        "kikärtefärs",
        "blomkålsbiff",
        "jackfruit",
    ],
    "Fisk & Skaldjur": [
        "lax",
        "torsk",
        "räkor",
        "tonfisk",
        "makrill",
        "sill",
        "strömming",
        "hummer",
        "krabba",
        "musslor",
        "kaviar",
        "abborre",
        "piggvar",
        "fiskfilé",
    ],
    "Frukt": [
        "äpple",
        "banan",
        "apelsin",
        "päron",
        "druvor",
        "jordgubbe",
        "hallon",
        "blåbär",
        "mango",
        "ananas",
        "citron",
        "lime",
        "mandarin",
        "persika",
        "melon",
        "kiwi",
        "plommon",
        "nektarin",
        "clementin",
        "citrus",
        "björnbär",
        "blåbär",
        "cantaloupe",
    ],
    "Grönsaker": [
        "tomat",
        "gurka",
        "sallad",
        "morot",
        "lök",
        "paprika",
        "broccoli",
        "blomkål",
        "zucchini",
        "aubergine",
        "spenat",
        "kål",
        "purjolök",
        "selleri",
        "majs",
        "ärtor",
        "potatis",
        "avokado",
        "rödlök",
        "vitlök",
        "squash",
        "rädisa",
        "svamp",
        "rabarber",
        "fänkål",
        "ruccola",
        "rucola",
        "rotselleri",
        "koriander",
        "persilja",
        "gräslök",
        "portabello",
        "champinjon",
        "salvia",
        "sparris",
        "dill",
    ],
    "Snacks & Godis": [
        "chips",
        "godis",
        "choklad",
        "popcorn",
        "lakrits",
        "gelé",
        "skumgodis",
        "kex",
        "nötmix",
        "cheez doodles",
        "smash",
        "nachos",
        "tortillachips",
        "peanuts",
        "jordnöt",
        "studentmat",
        "polly",
        "lördagsgodis",
    ],
    "Bröd & Bakverk": [
        # "kaka" excluded — ambiguous substring in "chokladkaka", "havrekaka"
        # "kex" excluded — already matched by Snacks & Godis (first-match wins)
        "bröd",
        "knäckebröd",
        "bulle",
        "croissant",
        "bagel",
        "pita",
        "tortilla",
        "levain",
        "rieska",
        "fralla",
        "limpa",
        "wienerbröd",
        "muffin",
        "ciabatta",
        "focaccia",
    ],
    "Skafferi": [
        "müsli",
        "granola",
        "cornflakes",
        "flingor",
        "mjöl",
        "konserv",
        "sås",
        "olja",
        "olivolja",
        "socker",
        "salt",
        "krydda",
        "senap",
        "ketchup",
        "majonäs",
        "vinäger",
        "buljong",
        "tomatsås",
        "honung",
        "sylt",
        "marmelad",
        "mandel",
        "cashew",
        "nötter",
        "kikärt",
        "linser",
        "bambu",
        "bön",
        "tapenade",
        "pesto",
        "oliv",
        "krossade tomater",
        "kokosmjölk",
        "soja",
        "teriyakisås",
        "sriracha",
        "gochujang",
        "harissa",
        "chipotlesås",
        "sambal oelek",
        "wasabi",
        "miso",
        "gryn",
        "panko",
        "kronärtskock",
        "kimchi",
    ],
    "Pasta, Ris & Gryn": [
        "pasta",
        "ris",
        "couscous",
        "bulgur",
        "quinoa",
        "gemelli",
        "fusilli",
        "penne",
        "spaghetti",
        "tagliatelle",
        "farfalle",
        "orzo",
        "risoni",
        "canneloni",
        "gnocchi",
        "lasagneplattor",
        "tortellini",
        "ravioli",
        "linguine",
        "havregryn",
        "mannagryn",
        "quinoa",
        "nudlar",
        "fusilloni",
        "udon",
        "tortiglioni",
    ],
    "Kryddor": [
        "peppar",
        "paprikapulver",
        "curry",
        "kanel",
        "salt",
        "krydda",
        "kummin",
        "lökpulver",
        "oregano",
        "timjan",
        "rosmarin",
        "basilika",
        "spiskummin",
        "kardemumma",
        "gurkmeja",
        "korianderpulver",
        "chilipulver",
        "cayenne",
        "muskot",
        "ingefärspulver",
        "vitlökspulver",
    ],
    "Fryst": [
        "fryst",
        "glass",
        "frysta",
    ],
    "Deli & Färdigmat": [
        "sushi",
        "pizza",
        "soppa",
        "färdigmat",
        "deli",
        "hummus",
        "tzatziki",
        "guacamole",
        "paj",
        "quiche",
        "lasagne",
        "färdigrätt",
        "wokrätt",
        "lunchbaren",
        "lunchbar",
        "lunch",
        "salladsbar",
        "smörgås",
        "smörgåstårta",
        "wrap",
        "falafel",
        "kebab",
        "gyros",
        "tacos",
        "burrito",
        "quesadilla",
        "moussaka",
        "gryta",
        "soppa",
    ],
    "Kosttillskott & Hälsa": [
        "protein",
        "kosttillskott",
        "kapslar",
        "omega",
        "vitamin",
        "järntablett",
        "magnesiumtablett",
        "collagen",
        "probiotika",
        "proteinpulver",
        "proteinbar",
        "whey",
        "kreatin",
        "bcaa",
    ],
    "Hushåll": [
        "batteri",
        "bestick",
        "aluminiumfolie",
        "plastfolie",
        "bakplåtspapper",
        "sopsäck",
        "papperspåse",
        "hushållspapper",
        "köksrulle",
        "tvättsvamp",
        "skursvamp",
        "diskborste",
        "moppar",
        "skovård",
        "glödlampa",
        "tändstickor",
        "ljus",
        "värmeljus",
        "ziplock",
        "matlåda",
    ],
    "Hygien & Rengöring": [
        "tvål",
        "schampo",
        "tandkräm",
        "tandk",
        "toapapper",
        "diskmedel",
        "tvättmedel",
        "balsam",
        "deodorant",
        "rakhyvel",
        "blöja",
        "rengöring",
        "tandborsta",
        "solkräm",
        "nivea",
        "lotion",
        "hudkräm",
        "hårspray",
        "intim",
        "toa",
        "dusch",
        "vätskeers",
    ],
    "Du glömde handlingskassen": ["plastkasse"],
}

UNCATEGORIZED = "Övrigt"

# Receipt lines that represent store/payment metadata rather than purchased goods.
# Items whose name contains any of these substrings (case-insensitive) should be
# dropped before analysis — they are not food or household purchases.
_ARTIFACT_PATTERNS: re.Pattern[str] = re.compile(
    "|".join(
        re.escape(kw)
        for kw in sorted(
            [
                "lojalitetspoäng",
                "returpant",
                "pant",
                "presentkort",
                "kupong",
                "rabattkupong",
                "kundklubb",
                "bonuspoäng",
            ],
            key=len,
            reverse=True,
        )
    ),
    re.IGNORECASE,
)


def is_receipt_artifact(name: str) -> bool:
    """Return True if the item is a receipt metadata line, not a purchasable product.

    These lines (e.g. loyalty points, deposit refunds) should be excluded from
    nutritional and spending analysis.

    Args:
        name: The item name from the receipt.

    Returns:
        True if the item is a receipt artifact that should be filtered out.
    """
    return bool(_ARTIFACT_PATTERNS.search(name))


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
