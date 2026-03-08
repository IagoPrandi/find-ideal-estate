#!/usr/bin/env python3
"""
Tilequery-only: coleta nomes de ruas dentro de um raio (aproximação por amostragem).

Requisitos:
  pip install requests python-dotenv

Arquivo .env (na mesma pasta do script):
  MAPBOX_ACCESS_TOKEN=SEU_TOKEN_AQUI

Como usar:
  export MAPBOX_ACCESS_TOKEN="SEU_TOKEN_AQUI"
  python tilequery_streets_in_radius.py --lon -46.655881 --lat -23.561414 --radius 600
  python tilequery_streets_in_radius.py --lon -46.726941166 --lat -23.521067997 --radius 600  # teste


Saída:
  - imprime as ruas (ordenadas) no stdout
  - opcionalmente salva em arquivo com --out

Observações importantes:
  - Tilequery retorna no máximo 50 features por chamada.
  - Para cobrir melhor a área, o script amostra vários pontos dentro do círculo.
  - Ajuste --step (distância entre pontos) e --query-radius (raio de cada tilequery) para equilibrar custo x cobertura.
"""

import argparse
import math
import os
import time

from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set, Tuple

import requests

EARTH_RADIUS_M = 6378137.0  # WGS84


def _meters_to_lat_deg(m: float) -> float:
    return (m / EARTH_RADIUS_M) * (180.0 / math.pi)


def _meters_to_lon_deg(m: float, lat_deg: float) -> float:
    lat_rad = math.radians(lat_deg)
    return (m / (EARTH_RADIUS_M * max(1e-12, math.cos(lat_rad)))) * (180.0 / math.pi)


def generate_points_in_circle(
    center_lon: float,
    center_lat: float,
    radius_m: float,
    step_m: float,
) -> List[Tuple[float, float]]:
    """
    Gera pontos (lon, lat) em uma malha dentro de um círculo.
    Quanto menor step_m, maior cobertura e maior custo (mais chamadas).
    """
    if radius_m <= 0:
        return [(center_lon, center_lat)]
    if step_m <= 0:
        raise ValueError("step_m precisa ser > 0")

    points: List[Tuple[float, float]] = []

    y = -radius_m
    while y <= radius_m:
        lat = center_lat + _meters_to_lat_deg(y)
        x = -radius_m
        while x <= radius_m:
            if (x * x + y * y) <= (radius_m * radius_m):
                lon = center_lon + _meters_to_lon_deg(x, center_lat)
                points.append((lon, lat))
            x += step_m
        y += step_m

    # garante que o centro esteja incluído
    points.append((center_lon, center_lat))
    return points


class MapboxTilequeryStreetFinder:
    """
    Consulta Mapbox Tilequery API no tileset mapbox-streets-v8, layer 'road'
    e extrai o nome da via (sem números de imóveis).
    """

    def __init__(self, access_token: str, session: Optional[requests.Session] = None):
        if not access_token:
            raise ValueError("access_token vazio (defina MAPBOX_ACCESS_TOKEN ou passe --token).")
        self.token = access_token
        self.session = session or requests.Session()

    def tilequery_road_names(
        self,
        lon: float,
        lat: float,
        radius_m: float,
        language_pref: str = "pt",
        timeout: float = 10.0,
        retries: int = 3,
        sleep_on_429: float = 0.6,
    ) -> Set[str]:
        """
        Retorna um conjunto de nomes de ruas encontrados por tilequery ao redor de (lon, lat).
        """
        url = f"https://api.mapbox.com/v4/mapbox.mapbox-streets-v8/tilequery/{lon:.6f},{lat:.6f}.json"
        params = {
            "access_token": self.token,
            "layers": "road",
            "geometry": "linestring",
            "radius": float(radius_m),
            "limit": 50,        # limite do endpoint (máximo 50)
            "dedupe": "true",
        }

        backoff = 0.8
        for attempt in range(retries + 1):
            r = self.session.get(url, params=params, timeout=timeout)

            # Rate limit
            if r.status_code == 429 and attempt < retries:
                time.sleep(sleep_on_429 + backoff)
                backoff *= 2
                continue

            r.raise_for_status()
            data = r.json()

            out: Set[str] = set()
            for feat in data.get("features", []):
                props = feat.get("properties", {}) or {}
                # Streets v8 costuma ter 'name' e, em alguns casos, 'name_pt', 'name_en', etc.
                name = props.get(f"name_{language_pref}") or props.get("name")
                if isinstance(name, str) and name.strip():
                    out.add(name.strip())
            return out

        return set()

    def reverse_geocode_context(
        self,
        lon: float,
        lat: float,
        language_pref: str = "pt",
        timeout: float = 10.0,
        retries: int = 3,
        sleep_on_429: float = 0.6,
    ) -> Tuple[str, str, str]:
        """
        Geocodificação reversa para obter (bairro, cidade, sigla_estado).
        Usa Mapbox Geocoding API v5.
        """
        url = (
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
            f"{lon:.6f},{lat:.6f}.json"
        )
        params = {
            "access_token": self.token,
            "types": "neighborhood,place,region",
            "language": language_pref,
        }

        backoff = 0.8
        for attempt in range(retries + 1):
            r = self.session.get(url, params=params, timeout=timeout)

            if r.status_code == 429 and attempt < retries:
                time.sleep(sleep_on_429 + backoff)
                backoff *= 2
                continue

            r.raise_for_status()
            data = r.json()

            bairro = ""
            cidade = ""
            estado = ""

            for feat in data.get("features", []):
                place_type = feat.get("place_type", [])
                text = feat.get("text", "")
                if "neighborhood" in place_type and not bairro:
                    bairro = text
                elif "place" in place_type and not cidade:
                    cidade = text
                elif "region" in place_type and not estado:
                    short_code = feat.get("properties", {}).get("short_code", "")
                    if short_code and "-" in short_code:
                        estado = short_code.split("-")[-1].upper()
                    else:
                        estado = text

            return (bairro, cidade, estado)

        return ("", "", "")


