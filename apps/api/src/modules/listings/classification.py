"""Helpers to infer listing usage from the captured listing URL."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

COMMERCIAL_KEYWORDS = (
    "conjunto-comercial",
    "sala-comercial",
    "imovel-comercial",
    "casa-comercial",
    "ponto-comercial",
    "predio-comercial",
    "andar-corporativo",
    "consultorio",
    "galpao",
    "loja",
    "sobreloja",
)

RESIDENTIAL_KEYWORDS = (
    "apartamento",
    "casa",
    "sobrado",
    "studio",
    "kitnet",
    "kitinete",
    "cobertura",
    "duplex",
    "triplex",
    "loft",
)


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", "", ascii_text)


def _parse_bedrooms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        if not match:
            return None
        return int(match.group(0))


def infer_listing_usage_type_from_url(listing_url: Any, bedrooms: Any) -> str:
    normalized_url = _normalize_url(listing_url)
    if normalized_url:
        if any(keyword in normalized_url for keyword in COMMERCIAL_KEYWORDS):
            return "commercial"
        if any(keyword in normalized_url for keyword in RESIDENTIAL_KEYWORDS):
            return "residential"

    bedroom_count = _parse_bedrooms(bedrooms)
    if bedroom_count is None or bedroom_count <= 0:
        return "commercial"
    return "residential"