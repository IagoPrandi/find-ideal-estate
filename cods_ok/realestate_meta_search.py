import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy

import orjson
import pandas as pd
import yaml
from rapidfuzz import fuzz
from tqdm import tqdm

from playwright.async_api import async_playwright

# Headers exigidos pelo Glue API do VivaReal
COMMON_PATHS_VIVAREAL = [
    'search.result.listings',
    'search.result.listings.listing',
    'result.listings',
    'listings',
]

VIVAREAL_PAGES_DEFAULT = 4  # número de páginas (offsets) para coletar no VivaReal

VIVAREAL_GLUE_HEADERS = {
    'x-domain': 'www.vivareal.com.br',
    'referer': 'https://www.vivareal.com.br/',
    'origin': 'https://www.vivareal.com.br',
}

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import html as _html


# ----------------------------
# Geocoding (endereço -> lat/lon)
# ----------------------------
def geocode_address_nominatim(address: str, countrycodes: str = "br", limit: int = 1) -> Optional[Dict[str, Any]]:
    """Geocodifica um endereço usando Nominatim (OpenStreetMap).
    Retorna dict com lat/lon e, quando disponível, city/state.
    Usa apenas urllib (sem deps externas).
    """
    address = (address or "").strip()
    if not address:
        return None

    # Nominatim exige User-Agent identificável. Permite override via env.
    ua = os.environ.get("NOMINATIM_USER_AGENT", "onde-morar-scraper/1.0 (contact: set NOMINATIM_USER_AGENT)")
    base = "https://nominatim.openstreetmap.org/search"
    q = {
        "format": "jsonv2",
        "q": address,
        "limit": str(limit),
        "addressdetails": "1",
        "countrycodes": countrycodes,
    }
    url = base + "?" + urlencode(list(q.items()))
    try:
        req = Request(url, headers={"User-Agent": ua, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"})
        with urlopen(req, timeout=20) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8", errors="ignore") or "[]")
        if not isinstance(data, list) or not data:
            return None
        best = data[0]
        lat = _as_float(best.get("lat"))
        lon = _as_float(best.get("lon"))
        if lat is None or lon is None:
            return None
        addr = best.get("address") if isinstance(best.get("address"), dict) else {}
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
        state = addr.get("state")
        return {
            "query": address,
            "lat": lat,
            "lon": lon,
            "display_name": best.get("display_name"),
            "city": city,
            "state": state,
            "raw": best,
        }
    except Exception:
        return None



def _qa_body_with_pagination(body: Any, from_: int, size: int) -> Any:
    """Tenta ajustar offset/paginação em corpos JSON do QuintoAndar.
    Funciona com padrões comuns: {from,size}, {offset,limit}, {page,size}, {pagination:{from,size}}.
    Retorna uma cópia (quando body é dict).
    """
    if not isinstance(body, dict):
        return body
    b = deepcopy(body)
    # nível raiz
    if "from" in b:
        b["from"] = from_
    if "size" in b:
        b["size"] = size
    if "offset" in b:
        b["offset"] = from_
    if "limit" in b:
        b["limit"] = size
    if "page" in b and isinstance(b.get("page"), int):
        # aproximação: page 0-based
        b["page"] = int(from_ / max(size, 1))
    # nested
    for key in ("pagination", "paging", "pageable"):
        if isinstance(b.get(key), dict):
            if "from" in b[key]:
                b[key]["from"] = from_
            if "size" in b[key]:
                b[key]["size"] = size
            if "offset" in b[key]:
                b[key]["offset"] = from_
            if "limit" in b[key]:
                b[key]["limit"] = size
            if "page" in b[key] and isinstance(b[key].get("page"), int):
                b[key]["page"] = int(from_ / max(size, 1))
    # algumas estruturas guardam a query em "search" / "query"
    for key in ("search", "query", "filters"):
        if isinstance(b.get(key), dict):
            if isinstance(b[key].get("pagination"), dict):
                if "from" in b[key]["pagination"]:
                    b[key]["pagination"]["from"] = from_
                if "size" in b[key]["pagination"]:
                    b[key]["pagination"]["size"] = size
    return b




# ----------------------------
# Utilidades: parsing e geo
# ----------------------------

_PRICE_RE = re.compile(r"(\d[\d\.\,]*)")

def parse_brl(value: Any) -> Optional[float]:
    """
    Converte preço em float (BRL).
    Aceita: número, "R$ 3.500", "3500", "3.500,00".
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = _PRICE_RE.search(value.replace(" ", ""))
        if not m:
            return None
        s = m.group(1)
        # Heurística pt-BR: "." milhar, "," decimal
        s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distância em metros via fórmula de Haversine.
    """
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def safe_filename(s: str, max_len: int = 120) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", s)
    return s[:max_len]


def get_by_path(obj: Any, path: str) -> Any:
    """
    Leitura simples por caminho "a.b.0.c" (ponto + índices numéricos).
    Retorna None se não achar.
    """
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(cur):
                    cur = cur[idx]
                else:
                    return None
            else:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def iter_nodes(obj: Any, path: str = ""):
    """Itera por todos os nós de um JSON retornando (path, value)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            yield from iter_nodes(v, p)
    elif isinstance(obj, list):
        # limita para evitar explosão
        for i, v in enumerate(obj[:80]):
            p = f"{path}.{i}" if path else str(i)
            yield from iter_nodes(v, p)
    else:
        yield path, obj


def score_list_candidates(json_obj: Any):
    """
    Encontra caminhos que parecem conter a lista de imóveis:
    - lista >= 10 itens
    - itens dict
    - sinais de geo/preço/url
    Retorna lista ordenada: [(score, path, n_items, sample_keys)]
    """
    cands = []
    for p, v in iter_nodes(json_obj):
        if isinstance(v, list) and len(v) >= 10 and all(isinstance(x, dict) for x in v[:10]):
            keys = set()
            for x in v[:10]:
                keys |= set(x.keys())

            keys_l = {k.lower() for k in keys}
            has_geo = any(k in keys_l for k in {"lat", "lng", "lon", "latitude", "longitude"}) or any(("location" in k) or ("coord" in k) for k in keys_l)
            has_price = any(any(tok in k for tok in ("price", "preco", "valor", "rent", "rental", "alug", "sale", "venda", "monthly")) for k in keys_l)
            has_url = any(k in keys_l or "url" in k for k in {"url", "link", "href"})
            has_id = any(k in keys_l for k in {"id", "listingid", "propertyid", "code"})

            score = 0
            score += 2 if has_geo else 0
            score += 2 if has_price else 0
            score += 1 if has_url else 0
            score += 1 if has_id else 0
            score += 1 if len(v) >= 20 else 0

            cands.append((score, p, len(v), sorted(list(keys))[:30]))

    cands.sort(key=lambda x: x[0], reverse=True)
    return cands


def find_leaf_paths(obj: Any, prefix: str = "", max_depth: int = 8):
    """
    Retorna paths até folhas/primitivos ou dicts simples.
    Usado para inferir campos dentro de um item.
    """
    out = []

    def rec(o, p, depth):
        if depth > max_depth:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                np = f"{p}.{k}" if p else k
                rec(v, np, depth + 1)
        elif isinstance(o, list):
            # examinamos só o primeiro item (padrão de schemas)
            if len(o) > 0:
                rec(o[0], f"{p}.0" if p else "0", depth + 1)
        else:
            out.append(p)

    rec(obj, prefix, 0)
    return out


def pick_best_path(paths: List[str], keywords: List[str]):
    """
    Escolhe um path que contenha mais keywords (em lowercase).
    """
    best = None
    best_score = -1
    for p in paths:
        pl = p.lower()
        s = sum(1 for kw in keywords if kw in pl)
        if s > best_score:
            best = p
            best_score = s
    return best if best_score > 0 else None


def infer_fields_from_item(sample_item: Dict[str, Any]) -> Dict[str, str]:
    """
    Heurística para inferir os fields comuns.
    """
    paths = find_leaf_paths(sample_item)

    # geo
    lat = pick_best_path(paths, ["lat", "latitude"])
    lon = pick_best_path(paths, ["lon", "lng", "longitude"])

    # preço
    price = pick_best_path(paths, ["price", "preco", "valor", "amount"])

    # url
    url = pick_best_path(paths, ["url", "href", "link"])

    # id
    _id = pick_best_path(paths, ["id", "listingid", "propertyid", "code", "uid"])

    # textos
    title = pick_best_path(paths, ["title", "titulo", "name", "nome"])
    address = pick_best_path(paths, ["address", "endereco", "street", "logradouro", "full"])

    # atributos
    area = pick_best_path(paths, ["area", "m2", "size", "usable"])
    bedrooms = pick_best_path(paths, ["bed", "quarto", "dorm"])
    bathrooms = pick_best_path(paths, ["bath", "banh"])
    parking = pick_best_path(paths, ["parking", "vaga", "garage"])

    fields = {}
    if _id: fields["id"] = _id
    if title: fields["title"] = title
    if address: fields["address"] = address
    if lat: fields["lat"] = lat
    if lon: fields["lon"] = lon
    if price: fields["price"] = price
    if url: fields["url"] = url
    if area: fields["area_m2"] = area
    if bedrooms: fields["bedrooms"] = bedrooms
    if bathrooms: fields["bathrooms"] = bathrooms
    if parking: fields["parking"] = parking
    return fields


def autoconfigure_platform(platform_dir: Path) -> Optional[Tuple[str, Dict[str, str]]]:
    """
    Lê JSONs capturados e tenta descobrir:
    - listing_path
    - fields
    Retorna (listing_path, fields) ou None.
    """
    json_files = sorted(platform_dir.glob("*.json"))
    if not json_files:
        return None

    best = None  # (score, listing_path, sample_item)
    for jf in json_files:
        try:
            data = orjson.loads(jf.read_bytes())
        except Exception:
            continue

        cands = score_list_candidates(data)
        if not cands:
            continue

        top_score, top_path, _, _ = cands[0]
        if top_score <= 0:
            continue

        items = get_by_path(data, top_path)
        if isinstance(items, list) and items and isinstance(items[0], dict):
            if best is None or top_score > best[0]:
                best = (top_score, top_path, items[0])

    if not best:
        return None

    _, listing_path, sample_item = best
    fields = infer_fields_from_item(sample_item)
    return listing_path, fields


def write_autogen_yaml(original_yaml_path: str, run_root: Path, mode: str, out_path: str) -> str:
    """
    Gera um YAML novo preenchendo listing_path/fields quando descobertos.
    Mantém o restante do YAML igual.
    """
    with open(original_yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg2 = deepcopy(cfg)
    platforms = (cfg2.get("platforms") or {})

    for pname, pcfg in platforms.items():
        pdir = run_root / pname
        if not pdir.exists():
            continue

        auto = autoconfigure_platform(pdir)
        if not auto:
            # marca que não conseguiu (não impede pipeline)
            pcfg["_autoconfig_status"] = f"no_json_or_no_list_found_{mode}"
            continue

        listing_path, fields = auto

        # Ajustes manuais por plataforma (quando a captura pega payload "vazio" ou só coordenadas)
        if pname == "quinto_andar":
            # Preferência 1: payload Next.js (__NEXT_DATA__/ _next/data) — traz preço/área/quartos/endereço (mas pode vir sem lat/lon).
            # Preferência 2: endpoint de busca (POST .../search) — costuma trazer lista rica completa.
            # Fallback: JSON de coordenadas -> enrich via página do anúncio e injeta em `enriched.*`.
            has_next_data = any(f.name.startswith("quintoandar_next_data_") or f.name.startswith("quintoandar_next_page_") for f in pdir.glob("*.json"))
            if has_next_data:
                listing_path = "__NEXT_DATA__"
                fields = {
                    "id": "id",
                    "title": "shortRentDescription",
                    # endereço completo montado no parse (rua + bairro + região + cidade)
                    "address": "address_full",
                    "price": "rentPrice",
                    "area_m2": "area",
                    "bedrooms": "bedrooms",
                    "bathrooms": "bathrooms",
                    "parking": "parkingSpots",
                    # lat/lon serão injetados (a partir do replay de coordinates) quando disponíveis
                    "lat": "lat",
                    "lon": "lon",
                    "url": "url",
                }
            else:
                has_geo = bool(fields.get("lat")) and bool(fields.get("lon"))
                has_price = bool(fields.get("price"))
                looks_like_coords_only = (listing_path or "") in ("hits.hits", "hits.hits.hits", "")

                if (not has_geo) or (not has_price) or looks_like_coords_only:
                    listing_path = listing_path or "hits.hits"
                    fields = {
                        "id": "_id",
                        "lat": "_source.location.lat",
                        "lon": "_source.location.lon",
                        "price": "enriched.price",
                        "title": "enriched.title",
                        "address": "enriched.address",
                        "bedrooms": "enriched.bedrooms",
                        "bathrooms": "enriched.bathrooms",
                        "parking": "enriched.parking",
                        "area_m2": "enriched.area_m2",
                        "url": "enriched.url",
                    }


        # Só sobrescreve se estiver vazio ou ausente (evita destruir config manual)
        if not pcfg.get("listing_path"):
            pcfg["listing_path"] = listing_path
        if not pcfg.get("fields"):
            pcfg["fields"] = fields
        else:
            # complementa campos faltantes
            for k, v in fields.items():
                pcfg["fields"].setdefault(k, v)

        pcfg["_autoconfig_status"] = f"ok_{mode}"

    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg2, f, sort_keys=False, allow_unicode=True)

    return out_path

# ----------------------------
# Saída padronizada (JSON)
# ----------------------------

STD_SCHEMA_VERSION = "1.0"

def _as_float(x):
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str) and x.strip() == "":
            return None
        return float(x)
    except Exception:
        return None



def to_float(v):
    """Alias compatível: converte para float quando possível."""
    return _as_float(v)
def _as_int(x):
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        if isinstance(x, (int, float)):
            return int(x)
        if isinstance(x, str) and x.strip().isdigit():
            return int(x.strip())
        return None
    except Exception:
        return None

def _min_price_from_any(obj) -> Optional[float]:
    """
    Retorna o menor preço detectável em estruturas comuns (dict/list),
    usado quando houver múltiplos pricingInfos etc.
    """
    prices = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).lower()
                if kl in ("price", "rentaltotalprice", "monthlyprice", "amount", "rentprice", "saleprice"):
                    pv = parse_brl(v)
                    if pv is not None:
                        prices.append(pv)
                walk(v)
        elif isinstance(o, list):
            for it in o[:200]:
                walk(it)

    walk(obj)
    return min(prices) if prices else None

def _find_first_dict_with_keys(obj, required_keys: set, max_nodes: int = 20000) -> Optional[dict]:
    """
    Busca BFS por um dict que contenha todas as required_keys.
    Evita varrer infinito.
    """
    from collections import deque
    q = deque([obj])
    seen = 0
    while q and seen < max_nodes:
        cur = q.popleft()
        seen += 1
        if isinstance(cur, dict):
            keys = set(cur.keys())
            if required_keys.issubset(keys):
                return cur
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(cur, list):
            for v in cur[:200]:
                if isinstance(v, (dict, list)):
                    q.append(v)
    return None

def _extract_quintoandar_ids_from_visible_pages(state: dict) -> List[str]:
    """
    Pega ids em visibleHouses.pages (como você pediu), de forma robusta.

    Observação importante:
      - Em alguns payloads do QuintoAndar, `visibleHouses.pages` pode ser:
          a) list[ list[int|str] ]           (mais simples)
          b) list[ dict{ids:[...]} ]         (variações)
          c) dict{ "0": [...], "1": [...] }  (muito comum: páginas indexadas por string)
      - Esta função normaliza esses formatos e devolve uma lista única (sem duplicatas, preservando ordem).
    """
    candidates: List[Tuple[str, Any]] = []

    # tentativas diretas (mais comuns)
    direct_paths = [
        "search.visibleHouses.pages",
        "houses.visibleHouses.pages",
        "search.searchResults.visibleHouses.pages",
        "search.searchResult.visibleHouses.pages",
        "search.results.visibleHouses.pages",
        "route.visibleHouses.pages",
    ]
    for p in direct_paths:
        pages = get_by_path(state, p)
        if isinstance(pages, (list, dict)):
            candidates.append((p, pages))

    if not candidates:
        # fallback: procura um dict que tenha {"visibleHouses": {"pages": ...}}
        vh = _find_first_dict_with_keys(state, {"visibleHouses"})
        if isinstance(vh, dict) and isinstance(vh.get("visibleHouses"), dict):
            pages = vh["visibleHouses"].get("pages")
            if isinstance(pages, (list, dict)):
                candidates.append(("visibleHouses.pages(fallback)", pages))

    if not candidates:
        return []

    def _iter_pages(obj: Any) -> List[Any]:
        """Normaliza pages para uma lista de páginas em ordem estável."""
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            # ordena chaves numéricas primeiro (0,1,2...), depois alfabético
            def _kkey(k: Any):
                ks = str(k)
                return (0, int(ks)) if ks.isdigit() else (1, ks)
            out = []
            for k in sorted(obj.keys(), key=_kkey):
                out.append(obj.get(k))
            return out
        return []

    def _count_ids(pages_obj: Any) -> int:
        n = 0
        for pg in _iter_pages(pages_obj):
            if isinstance(pg, list):
                n += len(pg)
            elif isinstance(pg, dict):
                for k in ("ids", "houseIds", "items", "results"):
                    if isinstance(pg.get(k), list):
                        n += len(pg[k])
        return n

    # escolhe o candidato com mais ids (melhor cobertura)
    best_pages_obj: Any = None
    best_n = -1
    for _, pages_obj in candidates:
        n = _count_ids(pages_obj)
        if n > best_n:
            best_n = n
            best_pages_obj = pages_obj

    ids: List[str] = []
    for pg in _iter_pages(best_pages_obj):
        if isinstance(pg, list):
            for x in pg:
                if isinstance(x, (int, str)):
                    ids.append(str(x))
        elif isinstance(pg, dict):
            for k in ("ids", "houseIds", "items", "results"):
                if isinstance(pg.get(k), list):
                    for x in pg[k]:
                        if isinstance(x, (int, str)):
                            ids.append(str(x))

    # unique preservando ordem
    seen = set()
    out: List[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out

def _pick_quintoandar_houses_map(state: dict) -> Optional[dict]:
    """
    Encontra o 'houses' que é um map id -> dict (como você pediu: houses[id]).
    Faz scoring por "parecer card" (rentPrice/area/bedrooms).
    """
    # tentativas diretas
    for p in (
        "houses",
        "houses.houses",
        "houses.byId",
        "houses.entities",
        "houses.housesById",
        "search.houses",
        "search.housesById",
    ):
        m = get_by_path(state, p)
        if isinstance(m, dict) and len(m) > 0:
            # checa se parece id->dict
            k0 = next(iter(m.keys()))
            v0 = m.get(k0)
            if isinstance(v0, dict):
                return m

    # fallback: varre procurando um dict grande id->dict
    # e pontua por campos típicos
    best = None
    best_score = -1

    def score_map(mp: dict) -> int:
        score = 0
        # amostra poucos itens
        for _, v in list(mp.items())[:20]:
            if not isinstance(v, dict):
                continue
            keys = {str(k).lower() for k in v.keys()}
            if "rentprice" in keys or "saleprice" in keys:
                score += 3
            if "area" in keys or "usablearea" in keys:
                score += 2
            if "bedrooms" in keys:
                score += 1
            if "bathrooms" in keys:
                score += 1
            if "parkingspots" in keys:
                score += 1
            if "id" in keys:
                score += 1
        return score

    from collections import deque
    q = deque([state])
    seen = 0
    while q and seen < 25000:
        cur = q.popleft()
        seen += 1
        if isinstance(cur, dict):
            # candidato: dict relativamente grande cujas values são dict
            if len(cur) >= 20:
                # checa se parece id->dict
                values = list(cur.values())[:10]
                if all(isinstance(v, dict) for v in values):
                    s = score_map(cur)
                    if s > best_score:
                        best_score = s
                        best = cur
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(cur, list):
            for v in cur[:200]:
                if isinstance(v, (dict, list)):
                    q.append(v)

    return best


def _quintoandar_latlon_from_house(h: dict):
    """Best-effort extraction of (lat, lon) from a QuintoAndar house dict."""
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
        cur = h
        ok = True
        for k in prefix:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if not ok or not isinstance(cur, dict):
            continue
        lat = cur.get(lat_k)
        lon = cur.get(lon_k)
        try:
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except Exception:
            pass
    return None, None


def _quintoandar_coords_map(coords_json: dict) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """
    replay_quintoandar_coordinates_full: hits.hits[*]._source.id + _source.location.{lat,lon}
    """
    mp: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    hits = get_by_path(coords_json, "hits.hits") or []
    if isinstance(hits, list):
        for h in hits:
            try:
                sid = str(get_by_path(h, "_source.id") or get_by_path(h, "_source.houseId") or get_by_path(h, "_id"))
                lat = _as_float(get_by_path(h, "_source.location.lat"))
                lon = _as_float(get_by_path(h, "_source.location.lon"))
                if sid and (lat is not None or lon is not None):
                    mp[sid] = (lat, lon)
            except Exception:
                continue
    return mp


def _qa_scan_quintoandar_coords_from_json_files(json_files: List[Path], max_files: int = 300) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Extrai um map id -> (lat, lon) varrendo JSONs já capturados do QuintoAndar.

    **Não faz requisições.** Apenas reutiliza payloads já presentes no run (network captures / replays).

    Estratégia:
      1) Se existir algum `replay_quintoandar_coordinates_full_*.json`, usa o que tiver mais hits.
      2) Caso contrário, varre outros JSONs e identifica respostas no formato ES-like com `hits.hits[*]._source.location.{lat,lon}`.
      3) Fallback: busca recursivamente por dicts com `location:{lat,lon}` e `id`.

    Retorna dict com chaves em string.
    """
    best_coords_obj = None
    best_n = -1

    # (1) replays explícitos (quando existem)
    for jf in json_files:
        name = jf.name
        if "replay_quintoandar_coordinates_full_" in name and name.endswith(".json"):
            try:
                obj = orjson.loads(jf.read_bytes())
                hits = get_by_path(obj, "hits.hits")
                n = len(hits) if isinstance(hits, list) else 0
                if n > best_n:
                    best_n = n
                    best_coords_obj = obj
            except Exception:
                continue

    # (2) se não achou, tenta achar respostas similares entre os demais JSONs
    if best_coords_obj is None:
        # limita para não ficar caro em runs enormes
        scanned = 0
        for jf in json_files:
            if scanned >= max_files:
                break
            name = jf.name
            if name.startswith("quintoandar_next_") or name.startswith("replay_"):
                continue
            if not name.endswith(".json"):
                continue
            scanned += 1
            try:
                obj = orjson.loads(jf.read_bytes())
            except Exception:
                continue

            hits = get_by_path(obj, "hits.hits")
            if isinstance(hits, list) and hits:
                # checa se parece response do coordinates (tem _source.location)
                lat0 = get_by_path(hits[0], "_source.location.lat")
                lon0 = get_by_path(hits[0], "_source.location.lon")
                if lat0 is not None and lon0 is not None:
                    n = len(hits)
                    if n > best_n:
                        best_n = n
                        best_coords_obj = obj

    mp: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    if isinstance(best_coords_obj, dict):
        mp.update(_quintoandar_coords_map(best_coords_obj))

    if mp:
        return mp

    # (3) fallback recursivo: procura estruturas do tipo {"id":..., "location":{"lat":...,"lon":...}}
    def walk(o: Any, depth: int = 0):
        if depth > 6:
            return
        if isinstance(o, dict):
            loc = o.get("location")
            if isinstance(loc, dict):
                lat = _as_float(loc.get("lat") or loc.get("latitude"))
                lon = _as_float(loc.get("lon") or loc.get("lng") or loc.get("longitude"))
                oid = o.get("id") or o.get("houseId") or o.get("_id")
                if oid is not None and (lat is not None and lon is not None):
                    mp[str(oid)] = (lat, lon)
            for v in o.values():
                walk(v, depth + 1)
        elif isinstance(o, list):
            for it in o[:200]:
                walk(it, depth + 1)

    scanned = 0
    for jf in json_files:
        if scanned >= max_files:
            break
        name = jf.name
        if name.startswith("quintoandar_next_"):
            continue
        if not name.endswith(".json"):
            continue
        scanned += 1
        try:
            obj = orjson.loads(jf.read_bytes())
        except Exception:
            continue
        walk(obj)

    return mp

