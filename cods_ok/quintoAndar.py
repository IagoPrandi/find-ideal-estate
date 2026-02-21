#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quintoAndar.py — parser dedicado (QuintoAndar)

Objetivo:
- Ler os artefatos gerados no run do realestate_meta_search (ex.: quintoandar_next_data_*.json, quintoandar_next_page_*.json,
  replay_quintoandar_coordinates_full_*.json).
- Gerar lista padronizada de imóveis:
  {schema_version, platform, listing_id, url, lat, lon, price_brl, area_m2, bedrooms, bathrooms, parking, address}

Este arquivo NÃO faz integração entre plataformas.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STD_SCHEMA_VERSION = 1


# ----------------------------
# Utilitários
# ----------------------------

def get_by_path(obj: Any, path: str) -> Any:
    """Acessa caminho com pontos: 'a.b.0.c'. Retorna None se não existir."""
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
        if isinstance(x, (int,)):
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


def _read_json(fp: str | Path) -> Any:
    return json.load(open(fp, "r", encoding="utf-8"))


def _latest_file(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


# ----------------------------
# QuintoAndar parse
# ----------------------------

def _extract_quintoandar_ids_from_visible_pages(state: dict) -> List[str]:
    """
    Extrai ids em visibleHouses.pages.
    Estruturas comuns:
      - state.search.visibleHouses.pages = [[id1,id2,...],[...],...]
      - state.visibleHouses.pages
    """
    pages = (
        get_by_path(state, "search.visibleHouses.pages")
        or get_by_path(state, "visibleHouses.pages")
        or get_by_path(state, "search.visibleHouses")
        or get_by_path(state, "visibleHouses")
    )
    out: List[str] = []
    if isinstance(pages, dict):
        pages = pages.get("pages") or pages.get("items") or pages.get("results")
    if isinstance(pages, list):
        for p in pages:
            if isinstance(p, list):
                for hid in p:
                    if hid is None:
                        continue
                    out.append(str(hid))
            elif isinstance(p, (str, int)):
                out.append(str(p))
    # dedupe preservando ordem
    seen = set()
    uniq = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def _pick_quintoandar_houses_map(state: dict) -> dict:
    """
    Localiza o mapa houses[id] no state.
    """
    candidates = [
        get_by_path(state, "houses"),
        get_by_path(state, "entities.houses"),
        get_by_path(state, "search.houses"),
        get_by_path(state, "search.entities.houses"),
    ]
    for cand in candidates:
        if isinstance(cand, dict) and cand:
            return cand
    return {}


def _quintoandar_latlon_from_house(h: dict) -> Tuple[Optional[float], Optional[float]]:
    candidates = [
        ("address", "point", "lat", "lon"),
        ("location", "point", "lat", "lon"),
        ("geoLocation", "lat", "lon"),
        ("geolocation", "lat", "lon"),
        ("coordinates", "lat", "lon"),
        ("coordinates", "latitude", "longitude"),
        ("address", "geoLocation", "lat", "lon"),
        ("address", "geolocation", "lat", "lon"),
    ]
    for cand in candidates:
        *prefix, lat_k, lon_k = cand
        cur: Any = h
        ok = True
        for k in prefix:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if not ok or not isinstance(cur, dict):
            continue
        lat = _as_float(cur.get(lat_k))
        lon = _as_float(cur.get(lon_k))
        if lat is not None and lon is not None:
            return lat, lon
    return None, None


def _quintoandar_coords_map(coords_json: Optional[dict]) -> Optional[Dict[str, Tuple[Optional[float], Optional[float]]]]:
    """
    Mapeia id -> (lat, lon) a partir do replay_quintoandar_coordinates_full_*.json (quando disponível).
    """
    if not isinstance(coords_json, dict):
        return None

    # Possíveis estruturas (dependendo do endpoint capturado)
    # - hits.hits[*]._id ou _source.id e _source.addressPointLat/Lon
    # - results[*].id + results[*].addressPointLat/Lon
    hits = get_by_path(coords_json, "hits.hits")
    if not isinstance(hits, list):
        hits = coords_json.get("hits") if isinstance(coords_json.get("hits"), list) else None

    out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}

    def _try_add(i: Any, src: dict):
        hid = None
        if isinstance(i, dict):
            hid = i.get("_id") or i.get("id") or src.get("id")
        if hid is None:
            return
        lat = src.get("addressPointLat") or src.get("lat") or get_by_path(src, "address.point.lat")
        lon = src.get("addressPointLon") or src.get("lon") or get_by_path(src, "address.point.lon")
        latf = _as_float(lat)
        lonf = _as_float(lon)
        out[str(hid)] = (latf, lonf)

    if isinstance(hits, list):
        for h in hits:
            if not isinstance(h, dict):
                continue
            src = h.get("_source") if isinstance(h.get("_source"), dict) else {}
            _try_add(h, src)

    # fallback: results list
    results = coords_json.get("results") or coords_json.get("result") or coords_json.get("listings")
    if isinstance(results, list):
        for r in results:
            if not isinstance(r, dict):
                continue
            _try_add(r, r)

    return out if out else None


