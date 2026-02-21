#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vivaReal.py — parser dedicado (VivaReal)

Objetivo:
- Ler os artefatos gerados no run do realestate_meta_search (ex.: replay_vivareal_glue_listings_p*.json).
- Gerar lista padronizada de imóveis:
  {schema_version, platform, listing_id, url, lat, lon, price_brl, area_m2, bedrooms, bathrooms, parking, address}
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

STD_SCHEMA_VERSION = 1


def get_by_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if part.isdigit():
            i = int(part)
            if isinstance(cur, list) and 0 <= i < len(cur):
                cur = cur[i]
            else:
                return None
        else:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
    return cur


def _as_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, int):
            return int(x)
        if isinstance(x, float):
            return int(round(x))
        if isinstance(x, str):
            s = x.strip().replace(".", "").replace(",", ".")
            if not s:
                return None
            return int(float(s))
    except Exception:
        return None
    return None


def _as_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return float(int(x))
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            s = x.strip().replace(".", "").replace(",", ".")
            if not s:
                return None
            return float(s)
    except Exception:
        return None
    return None


def _pick_first_url(listing: dict) -> Optional[str]:
    for k in ("url", "uri", "canonicalUrl", "canonicalURI", "href"):
        v = listing.get(k)
        if isinstance(v, str) and v.strip():
            if v.startswith("http"):
                return v
            if v.startswith("/"):
                return "https://www.vivareal.com.br" + v
    # link object
    link = listing.get("link")
    if isinstance(link, dict):
        for k in ("href", "url", "uri"):
            v = link.get(k)
            if isinstance(v, str) and v.strip():
                if v.startswith("http"):
                    return v
                if v.startswith("/"):
                    return "https://www.vivareal.com.br" + v
    return None


def _format_address(addr: dict) -> Optional[str]:
    if not isinstance(addr, dict):
        return None
    parts = []
    for k in ("street", "neighborhood", "city", "state"):
        v = addr.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return ", ".join(parts) if parts else None


def parse_vivareal_glue_to_std(glue_json: dict) -> List[dict]:
    listings = get_by_path(glue_json, "search.result.listings")
    if not isinstance(listings, list):
        return []

    out: List[dict] = []
    for it in listings:
        listing = it.get("listing") if isinstance(it, dict) and isinstance(it.get("listing"), dict) else it
        if not isinstance(listing, dict):
            continue

        lid = listing.get("id") or listing.get("listingId") or listing.get("listing_id")
        if lid is None:
            continue
        lid = str(lid)

        # preço: pricingInfos[0].price, ou pricingInfo.price
        price = None
        pi = listing.get("pricingInfos")
        if isinstance(pi, list) and pi:
            price = _as_int(pi[0].get("price") or pi[0].get("rentalTotalPrice") or pi[0].get("monthlyCondoFee"))
        if price is None and isinstance(listing.get("pricingInfo"), dict):
            price = _as_int(listing["pricingInfo"].get("price") or listing["pricingInfo"].get("rentalTotalPrice"))

        area = _as_float(listing.get("usableAreas") or listing.get("usableArea") or listing.get("area") or listing.get("totalAreas") or listing.get("totalArea"))
        bedrooms = _as_int(listing.get("bedrooms") or listing.get("bedroomCount"))
        bathrooms = _as_int(listing.get("bathrooms") or listing.get("bathroomCount"))
        parking = _as_int(listing.get("parkingSpaces") or listing.get("parking") or listing.get("garageSpaces"))

        address = listing.get("address") if isinstance(listing.get("address"), dict) else {}
        point = address.get("point") if isinstance(address.get("point"), dict) else {}
        lat = _as_float(point.get("lat") or point.get("latitude"))
        lon = _as_float(point.get("lon") or point.get("longitude"))

        url = _pick_first_url(listing) or f"https://www.vivareal.com.br/imovel/{lid}/"

        out.append({
            "schema_version": STD_SCHEMA_VERSION,
            "platform": "vivareal",
            "listing_id": lid,
            "url": url,
            "lat": lat,
            "lon": lon,
            "price_brl": price,
            "area_m2": area,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "parking": parking,
            "address": _format_address(address),
        })
    return out


def parse_run_dir(platform_dir: str | Path) -> List[dict]:
    p = Path(platform_dir)
    if not p.exists():
        return []

    files = sorted(glob.glob(str(p / "replay_vivareal_glue_listings_p*.json")))
    if not files:
        # fallback: qualquer replay vivareal
        files = sorted(glob.glob(str(p / "replay_vivareal_*.json")))
    out: List[dict] = []
    seen = set()
    for fp in files:
        try:
            data = json.load(open(fp, "r", encoding="utf-8"))
        except Exception:
            continue
        for item in parse_vivareal_glue_to_std(data):
            key = (item.get("platform"), item.get("listing_id"))
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Parser dedicado VivaReal (a partir do run do realestate_meta_search).")
    ap.add_argument("--dir", required=True, help="Diretório da plataforma, ex.: runs/run_x/vivareal")
    ap.add_argument("--out", default="", help="Arquivo JSON de saída (opcional).")
    args = ap.parse_args()

    items = parse_run_dir(args.dir)
    if args.out:
        Path(args.out).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(items[:3], ensure_ascii=False, indent=2))
        print(f"... total={len(items)}")

if __name__ == "__main__":
    main()