def _find_url_in_house(h: dict) -> Optional[str]:
    """
    Tenta achar uma URL em campos comuns; fallback para /imovel/<id> quando possível.
    """
    # comuns
    for k in ("url", "canonicalUrl", "canonical_url", "detailUrl", "detail_url", "href"):
        v = h.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
        if isinstance(v, str) and v.startswith("/"):
            return "https://www.quintoandar.com.br" + v

    # nested
    def walk(o):
        if isinstance(o, dict):
            for kk, vv in o.items():
                if str(kk).lower() in ("url", "href", "canonicalurl", "detailurl"):
                    if isinstance(vv, str):
                        return vv
                got = walk(vv)
                if got:
                    return got
        elif isinstance(o, list):
            for it in o[:50]:
                got = walk(it)
                if got:
                    return got
        return None

    u = walk(h)
    if isinstance(u, str):
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return "https://www.quintoandar.com.br" + u

    # fallback fraco: /imovel/<id>
    hid = h.get("id")
    if hid is not None:
        return f"https://www.quintoandar.com.br/imovel/{hid}"
    return None

def _quintoandar_address_full(h: dict) -> Optional[str]:
    """Monta endereço quando houver peças disponíveis.

    O QuintoAndar pode trazer endereço:
      - no topo (street/city/etc)
      - em h["address"] como dict: {"address": "...", "city": "..."}
      - e bairro/regionName em campos separados.
    """
    if not isinstance(h, dict):
        return None

    parts: List[str] = []

    # fontes possíveis
    sources: List[dict] = [h]
    addr_obj = h.get("address")
    if isinstance(addr_obj, dict):
        sources.append(addr_obj)

    def pick_str(keys: Tuple[str, ...]) -> Optional[str]:
        for src in sources:
            for k in keys:
                v = src.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return None

    def pick_any(keys: Tuple[str, ...]) -> Optional[str]:
        for src in sources:
            for k in keys:
                v = src.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
        return None

    street = pick_str(("street", "streetName", "addressStreet", "logradouro", "address"))
    number = pick_any(("streetNumber", "number", "addressNumber", "numero"))
    neigh = pick_str(("neighborhood", "neighbourhood", "bairro"))
    city = pick_str(("city", "cidade"))
    state = pick_str(("state", "uf", "estado"))

    # complementos do próprio card
    if not neigh:
        neigh = pick_str(("neighbourhood", "neighborhood")) or (h.get("regionName") if isinstance(h.get("regionName"), str) else None)

    for v in (street, number, neigh, city, state):
        if v:
            parts.append(v)

    if parts:
        # evita duplicatas simples
        out = []
        seen = set()
        for p in parts:
            if p.lower() in seen:
                continue
            seen.add(p.lower())
            out.append(p)
        return ", ".join(out)

    return None


def _infer_state_code_from_text(*values: Any) -> Optional[str]:
    """Infere UF (ex.: SP) a partir de trechos textuais confiáveis."""
    import re

    texts: List[str] = []
    for v in values:
        if isinstance(v, str) and v.strip():
            texts.append(v.strip())

    for t in texts:
        m = re.search(r"(?:^|[\s,\-/])([A-Za-z]{2})(?:$|[\s,\-/])", t)
        if m:
            uf = m.group(1).upper()
            if uf in {
                "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
                "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
                "RS", "RO", "RR", "SC", "SP", "SE", "TO",
            }:
                return uf

    for t in texts:
        low = t.lower()
        if "sao paulo" in low or "são paulo" in low:
            return "SP"

    return None



def parse_quintoandar_state_to_std(state: dict, coords_map: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]] = None) -> List[dict]:
    """Parseia um 'state' do QuintoAndar (seja do __NEXT_DATA__ ou de payloads de API) para o schema padrão."""
    if not isinstance(state, dict):
        return []

    ids = _extract_quintoandar_ids_from_visible_pages(state)
    houses_map = _pick_quintoandar_houses_map(state)
    if not isinstance(houses_map, dict) or not houses_map:
        return []

    # Se não achou ids, usa as chaves do map
    if not ids:
        ids = [str(k) for k in houses_map.keys() if str(k).isdigit()]

    if not ids:
        return []

    coords_map = coords_map or {}

    out: List[dict] = []
    for sid in ids:
        h = None
        if sid in houses_map:
            h = houses_map.get(sid)
        elif sid.isdigit() and int(sid) in houses_map:
            h = houses_map.get(int(sid))
        if not isinstance(h, dict):
            continue

        price = parse_brl(h.get("rentPrice")) or parse_brl(h.get("salePrice")) or _min_price_from_any(h)
        area = _as_float(h.get("area") or h.get("usableArea") or h.get("usableAreas"))
        bedrooms = _as_int(h.get("bedrooms"))
        bathrooms = _as_int(h.get("bathrooms"))
        parking = _as_int(h.get("parkingSpots") or h.get("parking") or h.get("parkingSpotsNumber") or h.get("parkingSpotsCount"))
        url = _find_url_in_house(h)
        addr = _quintoandar_address_full(h) or (h.get("address_full") if isinstance(h.get("address_full"), str) else None)

        h_addr = h.get("address") if isinstance(h.get("address"), dict) else {}
        city = h_addr.get("city") or h.get("city")
        state_name = (
            h_addr.get("state")
            or h_addr.get("stateAcronym")
            or h.get("state")
            or h.get("uf")
            or h.get("stateAcronym")
        )
        if not state_name:
            state_name = _infer_state_code_from_text(
                h_addr.get("address"),
                h_addr.get("city"),
                h.get("regionName"),
                addr,
                url,
            )

        lat, lon = (None, None)
        rid = str(h.get("id") or sid)
        if rid in coords_map:
            lat, lon = coords_map[rid]

        out.append({
            "schema_version": STD_SCHEMA_VERSION,
            "platform": "quinto_andar",
            "listing_id": rid,
            "url": url,
            "lat": lat,
            "lon": lon,
            "price_brl": price,
            "area_m2": area,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "parking": parking,
            "address": addr,
            "city": city,
            "state": state_name,
        })

    return out

def _qa_parse_quintoandar_search_list_payload(payload: dict, coords_map: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]] = None) -> List[dict]:
    """Parseia a resposta do endpoint do QuintoAndar `/house-listing-search/v2/search/list` (ES-like).
    Estrutura típica:
        {"hits": {"hits": [{"_id": "...", "_source": {...}}]}}
    """
    if not isinstance(payload, dict):
        return []

    root = payload
    # alguns replays podem embrulhar a resposta em {data|result|response|payload: {...}}
    for k in ("data", "result", "results", "response", "payload"):
        cand = payload.get(k)
        if isinstance(cand, dict) and isinstance(cand.get("hits"), dict):
            root = cand
            break

    hits = get_by_path(root, "hits.hits")
    if not isinstance(hits, list):
        return []

    out: List[dict] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        src = h.get("_source") if isinstance(h.get("_source"), dict) else {}
        lid = src.get("id") or h.get("_id") or h.get("id")
        if lid is None:
            continue
        lid = str(lid)

        # preço: prefere totalCost (aluguel + cond + iptu) se existir; fallback para rent/salePrice
        price = parse_brl(src.get("totalCost")) or parse_brl(src.get("rent")) or parse_brl(src.get("salePrice"))
        if price is None:
            price = _min_price_from_any(src)

        area = _as_float(src.get("area"))
        bedrooms = _as_int(src.get("bedrooms"))
        bathrooms = _as_int(src.get("bathrooms"))
        parking = _as_int(src.get("parkingSpaces"))

        # endereço (nem sempre vem completo; ao menos rua/bairro/cidade)
        addr_parts = []
        street = src.get("address")
        neigh = src.get("neighbourhood") or src.get("neighborhood")
        city = src.get("city")
        state_name = src.get("state") or src.get("stateAcronym") or src.get("uf")
        if isinstance(street, str) and street.strip():
            addr_parts.append(street.strip())
        if isinstance(neigh, str) and neigh.strip():
            addr_parts.append(neigh.strip())
        if isinstance(city, str) and city.strip():
            addr_parts.append(city.strip())
        if isinstance(state_name, str) and state_name.strip():
            addr_parts.append(state_name.strip())
        addr = ", ".join(addr_parts) if addr_parts else None
        if not state_name:
            state_name = _infer_state_code_from_text(street, neigh, city, addr)

        # url: fallback padrão
        url = f"https://www.quintoandar.com.br/imovel/{lid}"

        lat = lon = None
        if coords_map and lid in coords_map:
            lat, lon = coords_map[lid]

        out.append({
            "schema_version": STD_SCHEMA_VERSION,
            "platform": "quinto_andar",
            "listing_id": lid,
            "url": url,
            "lat": lat,
            "lon": lon,
            "price_brl": price,
            "area_m2": area,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "parking": parking,
            "address": addr,
            "city": city,
            "state": state_name,
        })
    return out

def parse_quintoandar_payload_to_std(payload: Any, coords_map: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]] = None) -> List[dict]:
    """Parseia payloads diversos do QuintoAndar (Next.js e respostas de API) para o schema padrão."""
    if not isinstance(payload, dict):
        return []

    # (A) Endpoint ES-like: /house-listing-search/v2/search/list
    # Detecta por `hits.hits[*]._source` contendo campos de listagem (totalCost/rent/area/etc).
    try:
        hh = get_by_path(payload, "hits.hits")
        if isinstance(hh, list) and hh:
            for _h in hh[:10]:
                if not isinstance(_h, dict):
                    continue
                _s = _h.get("_source") if isinstance(_h.get("_source"), dict) else {}
                if any(k in _s for k in ("totalCost", "rent", "salePrice", "area", "bedrooms", "bathrooms")):
                    return _qa_parse_quintoandar_search_list_payload(payload, coords_map=coords_map)
    except Exception:
        pass

    # Next.js wrapper
    state = get_by_path(payload, "props.pageProps.initialState") or get_by_path(payload, "pageProps.initialState")
    if not isinstance(state, dict):
        # alguns endpoints devolvem o state no topo, outros em chaves como "data"/"result"
        for p in ("data", "result", "results", "response", "payload"):
            cand = payload.get(p)
            if isinstance(cand, dict):
                # se parecer conter houses/search, use
                if ("houses" in cand) or ("search" in cand) or ("visibleHouses" in cand):
                    state = cand
                    break
        if not isinstance(state, dict):
            state = payload

    return parse_quintoandar_state_to_std(state, coords_map=coords_map)

