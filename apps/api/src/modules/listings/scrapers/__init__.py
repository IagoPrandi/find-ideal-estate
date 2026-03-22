"""Playwright-based real estate scrapers package.

Each scraper:
- Uses a realistic user-agent and respectful delays between page interactions.
- Intercepts API responses via Playwright's route/response mechanisms.
- Returns a list of raw listing dicts with standardised fields.
- Verifies robots.txt before proceeding (raises ScraperDisallowedError if blocked).

Shared schema output per listing:
    {
        "platform": str,
        "platform_listing_id": str,
        "url": str | None,
        "lat": float | None,
        "lon": float | None,
        "price_brl": float | None,
        "area_m2": float | None,
        "bedrooms": int | None,
        "bathrooms": int | None,
        "parking": int | None,
        "address": str | None,
        "condo_fee_brl": float | None,
        "iptu_brl": float | None,
    }
"""

from .base import ScraperBase, ScraperDisallowedError, ScraperError
from .quintoandar import QuintoAndarScraper
from .vivareal import VivaRealScraper
from .zapimoveis import ZapImoveisScraper

__all__ = [
    "QuintoAndarScraper",
    "VivaRealScraper",
    "ZapImoveisScraper",
    "ScraperBase",
    "ScraperDisallowedError",
    "ScraperError",
]
