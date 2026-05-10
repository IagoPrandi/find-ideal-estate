#!/usr/bin/env python3
"""
Busca POIs (supermercados, academias, parques, farmácias, mercados, restaurantes)
dentro de uma área (raio em metros) a partir de um ponto, usando Mapbox Search Box API (Category Search).

- Entrada: ponto (lon/lat) + raio (m)
- Saída: nome + coordenadas (lon/lat) por categoria (JSON ou CSV)

Docs (Mapbox):
- Category Search endpoint (/category/{canonical_category_id}) e /list/category:
  https://docs.mapbox.com/api/search/search-box/  (seção "Category Search" e "List categories")

Requisitos:
  pip install requests python-dotenv

.env (na mesma pasta do script):
  MAPBOX_ACCESS_TOKEN=SEU_TOKEN_AQUI

Exemplos (PowerShell):
  python .\pois_categoria_raio.py --lon -46.726941166 --lat -23.521067997 --radius 1200 --out pois.json --format json
  python .\pois_categoria_raio.py --lon -46.726941166 --lat -23.521067997 --radius 1200 --out pois.csv --format csv
"""

import argparse
import csv
import math
import os
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

EARTH_RADIUS_M = 6378137.0  # WGS84


def radius_to_bbox(lon: float, lat: float, radius_m: float) -> Tuple[float, float, float, float]:
    """Converte (lon,lat,raio_m) para bbox (minLon, minLat, maxLon, maxLat)."""
    lat_rad = math.radians(lat)

    dlat = (radius_m / EARTH_RADIUS_M) * (180.0 / math.pi)
    dlon = (radius_m / (EARTH_RADIUS_M * max(1e-12, math.cos(lat_rad)))) * (180.0 / math.pi)

    min_lon = lon - dlon
    max_lon = lon + dlon
    min_lat = lat - dlat
    max_lat = lat + dlat
    return (min_lon, min_lat, max_lon, max_lat)