def parse_quintoandar_nextjs_to_std(next_json: dict, coords_json: Optional[dict] = None) -> List[dict]:
    """
    QuintoAndar (Next.js):
    - ids em visibleHouses.pages
    - dados completos em houses[id]
    - lat/lon via replay coordinates_full (id->lat/lon)
    Saída padronizada por imóvel.
    """
    state = get_by_path(next_json, "props.pageProps.initialState") or get_by_path(next_json, "pageProps.initialState")
    if not isinstance(state, dict):
        return []
    coords_map = _quintoandar_coords_map(coords_json) if isinstance(coords_json, dict) else None
    return parse_quintoandar_state_to_std(state, coords_map=coords_map)


def parse_vivareal_glue_to_std(glue_json: dict) -> List[dict]:
    """
    VivaReal Glue API:
    - lista em search.result.listings
    - cada item pode ser {"listing": {...}} ou já o listing.
    """
    listings = get_by_path(glue_json, "search.result.listings")
    if not isinstance(listings, list):
        return []

    out = []
    for it in listings:
        listing = it.get("listing") if isinstance(it, dict) and isinstance(it.get("listing"), dict) else it
        if not isinstance(listing, dict):
            continue

        lid = listing.get("id") or listing.get("listingId") or listing.get("propertyId")
        # coords
        # Alguns listings retornam apenas lat/lon aproximados em address.point.approximateLat/approximateLon.
        # Tenta extrair na seguinte ordem:
        #   1) address.point.lat/lon
        #   2) address.geoLocation.location.lat/lon (quando existente)
        #   3) address.point.approximateLat/approximateLon
        #   4) address.point.latitude/longitude (nomes alternativos)
        lat_raw = (
            get_by_path(listing, "address.point.lat")
            or get_by_path(listing, "address.geoLocation.location.lat")
            or get_by_path(listing, "address.point.approximateLat")
            or get_by_path(listing, "address.point.latitude")
        )
        lon_raw = (
            get_by_path(listing, "address.point.lon")
            or get_by_path(listing, "address.geoLocation.location.lon")
            or get_by_path(listing, "address.point.approximateLon")
            or get_by_path(listing, "address.point.longitude")
        )
        lat = _as_float(lat_raw)
        lon = _as_float(lon_raw)
        # preço: menor entre pricingInfos (ou fallback varrendo)
        price = None
        pi = listing.get("pricingInfos")
        if isinstance(pi, list) and pi:
            cand = []
            for p in pi:
                if isinstance(p, dict):
                    pv = parse_brl(p.get("price")) or parse_brl(p.get("rentalTotalPrice")) or parse_brl(p.get("monthlyCondoFee"))
                    if pv is not None:
                        cand.append(pv)
            if cand:
                price = min(cand)
        if price is None:
            price = _min_price_from_any(listing)

        # área
        area = None
        ua = listing.get("usableAreas")
        if isinstance(ua, list) and ua:
            area = _as_float(ua[0])
        if area is None:
            area = _as_float(listing.get("usableArea") or listing.get("area"))
        # bedrooms / bathrooms / parking às vezes vêm como lista
        b_raw = listing.get("bedrooms")
        if isinstance(b_raw, list):
            b_raw = b_raw[0] if b_raw else None
        bedrooms = _as_int(b_raw)

        ba_raw = listing.get("bathrooms")
        if isinstance(ba_raw, list):
            ba_raw = ba_raw[0] if ba_raw else None
        bathrooms = _as_int(ba_raw)

        p_raw = listing.get("parkingSpaces") or listing.get("parking") or listing.get("garageSpaces")
        if isinstance(p_raw, list):
            p_raw = p_raw[0] if p_raw else None
        parking = _as_int(p_raw)

        # url
        # O link do anúncio frequentemente vem no wrapper do item (it["link"]["href"]),
        # não dentro do "listing". Tentamos wrapper primeiro e fazemos fallback para o listing.
        url = None
        if isinstance(it, dict):
            url = get_by_path(it, "link.href")
        if not url:
            url = get_by_path(listing, "link.href") or listing.get("url") or listing.get("href")
        if isinstance(url, str) and url.startswith("/"):
            url = "https://www.vivareal.com.br" + url

        # endereço (quando disponível)
        parts = []
        street = get_by_path(listing, "address.street") or get_by_path(listing, "address.streetName")
        number = get_by_path(listing, "address.streetNumber") or get_by_path(listing, "address.number")
        neigh = get_by_path(listing, "address.neighborhood")
        city = get_by_path(listing, "address.city")
        state = (
            get_by_path(listing, "address.state")
            or get_by_path(listing, "address.stateAcronym")
            or get_by_path(listing, "address.uf")
            or get_by_path(it, "address.state")
            or get_by_path(it, "address.stateAcronym")
            or get_by_path(it, "address.uf")
        )
        if not state:
            loc_id = (
                get_by_path(listing, "address.locationId")
                or get_by_path(it, "address.locationId")
                or ""
            )
            if isinstance(loc_id, str):
                low = loc_id.lower()
                if low.startswith("br>") and "sao paulo" in low:
                    state = "SP"

        for v in (street, number, neigh, city, state):
            if v is not None and str(v).strip():
                parts.append(str(v).strip())
        addr = ", ".join(parts) if parts else (neigh or city or None)


        out.append({
            "schema_version": STD_SCHEMA_VERSION,
            "platform": "vivareal",
            "listing_id": str(lid) if lid is not None else None,
            "url": url,
            "lat": lat,
            "lon": lon,
            "price_brl": price,
            "area_m2": area,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "parking": parking,
            "address": addr,
            "city": city,
            "state": state,
        })

    return out

def write_compiled_listings_json(items: List[dict], out_path: Path) -> None:
    ensure_dir(out_path.parent)
    # remove Nones excessivos e garante tipos simples
    cleaned = []
    for x in items:
        if not isinstance(x, dict):
            continue
        y = dict(x)
        cleaned.append(y)
    out_path.write_bytes(orjson.dumps(cleaned, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))


def _std_dedupe(items: List[dict]) -> List[dict]:
    """Dedup simples preservando ordem (platform + listing_id ou URL)."""
    seen = set()
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = (it.get("platform"), it.get("listing_id") or it.get("url"))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def compile_run_to_std(
    run_root: Path,
    config_path: str,
    mode: str,
    distance_lat: Optional[float] = None,
    distance_lon: Optional[float] = None,
) -> List[dict]:
    """Compila uma lista PADRONIZADA de imóveis a partir dos JSON de um run.

    Campos principais (quando disponíveis):
      - price_brl, area_m2, address, lat, lon, url
    Também calcula distance_m quando distance_lat/lon forem informados e houver coords.
    """
    items: List[dict] = []

    run_root = Path(run_root)

    # QuintoAndar: Next.js + payloads de API (quando existirem) reaproveitando respostas capturadas (sem novas requisições)
    qa_dir = run_root / "quinto_andar"
    if qa_dir.exists():
        qa_json_files = sorted(qa_dir.glob("*.json"))

        # 1) coords: varre JSONs do run para montar id -> (lat,lon) (replay ou responses de rede)
        coords_map = _qa_scan_quintoandar_coords_from_json_files(qa_json_files)

        # 2) payloads que podem conter LISTAGENS
        qa_parse_files: List[Path] = []
        qa_parse_files += sorted(qa_dir.glob("quintoandar_next_data_*.json"))
        qa_parse_files += sorted(qa_dir.glob("quintoandar_next_page_*.json"))
        qa_parse_files += sorted(qa_dir.glob("replay_quintoandar_search_*.json"))

        # 2.1) Se houver network_log, usa para pegar payloads do POST /search (mais completo do que __NEXT_DATA__)
        log_path = qa_dir / "network_log.csv"
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    rdr = csv.DictReader(f)
                    for row in rdr:
                        url = (row.get("url") or "")
                        saved = (row.get("saved_json") or "")
                        if not saved:
                            continue
                        if "/house-listing-search/" in url and "/search" in url and "/count" not in url and "/coordinates" not in url:
                            p = Path(saved)
                            if not p.exists():
                                # normalmente o CSV aponta para runs/run_x/...; resolve pelo nome do arquivo dentro do run atual
                                cand = qa_dir / Path(saved).name
                                if cand.exists():
                                    p = cand
                                else:
                                    cand2 = run_root / saved
                                    if cand2.exists():
                                        p = cand2
                            if p.exists():
                                qa_parse_files.append(p)
            except Exception:
                pass

        # 3) parseia e padroniza
        for jf in sorted(set(qa_parse_files)):
            try:
                payload = orjson.loads(jf.read_bytes())
            except Exception:
                continue
            try:
                items.extend(parse_quintoandar_payload_to_std(payload, coords_map=coords_map))
            except Exception:
                continue

        # 4) injeta coords quando faltarem (fallback)
        if coords_map:
            for it in items:
                if it.get("platform") != "quinto_andar":
                    continue
                if it.get("lat") is not None and it.get("lon") is not None:
                    continue
                rid = str(it.get("listing_id") or "")
                if rid in coords_map:
                    it["lat"], it["lon"] = coords_map[rid]

    # VivaReal: qualquer replay_* que seja Glue listings
    vr_dir = run_root / "vivareal"
    if vr_dir.exists():
        vr_files = sorted(vr_dir.glob("replay_vivareal_*_*.json")) + sorted(vr_dir.glob("replay_vivareal_*_p*.json"))
        # também inclui addrpoint/fallback (padronizamos pelo parser)
        vr_files += sorted(vr_dir.glob("replay_vivareal_*p*_*.json"))
        vr_files = sorted(set(vr_files))
        for jf in vr_files:
            try:
                glue_json = orjson.loads(jf.read_bytes())
                items.extend(parse_vivareal_glue_to_std(glue_json))
            except Exception:
                continue

    # distance_m
    if distance_lat is not None and distance_lon is not None:
        for it in items:
            lat = it.get("lat")
            lon = it.get("lon")
            if lat is None or lon is None:
                it["distance_m"] = None
                continue
            try:
                it["distance_m"] = haversine_m(float(distance_lat), float(distance_lon), float(lat), float(lon))
            except Exception:
                it["distance_m"] = None

    items = _std_dedupe(items)
    return items

def write_compiled_listings_csv(items: List[dict], out_path: Path) -> None:
    ensure_dir(out_path.parent)
    cols = [
        "schema_version",
        "platform",
        "listing_id",
        "url",
        "price_brl",
        "area_m2",
        "bedrooms",
        "bathrooms",
        "parking",
        "address",
        "lat",
        "lon",
        "distance_m",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for it in items:
            row = {k: it.get(k) for k in cols}
            w.writerow(row)

# ----------------------------
# Modelos
# ----------------------------

@dataclass
class Listing:
    canonical_id: str
    title: str
    address: str
    lat: float
    lon: float
    distance_m: float
    min_price: float
    area_m2: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # {source: {price, url, raw_id}}
    score: float = 0.0

    def best_url(self) -> str:
        # Preferir URL da fonte com menor preço; fallback qualquer
        best = None
        for src, info in self.sources.items():
            p = info.get("price")
            if p is None:
                continue
            if best is None or p < best[0]:
                best = (p, info.get("url", ""))
        if best and best[1]:
            return best[1]
        for info in self.sources.values():
            if info.get("url"):
                return info["url"]
        return ""


# ----------------------------
# Config
# ----------------------------

@dataclass
class PlatformConfig:
    name: str
    start_urls_rent: List[str]
    start_urls_buy: List[str]
    include_url_substrings: List[str]
    listing_path: str
    fields: Dict[str, str]
    prefer_headful: bool = False

    # Opcional: quando a plataforma NÃO aceita lat/lon direto, você pode fornecer uma
    # "busca por endereço" (ex.: rua/bairro/cidade) para chegar numa URL de listagem.
    # Pode vir do YAML (search_query) ou do CLI (--qa-query).
    search_query_rent: Optional[str] = None
    search_query_buy: Optional[str] = None
    search_query_override: Optional[str] = None

def load_config(path: str) -> Dict[str, PlatformConfig]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    platforms = {}
    for name, pcfg in cfg.get("platforms", {}).items():
        start_urls = pcfg.get("start_urls", {}) or {}

        # Opcional: search_query pode ser:
        # - string (vale para rent/buy)
        # - dict com chaves {rent: "...", buy: "..."}
        sq = pcfg.get("search_query")
        sq_rent = None
        sq_buy = None
        if isinstance(sq, dict):
            sq_rent = (sq.get("rent") or "").strip() or None
            sq_buy = (sq.get("buy") or "").strip() or None
        elif isinstance(sq, str):
            sq = sq.strip()
            if sq:
                sq_rent = sq_buy = sq

        platforms[name] = PlatformConfig(
            name=name,
            start_urls_rent=list(start_urls.get("rent", []) or []),
            start_urls_buy=list(start_urls.get("buy", []) or []),
            include_url_substrings=list(pcfg.get("include_url_substrings", []) or []),
            listing_path=str(pcfg.get("listing_path", "") or ""),
            fields=dict(pcfg.get("fields", {}) or {}),
            prefer_headful=bool(pcfg.get("prefer_headful", False)),
            search_query_rent=sq_rent,
            search_query_buy=sq_buy,
        )
    return platforms


# ----------------------------
# Captura de Network (XHR/Fetch/GraphQL/JSON)
# ----------------------------
def _tweak_url_remove_fields_params(url: str, drop_prefixes: tuple[str, ...]) -> str:
    """
    Remove parâmetros que começam com certos prefixos (ex: fields[0], fields%5B0%5D etc. já chegam decodificados em parse_qsl).
    """
    parts = urlsplit(url.strip())
    q = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        if any(k.startswith(pfx) for pfx in drop_prefixes):
            continue
        q.append((k, v))
    new_query = urlencode(q, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _tweak_vivareal_listings_url(url: str, size: int = 60, from_: int = 0) -> str:
    """Normaliza uma URL do Glue (/v2/listings) para retornar LISTINGS de fato.

    Observação importante:
    - durante a navegação, o VivaReal dispara chamadas "count-only" com:
        includeFields=facets,search(totalCount)  e size=1
      que NÃO retornam `search.result.listings`.
    - aqui promovemos essas chamadas para "listings", removendo includeFields restritivo
      e ajustando size/from para paginação por offset.
    """
    parts = urlsplit(url.strip())
    q = dict(parse_qsl(parts.query, keep_blank_values=True))

    # paginação por offset
    q["size"] = str(size)
    q["from"] = str(from_)

    # alguns requests carregam "page" (o Glue usa principalmente "from")
    if "page" in q:
        q["page"] = "1"

    # Se includeFields for restritivo (count-only), remove para obter payload completo
    inc = (q.get("includeFields") or "")
    if "search(totalCount)" in inc or inc.strip() in ("facets,search(totalCount)", "facets%2Csearch%28totalCount%29"):
        q.pop("includeFields", None)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment))





def _slug_to_title(slug: str) -> str:
    slug = (slug or "").strip().replace("-", " ")
    return " ".join([w.capitalize() for w in slug.split() if w])

def _br_state_code_to_name(code: str) -> str:
    code = (code or "").strip().lower()
    return {
        "sp": "São Paulo",
        "rj": "Rio de Janeiro",
        "mg": "Minas Gerais",
        "rs": "Rio Grande do Sul",
        "sc": "Santa Catarina",
        "pr": "Paraná",
        "ba": "Bahia",
        "pe": "Pernambuco",
        "ce": "Ceará",
        "df": "Distrito Federal",
        "go": "Goiás",
        "es": "Espírito Santo",
        "am": "Amazonas",
        "pa": "Pará",
        "pb": "Paraíba",
        "rn": "Rio Grande do Norte",
        "mt": "Mato Grosso",
        "ms": "Mato Grosso do Sul",
    }.get(code, code.upper())

def _infer_city_state_from_vivareal_url(page_url: str):
    """Tenta inferir (city_name, state_name) do caminho /aluguel/<uf>/<cidade>/"""
    try:
        parts = urlsplit(page_url)
        segs = [s for s in parts.path.split("/") if s]
        if len(segs) >= 3 and segs[0] in ("aluguel", "venda"):
            state = _br_state_code_to_name(segs[1])
            city = _slug_to_title(segs[2])
            return city, state
    except Exception:
        pass
    return "São Paulo", "São Paulo"