def _format_address(h: dict) -> Optional[str]:
    # tenta pegar strings comuns
    if isinstance(h.get("address"), str) and h["address"].strip():
        # em alguns payloads isso já é a rua completa
        street = h["address"].strip()
    else:
        street = None

    addr = h.get("address") if isinstance(h.get("address"), dict) else {}
    neigh = addr.get("neighbourhood") or addr.get("neighborhood") or h.get("neighbourhood") or h.get("neighborhood")
    city = addr.get("city") or h.get("city")
    state = addr.get("state") or h.get("state")

    parts = []
    if street:
        parts.append(street)
    elif isinstance(addr.get("street"), str) and addr["street"].strip():
        parts.append(addr["street"].strip())
    if isinstance(neigh, str) and neigh.strip():
        parts.append(neigh.strip())
    if isinstance(city, str) and city.strip():
        parts.append(city.strip())
    if isinstance(state, str) and state.strip():
        parts.append(state.strip())
    return ", ".join(parts) if parts else None


def _min_price_from_house(h: dict) -> Optional[int]:
    # tenta chaves comuns
    for k in ("totalCost", "rent", "salePrice", "price", "monthlyRent", "totalPrice"):
        if k in h:
            v = _as_int(h.get(k))
            if v is not None:
                return v
    # pricing dict
    pricing = h.get("pricing") if isinstance(h.get("pricing"), dict) else {}
    for k in ("totalCost", "rent", "salePrice", "price"):
        v = _as_int(pricing.get(k))
        if v is not None:
            return v
    return None


def parse_quintoandar_state_to_std(state: dict, coords_map: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]] = None) -> List[dict]:
    ids = _extract_quintoandar_ids_from_visible_pages(state)
    houses = _pick_quintoandar_houses_map(state)
    out: List[dict] = []

    for hid in ids:
        h = houses.get(hid) if isinstance(houses, dict) else None
        if not isinstance(h, dict):
            continue

        price = _min_price_from_house(h)
        area = _as_float(h.get("area") or h.get("usableArea") or h.get("size"))
        bedrooms = _as_int(h.get("bedrooms") or h.get("bedroomCount") or h.get("rooms"))
        bathrooms = _as_int(h.get("bathrooms") or h.get("bathroomCount"))
        parking = _as_int(h.get("parkingSpaces") or h.get("parking") or h.get("garage"))

        lat = lon = None
        if coords_map and hid in coords_map:
            lat, lon = coords_map[hid]
        if lat is None or lon is None:
            lat, lon = _quintoandar_latlon_from_house(h)

        url = f"https://www.quintoandar.com.br/imovel/{hid}"
        # alguns payloads possuem slug/uri
        if isinstance(h.get("uri"), str) and h["uri"].startswith("/"):
            url = "https://www.quintoandar.com.br" + h["uri"]
        elif isinstance(h.get("url"), str) and h["url"].startswith("http"):
            url = h["url"]

        out.append({
            "schema_version": STD_SCHEMA_VERSION,
            "platform": "quinto_andar",
            "listing_id": str(hid),
            "url": url,
            "lat": lat,
            "lon": lon,
            "price_brl": price,
            "area_m2": area,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "parking": parking,
            "address": _format_address(h),
        })
    return out


def parse_run_dir(platform_dir: str | Path) -> List[dict]:
    """
    Lê artefatos de um diretório de plataforma (ex.: runs/run_x/quinto_andar) e retorna lista padronizada.
    Preferência:
      1) arquivo `quintoandar_next_data_*.json` (mais completo)
      2) arquivo `quintoandar_next_page_*.json`
    coords:
      - replay_quintoandar_coordinates_full_*.json se existir
    """
    p = Path(platform_dir)
    if not p.exists():
        return []

    next_data = _latest_file(str(p / "quintoandar_next_data_*.json"))
    next_page = _latest_file(str(p / "quintoandar_next_page_*.json"))
    coords_fp = _latest_file(str(p / "replay_quintoandar_coordinates_full_*.json"))

    coords_json = _read_json(coords_fp) if coords_fp else None
    coords_map = _quintoandar_coords_map(coords_json) if isinstance(coords_json, dict) else None

    payload_fp = next_data or next_page
    if not payload_fp:
        return []
    payload = _read_json(payload_fp)
    state = get_by_path(payload, "props.pageProps.initialState") or get_by_path(payload, "pageProps.initialState")
    if not isinstance(state, dict):
        # fallback: alguns endpoints devolvem o state no topo
        if isinstance(payload, dict):
            for key in ("initialState", "state", "data", "result"):
                cand = payload.get(key)
                if isinstance(cand, dict):
                    state = cand
                    break
    if not isinstance(state, dict):
        return []

    return parse_quintoandar_state_to_std(state, coords_map=coords_map)


# ----------------------------
# CLI
# ----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Parser dedicado QuintoAndar (a partir do run do realestate_meta_search).")
    ap.add_argument("--dir", required=True, help="Diretório da plataforma, ex.: runs/run_x/quinto_andar")
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