def _format_street_address(
    street: str, bairro: str, cidade: str, estado: str
) -> str:
    """Formata como 'Rua, Bairro, Cidade - Sigla_Estado'."""
    parts = [street]
    if bairro:
        parts.append(bairro)
    if cidade:
        parts.append(cidade)
    base = ", ".join(parts)
    if estado:
        return f"{base} - {estado}"
    return base


def streets_within_radius_via_tilequery(
    access_token: str,
    center_lon: float,
    center_lat: float,
    radius_m: float,
    step_m: float = 150.0,
    tilequery_radius_m: float = 120.0,
    max_workers: int = 8,
    language_pref: str = "pt",
) -> List[str]:
    """
    Aproxima as ruas dentro de um raio, executando tilequery em vários pontos amostrados.
    Retorna cada rua formatada como "Rua, Bairro, Cidade - Sigla_Estado".
    """
    points = generate_points_in_circle(center_lon, center_lat, radius_m, step_m)
    finder = MapboxTilequeryStreetFinder(access_token)
    max_workers = max(1, int(max_workers))

    # Fase 1: tilequery em todos os pontos, rastreando qual ponto encontrou cada rua
    street_to_point: Dict[str, Tuple[float, float]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                finder.tilequery_road_names,
                lon,
                lat,
                tilequery_radius_m,
                language_pref,
            ): (lon, lat)
            for lon, lat in points
        }
        for fut in as_completed(futures):
            point = futures[fut]
            for name in fut.result():
                if name not in street_to_point:
                    street_to_point[name] = point

    if not street_to_point:
        return []

    # Fase 2: geocodificação reversa dos pontos representativos (um por rua)
    unique_points = set(street_to_point.values())
    point_to_context: Dict[Tuple[float, float], Tuple[str, str, str]] = {}

    with ThreadPoolExecutor(max_workers=max(1, max_workers // 2)) as ex:
        futures = {
            ex.submit(
                finder.reverse_geocode_context,
                lon,
                lat,
                language_pref,
            ): (lon, lat)
            for lon, lat in unique_points
        }
        for fut in as_completed(futures):
            point = futures[fut]
            point_to_context[point] = fut.result()

    # Fase 3: montar resultado formatado
    results: List[str] = []
    for street, point in street_to_point.items():
        bairro, cidade, estado = point_to_context.get(point, ("", "", ""))
        results.append(_format_street_address(street, bairro, cidade, estado))

    return sorted(results)


def main() -> int:
    load_dotenv()

    p = argparse.ArgumentParser(
        description="Coleta nomes de ruas dentro de um raio usando APENAS Mapbox Tilequery (amostragem)."
    )
    # Se executar sem argumentos, usa as coordenadas de teste e radius padrão.
    p.add_argument("--lon", type=float, required=True, help="Longitude do centro (ex.: -46.655881)")
    p.add_argument("--lat", type=float, required=True, help="Latitude do centro (ex.: -23.561414)")
    p.add_argument("--radius", type=float, required=True, help="Raio do círculo em metros (ex.: 600)")
    p.add_argument("--step", type=float, default=150.0, help="Passo da malha em metros (menor = mais cobertura/custo)")
    p.add_argument("--query-radius", type=float, default=120.0, help="Raio (m) de cada tilequery ao redor de cada ponto")
    p.add_argument("--max-workers", type=int, default=8, help="Número de threads (cuidado com rate limit)")
    p.add_argument("--language", type=str, default="pt", help="Preferência de idioma para name_<lang> (ex.: pt, en)")
    p.add_argument("--token", type=str, default="", help="Token Mapbox (se vazio, usa MAPBOX_ACCESS_TOKEN)")
    p.add_argument("--out", type=str, default="", help="Arquivo de saída (opcional)")
    p.add_argument("--format", choices=["txt", "json"], default="txt", help="Formato de saída")

    args = p.parse_args()

    token = (args.token or os.getenv("MAPBOX_ACCESS_TOKEN", "")).strip()  # carregado do .env via load_dotenv()
    if not token:
        raise SystemExit("Erro: defina MAPBOX_ACCESS_TOKEN ou passe --token.")

    streets = streets_within_radius_via_tilequery(
        access_token=token,
        center_lon=args.lon,
        center_lat=args.lat,
        radius_m=args.radius,
        step_m=args.step,
        tilequery_radius_m=args.query_radius,
        max_workers=args.max_workers,
        language_pref=args.language,
    )

    if args.format == "json":
        import json
        output = json.dumps({"count": len(streets), "streets": streets}, ensure_ascii=False, indent=2)
    else:
        output = "\n".join(streets)

    print(output)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
            if args.format != "json":
                f.write("\n")
        print(f"\nSalvo em: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