def _vivareal_fallback_glue_url(
    business: str,
    lat: float,
    lon: float,
    size: int = 72,
    from_: int = 0,
    city: str = "São Paulo",
    state: str = "São Paulo",
    ref: str = "/aluguel/sp/sao-paulo/",
    include_fields: str | None = None,
) -> str:
    """Monta uma URL do Glue quando não capturamos uma chamada rica via navegação.

    Dica prática:
    - O VivaReal costuma responder com `search.result.listings` quando NÃO limitamos includeFields
      (ou quando includeFields inclui `search` completo).
    - Por isso, por padrão, NÃO setamos includeFields aqui.
    """
    base = "https://glue-api.vivareal.com/v2/listings"
    # VivaReal aceita nomes completos (ex.: 'São Paulo') e `addressLocationId` em ASCII Title Case
    # (ex.: 'BR>Sao Paulo>NULL>Sao Paulo'). Forçar UF/slug aqui tende a causar HTTP 400.
    state_name = (state or "São Paulo")
    city_name = (city or "São Paulo")
    loc_state = _vr_norm_location_name(state_name)
    loc_city = _vr_norm_location_name(city_name)

    q = {
        "business": business,
        "parentId": "null",
        "listingType": "USED",
        "__zt": "mtc:deduplication2023",
        "addressCity": city_name,
        "addressZone": "",
        "addressStreet": "",
        "addressNeighborhood": "",
        "addressLocationId": f"BR>{loc_state}>NULL>{loc_city}",
        "addressState": state_name,
        "addressPointLat": str(lat),
        "addressPointLon": str(lon),
        "addressType": "city",
        "page": str(int(from_ / max(size, 1)) + 1),
        "size": str(size),
        "from": str(from_),
        "images": "webp",
        "categoryPage": "RESULT",
    }
    if include_fields:
        q["includeFields"] = include_fields
    return base + "?" + urlencode(list(q.items()))




def _qa_trim_location_only(url: str, mode: str) -> str:
    """Mantém apenas /{alugar|comprar}/imovel/<slug>, removendo filtros no path."""
    try:
        parts = urlsplit(url)
        segs = [s for s in (parts.path or "").split("/") if s]
        if len(segs) >= 3 and segs[0] in ("alugar", "comprar") and segs[1] == "imovel":
            segs = segs[:3]
            new_path = "/" + "/".join(segs)
            return urlunsplit((parts.scheme, parts.netloc, new_path, "", ""))
    except Exception:
        pass
    return url





# ----------------------------
# QuintoAndar: paginação por URL (coleta mais __NEXT_DATA__)
# ----------------------------

def _qa_strip_pagina_param(url: str) -> str:
    """Remove parâmetros `pagina`/`page` da query string."""
    try:
        parts = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in ("pagina", "page")]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment))
    except Exception:
        return url


def _qa_url_with_pagina(url: str, page_num: int, param: str = "pagina") -> str:
    """Adiciona/atualiza `pagina=<n>` na URL."""
    try:
        parts = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in ("pagina", "page")]
        q.append((param, str(int(page_num))))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment))
    except Exception:
        return url


async def _qa_dom_listing_ids_quintoandar(page) -> List[str]:
    """Coleta IDs visíveis no DOM do QuintoAndar (a href contém /imovel/<id>)."""
    try:
        ids = await page.evaluate(
            """() => {
                const out = new Set();
                const els = Array.from(document.querySelectorAll('a[href]'));
                for (const a of els) {
                    const h = (a.getAttribute('href') || '').trim();
                    const m = h.match(/\/imovel\/(\d+)/);
                    if (m && m[1]) out.add(m[1]);
                }
                return Array.from(out);
            }"""
        )
        if isinstance(ids, list):
            return [str(x) for x in ids if x is not None and str(x).strip()]
    except Exception:
        pass
    return []

async def _qa_try_dismiss_overlays(page) -> None:
    """Best-effort para fechar overlays que atrapalham clique (cookies, modais)."""
    candidates = [
        "button:has-text('Aceitar')",
        "button:has-text('Concordo')",
        "button:has-text('Entendi')",
        "button:has-text('Fechar')",
        "[aria-label='Fechar']",
        "[aria-label='Close']",
        "button[aria-label='Close']",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                try:
                    await loc.click(timeout=800)
                    await page.wait_for_timeout(200)
                except Exception:
                    pass
        except Exception:
            continue
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

async def _qa_load_more_quintoandar(page, clicks: int, wait_seconds: int = 10) -> int:
    """Clica no botão 'Ver mais' do QuintoAndar até `clicks` vezes ou até não haver novos itens.
    Retorna quantas vezes conseguiu efetivamente aumentar a lista.
    """
    if not clicks or clicks <= 0:
        return 0

    button_selectors = [
        "button:has-text('Ver mais')",
        "button:has-text('Mostrar mais')",
        "button:has-text('Carregar mais')",
        "a:has-text('Ver mais')",
        "[data-testid*='load']:has-text('Ver mais')",
    ]

    def per_click_wait_ms(ws: int) -> int:
        ms = int(ws * 1000) if isinstance(ws, int) else 3000
        return max(1200, min(ms, 6000))

    increased = 0
    prev_ids = set(await _qa_dom_listing_ids_quintoandar(page))

    for i in range(int(clicks)):
        await _qa_try_dismiss_overlays(page)

        btn = None
        for sel in button_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    btn = loc
                    break
            except Exception:
                continue

        if btn is None:
            try:
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(800)
            except Exception:
                pass
        else:
            try:
                await btn.scroll_into_view_if_needed(timeout=1500)
            except Exception:
                pass
            try:
                await btn.click(timeout=2000)
            except Exception:
                try:
                    await btn.evaluate("(el) => el.click()")
                except Exception:
                    pass

        try:
            await page.wait_for_timeout(per_click_wait_ms(wait_seconds))
        except Exception:
            pass

        try:
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(400)
        except Exception:
            pass

        grew = False
        for _ in range(20):
            cur_ids = set(await _qa_dom_listing_ids_quintoandar(page))
            if len(cur_ids) > len(prev_ids):
                prev_ids = cur_ids
                grew = True
                break
            await page.wait_for_timeout(250)

        if not grew:
            break

        increased += 1
        print(f"[quinto_andar] 'Ver mais' OK ({increased}/{clicks}) | ids_dom={len(prev_ids)}")

    return increased


def _vr_norm_location_name(s: str) -> str:
    """Normaliza nomes para `addressLocationId` do VivaReal (ex.: 'BR>Sao Paulo>NULL>Sao Paulo').
    - remove acentos
    - mantém espaços
    - usa Title Case
    """
    if not s:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"\s+", " ", t).strip()
    return t.title()



# ----------------------------
# VivaReal: endereço -> URL de rua/bairro (quando possível)
# ----------------------------
def _vr_slugify(text: str) -> str:
    """Slugify compatível com padrões do VivaReal (sem acentos, '-' como separador)."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^a-z0-9\s\-]", "", t)
    t = t.strip().replace(" ", "-")
    t = re.sub(r"-{2,}", "-", t).strip("-")
    return t

_VR_SP_ZONE_BY_NEIGHBORHOOD = {
    # mapeamento mínimo (pode ser expandido conforme necessário)
    "vila leopoldina": "zona-oeste",
    "pinheiros": "zona-oeste",
    "perdizes": "zona-oeste",
    "itaim bibi": "zona-sul",
    "moema": "zona-sul",
    "tatuape": "zona-leste",
    "santana": "zona-norte",
}

def _vr_parse_br_address(address: str) -> Dict[str, Optional[str]]:
    """Heurística simples para endereços pt-BR (rua, bairro, cidade, UF)."""
    out = {"street": None, "neighborhood": None, "city": None, "state_code": None}
    if not address:
        return out
    parts = [p.strip() for p in str(address).split(",") if p.strip()]
    if len(parts) >= 1:
        out["street"] = parts[0]
    if len(parts) >= 2:
        out["neighborhood"] = parts[1]
    # cidade/UF costuma vir como "São Paulo - SP" ou só "São Paulo"
    if len(parts) >= 3:
        city_state = parts[2]
        m = re.search(r"^(.*?)(?:\s*-\s*([A-Za-z]{2}))?$", city_state)
        if m:
            out["city"] = (m.group(1) or "").strip() or None
            out["state_code"] = (m.group(2) or "").strip().lower() or None
    return out

def _vr_build_street_url_from_address(address: str, mode: str = "rent", geo: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Tenta construir a URL de rua do VivaReal, no estilo:
    /aluguel/sp/sao-paulo/zona-oeste/vila-leopoldina/rua-guaipa

    - Se não conseguir inferir algum componente, retorna None (cai no fluxo atual).
    - `geo` (Nominatim) pode ajudar com city/state quando o texto é incompleto.
    """
    if not address:
        return None

    parsed = _vr_parse_br_address(address)
    street = parsed.get("street")
    neigh = parsed.get("neighborhood")
    city = parsed.get("city") or (geo.get("city") if isinstance(geo, dict) else None) or "São Paulo"
    state_code = parsed.get("state_code")

    # normaliza UF (preferir a do texto; senão tentar do geo['state'])
    if not state_code and isinstance(geo, dict):
        st = (geo.get("state") or "").strip().lower()
        # mapeia nomes comuns -> UF
        state_code = {
            "são paulo": "sp",
            "rio de janeiro": "rj",
            "minas gerais": "mg",
            "paraná": "pr",
            "rio grande do sul": "rs",
            "santa catarina": "sc",
            "bahia": "ba",
            "pernambuco": "pe",
            "ceará": "ce",
            "distrito federal": "df",
        }.get(st, None)

    # precisamos ao menos de street e state_code para formar URL estável
    if not street or not state_code:
        return None

    base = "https://www.vivareal.com.br"
    prefix = "aluguel" if mode == "rent" else "venda"

    city_slug = _vr_slugify(city or "")
    street_slug = _vr_slugify(street)

    if not city_slug or not street_slug:
        return None

    # Para São Paulo, o padrão mais comum inclui zona + bairro.
    zone_slug = None
    neigh_slug = _vr_slugify(neigh) if neigh else None
    if state_code == "sp" and city_slug == "sao-paulo" and neigh:
        zone_slug = _VR_SP_ZONE_BY_NEIGHBORHOOD.get(str(neigh).strip().lower())

    path_parts = [prefix, state_code, city_slug]
    if zone_slug and neigh_slug:
        path_parts.extend([zone_slug, neigh_slug, street_slug])
    elif neigh_slug:
        # fallback: sem zona (ainda costuma funcionar em alguns casos)
        path_parts.extend([neigh_slug, street_slug])
    else:
        path_parts.append(street_slug)

    return base + "/" + "/".join(path_parts).rstrip("/")

def _qa_slugify(text: str) -> str:
    """Slugifica texto pt-BR (remove acentos, normaliza espaços e pontuação)."""
    if text is None:
        return ""
    # normaliza acentos
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower().strip()
    # separadores comuns
    t = t.replace(" - ", ",")
    t = re.sub(r"\s+", " ", t)
    # remove caracteres fora do conjunto permitido
    t = re.sub(r"[^a-z0-9\s,]", "", t)
    t = t.strip().replace(" ", "-").replace(",", "-")
    t = re.sub(r"-{2,}", "-", t).strip("-")
    return t


def _qa_build_slug_url(query: str, mode: str) -> Optional[str]:
    """Fallback quando a busca por UI falha: monta uma URL /{alugar|comprar}/imovel/<slug>-brasil.

    Ex.: "Rua Guaipa, Vila Leopoldina, São Paulo - SP" ->
         https://www.quintoandar.com.br/alugar/imovel/rua-guaipa-vila-leopoldina-sao-paulo-sp-brasil
    """
    if not query:
        return None
    q = str(query).strip()
    if not q:
        return None
    # se já é URL, devolve como está
    if q.lower().startswith("http://") or q.lower().startswith("https://"):
        return q

    slug = _qa_slugify(q)
    if not slug:
        return None

    if not slug.endswith("brasil"):
        slug = slug + "-brasil"

    prefix = "alugar" if mode == "rent" else "comprar"
    return f"https://www.quintoandar.com.br/{prefix}/imovel/{slug}"

async def _qa_try_resolve_location_url(page, query: str, mode: str) -> Optional[str]:
    """Tenta usar a busca do QuintoAndar para chegar numa URL de listagem por bairro/rua.

    Observação: o QuintoAndar costuma aceitar melhor até nível de rua (não número).
    """
    if not query:
        return None

    q0 = str(query).strip()
    if q0.lower().startswith('http://') or q0.lower().startswith('https://'):
        return q0

    # Seletores "prováveis" de caixa de busca (mudam com o tempo).
    selectors = [
        'input[type="search"]',
        'input[placeholder*="Busque"]',
        'input[placeholder*="Buscar"]',
        'input[aria-label*="Busque"]',
        'input[aria-label*="Buscar"]',
        'input[name*="search"]',
    ]

    for sel in selectors:
        loc = page.locator(sel).first
        try:
            await loc.wait_for(state="visible", timeout=3000)
        except Exception:
            continue

        try:
            await loc.click()
            # Em alguns sites, fill exige "actionability"; usamos teclado para máxima compatibilidade.
            try:
                await loc.fill("")
            except Exception:
                pass
            await page.keyboard.type(query, delay=35)
            # Seleciona a primeira sugestão (se houver) e confirma
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")
        except Exception:
            continue

        # Aguarda a navegação para a listagem
        pattern = "**/alugar/imovel/**" if mode == "rent" else "**/comprar/imovel/**"
        try:
            await page.wait_for_url(pattern, timeout=20000)
        except Exception:
            # Mesmo se não mudar de URL, retornamos a URL atual para debug.
            pass

        return page.url

    return None

