"""ICA receipt PDF parser.

Supported format: digital receipts from ICA-appen or ICA's web portal.
Items are expected to appear as lines ending with a Swedish-format price
(e.g. '12,90') before the Summa/total line.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber


# Lines whose lowercase content contains these tokens are skipped entirely.
_SKIP_TOKENS: frozenset[str] = frozenset(
    [
        "summa",
        "att betala",
        "totalt",
        "moms",
        "betalsätt",
        "betalning",
        "kort",
        "visa",
        "mastercard",
        "maestro",
        "kontant",
        "swish",
        "kassakvitto",
        "kvitto nr",
        "org.nr",
        "org nr",
        "tel:",
        "telefon",
        "välkommen",
        "tack för",
        "öppet",
        "kundvagn",
        "handla",
        "erhållen rabatt",
        "stamkund",
        "klubbkort",
        "pant",
        "retur",
        "betalat",
        "köp",
    ]
)

# Rightmost Swedish price on a line: optional leading digits+space, comma, two decimals.
_PRICE_RE = re.compile(r"(\d[\d\s]*,\d{2})\s*$")

# Quantity line: "2 x 6,45" / "0,456 kg x 199,00 kr/kg" / "3 st x 9,90"
_QTY_LINE_RE = re.compile(
    r"^(\d+(?:[,.]\d+)?)\s*(?:st|kg|l|liter|pack|fp)?\s*[xX×]", re.IGNORECASE
)

# Leading EAN/article codes: 7+ consecutive digits at the start of a name.
_LEADING_CODE_RE = re.compile(r"^\d[\d\s]{6,}\s+")

# Embedded ICA receipt detail: " <article_no> <unit_price> <qty> <unit>" before line total.
# Format: ArticleNumber(5+digits) UnitPrice(Swedish) Quantity(decimal) Unit(st/kg/…)
_ITEM_DETAIL_RE = re.compile(
    r"\s+\d{5,}\s+[\d ]+,\d{2}\s+[\d.,]+\s+(?:st|kg|l|liter|pack|fp)\s*$",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_ica_receipt(pdf_path: str | Path) -> dict[str, Any]:
    """Parse an ICA receipt PDF and extract structured data.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Dictionary with keys:
            date (str): ISO date string (YYYY-MM-DD).
            store (str): Store name.
            items (list[dict]): Each item has name, price, quantity, and
                deal (None or {name, discount} when a club-card deal is active).
            total (float): Receipt total.
            savings (list[dict]): Cart-level discounts such as storköpsrabatt
                or lojalitetspoäng. Each entry has name and amount (negative float).

    Raises:
        FileNotFoundError: If the PDF does not exist.
        ValueError: If no text can be extracted or no items are found.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("rb") as f:
        magic = f.read(5)
    if magic != b"%PDF-":
        raise ValueError("File does not appear to be a valid PDF.")

    lines = _extract_lines(path)
    if not lines:
        raise ValueError("Could not extract any text from the PDF.")

    items, savings = _extract_items(lines)
    if not items:
        raise ValueError(
            "No items found. Make sure this is a digital ICA receipt in PDF format."
        )

    return {
        "date": _extract_date(lines),
        "store": _extract_store(lines),
        "items": items,
        "total": _extract_total(lines),
        "savings": savings,
    }


def _extract_lines(path: Path) -> list[str]:
    """Extract non-empty text lines from all pages of a PDF."""
    with pdfplumber.open(path) as pdf:
        raw_lines: list[str] = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                raw_lines.extend(text.splitlines())
    return [line.strip() for line in raw_lines if line.strip()]


def _extract_date(lines: list[str]) -> str:
    """Extract the first YYYY-MM-DD date found in the receipt."""
    for line in lines:
        match = _DATE_RE.search(line)
        if match:
            return match.group()
    return datetime.now().strftime("%Y-%m-%d")


def _extract_store(lines: list[str]) -> str:
    """Extract the store name from the receipt header."""
    for line in lines[:10]:
        if "ica" in line.lower():
            return line.strip()
    return "ICA"


def _extract_total(lines: list[str]) -> float:
    """Extract the receipt grand total."""
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in ("summa", "att betala", "totalt")):
            match = _PRICE_RE.search(line)
            if match:
                return _parse_price(match.group(1))
    return 0.0