class MapboxCategoryPOI:
    def __init__(self, token: str, session: Optional[requests.Session] = None):
        if not token:
            raise ValueError("Token vazio. Defina MAPBOX_ACCESS_TOKEN no .env (ou passe --token).")
        self.token = token
        self.session = session or requests.Session()

    def list_categories(self, language: str = "pt") -> List[Dict]:
        url = "https://api.mapbox.com/search/searchbox/v1/list/category"
        params = {"access_token": self.token, "language": language}
        r = self.session.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("listItems", []) or data.get("list_items", []) or []

    def resolve_canonical_ids(
        self,
        wanted: Dict[str, List[str]],
        language: str = "pt",
        hard_fallback: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Resolve as categorias desejadas para canonical_id."""
        hard_fallback = hard_fallback or {}

        cats = self.list_categories(language=language)
        by_id = {c.get("canonical_id"): c for c in cats if c.get("canonical_id")}

        by_name = {}
        for c in cats:
            name = c.get("name") or ""
            cid = c.get("canonical_id")
            if name and cid:
                by_name[name.strip().lower()] = cid

        resolved: Dict[str, str] = {}
        for user_cat, candidates in wanted.items():
            picked = None

            # 1) canonical_id exato
            for cand in candidates:
                if cand in by_id:
                    picked = cand
                    break

            # 2) match por nome (contains)
            if not picked:
                for cand in candidates:
                    cand_norm = cand.replace("_", " ").strip().lower()
                    for name_norm, cid in by_name.items():
                        if cand_norm in name_norm:
                            picked = cid
                            break
                    if picked:
                        break

            # 3) fallback
            if not picked and user_cat in hard_fallback:
                picked = hard_fallback[user_cat]

            if picked:
                resolved[user_cat] = picked

        return resolved

    def search_category(
        self,
        canonical_id: str,
        lon: float,
        lat: float,
        bbox: Tuple[float, float, float, float],
        limit: int = 25,
        language: str = "pt",
        country: str = "BR",
    ) -> List[Dict]:
        """Chama /category/{canonical_id}. limit máximo 25 (docs)."""
        url = f"https://api.mapbox.com/search/searchbox/v1/category/{canonical_id}"
        params = {
            "access_token": self.token,
            "language": language,
            "limit": int(max(1, min(25, limit))),
            "proximity": f"{lon},{lat}",
            "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "country": country,
        }
        r = self.session.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("features", []) or []


def extract_name_location_and_address(feature: Dict) -> Optional[Tuple[str, float, float, str]]:
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}

    name = props.get("name")
    coords = geom.get("coordinates")
    if not (isinstance(name, str) and name.strip() and isinstance(coords, list) and len(coords) >= 2):
        return None

    # Endereço: preferir full_address; se não existir, montar a partir de address + place_formatted
    full_address = props.get("full_address")
    if not full_address:
        addr = props.get("address") or ""
        place = props.get("place_formatted") or ""
        full_address = (f"{addr}, {place}".strip(", ")).strip() or None

    lon, lat = coords[0], coords[1]
    try:
        return (name.strip(), float(lon), float(lat), (full_address or "").strip())
    except Exception:
        return None



    lon, lat = coords[0], coords[1]
    try:
        return (name.strip(), float(lon), float(lat))
    except Exception:
        return None


def main() -> int:
    load_dotenv()

    p = argparse.ArgumentParser(description="Busca POIs por categoria dentro de um raio usando Mapbox Search Box API.")
    p.add_argument("--lon", type=float, required=True, help="Longitude do ponto (ex.: -46.726941166)")
    p.add_argument("--lat", type=float, required=True, help="Latitude do ponto (ex.: -23.521067997)")
    p.add_argument("--radius", type=float, required=True, help="Raio em metros (ex.: 1200)")
    p.add_argument("--limit", type=int, default=25, help="Máximo de resultados por categoria (1 a 25)")
    p.add_argument("--language", type=str, default="pt", help="Idioma (ex.: pt, en)")
    p.add_argument("--country", type=str, default="BR", help="País ISO2 (ex.: BR)")
    p.add_argument("--token", type=str, default="", help="Token Mapbox (se vazio, usa MAPBOX_ACCESS_TOKEN do .env)")
    p.add_argument("--out", type=str, default="", help="Arquivo de saída (opcional). Ex.: pois.json / pois.csv")
    p.add_argument("--format", choices=["json", "csv"], default="json", help="Formato de saída")

    args = p.parse_args()

    token = (args.token or os.getenv("MAPBOX_ACCESS_TOKEN", "")).strip()
    if not token:
        raise SystemExit("Erro: defina MAPBOX_ACCESS_TOKEN no .env (ou passe --token).")

    client = MapboxCategoryPOI(token)

    wanted = {
        "supermercados": ["supermarket", "grocery"],
        "academias": ["fitness_centre", "fitness_center", "gym", "fitness"],
        "parques": ["park"],
        "farmacias": ["pharmacy", "drugstore"],
        "mercados": ["grocery", "convenience_store", "market"],
        "restaurantes": ["restaurant", "food_and_drink", "food"],
    }

    hard_fallback = {
        "parques": "park",
        "restaurantes": "restaurant",
        "farmacias": "pharmacy",
        "supermercados": "supermarket",
        "mercados": "grocery",
        "academias": "fitness_centre",
    }

    resolved = client.resolve_canonical_ids(wanted, language=args.language, hard_fallback=hard_fallback)
    if not resolved:
        raise SystemExit("Não foi possível resolver nenhuma categoria. Tente --language en.")

    bbox = radius_to_bbox(args.lon, args.lat, args.radius)

    results: List[Dict] = []
    seen = set()

    for user_cat, canonical_id in resolved.items():
        feats = client.search_category(
            canonical_id=canonical_id,
            lon=args.lon,
            lat=args.lat,
            bbox=bbox,
            limit=args.limit,
            language=args.language,
            country=args.country,
        )
        for f in feats:
            parsed = extract_name_location_and_address(f)
            if not parsed:
                continue
            name, lon, lat, endereco = parsed
            key = (user_cat, name.lower(), round(lon, 6), round(lat, 6))
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "categoria": user_cat,
                    "canonical_id": canonical_id,
                    "nome": name,
                    "longitude": lon,
                    "latitude": lat,
                    "endereco": endereco,
                }
            )

    results.sort(key=lambda x: (x["categoria"], x["nome"].lower()))

    if args.format == "json":
        import json
        payload = {"center": {"lon": args.lon, "lat": args.lat}, "radius_m": args.radius, "results": results}
        out_text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(out_text)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(out_text)
            print(f"\nSalvo em: {args.out}")
    else:
        fieldnames = ["categoria", "canonical_id", "nome", "endereco", "longitude", "latitude"]
        if args.out:
            with open(args.out, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            print(f"Salvo em: {args.out}")
        else:
            writer = csv.DictWriter(os.sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