async def capture_platform(
    platform: PlatformConfig,
    mode: str,
    run_dir: Path,
    headless: bool,
    wait_seconds: int,
    max_pages: Optional[int] = None,
    # Busca por endereço (comum a todas as plataformas)
    search_address: Optional[str] = None,
    search_lat: Optional[float] = None,
    search_lon: Optional[float] = None,
    search_city: Optional[str] = None,
    search_state: Optional[str] = None,
) -> None:
    """
    Abre as start URLs e salva:
    - network_log.csv (todas XHR/Fetch)
    - *.json (respostas com content-type JSON)
    """
    ensure_dir(run_dir)
    log_path = run_dir / "network_log.csv"

    start_urls = platform.start_urls_rent if mode == "rent" else platform.start_urls_buy
    if not start_urls:
        print(f"[{platform.name}] Sem start_urls para mode={mode}. Pulando captura.")
        return

    rows = []
    captured_urls = []

    # QuintoAndar: captura de templates de busca (POST) para replay paginado.
    # - count (útil para entender filtros)
    # - search (normalmente retorna cards completos com preço/quartos/área/endereço)
    qa_count_url = None
    qa_count_body = None  # dict ou str
    qa_count_headers = None
    qa_search_templates: List[Dict[str, Any]] = []  # [{url, headers, body}]


    async with async_playwright() as p:
        # ---------------------------
        # Contexto do browser
        # ---------------------------
        # VivaReal: tem bloqueado headless via Cloudflare de forma intermitente.
        # No container usamos Xvfb, então podemos rodar "headful" sem abrir janela no host.
        effective_headless = headless
        if platform.name == "vivareal":
            effective_headless = False  # força headful dentro do container (Xvfb)

        # Persistência:
        # - para a maioria, isolamos por run (evita sujeira)
        # - para VivaReal, reusamos um perfil estável para manter cookies e reduzir desafios.
        if platform.name == "vivareal":
            user_data_dir = os.environ.get("VIVAREAL_PROFILE_DIR", "/app/.profiles/vivareal")
            os.makedirs(user_data_dir, exist_ok=True)
        else:
            user_data_dir = os.path.join(str(run_dir), "_user_data")

        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=effective_headless,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = await context.new_page()

        async def on_response(resp):
            try:
                nonlocal qa_count_url, qa_count_body, qa_count_headers
                req = resp.request
                rtype = req.resource_type  # "xhr", "fetch", "document", etc.
                if rtype not in ("xhr", "fetch", "document"):
                    return

                url = resp.url
                captured_urls.append(url)
                status = resp.status
                ct = (resp.headers or {}).get("content-type", "")

                # QuintoAndar: guarda o payload do POST /v2/search/count (normalmente contém filtros/viewport)
                if platform.name == "quinto_andar" and req.method.upper() == "POST" and "/house-listing-search/v2/search/count" in url:
                    qa_count_url = url
                    try:
                        qa_count_headers = dict(req.headers)
                    except Exception:
                        qa_count_headers = None
                    # tenta obter JSON do corpo (Playwright pode expor post_data_json)
                    body_json = None
                    try:
                        body_json = req.post_data_json
                    except Exception:
                        body_json = None
                    if body_json is None:
                        try:
                            pd = req.post_data or ""
                            body_json = json.loads(pd) if pd else None
                        except Exception:
                            body_json = None
                    qa_count_body = body_json if body_json is not None else (req.post_data or "")

                # QuintoAndar: captura template de busca (POST .../search) para replay paginado.
                # Importante: NÃO inclui /coordinates e NÃO inclui /count.
                if platform.name == "quinto_andar" and req.method.upper() == "POST" and "/house-listing-search/" in url and "/search" in url and "/coordinates" not in url and "/count" not in url:
                    try:
                        body_json = None
                        try:
                            body_json = req.post_data_json
                        except Exception:
                            body_json = None
                        if body_json is None:
                            try:
                                pd = req.post_data or ""
                                body_json = json.loads(pd) if pd else None
                            except Exception:
                                body_json = None
                        # guarda apenas se tiver corpo (evita noise)
                        if body_json is not None:
                            qa_search_templates.append({
                                "url": url,
                                "headers": dict(req.headers) if getattr(req, "headers", None) else {},
                                "body": body_json,
                            })
                    except Exception:
                        pass


                # Log básico de tudo
                row = {
                    "ts": time.time(),
                    "platform": platform.name,
                    "resource_type": rtype,
                    "method": req.method,
                    "status": status,
                    "content_type": ct,
                    "url": url,
                    "saved_json": "",
                }

                if rtype == "document":
                    # Diagnóstico: quando cair em 403/404/challenge, salva screenshot
                    if status in (403, 404) or "cdn-cgi" in url:
                        try:
                            fname = safe_filename(f"diagnostic_{int(time.time()*1000)}_{status}.png")
                            await page.screenshot(path=str(run_dir / fname), full_page=True)
                            row["saved_json"] = str(run_dir / fname)  # reutiliza coluna p/ apontar artefato
                        except Exception:
                            pass

                # Filtro por substring (se configurado)
                if platform.include_url_substrings:
                    if not any(s in url for s in platform.include_url_substrings):
                        rows.append(row)
                        return

                if "application/json" in ct or "json" in ct.lower():
                    # tenta salvar JSON mesmo se content-type não ajudar
                    try:
                        body = await resp.body()
                        if body:
                            data = orjson.loads(body)  # se não for JSON, vai dar exception e cai fora
                            h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
                            fname = safe_filename(f"{int(time.time()*1000)}_{h}.json")
                            fpath = run_dir / fname
                            with open(fpath, "wb") as f:
                                f.write(orjson.dumps(data))
                            row["saved_json"] = str(fpath)
                    except Exception:
                        pass


                rows.append(row)

            except Exception:
                # não derruba a execução
                return

        page.on("response", on_response)

        # Navega e espera a página disparar as chamadas de busca
        for u in start_urls:
            print(f"[{platform.name}] GOTO: {u}")
            await page.goto(u, wait_until="domcontentloaded")

            # QuintoAndar: se informado um "search_query" (rua/bairro/cidade), usa a busca do site
            # para chegar numa URL de listagem correta e mais estável que lat/lon direto.
            if platform.name == "quinto_andar":
                qa_query = platform.search_query_override or (
                    platform.search_query_rent if mode == "rent" else platform.search_query_buy
                )
                if qa_query:
                    target = None
                    q0 = str(qa_query).strip()
                    # Se o usuário já passou uma URL, use diretamente
                    if q0.lower().startswith("http://") or q0.lower().startswith("https://"):
                        target = _qa_trim_location_only(q0, mode)
                    else:
                        # 1) tenta via UI de busca (mais robusto quando o site muda o slug)
                        resolved = await _qa_try_resolve_location_url(page, qa_query, mode)
                        if resolved:
                            target = _qa_trim_location_only(resolved, mode)
                        else:
                            # 2) fallback determinístico: slugify do texto
                            built = _qa_build_slug_url(qa_query, mode)
                            if built:
                                target = _qa_trim_location_only(built, mode)

                    if target and target != page.url:
                        await page.goto(target, wait_until="domcontentloaded")
                    if target:
                        print(f"[{platform.name}] URL por busca/slug: {page.url}")

            print(f"[{platform.name}] Final URL: {page.url} | Title: {await page.title()}")

            # QuintoAndar (Next.js): além de XHR/Fetch, muita informação pode vir no __NEXT_DATA__
            # (server-side props), incluindo cards com preço/área/quartos e localização.
            if platform.name == "quinto_andar":
                try:
                    nd = await page.evaluate("() => window.__NEXT_DATA__")
                    if nd:
                        out_nd = run_dir / f"quintoandar_next_data_{int(time.time()*1000)}.json"
                        out_nd.write_bytes(orjson.dumps(nd))
                        print(f"[{platform.name}] salvou __NEXT_DATA__ -> {out_nd.name}")

                        # opcional: tenta endpoint _next/data (quando disponível)
                        build_id = None
                        try:
                            build_id = nd.get("buildId") if isinstance(nd, dict) else None
                        except Exception:
                            build_id = None
                        if build_id:
                            try:
                                parts = urlsplit(page.url)
                                pth = (parts.path or "").rstrip("/")
                                next_url = urlunsplit((parts.scheme, parts.netloc, f"/_next/data/{build_id}{pth}.json", "", ""))
                                r2 = await page.request.get(next_url)
                                if r2.ok and "json" in (r2.headers.get("content-type") or "").lower():
                                    nd2 = await r2.json()
                                    out_nd2 = run_dir / f"quintoandar_next_page_{int(time.time()*1000)}.json"
                                    out_nd2.write_bytes(orjson.dumps(nd2))
                                    print(f"[{platform.name}] salvou _next/data -> {out_nd2.name}")
                            except Exception:
                                pass
                except Exception:
                    pass


            # Scroll leve para disparar lazy-load/XHR
            try:
                for _ in range(8):
                    await page.mouse.wheel(0, 1400)
                    await page.wait_for_timeout(350)
            except Exception:
                pass

            # espera “coletar” requests
            await page.wait_for_timeout(wait_seconds * 1000)

            # QuintoAndar: a listagem é expandida via botão "Ver mais" (não por paginação via ?pagina=).
            if platform.name == "quinto_andar":
                try:
                    qa_pages = max_pages if isinstance(max_pages, int) and max_pages > 0 else int(os.environ.get("QA_MAX_PAGES", "1") or "1")
                    qa_pages = max(1, min(int(qa_pages), 50))  # safety cap
                except Exception:
                    qa_pages = 1

                # qa_pages inclui a primeira "tela"; então clicamos qa_pages-1 vezes
                if qa_pages > 1:
                    print(f"[quinto_andar] expandindo listagem via 'Ver mais' até {qa_pages} páginas (cliques={qa_pages-1})...")
                    try:
                        await _qa_load_more_quintoandar(page, clicks=qa_pages - 1, wait_seconds=wait_seconds)
                    except Exception:
                        pass
            if platform.name == "vivareal":
                # força a página a carregar mais conteúdo e disparar requests reais
                for _ in range(6):
                    await page.mouse.wheel(0, 1200)
                    await page.wait_for_timeout(1200)

        
        # ---------------------------
        # Replay automático (enriquecimento)
        # ---------------------------
        async def replay_and_save(url: str, tag: str) -> bool:
            """Faz GET no endpoint e salva JSON.

            Para VivaReal, a navegação frequentemente captura chamadas "count-only" (sem `search.result.listings`).
            Neste caso, salvamos o JSON para debug, mas retornamos False para acionar o fallback/promote.
            """
            try:
                r = await page.request.get(
                    url,
                    headers=(VIVAREAL_GLUE_HEADERS if "glue-api.vivareal.com" in url else None),
                )
                if not r.ok:
                    try:
                        body_txt = await r.text()
                    except Exception:
                        body_txt = ""
                    snippet = body_txt[:400].replace("\n", " ")
                    print(f"[{platform.name}] replay {tag} falhou: HTTP {r.status} {url[:140]} | body={snippet}")
                    return False

                ct = (r.headers.get("content-type") or "").lower()
                if "json" not in ct:
                    print(f"[{platform.name}] replay {tag} não é JSON: {ct} {url[:140]}")
                    return False

                data = await r.json()
                out = run_dir / f"replay_{tag}_{int(time.time()*1000)}.json"
                out.write_bytes(orjson.dumps(data))

                # validação leve: se for VivaReal, queremos de fato `search.result.listings`
                if platform.name == "vivareal":
                    lst = get_by_path(data, platform.listing_path or "search.result.listings") or []
                    n = len(lst) if isinstance(lst, list) else 0
                    print(f"[{platform.name}] replay {tag} OK -> {out.name} | listings={n}")
                    return n > 0

                print(f"[{platform.name}] replay {tag} OK -> {out.name}")
                return True

            except Exception as e:
                print(f"[{platform.name}] replay {tag} erro: {e}")
                return False

        # VivaReal: tenta pegar a chamada glue-api e “abrir” o payload (size maior + paginação por offset 'from')
        if platform.name == "vivareal":
            glue = None
            for u in reversed(captured_urls):
                if "glue-api.vivareal.com/v2/listings" in u:
                    glue = u
                    break

            glue_ok_any = False

            # Se temos um endereço (geocodificado), prioriza sempre uma busca por ponto (Glue API) ancorada nesse endereço,
            # independentemente do que foi capturado durante a navegação.
            if os.environ.get("VIVAREAL_ENABLE_ADDRPOINT", "0") == "1" and (search_lat is not None) and (search_lon is not None):
                try:
                    city2, state2 = (search_city or "São Paulo"), (search_state or "São Paulo")
                    ref2 = page.url.replace("https://www.vivareal.com.br", "")
                    if not ref2.startswith("/"):
                        ref2 = "/" + ref2
                    for i in range(VIVAREAL_PAGES_DEFAULT):
                        url_i = _vivareal_fallback_glue_url(
                            business="RENTAL" if mode == "rent" else "SALE",
                            lat=float(search_lat),
                            lon=float(search_lon),
                            size=72,
                            from_=i * 72,
                            city=city2,
                            state=state2,
                            ref=ref2,
                        )
                        ok = await replay_and_save(url_i, f"vivareal_addrpoint_p{i+1}")
                        glue_ok_any = glue_ok_any or ok
                except Exception:
                    pass

            if glue:
                # IMPORTANTE: parentId pode vir "null" na query e ainda assim o endpoint retorna listings.
                for i in range(VIVAREAL_PAGES_DEFAULT):
                    enriched_i = _tweak_vivareal_listings_url(glue, size=80, from_=i * 80)
                    ok = await replay_and_save(enriched_i, f"vivareal_glue_listings_p{i+1}")
                    glue_ok_any = glue_ok_any or ok
        
            # Fallback: se não capturou glue na navegação, tenta montar uma URL por ponto/cidade
            if (not glue_ok_any) and os.environ.get("VIVAREAL_ENABLE_CITYPOINT", "0") == "1":
                print(f"[{platform.name}] glue não capturado (ou falhou). Tentando fallback por ponto/cidade...")
                city, state = _infer_city_state_from_vivareal_url(page.url)
                # se recebemos um endereço, usamos o geocode (lat/lon e, quando possível, city/state)
                if search_city:
                    city = search_city
                if search_state:
                    state = search_state
                fallback_lat = search_lat if search_lat is not None else -23.5615
                fallback_lon = search_lon if search_lon is not None else -46.6559
                ref = page.url.replace("https://www.vivareal.com.br", "")
                if not ref.startswith("/"):
                    ref = "/" + ref
                for i in range(VIVAREAL_PAGES_DEFAULT):
                    fallback_url_i = _vivareal_fallback_glue_url(
                        business="RENTAL" if mode == "rent" else "SALE",
                        lat=fallback_lat,
                        lon=fallback_lon,
                        size=72,
                        from_=i * 72,
                        city=city,
                        state=state,
                        ref=ref,
                    )
                    ok = await replay_and_save(fallback_url_i, f"vivareal_fallback_citypoint_p{i+1}")
                    glue_ok_any = glue_ok_any or ok

        # QuintoAndar: se capturamos um template POST de busca (/search), fazemos replay paginado.
        if platform.name == "quinto_andar" and qa_search_templates:
            # usa o último template (normalmente o mais completo, após scroll)
            tpl = qa_search_templates[-1]
            try:
                base_url = tpl["url"]
                base_headers = tpl.get("headers") or {}
                base_body = tpl.get("body") or {}
                async def replay_post(url: str, body: Any, tag: str) -> bool:
                    try:
                        r = await page.request.post(url, data=orjson.dumps(body), headers={**base_headers, "content-type": "application/json"})
                        if not r.ok:
                            try:
                                body_txt = await r.text()
                            except Exception:
                                body_txt = ""
                            snippet2 = body_txt[:400].replace("\n", " ")
                            print(f"[{platform.name}] replay {tag} falhou: HTTP {r.status} {url[:140]} | body={snippet2}")
                            return False
                        ct = (r.headers.get("content-type") or "").lower()
                        if "json" not in ct:
                            print(f"[{platform.name}] replay {tag} não é JSON: {ct} {url[:140]}")
                            return False
                        data = await r.json()
                        out = run_dir / f"replay_{tag}_{int(time.time()*1000)}.json"
                        out.write_bytes(orjson.dumps(data))
                        # tenta estimar tamanho da lista
                        n = 0
                        try:
                            cands = score_list_candidates(data)
                            if cands:
                                _, pth, n, _ = cands[0]
                                print(f"[{platform.name}] replay {tag} OK -> {out.name} | best_list={pth} n={n}")
                            else:
                                print(f"[{platform.name}] replay {tag} OK -> {out.name}")
                        except Exception:
                            print(f"[{platform.name}] replay {tag} OK -> {out.name}")
                        return True
                    except Exception as e:
                        print(f"[{platform.name}] replay {tag} erro: {e}")
                        return False

                # Quantidade de páginas do replay paginado do QuintoAndar.
                # Prioridade:
                #  1) --max-pages (CLI)
                #  2) env QA_SEARCH_PAGES
                #  3) default 4
                qa_pages = max_pages if isinstance(max_pages, int) and max_pages > 0 else int(os.environ.get("QA_SEARCH_PAGES", "4") or "4")
                qa_pages = max(1, min(int(qa_pages), 50))  # safety cap
                for i in range(qa_pages):
                    body_i = _qa_body_with_pagination(base_body, from_=i*60, size=60)
                    await replay_post(base_url, body_i, f"quintoandar_search_p{i+1}")
            except Exception:
                pass

# QuintoAndar: tenta pegar o search coordinates e remover limitações de fields[]
        if platform.name == "quinto_andar" and os.environ.get("QA_ENABLE_COORDINATES_REPLAY", "0") == "1":
            qa = None
            for u in reversed(captured_urls):
                if "/house-listing-search/v2/search/coordinates" in u:
                    qa = u
                    break
            if qa:
                enriched = _tweak_url_remove_fields_params(qa, drop_prefixes=("fields[", "fields%5B"))
                await replay_and_save(enriched, "quintoandar_coordinates_full")
        await context.close()

    # escreve o log
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ts","platform","resource_type","method","status","content_type","url","saved_json"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"[{platform.name}] Captura concluída. Log: {log_path}")