def _try_parse_item_line(line: str) -> tuple[str, float, bool] | None:
    """Parse a positive-price product line.

    Returns:
        (name, price, has_deal_marker) or None if the line is not a product.
    """
    if _should_skip(line):
        return None
    price_match = _PRICE_RE.search(line)
    if not price_match:
        return None
    pre_price = line[: price_match.start()].rstrip()
    if pre_price.endswith("-"):
        return None  # negative line — handled by _parse_negative_line
    price = _parse_price(price_match.group(1))
    if price == 0 or not pre_price or not any(c.isalpha() for c in pre_price):
        return None
    return pre_price, price, pre_price.startswith("*")


def _consume_quantity_line(lines: list[str], i: int) -> tuple[float, int]:
    """Consume lines[i+1] if it is a quantity line.

    Returns:
        (quantity, new_i) — new_i is i+1 if consumed, i otherwise.
    """
    if i + 1 < len(lines):
        qty_match = _QTY_LINE_RE.match(lines[i + 1])
        if qty_match:
            raw = qty_match.group(1).replace(",", ".")
            try:
                return float(raw), i + 1
            except ValueError:
                pass
    return 1.0, i


def _consume_deal_line(lines: list[str], i: int) -> tuple[dict[str, Any] | None, int]:
    """Consume lines[i+1] if it is a club-card deal line.

    Returns:
        (deal_dict, new_i) — new_i is i+1 if consumed, i otherwise.
    """
    if i + 1 < len(lines):
        deal = _try_parse_deal(lines[i + 1])
        if deal is not None:
            return deal, i + 1
    return None, i


def _extract_items(
    lines: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract product items and cart-level savings from the receipt body.

    Returns:
        Tuple of (items, savings). Items are positive-price product lines with
        an optional attached deal. Savings are standalone negative-price lines
        such as storköpsrabatt or lojalitetspoäng.
    """
    items: list[dict[str, Any]] = []
    savings: list[dict[str, Any]] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        saving = _parse_negative_line(line)
        if saving is not None:
            name, amount = saving
            savings.append({"name": name, "amount": amount})
            i += 1
            continue

        item_line = _try_parse_item_line(line)
        if item_line is None:
            i += 1
            continue

        name, price, has_deal_marker = item_line
        quantity, i = _consume_quantity_line(lines, i)

        # price on the item line is the line total; convert to unit price
        # so that price * quantity = line total in all analytics.
        if quantity > 1:
            price = price / quantity

        deal, i = _consume_deal_line(lines, i) if has_deal_marker else (None, i)

        items.append(
            {"name": _clean_name(name), "price": price, "quantity": quantity, "deal": deal}
        )
        i += 1

    return items, savings


def _parse_negative_line(line: str) -> tuple[str, float] | None:
    """Parse a negative-price line, returning (name, negative_amount) or None.

    A negative line has the form "<name>- <price>" where the trailing dash
    signals a discount. Used by both the standalone-savings branch in
    _extract_items and the club-deal detection in _try_parse_deal.
    """
    if _should_skip(line):
        return None
    price_match = _PRICE_RE.search(line)
    if not price_match:
        return None
    pre_price = line[: price_match.start()].rstrip()
    if not pre_price.endswith("-"):
        return None
    name = pre_price[:-1].strip()
    if not name or not any(c.isalpha() for c in name):
        return None
    amount = -_parse_price(price_match.group(1))
    if amount >= 0:
        return None
    return name, amount


def _try_parse_deal(line: str) -> dict[str, Any] | None:
    """Return a deal dict if the line is a negative-price club-card discount, else None."""
    result = _parse_negative_line(line)
    if result is None:
        return None
    name, discount = result
    return {"name": name, "discount": discount}


def _clean_name(name: str) -> str:
    """Strip asterisk prefix, embedded ICA article details, and normalize whitespace."""
    name = name.lstrip("*").strip()
    name = _ITEM_DETAIL_RE.sub("", name)
    name = _LEADING_CODE_RE.sub("", name)
    return " ".join(name.split())


def _should_skip(line: str) -> bool:
    """Return True if the line is a header, footer, or summary line."""
    lower = line.lower()
    return any(
        re.search(r"(?<!\w)" + re.escape(token), lower) for token in _SKIP_TOKENS
    )


def _parse_price(price_str: str) -> float:
    """Convert a Swedish-format price string to a float.

    Args:
        price_str: String like '12,90' or '1 234,00'.

    Returns:
        Float value, or 0.0 if conversion fails.
    """
    cleaned = price_str.replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
