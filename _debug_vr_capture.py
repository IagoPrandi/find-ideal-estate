"""Debug script: run VR scraper and see exactly what Glue URLs are captured."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from urllib.parse import urlsplit, parse_qs

ADDRESS = "Rua Guaipa, Vila Leopoldina, Sao Paulo - SP"

async def main():
    from playwright.async_api import async_playwright
    from apps.api.src.modules.listings.scrapers.vivareal import (
        _glue_try_resolve_location_url,
        _tweak_glue_listings_url,
        GLUE_API_HOST,
        GLUE_API_ALT_HOST,
    )

    glue_urls = set()
    intercepted_count = []  # (url, n_listings)

    async with async_playwright() as pw:
        # Use headless=False to visually verify UI search
        import shutil, os
        profile_dir = str(ROOT / "runs" / ".debug_vr_profile")
        if os.path.isdir(profile_dir):
            shutil.rmtree(profile_dir, ignore_errors=True)
        os.makedirs(profile_dir, exist_ok=True)

        context = await pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
            ],
            ignore_default_args=["--enable-automation"],
            ignore_https_errors=True,
        )
        page = await context.new_page()

        live_glue_headers = {}

        async def _glue_route_handler(route):
            req = route.request
            url_raw = req.url
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
            parts = urlsplit(url_raw)
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            inc = str(query.get("includeFields") or "")
            if "totalCount" in inc and "listings" not in inc.lower():
                tweaked = _tweak_glue_listings_url(url_raw, size=36, from_=0)
                print(f"[ROUTE] Promoted count-only to listings: {url_raw[:120]}")
                await route.continue_(url=tweaked)
                return
            await route.continue_()

        await page.route("**/glue-api.vivareal.com/v2/listings**", _glue_route_handler)

        async def _capture_response(response):
            url = response.url
            if (GLUE_API_HOST in url or GLUE_API_ALT_HOST in url) and response.status == 200:
                glue_urls.add(url)
                try:
                    req_headers = await response.request.all_headers()
                    if isinstance(req_headers, dict):
                        live_glue_headers.update(req_headers)
                except Exception:
                    pass
                try:
                    body = await response.json()
                    # Count listings
                    n = 0
                    if isinstance(body, list):
                        n = len(body)
                    elif isinstance(body, dict):
                        listings = body.get("search", {}).get("result", {}).get("listings", [])
                        n = len(listings) if isinstance(listings, list) else 0
                    parts = urlsplit(url)
                    qs = dict(parse_qs(parts.query))
                    addr_type = qs.get("addressType", ["?"])[0]
                    addr_street = qs.get("addressStreet", [""])[0]
                    from_ = qs.get("from", ["0"])[0]
                    print(f"[CAPTURED] {addr_type}/{addr_street} from={from_} -> {n} listings | url={url[:100]}")
                    intercepted_count.append((url, n))
                except Exception as e:
                    print(f"[CAPTURED] Error parsing: {e}")

        page.on("response", _capture_response)

        print(f"[NAV] Going to https://www.vivareal.com.br/aluguel/sp/sao-paulo/")
        await page.goto("https://www.vivareal.com.br/aluguel/sp/sao-paulo/", wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            await page.wait_for_timeout(3000)

        print(f"[PAGE] Current URL: {page.url}")

        print(f"\n[UI SEARCH] Searching for: {ADDRESS}")
        resolved = await _glue_try_resolve_location_url(
            page,
            ADDRESS,
            "vivareal",
            full_address=ADDRESS,
        )
        print(f"\n[RESOLVED] UI resolved to: {resolved}")

        if resolved and resolved != page.url:
            print(f"[NAV] Going to resolved URL: {resolved}")
            await page.goto(resolved, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                await page.wait_for_timeout(3000)

        print(f"[PAGE] Final URL: {page.url}")

        # Scroll
        for _ in range(4):
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            await page.wait_for_timeout(1500)

        print(f"\n=== SUMMARY ===")
        print(f"Captured Glue URLs ({len(glue_urls)}):")
        for url in sorted(glue_urls):
            parts = urlsplit(url)
            qs = dict(parse_qs(parts.query))
            addr_type = qs.get("addressType", ["?"])[0]
            addr_street = qs.get("addressStreet", [""])[0]
            addr_neigh = qs.get("addressNeighborhood", [""])[0]
            from_ = qs.get("from", ["0"])[0]
            print(f"  {addr_type} street={addr_street} neigh={addr_neigh} from={from_} | {url[:130]}")

        print(f"\nIntercepted payloads: {intercepted_count}")
        print(f"\nTotal unique glue URLs: {len(glue_urls)}")

        await context.close()

asyncio.run(main())