async def capture_all(
    config_path: str,
    mode: str,
    out_dir: str,
    headless: bool,
    wait_seconds: int,
    max_pages: Optional[int] = None,
    search_address: Optional[str] = None,
) -> Tuple[Path, Optional[Dict[str, Any]]]:
    platforms = load_config(config_path)

    # 1) Busca sempre por ENDEREÇO (quando informado).
    #    - QuintoAndar: usa UI/slug para chegar numa URL de listagem.
    #    - VivaReal: usa geocode (lat/lon do endereço) para puxar o Glue API por ponto.
    geo = None
    if search_address:
        # geocode é best-effort; mesmo se falhar, QA ainda tenta via slugify/URL.
        geo = geocode_address_nominatim(search_address)

        # QuintoAndar: busca por slug/endereço
        if "quinto_andar" in platforms:
            platforms["quinto_andar"].search_query_override = search_address

        # VivaReal: quando possível, navega direto para a URL de rua/bairro (mais consistente do que o fallback "CITY").
        if "vivareal" in platforms:
            vr_url = _vr_build_street_url_from_address(search_address, mode=mode, geo=geo)
            if vr_url:
                if mode == "rent":
                    platforms["vivareal"].start_urls_rent = [vr_url]
                else:
                    platforms["vivareal"].start_urls_buy = [vr_url]

    run_root = Path(out_dir) / "runs" / f"run_{int(time.time())}"
    ensure_dir(run_root)

    # Meta do run (ajuda no debug e evita dúvida sobre qual entrada foi usada)
    try:
        meta = {
            "ts": time.time(),
            "mode": mode,
            "config_path": config_path,
            "search_address": search_address,
            "geocode": geo,
        }
        (run_root / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # sequencial (menos risco de bloqueio e sem corrotinas penduradas)
    for p in platforms.values():
        pdir = run_root / p.name

        # Se a plataforma preferir headful, força headless=False mesmo que a flag --headless tenha sido usada
        effective_headless = headless and (not p.prefer_headful)

        await capture_platform(
            p,
            mode=mode,
            run_dir=pdir,
            headless=effective_headless,
            wait_seconds=wait_seconds,
            max_pages=max_pages,
            search_address=search_address,
            # IMPORTANTE: não usamos coordenadas para REQUISIÇÕES de busca; elas serão usadas apenas após a lista de imóveis.
            search_lat=None,
            search_lon=None,
            search_city=(geo.get("city") if isinstance(geo, dict) else None),
            search_state=(geo.get("state") if isinstance(geo, dict) else None),
        )

    return run_root, geo

# ----------------------------
# Extração + Normalização
# ----------------------------

def extract_listings_from_json(platform: PlatformConfig, json_obj: Any) -> List[Dict[str, Any]]:
    """
    Retorna a lista de itens brutos (dict) que representam imóveis.

    Se listing_path estiver vazio, tenta auto-detectar dentro do JSON
    (fallback autônomo) usando score_list_candidates().
    """
    # QuintoAndar (Next.js): a lista costuma vir embutida em payload SSR/Next:
    #  - __NEXT_DATA__: props.pageProps.initialState
    #  - _next/data:   pageProps.initialState
    #
    # Estrutura típica:
    #   initialState.search.visibleHouses.pages : dict{pageIndex:[ids...]} (ou lista)
    #   initialState.houses : dict{id->house}
    #
    # Aqui:
    # - Pegamos os ids em visibleHouses.pages (mantendo ordem por página).
    # - Montamos os itens completos lendo houses[id].
    # - Acrescentamos `address_full` e `url` para saída padronizada (preço/área/quartos/localização/URL).
    if platform.name == "quinto_andar" and isinstance(json_obj, dict):
        try:
            page_props: Dict[str, Any] = {}
            if "props" in json_obj:
                page_props = ((json_obj.get("props") or {}).get("pageProps") or {})
            elif "pageProps" in json_obj:
                page_props = (json_obj.get("pageProps") or {})

            st = (page_props.get("initialState") or {})
            houses = st.get("houses") or {}
            pages = (((st.get("search") or {}).get("visibleHouses") or {}).get("pages") or {})

            if isinstance(houses, dict) and houses:
                ordered_ids: List[str] = []

                # pages pode ser dict {'0':[...], '1':[...]} ou lista
                if isinstance(pages, dict):
                    def _k(x):
                        try:
                            return int(str(x))
                        except Exception:
                            return str(x)
                    for k in sorted(pages.keys(), key=_k):
                        v = pages.get(k)
                        if isinstance(v, list):
                            ordered_ids.extend([str(i) for i in v])
                elif isinstance(pages, list):
                    for v in pages:
                        if isinstance(v, list):
                            ordered_ids.extend([str(i) for i in v])
                        else:
                            ordered_ids.append(str(v))

                # fallback: todos os houses
                if not ordered_ids:
                    ordered_ids = [str(k) for k in houses.keys()]

                # de-dup preservando ordem
                seen: set = set()
                flat: List[str] = []
                for hid in ordered_ids:
                    hid = str(hid)
                    if hid in seen:
                        continue
                    seen.add(hid)
                    flat.append(hid)

                # inclui houses que não estavam em pages
                for k in houses.keys():
                    ks = str(k)
                    if ks not in seen:
                        flat.append(ks)
                        seen.add(ks)

                out: List[Dict[str, Any]] = []
                for hid in flat:
                    h = houses.get(hid)
                    if not isinstance(h, dict):
                        h = houses.get(str(hid))
                    if not isinstance(h, dict):
                        continue

                    it = deepcopy(h)
                    it["id"] = str(hid)

                    # URL pode não vir no payload — placeholder de detalhe do imóvel
                    it.setdefault("url", f"https://www.quintoandar.com.br/imovel/{hid}")

                    # localização: rua + bairro + região + cidade
                    try:
                        addr = it.get("address") or {}
                        street = None
                        city = None
                        if isinstance(addr, dict):
                            street = addr.get("address") or addr.get("street") or addr.get("address1")
                            city = addr.get("city")
                        else:
                            street = str(addr)

                        neigh = it.get("neighbourhood") or it.get("neighborhood")
                        region = it.get("regionName") or it.get("region")

                        parts: List[str] = []
                        for p in [street, neigh, region, city]:
                            if p is None:
                                continue
                            s = str(p).strip()
                            if not s:
                                continue
                            if s not in parts:
                                parts.append(s)

                        it["address_full"] = ", ".join(parts) if parts else (str(street or "")).strip()
                    except Exception:
                        it["address_full"] = str(get_by_path(it, "address.address") or "")

                    # chaves padronizadas (não substitui as originais; só facilita `fields`)
                    if it.get("area_m2") is None and it.get("area") is not None:
                        it["area_m2"] = it.get("area")
                    if it.get("parking") is None and it.get("parkingSpots") is not None:
                        it["parking"] = it.get("parkingSpots")
                    if it.get("price") is None and it.get("rentPrice") is not None:
                        it["price"] = it.get("rentPrice")

                    out.append(it)

                if out:
                    return out
        except Exception:
            pass

    # 1) Se tiver listing_path configurado, usa ele
    if platform.listing_path:
        items = get_by_path(json_obj, platform.listing_path)
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        return []

    # 2) Fallback autônomo: descobrir o caminho da lista dentro do JSON
    try:
        cands = score_list_candidates(json_obj)
        if not cands:
            return []
        _, best_path, _, _ = cands[0]
        items = get_by_path(json_obj, best_path)

        if not getattr(platform, "_printed_autopath", False):
            print(f"[{platform.name}] listing_path detectado automaticamente: {best_path}")
            platform._printed_autopath = True

        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    except Exception:
        pass

    return []


def normalize_listing(
    platform: PlatformConfig,
    item: Dict[str, Any],
    center_lat: float,
    center_lon: float,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Normaliza um item de um portal para campos comuns.
    Retorna (raw_id, normalized_dict) ou None.
    """
    f = platform.fields

    raw_id = get_by_path(item, f.get("id", "")) or ""
    title = get_by_path(item, f.get("title", "")) or ""
    address = get_by_path(item, f.get("address", "")) or ""
    lat = get_by_path(item, f.get("lat", ""))
    lon = get_by_path(item, f.get("lon", ""))

    # Fallbacks por plataforma (quando o YAML não acompanha o schema real do payload)
    if platform.name == "vivareal":
        # Glue: coords costumam vir em address.point.* (em alguns payloads é approximateLat/approximateLon)
        if lat is None:
            lat = (
                get_by_path(item, "address.point.lat")
                or get_by_path(item, "address.point.approximateLat")
                or get_by_path(item, "address.geoLocation.location.lat")
            )
        if lon is None:
            lon = (
                get_by_path(item, "address.point.lon")
                or get_by_path(item, "address.point.approximateLon")
                or get_by_path(item, "address.geoLocation.location.lon")
            )
    url = get_by_path(item, f.get("url", "")) or ""

    # URLs relativas -> absolutas (quando conhecido)
    if isinstance(url, str) and url.startswith("/"):
        if platform.name == "vivareal":
            url = "https://www.vivareal.com.br" + url

    price_raw = get_by_path(item, f.get("price", ""))

    if platform.name == "vivareal" and price_raw in (None, "", 0):
        # Glue: geralmente vem como pricingInfos (lista)
        price_raw = item.get("pricingInfos") or get_by_path(item, "pricingInfos") or get_by_path(item, "pricingInfo") or price_raw
    price: Optional[float] = None
    # Suporta: número/string direta OU lista (ex: VivaReal pricingInfos) — usa o menor preço disponível.
    if isinstance(price_raw, list):
        vals: List[float] = []
        for el in price_raw:
            if el is None:
                continue
            if isinstance(el, (int, float, str)):
                v = parse_brl(el)
                if v is not None:
                    vals.append(v)
                continue
            if isinstance(el, dict):
                if "price" in el:
                    v = parse_brl(el.get("price"))
                    if v is not None:
                        vals.append(v)
                ri = el.get("rentalInfo")
                if isinstance(ri, dict) and ri.get("monthlyRentalTotalPrice") is not None:
                    v = parse_brl(ri.get("monthlyRentalTotalPrice"))
                    if v is not None:
                        vals.append(v)
        if vals:
            price = min(vals)
    else:
        price = parse_brl(price_raw)

    if lat is None or lon is None or price is None:
        return None

    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return None

    dist = haversine_m(center_lat, center_lon, lat, lon)

    def to_int(v):
        try:
            if v is None:
                return None
            return int(v)
        except Exception:
            return None

    def to_float(v):
        try:
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    area = to_float(get_by_path(item, f.get("area_m2", "")))
    bedrooms = to_int(get_by_path(item, f.get("bedrooms", "")))
    bathrooms = to_int(get_by_path(item, f.get("bathrooms", "")))
    parking = to_int(get_by_path(item, f.get("parking", "")))

    norm = {
        "raw_id": str(raw_id),
        "title": str(title),
        "address": str(address),
        "lat": lat,
        "lon": lon,
        "distance_m": dist,
        "price": price,
        "area_m2": area,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "parking": parking,
        "url": str(url),
    }
    return str(raw_id), norm


def canonicalize_key(lat: float, lon: float, bedrooms: Optional[int], area_m2: Optional[float]) -> str:
    """
    Chave para dedupe: arredonda coords + discretiza área + quartos.
    """
    lat_r = round(lat, 4)   # ~11m
    lon_r = round(lon, 4)
    b = bedrooms or 0
    a = int((area_m2 or 0) // 5) * 5  # bucket de 5m²
    return f"{lat_r}_{lon_r}_b{b}_a{a}"


def merge_candidates(cands: List[Listing]) -> Listing:
    """
    Mescla listings (mesmo imóvel) combinando fontes e pegando o menor preço global.
    """
    base = cands[0]
    for other in cands[1:]:
        # título/endereço: mantém o mais informativo
        if len(other.title) > len(base.title):
            base.title = other.title
        if len(other.address) > len(base.address):
            base.address = other.address

        # fontes
        for src, info in other.sources.items():
            if src not in base.sources:
                base.sources[src] = info
            else:
                # se já existe, mantém menor preço daquela fonte
                p_old = base.sources[src].get("price")
                p_new = info.get("price")
                if p_old is None or (p_new is not None and p_new < p_old):
                    base.sources[src] = info

        # menor preço global
        base.min_price = min(base.min_price, other.min_price)

        # atributos: mantém o que existir
        base.area_m2 = base.area_m2 or other.area_m2
        base.bedrooms = base.bedrooms or other.bedrooms
        base.bathrooms = base.bathrooms or other.bathrooms
        base.parking = base.parking or other.parking

    return base


def fuzzy_dedupe_refine(group: List[Listing], max_dist_m: float = 35.0, min_addr_sim: int = 80) -> List[Listing]:
    """
    Refinamento: dentro do mesmo bucket, separa imóveis diferentes via distância + similaridade de endereço.
    """
    out: List[Listing] = []
    for cand in group:
        placed = False
        for i, keep in enumerate(out):
            d = haversine_m(cand.lat, cand.lon, keep.lat, keep.lon)
            sim = fuzz.token_set_ratio((cand.address or ""), (keep.address or ""))
            if d <= max_dist_m and sim >= min_addr_sim:
                out[i] = merge_candidates([keep, cand])
                placed = True
                break
        if not placed:
            out.append(cand)
    return out


def score_listings(listings: List[Listing], w_price: float, w_dist: float, max_radius_m: float) -> None:
    """
    Nota baseada em preço (quanto menor melhor) + distância (quanto menor melhor).
    Normaliza em [0,1] e converte para score em [0,100].
    """
    if not listings:
        return

    prices = [l.min_price for l in listings if l.min_price is not None]
    pmin, pmax = (min(prices), max(prices)) if prices else (0.0, 0.0)

    def norm_price(p: float) -> float:
        if pmax <= pmin:
            return 1.0
        return 1.0 - (p - pmin) / (pmax - pmin)

    def norm_dist(d: float) -> float:
        # usa max_radius_m como normalizador
        if max_radius_m <= 0:
            return 1.0
        x = max(0.0, min(1.0, 1.0 - (d / max_radius_m)))
        return x

    # normaliza pesos
    s = w_price + w_dist
    w_price_n = w_price / s if s > 0 else 0.5
    w_dist_n = w_dist / s if s > 0 else 0.5

    for l in listings:
        ps = norm_price(l.min_price)
        ds = norm_dist(l.distance_m)
        l.score = 100.0 * (w_price_n * ps + w_dist_n * ds)


# -----------------------------
# QuintoAndar: enriquecimento por página do imóvel
# -----------------------------

_QA_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

def _strip_html(s: str) -> str:
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _qa_extract_next_data_from_html(html_text: str) -> Optional[dict]:
    """Extrai e parseia o JSON do script __NEXT_DATA__ da página do QuintoAndar.

    Retorna um dict (JSON) ou None.
    """
    if not isinstance(html_text, str) or not html_text:
        return None
    # padrão mais comum: <script id="__NEXT_DATA__" type="application/json">...</script>
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(?P<json>[\s\S]*?)</script>',
        html_text,
        flags=re.I,
    )
    if not m:
        return None
    raw = (m.group("json") or "").strip()
    if not raw:
        return None
    # o conteúdo pode vir com entidades HTML
    raw = _html.unescape(raw)
    try:
        return json.loads(raw)
    except Exception:
        # alguns casos têm escapes/bytes estranhos; tenta limpar NUL e reparsear
        try:
            raw2 = raw.replace("\u0000", "")
            return json.loads(raw2)
        except Exception:
            return None


def _qa_find_latlon_in_obj(obj: Any) -> Optional[Tuple[float, float]]:
    """Procura recursivamente um par (lat, lon/lng) dentro de um objeto JSON.

    Heurística:
      - procura por chaves: lat/lng, lat/lon, latitude/longitude
      - valida ranges: lat [-90,90], lon [-180,180]
    """
    def _to_f(v):
        try:
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                v2 = v.strip().replace(",", ".")
                return float(v2)
        except Exception:
            return None
        return None

    def _valid(lat, lon):
        return lat is not None and lon is not None and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0

    # BFS para achar o primeiro par plausível
    stack = [obj]
    seen = set()
    while stack:
        cur = stack.pop()
        cid = id(cur)
        if cid in seen:
            continue
        seen.add(cid)

        if isinstance(cur, dict):
            # pares possíveis no mesmo nível
            cand_pairs = [
                ("lat", "lng"),
                ("lat", "lon"),
                ("latitude", "longitude"),
                ("latitude", "lng"),
            ]
            lower_keys = {str(k).lower(): k for k in cur.keys()}
            for a, b in cand_pairs:
                if a in lower_keys and b in lower_keys:
                    lat = _to_f(cur[lower_keys[a]])
                    lon = _to_f(cur[lower_keys[b]])
                    if _valid(lat, lon):
                        return (lat, lon)

            # empilha valores para busca profunda
            for v in cur.values():
                if isinstance(v, (dict, list, tuple)):
                    stack.append(v)

        elif isinstance(cur, (list, tuple)):
            for v in cur:
                if isinstance(v, (dict, list, tuple)):
                    stack.append(v)

    return None


def _qa_detail_url(listing_id: str, mode: str) -> str:
    action = "alugar" if mode == "rent" else "comprar"
    return f"https://www.quintoandar.com.br/imovel/{listing_id}/{action}"

def _qa_parse_details_from_text(txt: str, mode: str) -> Dict[str, Any]:
    # Preço: para aluguel prioriza "Aluguel R$"; para compra prioriza "Venda R$" / "Preço"
    price = None
    if mode == "rent":
        m = re.search(r"Aluguel\s*R\$\s*([0-9\.\,]+)", txt, flags=re.I)
        if m:
            price = parse_brl(m.group(1))
    else:
        m = re.search(r"(Venda|Preço)\s*(de\s*)?R\$\s*([0-9\.\,]+)", txt, flags=re.I)
        if m:
            price = parse_brl(m.group(3))
    # fallback genérico: primeiro R$ que pareça preço
    if price is None:
        m = re.search(r"R\$\s*([0-9\.\,]+)", txt)
        if m:
            price = parse_brl(m.group(1))

    # métricas
    area_m2 = None
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*m²", txt, flags=re.I)
    if m:
        try:
            area_m2 = float(m.group(1).replace(".", "").replace(",", "."))
        except Exception:
            area_m2 = None

    bedrooms = None
    m = re.search(r"(\d+)\s*quartos?", txt, flags=re.I)
    if m:
        bedrooms = int(m.group(1))

    bathrooms = None
    m = re.search(r"(\d+)\s*banheiros?", txt, flags=re.I)
    if m:
        bathrooms = int(m.group(1))

    parking = None
    m = re.search(r"(\d+)\s*vagas?", txt, flags=re.I)
    if m:
        parking = int(m.group(1))
    elif re.search(r"sem\s+vaga", txt, flags=re.I):
        parking = 0

    # endereço (best-effort): tenta capturar linha com bairro/cidade
    address = None
    # Exemplos comuns: "Pinheiros, São Paulo" ou "Vila Mariana, São Paulo"
    m = re.search(r"([A-Za-zÀ-ÿ\-\s]{3,}),\s*(São\s*Paulo)", txt)
    if m:
        address = f"{m.group(1).strip()}, {m.group(2).strip()}"
    # tenta Rua/Avenida
    if not address:
        m = re.search(r"\b(Rua|Avenida|Alameda|Travessa|Estrada)\s+([A-Za-zÀ-ÿ0-9'’\-\s\.]{4,60})", txt)
        if m:
            address = f"{m.group(1)} {m.group(2).strip()}"

    return {
        "price": price,
        "area_m2": area_m2,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "parking": parking,
        "address": address,
    }


# ----------------------------
# QuintoAndar (detalhe): extrair lat/lon do HTML (__NEXT_DATA__)
# ----------------------------

_NEXT_DATA_RE = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.I | re.S)

# def _qa_extract_next_data_json(html_text: str) -> Optional[Dict[str, Any]]:
#     """Extrai e parseia o JSON do script __NEXT_DATA__ (Next.js)."""
#     if not html_text:
#         return None
#     m = _NEXT_DATA_RE.search(html_text)
#     if not m:
#         return None
#     blob = (m.group(1) or '').strip()
#     if not blob:
#         return None
#     try:
#         return json.loads(blob)
#     except Exception:
#         try:
#             return orjson.loads(blob.encode('utf-8', errors='ignore'))
#         except Exception:
#             return None

# def _qa_find_first_latlon(obj: Any) -> Optional[Tuple[float, float]]:
#     """Procura recursivamente por um par (lat, lon/lng) plausível em um objeto JSON."""
#     stack = [obj]
#     while stack:
#         cur = stack.pop()
#         if isinstance(cur, dict):
#             # casos comuns
#             if 'lat' in cur and ('lon' in cur or 'lng' in cur or 'long' in cur):
#                 lat = cur.get('lat')
#                 lon = cur.get('lon') if 'lon' in cur else (cur.get('lng') if 'lng' in cur else cur.get('long'))
#                 try:
#                     latf = float(lat)
#                     lonf = float(lon)
#                     if -90.0 <= latf <= 90.0 and -180.0 <= lonf <= 180.0:
#                         # evita (0,0)
#                         if abs(latf) > 1e-6 or abs(lonf) > 1e-6:
#                             return latf, lonf
#                 except Exception:
#                     pass

#             if 'latitude' in cur and 'longitude' in cur:
#                 try:
#                     latf = float(cur.get('latitude'))
#                     lonf = float(cur.get('longitude'))
#                     if -90.0 <= latf <= 90.0 and -180.0 <= lonf <= 180.0:
#                         if abs(latf) > 1e-6 or abs(lonf) > 1e-6:
#                             return latf, lonf
#                 except Exception:
#                     pass

#             # empilha valores
#             for v in cur.values():
#                 if isinstance(v, (dict, list)):
#                     stack.append(v)
#         elif isinstance(cur, list):
#             for v in cur:
#                 if isinstance(v, (dict, list)):
#                     stack.append(v)
#     return None


def _qa_fetch_details_html(listing_id: str, mode: str, timeout_s: int = 20) -> Optional[Dict[str, Any]]:
    """Busca detalhes de um imóvel do QuintoAndar via HTML.

    Não usa coordenadas para requisições. As coordenadas (lat/lon) são extraídas do __NEXT_DATA__
    embutido no HTML, quando disponível.
    """
    url = _qa_detail_url(listing_id, mode)
    try:
        req = Request(
            url,
            headers={
                "User-Agent": _QA_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        )
        with urlopen(req, timeout=timeout_s) as resp:
            final_url = getattr(resp, "geturl", lambda: url)()
            raw = resp.read()

        html_text = raw.decode("utf-8", errors="ignore")
        txt = _strip_html(html_text)

        title = None
        m = re.search(r"<title>(.*?)</title>", html_text, flags=re.I | re.S)
        if m:
            title = _strip_html(m.group(1))

        det = _qa_parse_details_from_text(txt, mode)

        # tenta extrair lat/lon do __NEXT_DATA__
        try:
            nd = _qa_extract_next_data_from_html(html_text)
            if nd:
                latlon = _qa_find_latlon_in_obj(nd)
                if latlon:
                    det["lat"], det["lon"] = float(latlon[0]), float(latlon[1])
        except Exception:
            pass

        det["url"] = final_url
        det["title"] = title
        det["id"] = str(listing_id)
        return det
    except HTTPError:
        return None
    except URLError:
        return None
    except Exception:
        return None


def _qa_cache_load(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and isinstance(obj.get("items"), dict):
                return obj["items"]
            if isinstance(obj, dict):
                # compat: cache direto
                return obj
        except Exception:
            return {}
    return {}

def _qa_cache_save(path: Path, items: Dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps({"version": 1, "items": items}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def _process_quintoandar_platform(
    p: PlatformConfig,
    pdir: Path,
    json_files: List[Path],
    center_lat: float,
    center_lon: float,
    radius_m: float,
    mode: str,
    min_price: Optional[float],
    max_price: Optional[float],
    min_bedrooms: Optional[int],
    min_area_m2: Optional[float],
) -> List[Listing]:
    """Processa o QuintoAndar em 2 etapas:

    1) **Lista baseada em endereço**: extrai IDs + dados básicos dos payloads Next.js obtidos ao navegar pela URL do endereço.
    2) **Pós-processamento**: visita a página de cada anúncio (por ID) para extrair lat/lon e consolidar campos.

    Importante: **não usa as coordenadas do usuário para fazer requisições de busca**.
    As coordenadas (lat/lon) são usadas apenas para:
      - calcular distância até o ponto de referência informado pelo usuário
      - filtrar por raio
    """

    # 1) Coleta dos imóveis a partir dos payloads Next.js (listagem do endereço)
    houses_by_id: Dict[str, Dict[str, Any]] = {}

    def _is_next_payload(obj: Any) -> bool:
        if not isinstance(obj, dict):
            return False
        if "props" in obj and isinstance(obj.get("props"), dict):
            if "pageProps" in (obj.get("props") or {}):
                return True
        if "pageProps" in obj and isinstance(obj.get("pageProps"), dict):
            return True
        return False

    for jf in json_files:
        try:
            data = orjson.loads(jf.read_bytes())
        except Exception:
            continue
        if not _is_next_payload(data):
            continue

        # QuintoAndar: o payload Next.js contém:
        # - ids em visibleHouses.pages
        # - dados completos em houses[id]
        # Para manter a coleta baseada em ENDEREÇO (sem coordenadas), extraímos os cards pelo Next payload.
        try:
            parsed = parse_quintoandar_nextjs_to_std(data, coords_json=None)
        except Exception:
            parsed = []

        for std in parsed:
            try:
                rid = str(std.get("listing_id") or std.get("id") or "").strip()
            except Exception:
                rid = ""
            if not rid:
                continue

            # Converte para um "card" interno compatível com os pré-filtros abaixo
            it = {
                "id": rid,
                "url": std.get("url"),
                "address_full": std.get("address"),
                "area": std.get("area_m2"),
                "area_m2": std.get("area_m2"),
                "bedrooms": std.get("bedrooms"),
                "bathrooms": std.get("bathrooms"),
                "parking": std.get("parking"),
                "rentPrice": std.get("price_brl") if mode == "rent" else None,
                "salePrice": std.get("price_brl") if mode != "rent" else None,
                "price": std.get("price_brl"),
            }

            # preserva a primeira ocorrência para manter ordem; mas atualiza campos "vazios" se surgirem depois
            if rid not in houses_by_id:
                houses_by_id[rid] = it
            else:
                cur = houses_by_id[rid]
                for k in ("url", "address_full", "area", "area_m2", "bedrooms", "bathrooms", "parking", "rentPrice", "salePrice", "price"):
                    if (cur.get(k) in (None, "", 0)) and (it.get(k) not in (None, "", 0)):
                        cur[k] = it.get(k)

    if not houses_by_id:
        return []

    # 2) Pré-filtros (preço/quartos/área) usando dados do card (sem coordenadas)
    def _house_price(h: Dict[str, Any]) -> Optional[float]:
        v = None
        if mode == "rent":
            v = h.get("rentPrice") or h.get("price") or get_by_path(h, "pricingInfos.0.price")
        else:
            v = h.get("salePrice") or h.get("price") or get_by_path(h, "pricingInfos.0.price")
        return to_float(v)

    def _house_area(h: Dict[str, Any]) -> Optional[float]:
        return to_float(h.get("area_m2") if h.get("area_m2") is not None else h.get("area"))

    def _house_bedrooms(h: Dict[str, Any]) -> Optional[int]:
        try:
            v = h.get("bedrooms")
            if v is None:
                return None
            return int(float(v))
        except Exception:
            return None

    candidates: List[Tuple[str, Dict[str, Any], Optional[float]]] = []
    for rid, h in houses_by_id.items():
        p0 = _house_price(h)
        if min_price is not None and p0 is not None and p0 < min_price:
            continue
        if max_price is not None and p0 is not None and p0 > max_price:
            continue

        if min_bedrooms is not None:
            b0 = _house_bedrooms(h)
            if b0 is None or b0 < min_bedrooms:
                continue

        if min_area_m2 is not None:
            a0 = _house_area(h)
            if a0 is None or a0 < min_area_m2:
                continue

        candidates.append((rid, h, p0))

    if not candidates:
        return []

    # ordena por preço aproximado (quando houver) e mantém ordem estável
    candidates.sort(key=lambda x: (x[2] is None, x[2] if x[2] is not None else 0.0))


    # 3) Coordenadas já capturadas (sem novas requisições)
    #    O QuintoAndar costuma disparar uma chamada "coordinates" ao carregar a listagem.
    #    Reaproveitamos esse payload (se existir) para mapear id -> (lat,lon).
    coords_map = _qa_scan_quintoandar_coords_from_json_files(json_files)

    # 4) (Opcional) Enriquecimento por página do anúncio (para obter lat/lon quando não veio no payload de coordinates)
    #    Também não usa as coordenadas do usuário para fazer requisições; visita apenas a URL do anúncio.
    max_enrich = int(os.environ.get("QA_MAX_ENRICH", "250"))
    candidates = candidates[:max(1, max_enrich)]

    cache_path = pdir / "quintoandar_details_cache.json"
    cache: Dict[str, Any] = _qa_cache_load(cache_path)

    def _det_has_coords(d: Any) -> bool:
        if not isinstance(d, dict):
            return False
        return d.get("lat") is not None and d.get("lon") is not None

    # Só enriquece quem ainda não tem coords nem no coords_map nem no cache
    need = []
    for rid, _, _ in candidates:
        if rid in coords_map:
            continue
        d = cache.get(rid)
        if _det_has_coords(d):
            continue
        need.append(rid)

    if need:
        print(f"[quinto_andar] enriquecendo {len(need)} imóveis (sem coords no payload) — isso pode levar alguns segundos...")
        for rid in tqdm(need, desc="Enrich quinto_andar", leave=False):
            det = _qa_fetch_details_html(rid, mode)
            if det:
                cache[rid] = det
            time.sleep(0.12)
        _qa_cache_save(cache_path, cache)

    # 5) Pós-processamento: distância + filtros finais + normalização
    out: List[Listing] = []

    for rid, h, p0 in candidates:
        det = cache.get(rid)
        if not isinstance(det, dict):
            det = {}

        # coords: primeiro do cache/enriquecimento; depois do payload de coordinates
        lat = det.get("lat")
        lon = det.get("lon")
        if (lat is None or lon is None) and (rid in coords_map):
            lat, lon = coords_map[rid]

        if lat is None or lon is None:
            # sem coordenadas => não dá pra filtrar por raio
            continue

        try:
            latf = float(lat)
            lonf = float(lon)
        except Exception:
            continue

        dist = haversine_m(center_lat, center_lon, latf, lonf)
        if dist > radius_m:
            continue

        price = to_float(det.get("price"))
        if price is None:
            price = p0
        if price is None:
            continue

        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue

        area = to_float(det.get("area_m2"))
        if area is None:
            area = _house_area(h)

        bedrooms = det.get("bedrooms")
        if bedrooms is None:
            bedrooms = _house_bedrooms(h)

        bathrooms = det.get("bathrooms")
        if bathrooms is None:
            bathrooms = to_float(h.get("bathrooms"))

        parking = det.get("parking")
        if parking is None:
            parking = to_float(h.get("parking"))

        address = (det.get("address") or h.get("address_full") or "").strip()
        url = (det.get("url") or h.get("url") or f"https://www.quintoandar.com.br/imovel/{rid}").strip()
        title = (det.get("title") or "").strip()
        if not title:
            # fallback simples
            title = f"Imóvel {rid}"

        cid = canonicalize_key(latf, lonf, bedrooms, area)

        out.append(Listing(
            canonical_id=cid,
            title=title,
            address=address,
            lat=latf,
            lon=lonf,
            distance_m=float(dist),
            min_price=float(price),
            area_m2=area,
            bedrooms=bedrooms if bedrooms is None else int(bedrooms),
            bathrooms=bathrooms if bathrooms is None else int(bathrooms),
            parking=parking if parking is None else int(parking),
            sources={
                p.name: {
                    "price": float(price),
                    "url": url,
                    "raw_id": str(rid),
                }
            },
        ))

    return out


def aggregate_runs(
    config_path: str,
    runs_dir: str,
    center_lat: float,
    center_lon: float,
    radius_m: float,
    mode: str,
    min_price: Optional[float],
    max_price: Optional[float],
    filters: Dict[str, Optional[float]],
    w_price: float,
    w_dist: float,
) -> pd.DataFrame:
    """
    Lê JSON capturados, extrai listagens configuradas, deduplica, filtra e ranqueia.
    """
    platforms = load_config(config_path)
    runs_path = Path(runs_dir)
    if not runs_path.exists():
        raise FileNotFoundError(f"runs_dir não existe: {runs_dir}")

    all_listings: List[Listing] = []
    qa_coords_map: Dict[str, Tuple[float, float]] = {}

    for pname, p in platforms.items():
        pdir = runs_path / pname
        if not pdir.exists():
            continue
        json_files = list(pdir.glob("*.json"))
        if not json_files:
            continue

        # QuintoAndar: usa sempre o fluxo baseado em endereço -> detalhes (extrai lat/lon do HTML).
        if pname == "quinto_andar":
            bmin = filters.get("min_bedrooms")
            amin = filters.get("min_area_m2")
            qa_listings = _process_quintoandar_platform(
                p=p,
                pdir=pdir,
                json_files=json_files,
                center_lat=center_lat,
                center_lon=center_lon,
                radius_m=radius_m,
                mode=mode,
                min_price=min_price,
                max_price=max_price,
                min_bedrooms=bmin,
                min_area_m2=amin,
            )
            all_listings.extend(qa_listings)
            continue

        for jf in tqdm(json_files, desc=f"Parse {pname}"):

            try:
                data = orjson.loads(jf.read_bytes())
            except Exception:
                continue

            items = extract_listings_from_json(p, data)
            if not items:
                continue

            for item in items:
                # VivaReal: o Glue frequentemente retorna itens no formato {"listing": {...}}.
                # Para compatibilizar com fields no YAML (id, geoLocation..., pricingInfos...), "desembrulhamos".
                if pname == "vivareal" and isinstance(item, dict) and isinstance(item.get("listing"), dict):
                    # IMPORTANT: o Glue do VivaReal costuma trazer o link do anúncio no *wrapper* (item["link"]["href"]),
                    # enquanto o conteúdo do imóvel fica em item["listing"].
                    # Se "desembrulharmos" sem copiar esse link, perdemos a URL e a saída fica sem o campo.
                    listing = item["listing"]
                    try:
                        href = get_by_path(item, "link.href") or get_by_path(item, "link.href")
                    except Exception:
                        href = None
                    if isinstance(href, str) and href:
                        # padroniza para os formatos que o resto do pipeline já entende
                        if not isinstance(listing.get("link"), dict):
                            listing["link"] = {}
                        listing["link"]["href"] = href
                        listing.setdefault("url", href)
                    item = listing

                # QuintoAndar: injeta lat/lon a partir do replay de coordinates quando o payload do card não traz geolocalização.
                # Também replica para os paths esperados pelo platforms.yaml (address.geo.lat/lon, pricing.price, address.full).
                if pname == "quinto_andar" and qa_coords_map and isinstance(item, dict):
                    try:
                        hid = str(item.get("id") or item.get("_id") or "")
                        if hid in qa_coords_map:
                            lat, lon = qa_coords_map[hid]
                            # campos "flat" (úteis para outras rotas)
                            if item.get("lat") is None:
                                item["lat"] = lat
                            if item.get("lon") is None:
                                item["lon"] = lon

                            # campos aninhados conforme YAML atual
                            addr = item.get("address")
                            if not isinstance(addr, dict):
                                addr = {}
                                item["address"] = addr
                            geo = addr.get("geo")
                            if not isinstance(geo, dict):
                                geo = {}
                                addr["geo"] = geo
                            geo.setdefault("lat", lat)
                            geo.setdefault("lon", lon)

                            # address.full (se já houver address_full do parser, usa; senão tenta montar)
                            if not addr.get("full"):
                                if isinstance(item.get("address_full"), str) and item["address_full"].strip():
                                    addr["full"] = item["address_full"].strip()
                                else:
                                    # fallback simples
                                    parts = []
                                    if isinstance(addr.get("address"), str): parts.append(addr.get("address"))
                                    if isinstance(item.get("neighbourhood") or item.get("neighborhood"), str):
                                        parts.append(item.get("neighbourhood") or item.get("neighborhood"))
                                    if isinstance(item.get("regionName"), str): parts.append(item.get("regionName"))
                                    if isinstance(addr.get("city"), str): parts.append(addr.get("city"))
                                    addr["full"] = ", ".join([p for p in parts if p])

                            # pricing.price (para compatibilizar com YAML)
                            if not isinstance(item.get("pricing"), dict):
                                item["pricing"] = {}
                            if item["pricing"].get("price") is None:
                                # prioriza price já existente; fallback para rentPrice/salePrice
                                item["pricing"]["price"] = item.get("price") or item.get("rentPrice") or item.get("salePrice")
                    except Exception:
                        pass

                norm = normalize_listing(p, item, center_lat, center_lon)
                if not norm:
                    continue
                raw_id, d = norm

                # raio
                if d["distance_m"] > radius_m:
                    continue

                # filtros de preço
                if min_price is not None and d["price"] < min_price:
                    continue
                if max_price is not None and d["price"] > max_price:
                    continue

                # filtros adicionais
                # (bedrooms >= X, area_m2 >= X, etc)
                bmin = filters.get("min_bedrooms")
                if bmin is not None and (d["bedrooms"] is None or d["bedrooms"] < bmin):
                    continue
                amin = filters.get("min_area_m2")
                if amin is not None and (d["area_m2"] is None or d["area_m2"] < amin):
                    continue

                # cria listing (por enquanto 1 fonte)
                cid = canonicalize_key(d["lat"], d["lon"], d["bedrooms"], d["area_m2"])
                l = Listing(
                    canonical_id=cid,
                    title=d["title"],
                    address=d["address"],
                    lat=d["lat"],
                    lon=d["lon"],
                    distance_m=d["distance_m"],
                    min_price=d["price"],
                    area_m2=d["area_m2"],
                    bedrooms=d["bedrooms"],
                    bathrooms=d["bathrooms"],
                    parking=d["parking"],
                    sources={
                        pname: {"price": d["price"], "url": d["url"], "raw_id": raw_id}
                    },
                )
                all_listings.append(l)

    # Dedup por bucket
    buckets: Dict[str, List[Listing]] = {}
    for l in all_listings:
        buckets.setdefault(l.canonical_id, []).append(l)

    merged: List[Listing] = []
    for _, group in buckets.items():
        # refine fuzzy para separar imóveis colados por bucket
        refined = fuzzy_dedupe_refine(group)
        merged.extend(refined)

    # score
    score_listings(merged, w_price=w_price, w_dist=w_dist, max_radius_m=radius_m)

    # dataframe
    rows = []
    for l in merged:
        price_by_source = {src: info.get("price") for src, info in l.sources.items()}
        url_by_source = {src: info.get("url") for src, info in l.sources.items()}
        rows.append({
            "score": l.score,
            "distance_m": round(l.distance_m, 1),
            "min_price_brl": l.min_price,
            "title": l.title,
            "address": l.address,
            "lat": l.lat,
            "lon": l.lon,
            "area_m2": l.area_m2,
            "bedrooms": l.bedrooms,
            "bathrooms": l.bathrooms,
            "parking": l.parking,
            "sources": ",".join(sorted(l.sources.keys())),
            "price_by_source": price_by_source,
            "url_by_source": url_by_source,
            "best_url": l.best_url(),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["score", "min_price_brl", "distance_m"], ascending=[False, True, True]).reset_index(drop=True)
    return df


# ----------------------------
# CLI
# ----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Meta-buscador de imóveis via network scraping (XHR/Fetch/GraphQL/JSON) com Playwright.")
    sub = p.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="Captura XHR/Fetch e salva JSON + log por plataforma.")
    cap.add_argument("--config", required=True)
    cap.add_argument("--mode", choices=["rent", "buy"], required=True)
    cap.add_argument("--out-dir", default=".")
    cap.add_argument("--headless", action="store_true")
    cap.add_argument("--wait-seconds", type=int, default=12)
    cap.add_argument("--max-pages", type=int, default=None, help="Máx. de páginas para capturar por plataforma (quando aplicável; ex.: QuintoAndar via replay paginado).")
    cap.add_argument("--address", "--qa-query", dest="search_address", default=None, help="Endereço (texto) para buscar imóveis. Ex.: 'Rua Guaipá, Vila Leopoldina, São Paulo - SP'.")

    capauto = sub.add_parser("capture_autoconfig", help="Captura e tenta autoconfigurar listing_path/fields gerando platforms.autogen.yaml.")
    capauto.add_argument("--config", required=True)
    capauto.add_argument("--mode", choices=["rent", "buy"], required=True)
    capauto.add_argument("--out-dir", default=".")
    capauto.add_argument("--headless", action="store_true")
    capauto.add_argument("--wait-seconds", type=int, default=12)
    capauto.add_argument("--max-pages", type=int, default=None, help="Máx. de páginas para capturar por plataforma (quando aplicável; ex.: QuintoAndar via replay paginado).")
    capauto.add_argument("--address", "--qa-query", dest="search_address", default=None, help="Endereço (texto) para buscar imóveis (usado antes do autoconfig).")
    capauto.add_argument("--out-config", default="platforms.autogen.yaml")

    
    probe = sub.add_parser("probe_vivareal", help="Testa chamadas possíveis do glue-api do VivaReal e identifica qual retorna lista de imóveis.")
    probe.add_argument("--mode", choices=["rent", "buy"], required=True)
    probe.add_argument("--lat", type=float, required=True)
    probe.add_argument("--lon", type=float, required=True)
    probe.add_argument("--city", default="São Paulo")
    probe.add_argument("--state", default="São Paulo")
    probe.add_argument("--ref", default="/aluguel/sp/sao-paulo/")
    probe.add_argument("--size", type=int, default=36)
    probe.add_argument("--out", default="vivareal_probe.json")

    rank = sub.add_parser("rank", help="Extrai dos JSON salvos, deduplica, filtra e ranqueia.")
    rank.add_argument("--config", required=True)
    rank.add_argument("--runs-dir", required=True)
    rank.add_argument("--lat", type=float, required=False, default=None)
    rank.add_argument("--lon", type=float, required=False, default=None)
    rank.add_argument("--address", "--qa-query", dest="search_address", default=None, help="Endereço (texto) para geocodificar e usar como ponto (lat/lon) quando --lat/--lon não forem informados.")
    rank.add_argument("--radius-m", type=float, required=True)
    rank.add_argument("--mode", choices=["rent", "buy"], required=True)
    rank.add_argument("--min-price", type=float, default=None)
    rank.add_argument("--max-price", type=float, default=None)
    rank.add_argument("--min-bedrooms", type=int, default=None)
    rank.add_argument("--min-area-m2", type=float, default=None)
    rank.add_argument("--w-price", type=float, default=0.65)
    rank.add_argument("--w-dist", type=float, default=0.35)
    rank.add_argument("--out", default="results.csv")

    allcmd = sub.add_parser("all", help="Faz capture e depois rank em sequência.")
    allcmd.add_argument("--config", required=True)
    allcmd.add_argument("--mode", choices=["rent", "buy"], required=True)
    allcmd.add_argument("--lat", type=float, required=False, default=None)
    allcmd.add_argument("--lon", type=float, required=False, default=None)
    allcmd.add_argument("--address", "--qa-query", dest="search_address", default=None, help="Endereço (texto) para buscar imóveis e (se --lat/--lon não forem informados) também definir o ponto de distância/raio.")
    allcmd.add_argument("--radius-m", type=float, required=True)
    allcmd.add_argument("--min-price", type=float, default=None)
    allcmd.add_argument("--max-price", type=float, default=None)
    allcmd.add_argument("--min-bedrooms", type=int, default=None)
    allcmd.add_argument("--min-area-m2", type=float, default=None)
    allcmd.add_argument("--w-price", type=float, default=0.65)
    allcmd.add_argument("--w-dist", type=float, default=0.35)
    allcmd.add_argument("--out-dir", default=".")
    allcmd.add_argument("--headless", action="store_true")
    allcmd.add_argument("--wait-seconds", type=int, default=12)
    allcmd.add_argument("--max-pages", type=int, default=None, help="Máx. de páginas para capturar por plataforma (quando aplicável; ex.: QuintoAndar via replay paginado).")
    allcmd.add_argument("--out", default="results.csv")

    return p


async def main_async():
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "capture":
        run_root, geo = await capture_all(
            config_path=args.config,
            mode=args.mode,
            out_dir=args.out_dir,
            headless=args.headless,
            wait_seconds=args.wait_seconds,
            max_pages=getattr(args, "max_pages", None),
            search_address=getattr(args,'search_address', None),
        )
        print(f"Run gerado em: {run_root}")
        if geo:
            print(f"[geocode] {geo.get('display_name') or geo.get('query')} -> ({geo.get('lat')},{geo.get('lon')})")

    
    elif args.cmd == "probe_vivareal":
        business = "RENTAL" if args.mode == "rent" else "SALE"
        url1 = _vivareal_fallback_glue_url(
            business=business,
            lat=args.lat,
            lon=args.lon,
            size=args.size,
            from_=0,
            city=args.city,
            state=args.state,
            ref=args.ref,
        )
        # Variante problemática (mantida só para diagnosticar)
        url2 = url1 + "&pointRadius="
        parts = urlsplit(url1)
        q = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k != "includeFields"]
        url3 = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment))

        urls = [("fallback_v1", url1), ("fallback_v1_pointRadius", url2), ("fallback_no_includeFields", url3)]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await (await browser.new_context()).new_page()

            best = None
            best_data = None

            for tag, u in urls:
                r = await page.request.get(u, headers=VIVAREAL_GLUE_HEADERS)
                ct = (r.headers.get("content-type") or "").lower()
                print(f"[vivareal_probe] {tag}: HTTP {r.status} ct={ct}")

                if not r.ok:
                    try:
                        print((await r.text())[:400])
                    except Exception:
                        pass
                    continue

                if "json" not in ct:
                    continue

                data = await r.json()

                # Debug estrutural
                try:
                    if isinstance(data, dict):
                        print(f"[vivareal_probe] {tag}: top_keys={list(data.keys())[:25]}")
                        if isinstance(data.get("search"), dict):
                            print(f"[vivareal_probe] {tag}: search_keys={list(data['search'].keys())[:25]}")
                            print(f"[vivareal_probe] {tag}: totalCount={data['search'].get('totalCount')}")
                            if isinstance(data['search'].get("result"), dict):
                                print(f"[vivareal_probe] {tag}: search.result_keys={list(data['search']['result'].keys())[:25]}")
                except Exception:
                    pass

                cands = score_list_candidates(data)
                if cands:
                    score, path, n, _ = cands[0]
                    print(f"[vivareal_probe] {tag}: melhor lista={path} score={score} n={n}")
                    if best is None or score > best[0]:
                        best = (score, tag, path, n, u)
                        best_data = data
                else:
                    picked = None
                    for pth in COMMON_PATHS_VIVAREAL:
                        try:
                            obj = get_by_path(data, pth)
                            if isinstance(obj, list):
                                print(f"[vivareal_probe] {tag}: common_path {pth} -> list len={len(obj)}")
                                if len(obj) >= 10 and all(isinstance(x, dict) for x in obj[:10]):
                                    picked = pth
                        except Exception:
                            pass

                    if picked:
                        n = len(get_by_path(data, picked) or [])
                        score = 1
                        print(f"[vivareal_probe] {tag}: candidato via common_path={picked} n={n}")
                        if best is None or score > best[0]:
                            best = (score, tag, picked, n, u)
                            best_data = data
                    else:
                        print(f"[vivareal_probe] {tag}: sem lista detectável")

            await browser.close()

        if best_data is None:
            raise SystemExit("Nenhuma chamada retornou lista de imóveis detectável. Veja logs acima (HTTP/erro).")

        with open(args.out, "wb") as f:
            f.write(orjson.dumps(best_data))

        print(f"[vivareal_probe] OK: salvou {args.out} | melhor={best}")

    elif args.cmd == "rank":
        run_root = Path(args.runs_dir)

        # Ponto de distância/raio:
        # - usa --lat/--lon quando informado
        # - senão, tenta geocodificar --address
        # - senão, tenta ler run_meta.json do próprio run
        center_lat = args.lat
        center_lon = args.lon
        geo = None

        if center_lat is None or center_lon is None:
            if getattr(args, "search_address", None):
                geo = geocode_address_nominatim(args.search_address)

            if geo is None:
                meta_path = run_root / "run_meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        g = meta.get("geocode")
                        if isinstance(g, dict):
                            geo = g
                    except Exception:
                        pass

            if isinstance(geo, dict):
                center_lat = geo.get("lat")
                center_lon = geo.get("lon")

        if center_lat is None or center_lon is None:
            raise SystemExit("Você deve informar --lat/--lon ou --address (para geocode) para definir o ponto de distância/raio.")

        df = aggregate_runs(
            config_path=args.config,
            runs_dir=args.runs_dir,
            center_lat=float(center_lat),
            center_lon=float(center_lon),
            radius_m=args.radius_m,
            mode=args.mode,
            min_price=args.min_price,
            max_price=args.max_price,
            filters={"min_bedrooms": args.min_bedrooms, "min_area_m2": args.min_area_m2},
            w_price=args.w_price,
            w_dist=args.w_dist,
        )
        df.to_csv(args.out, index=False)
        print(f'OK: {args.out} ({len(df)} imóveis)')

        # --- COMPILAR SAÍDA PADRONIZADA (JSON + CSV) ---
        compiled = compile_run_to_std(
            run_root=run_root,
            config_path=args.config,
            mode=args.mode,
            distance_lat=float(center_lat),
            distance_lon=float(center_lon),
        )

        compiled_out_json = run_root / "compiled_listings.json"
        compiled_out_csv = run_root / "compiled_listings.csv"
        write_compiled_listings_json(compiled, compiled_out_json)
        write_compiled_listings_csv(compiled, compiled_out_csv)

        # # opcional: somente os imóveis com coords dentro do raio
        # within = [
        #     it for it in compiled
        #     if (it.get("distance_m") is not None) and (float(it["distance_m"]) <= float(args.radius_m))
        # ]
        # if within:
        #     write_compiled_listings_csv(within, run_root / "compiled_within_radius.csv")

        # print(f"[compile] salvou {compiled_out_json.name} e {compiled_out_csv.name} | itens={len(compiled)}")


    elif args.cmd == "capture_autoconfig":
        run_root, geo = await capture_all(
            config_path=args.config,
            mode=args.mode,
            out_dir=args.out_dir,
            headless=args.headless,
            wait_seconds=args.wait_seconds,
            max_pages=getattr(args, "max_pages", None),
            search_address=getattr(args,'search_address', None),
        )
        out_yaml = write_autogen_yaml(
            original_yaml_path=args.config,
            run_root=run_root,
            mode=args.mode,
            out_path=args.out_config,
        )
        print(f"Run gerado em: {run_root}")
        print(f"Config autogerada: {out_yaml}")

    elif args.cmd == "all":
        run_root, geo = await capture_all(
            config_path=args.config,
            mode=args.mode,
            out_dir=args.out_dir,
            headless=args.headless,
            wait_seconds=args.wait_seconds,
            max_pages=getattr(args, "max_pages", None),
            search_address=getattr(args,'search_address', None),
        )

        # Ponto de distância/raio: usa --lat/--lon se fornecido; senão, cai para o geocode do endereço.
        center_lat = args.lat
        center_lon = args.lon
        if (center_lat is None or center_lon is None) and isinstance(geo, dict):
            center_lat = geo.get('lat')
            center_lon = geo.get('lon')
        if center_lat is None or center_lon is None:
            raise SystemExit("Você deve informar --lat/--lon ou --address para definir o ponto de distância/raio.")

        df = aggregate_runs(
            config_path=args.config,
            runs_dir=str(run_root),
            center_lat=center_lat,
            center_lon=center_lon,
            radius_m=args.radius_m,
            mode=args.mode,
            min_price=args.min_price,
            max_price=args.max_price,
            filters={"min_bedrooms": args.min_bedrooms, "min_area_m2": args.min_area_m2},
            w_price=args.w_price,
            w_dist=args.w_dist,
        )
        out_csv = args.out
        df.to_csv(out_csv, index=False)
        parquet_out = os.path.splitext(out_csv)[0] + ".parquet"
        try:
            df.to_parquet(parquet_out, index=False)
            print(f"OK: {out_csv} e {parquet_out} ({len(df)} imóveis)")
        except ImportError:
            print(f"OK: {out_csv} ({len(df)} imóveis) — parquet ignorado (instale pyarrow/fastparquet se quiser)")
        # --- COMPILAR SAÍDA PADRONIZADA (JSON + CSV) ---
        compiled = compile_run_to_std(
            run_root=run_root,
            config_path=args.config,
            mode=args.mode,
            distance_lat=float(center_lat),
            distance_lon=float(center_lon),
        )
        write_compiled_listings_json(compiled, Path(run_root) / "compiled_listings.json")
        write_compiled_listings_csv(compiled, Path(run_root) / "compiled_listings.csv")
        within = [
            it for it in compiled
            if (it.get("distance_m") is not None) and (float(it["distance_m"]) <= float(args.radius_m))
        ]
        if within:
            write_compiled_listings_csv(within, Path(run_root) / "compiled_within_radius.csv")

        print(f"JSON/Logs em: {run_root}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
