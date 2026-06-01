"""Loft scraper based on the public search page's hydrated listing payload."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from typing import Any
from urllib.request import Request, urlopen

from .base import REALISTIC_USER_AGENT, ScraperBase, ScraperError, _as_float, _as_int, _get_by_path

LOFT_BASE = "https://loft.com.br"


def _loft_slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9\s\-]", "", lowered)
    return re.sub(r"-{2,}", "-", lowered.replace(" ", "-")).strip("-")


def _build_loft_search_url(search_address: str, search_type: str, configured_start: list[str]) -> str:
    if configured_start:
        return configured_start[0].rstrip("/")

    city = "sao-paulo"
    state = "sp"
    parts = [part.strip() for part in (search_address or "").split(",") if part.strip()]
    if len(parts) >= 3:
        city_state = parts[2]
        match = re.search(r"^(.*?)(?:\s*-\s*([A-Za-z]{2}))?$", city_state)
        if match:
            city = _loft_slugify(match.group(1) or city) or city
            state = (match.group(2) or state).strip().lower() or state
    transaction = "venda" if search_type == "sale" else "aluguel"
    return f"{LOFT_BASE}/{transaction}/imoveis/{state}/{city}"


def _extract_next_data(html: str) -> dict[str, Any]:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise ScraperError("Loft search page did not include __NEXT_DATA__")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ScraperError("Loft __NEXT_DATA__ payload is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ScraperError("Loft __NEXT_DATA__ payload has unexpected shape")
    return payload


def _find_listing_groups(payload: Any) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            listing = node.get("listing")
            if isinstance(listing, dict):
                groups.append(node)
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return groups


def _listing_url(listing: dict[str, Any]) -> str:
    listing_id = str(listing.get("id") or listing.get("objectID") or "").strip()
    if not listing_id:
        return LOFT_BASE
    address = listing.get("address") if isinstance(listing.get("address"), dict) else {}
    title_parts = [
        str(listing.get("homeType") or listing.get("propertyType") or "imovel"),
        str(address.get("streetName") or address.get("streetFullName") or ""),
        str(address.get("neighborhood") or ""),
        str(address.get("city") or ""),
        f"{listing.get('bedrooms')} quartos" if listing.get("bedrooms") is not None else "",
        f"{listing.get('area')}m2" if listing.get("area") is not None else "",
    ]
    slug = _loft_slugify(" ".join(part for part in title_parts if part))
    return f"{LOFT_BASE}/imovel/{slug}/{listing_id}" if slug else f"{LOFT_BASE}/imovel/{listing_id}"


def _address_label(listing: dict[str, Any]) -> str | None:
    address = listing.get("address") if isinstance(listing.get("address"), dict) else {}
    facets = address.get("facets") if isinstance(address.get("facets"), dict) else {}
    for key in ("street", "neighborhood", "city"):
        value = facets.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    parts = [
        address.get("streetFullName") or address.get("streetName"),
        address.get("neighborhood"),
        address.get("city"),
        address.get("state"),
    ]
    label = ", ".join(str(part).strip() for part in parts if str(part or "").strip())
    return label or None


def _parse_loft_groups(groups: list[dict[str, Any]], search_type: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        listing = group.get("listing")
        if not isinstance(listing, dict):
            continue

        listing_id = str(listing.get("id") or listing.get("objectID") or "").strip()
        if not listing_id or listing_id in seen:
            continue
        seen.add(listing_id)

        if search_type == "rent":
            price = _as_float(listing.get("rentalPrice") or _get_by_path(group, "groupSummary.rentalPriceMin"))
        else:
            price = _as_float(listing.get("price") or _get_by_path(group, "groupSummary.priceMin"))
        if price is None:
            continue

        lat = _as_float(_get_by_path(listing, "location.lat") or _get_by_path(listing, "_geoloc.lat") or _get_by_path(listing, "address.lat"))
        lon = _as_float(_get_by_path(listing, "location.lon") or _get_by_path(listing, "_geoloc.lng") or _get_by_path(listing, "address.lng"))

        parsed.append(
            {
                "platform": "loft",
                "platform_listing_id": listing_id,
                "url": _listing_url(listing),
                "image_url": None,
                "lat": lat,
                "lon": lon,
                "price_brl": price,
                "area_m2": _as_float(listing.get("area") or _get_by_path(group, "groupSummary.areaMin")),
                "bedrooms": _as_int(listing.get("bedrooms")),
                "bathrooms": _as_int(listing.get("restrooms") or listing.get("bathrooms")),
                "parking": _as_int(listing.get("parkingSpots")),
                "address": _address_label(listing),
                "condo_fee_brl": _as_float(listing.get("complexFee") or _get_by_path(group, "groupSummary.complexMin")),
                "iptu_brl": _as_float(listing.get("propertyTax")),
            }
        )
    return parsed


def _fetch_loft_html(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": REALISTIC_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )
    with urlopen(req, timeout=45) as response:
        return response.read().decode("utf-8", errors="ignore")


class LoftScraper(ScraperBase):
    platform = "loft"
    base_url = LOFT_BASE

    async def scrape(self) -> list[dict[str, Any]]:
        return await self._scrape_via_http()

    async def _scrape_with_context(self, context: Any) -> list[dict[str, Any]]:
        del context
        return await self._scrape_via_http()

    async def _scrape_via_http(self) -> list[dict[str, Any]]:
        self._check_robots("/venda/imoveis/" if self.search_type == "sale" else "/aluguel/imoveis/")
        url = _build_loft_search_url(
            self.search_address,
            self.search_type,
            self._configured_start_urls(),
        )
        html = await asyncio.to_thread(_fetch_loft_html, url)
        payload = _extract_next_data(html)
        groups = _find_listing_groups(payload)
        return _parse_loft_groups(groups, self.search_type)
