#!/usr/bin/env python3
"""
candidate_zones_from_cache.py — Urban Living Optimizer (SP/RMSP) — arquivo único
Versão: v4 (refactor: main menor + bugfix: função faltante)

Mudanças nesta versão:
- Refatoração: `main()` ficou menor (delegando para funções: load_inputs, resolve_seeds, run_bus_pipeline, run_rail_pipeline, export_outputs)
- Bugfix: adicionada função `find_gpkg_by_keywords()` (era chamada mas não existia)
- Mantém: ônibus via GTFS (sentido + frequência), cruzamento opcional com GPKG de linhas (enriquecimento), inundação via STRtree
- Mantém: smoke test com coordenadas default (-23.582013144135555, -46.67134403540264)

Entradas esperadas (cache_dir):
- {cache_dir}/gtfs/*.txt  (stops, routes, trips, stop_times, frequencies, ...)
- {cache_dir}/geosampa/*.gpkg  (estações/linhas metrô e trem, mancha inundação, e opcionalmente linhas ônibus)

Saídas (em --out-dir):
- outputs/zones.geojson
- outputs/ranking.csv
- outputs/trace.json

Requisitos (pip):
- pandas
- shapely
- pyproj
- fiona
- networkx

Exemplos (Windows):

1) Smoke test (usa coordenadas padrão caso nenhum seed seja informado):
  python candidate_zones_from_cache_v4.py ^
    --cache-dir "C:\\Users\\iagoo\\PESSOAL\\projetos\\onde_morar\\data_cache" ^
    --smoke-test ^
    --out-dir ".\\runs\\smoke"

2) Seed por coordenadas (lat,lon):
  python candidate_zones_from_cache_v4.py ^
    --cache-dir "C:\\Users\\iagoo\\PESSOAL\\projetos\\onde_morar\\data_cache" ^
    --seed-bus-coord "-23.582013144135555,-46.67134403540264" ^
    --t-bus 25 --buffer-m 600 ^
    --out-dir ".\\runs\\coord"

3) Listar stops para descobrir stop_id:
  python candidate_zones_from_cache_v4.py ^
    --cache-dir "C:\\Users\\iagoo\\PESSOAL\\projetos\\onde_morar\\data_cache" ^
    --list-bus-stops
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

import pandas as pd
import numpy as np
import networkx as nx
import fiona
from shapely.geometry import Point, shape, mapping
from shapely.strtree import STRtree
from shapely.ops import transform as shp_transform
from pyproj import Transformer


# -------------------------
# Progresso / Telemetria
# -------------------------

class Progress:
    """
    Progresso simples (sem dependências pesadas).
    - imprime estágios, contagens e tempos parciais
    - suporta barra opcional via tqdm, se instalado
    """
    def __init__(self, enabled: bool = True, use_tqdm: bool = True):
        self.enabled = enabled
        self.use_tqdm = use_tqdm
        self._t0 = datetime.now()
        self._last = datetime.now()
        self._tqdm = None
        if self.enabled and self.use_tqdm:
            try:
                from tqdm import tqdm  # type: ignore
                self._tqdm = tqdm
            except Exception:
                self._tqdm = None

    def stage(self, name: str) -> None:
        if not self.enabled:
            return
        dt = (datetime.now() - self._t0).total_seconds()
        print(f"\n=== [{dt:8.1f}s] {name} ===")
        self._last = datetime.now()

    def info(self, msg: str) -> None:
        if self.enabled:
            print(f"[INFO] {msg}")

    def warn(self, msg: str) -> None:
        if self.enabled:
            print(f"[WARN] {msg}")

    def iter(self, it, total: int | None = None, desc: str = ""):
        if not self.enabled:
            return it
        if self._tqdm is None:
            # fallback: imprime checkpoints
            for i, x in enumerate(it, start=1):
                if i == 1 or (total and i % max(1, total // 10) == 0):
                    print(f"[PROGRESS] {desc} {i}/{total if total else '?'}")
                yield x
            return
        return self._tqdm(it, total=total, desc=desc)

    def done(self, msg: str = "Concluído") -> None:
        if not self.enabled:
            return
        dt = (datetime.now() - self._t0).total_seconds()
        print(f"\n=== [{dt:8.1f}s] {msg} ===\n")
EPSG_WGS84 = "EPSG:4326"
EPSG_UTM_SP = "EPSG:31983"  # SIRGAS 2000 / UTM 23S

Mode = Literal["bus", "rail"]


# -------------------------
# Modelos
# -------------------------

@dataclass(frozen=True)
class ZoneRow:
    zone_id: str
    mode: Mode
    seed_id: str
    source_point_id: str
    travel_time_from_seed_minutes: float
    centroid_lon: float
    centroid_lat: float
    flood_intersection_ratio: float
    score: float
    trace: Dict[str, Any]


# -------------------------
# Utilitários gerais
# -------------------------

def stable_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:16]


def now_id() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def parse_gtfs_time_to_seconds(t: str) -> Optional[int]:
    """GTFS time HH:MM:SS (HH pode ser > 24)."""
    if not isinstance(t, str) or not t or t.lower() == "nan":
        return None
    parts = t.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        hh = int(parts[0]); mm = int(parts[1]); ss = int(parts[2])
        return hh * 3600 + mm * 60 + ss
    except Exception:
        return None


def centroid_lonlat(geom) -> Tuple[float, float]:
    c = geom.centroid
    return float(c.x), float(c.y)


def score_simple(generalized_time_min: float, flood_ratio: float, w_time: float = 0.65, w_flood: float = 0.35) -> float:
    """Maior é melhor. Penaliza tempo (viagem+espera) e alagamento."""
    return -(w_time * generalized_time_min + w_flood * (100.0 * flood_ratio))


def normalize_text(s: str) -> str:
    """Normaliza para matching: remove acentos/pontuação, upper, espaços."""
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join([c for c in s if not unicodedata.combining(c)])
    s = s.upper()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# -------------------------
# I/O: GTFS + GPKG
# -------------------------


def load_gtfs_tables(gtfs_dir: Path) -> Dict[str, pd.DataFrame]:
    """Carrega tabelas GTFS com I/O otimizado (colunas mínimas nas maiores tabelas).

    Observação: mantemos dtype=str para consistência e conversões explícitas depois.
    """
    required = ["stops.txt", "trips.txt", "stop_times.txt", "routes.txt"]
    for f in required:
        if not (gtfs_dir / f).exists():
            raise FileNotFoundError(f"GTFS faltando: {gtfs_dir / f}")

    usecols_map: Dict[str, List[str]] = {
        # tabelas grandes — reduza I/O e memória
        "stop_times": ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        "stops": ["stop_id", "stop_name", "stop_lat", "stop_lon"],
        "trips": ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id", "shape_id"],
        "routes": ["route_id", "route_short_name", "route_long_name", "route_type"],
        "frequencies": ["trip_id", "start_time", "end_time", "headway_secs"],
        # calendários (se existirem)
        "calendar": ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
        "calendar_dates": ["service_id", "date", "exception_type"],
        "shapes": ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
    }

    tables: Dict[str, pd.DataFrame] = {}
    for name in ["stops", "trips", "stop_times", "routes", "frequencies", "calendar", "calendar_dates", "shapes"]:
        fp = gtfs_dir / f"{name}.txt"
        if not fp.exists():
            continue
        uc = usecols_map.get(name)
        try:
            tables[name] = pd.read_csv(fp, dtype=str, usecols=uc) if uc else pd.read_csv(fp, dtype=str)
        except ValueError:
            # Se o GTFS não tiver alguma coluna esperada, faz fallback para leitura completa.
            tables[name] = pd.read_csv(fp, dtype=str)
    return tables


def list_layers(gpkg_path: Path) -> List[str]:
    return list(fiona.listlayers(str(gpkg_path)))


def can_open_gpkg(gpkg_path: Path) -> bool:
    try:
        _ = list_layers(gpkg_path)
        return True
    except Exception:
        return False


def read_gpkg_features(gpkg_path: Path, layer: Optional[str] = None, max_features: Optional[int] = None) -> Tuple[List[Dict[str, Any]], str]:
    layers = list_layers(gpkg_path)
    if not layers:
        raise ValueError(f"Nenhuma layer em {gpkg_path}")
    use = layer or layers[0]
    if use not in layers:
        raise ValueError(f"Layer '{use}' não existe em {gpkg_path}. Disponíveis: {layers}")
    feats: List[Dict[str, Any]] = []
    with fiona.open(str(gpkg_path), layer=use) as src:
        crs_wkt = src.crs_wkt or ""
        for i, feat in enumerate(src):
            feats.append(feat)
            if max_features is not None and i + 1 >= max_features:
                break
    return feats, crs_wkt


def guess_prop_key(props: Dict[str, Any], candidates: List[str]) -> str:
    keys = list(props.keys())
    low = {k.lower(): k for k in keys}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    if not keys:
        raise ValueError("Feature sem propriedades.")
    return keys[0]


def find_gpkg_by_keywords(root: Path, keywords: List[str]) -> Optional[Path]:
    """
    Procura recursivamente por .gpkg cujo nome contenha qualquer keyword (case-insensitive).
    Retorna o primeiro match (ordem lexicográfica), ou None.
    """
    if not root.exists():
        return None
    kws = [k.lower() for k in keywords if k]
    matches: List[Path] = []
    for p in root.rglob("*.gpkg"):
        name = p.name.lower()
        if any(k in name for k in kws):
            matches.append(p)
    return sorted(matches)[0] if matches else None


def print_open_confirmation(
    gtfs_dir: Path,
    geo_dir: Path,
    gtfs: Dict[str, pd.DataFrame],
    gpkg_paths: List[Tuple[str, Optional[Path]]],
) -> None:
    print("\n=== CONFIRMAÇÃO DE ABERTURA (INPUTS) ===")
    print(f"GTFS dir: {gtfs_dir}")
    for k, df in gtfs.items():
        cols = list(df.columns)
        print(f" - {k}.txt: {len(df):,} linhas | cols={cols[:8]}{'...' if len(cols)>8 else ''}")

    print(f"\nGeo dir: {geo_dir}")
    for label, p in gpkg_paths:
        if p is None:
            print(f" - {label}: (não definido)")
            continue
        if not p.exists():
            print(f" - {label}: {p.name} (NÃO ENCONTRADO)")
            continue
        try:
            layers = list_layers(p)
            print(f" - {label}: {p.name} | layers={layers}")
        except Exception as e:
            print(f" - {label}: {p.name} | [ERRO ao listar layers] {e}")
    print("=== FIM CONFIRMAÇÃO ===\n")


# -------------------------
# Inundação: STRtree
# -------------------------

def load_flood_tree(flood_gpkg: Path) -> STRtree:
    feats, _ = read_gpkg_features(flood_gpkg)
    geoms: List[Any] = []
    for f in feats:
        g = f.get("geometry")
        if not g:
            continue
        geom = shape(g)
        if geom.is_empty:
            continue
        geoms.append(geom)
    tree = STRtree(geoms) if geoms else STRtree([])
    # Compat: dependendo da versão do Shapely, STRtree.query pode retornar índices (int) ao invés de geometrias.
    # Guardamos a lista original para converter índices -> geometrias quando necessário.
    setattr(tree, "_geoms", geoms)
    return tree



def flood_ratio_for_buffers_utm(buffers_utm: List[Any], flood_tree: STRtree) -> List[float]:
    """Calcula razão de área alagável dentro de cada buffer (em CRS métrico).

    Otimizações:
    - usa geometria preparada (prep) para acelerar testes de interseção;
    - evita intersection() quando não intersecta;
    - early-break quando a cobertura já está ~saturada (>=95%).
    """
    from shapely.prepared import prep

    ratios: List[float] = []
    geoms_src = getattr(flood_tree, "_geoms", None)

    for buf in buffers_utm:
        if buf is None or buf.is_empty:
            ratios.append(0.0)
            continue

        a = float(buf.area)
        if a <= 0:
            ratios.append(0.0)
            continue

        cand = flood_tree.query(buf)
        pbuf = prep(buf)
        inter_area = 0.0
        # limiar para parar cedo (trade-off velocidade x precisão)
        sat = 0.95 * a

        for g_obj in cand:
            if isinstance(g_obj, (int, np.integer)) and geoms_src is not None:
                g = geoms_src[int(g_obj)]
            else:
                g = g_obj

            # teste rápido com geometria preparada
            if not pbuf.intersects(g):
                continue

            inter = g.intersection(buf)
            if not inter.is_empty:
                inter_area += float(inter.area)
                if inter_area >= sat:
                    inter_area = min(inter_area, a)
                    break

        ratios.append(inter_area / a)
    return ratios


def buffers_from_points(points_wgs: List[Tuple[str, float, float]], radius_m: float) -> Tuple[List[Any], List[Any]]:
    to_utm = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)
    to_wgs = Transformer.from_crs(EPSG_UTM_SP, EPSG_WGS84, always_xy=True)

    def _tx(x, y, z=None):
        return to_utm.transform(x, y)

    def _rx(x, y, z=None):
        return to_wgs.transform(x, y)

    bufs_utm: List[Any] = []
    bufs_wgs: List[Any] = []

    for _, lon, lat in points_wgs:
        p = Point(float(lon), float(lat))
        p_utm = shp_transform(_tx, p)
        b_utm = p_utm.buffer(radius_m)
        b_wgs = shp_transform(_rx, b_utm)
        bufs_utm.append(b_utm)
        bufs_wgs.append(b_wgs)

    return bufs_utm, bufs_wgs


# -------------------------
# Ônibus via GTFS: seed por coordenadas + sentido + frequência
# -------------------------


def find_nearest_stop_id_by_coord(stops: pd.DataFrame, lat: float, lon: float, max_dist_m: float = 120.0) -> Tuple[str, float]:
    """Encontra o stop_id mais próximo de (lat, lon).

    Otimizações:
    - transforma coordenadas em lote com pyproj (vetorizado);
    - evita list comprehensions custosas em GTFS grandes.
    """
    stops_xy = stops[["stop_id", "stop_lat", "stop_lon"]].copy()
    stops_xy["stop_id"] = stops_xy["stop_id"].astype(str)
    stops_xy["stop_lat"] = stops_xy["stop_lat"].astype(float)
    stops_xy["stop_lon"] = stops_xy["stop_lon"].astype(float)

    to_utm = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)
    x0, y0 = to_utm.transform(float(lon), float(lat))

    # transformação vetorizada (arrays)
    xs, ys = to_utm.transform(stops_xy["stop_lon"].to_numpy(), stops_xy["stop_lat"].to_numpy())
    stops_xy["x"] = xs
    stops_xy["y"] = ys

    dx = stops_xy["x"] - x0
    dy = stops_xy["y"] - y0
    stops_xy["d2"] = dx * dx + dy * dy

    best = stops_xy.loc[stops_xy["d2"].idxmin()]
    dist = math.sqrt(float(best["d2"]))
    if dist > max_dist_m:
        raise ValueError(
            f"Nenhum stop dentro de {max_dist_m} m. Melhor distância foi {dist:.1f} m (stop_id={best['stop_id']})."
        )
    return str(best["stop_id"]), dist


def resolve_bus_seed_stop_id(stops: pd.DataFrame, seed: str) -> str:
    if seed in set(stops["stop_id"].astype(str)):
        return str(seed)
    mask = stops["stop_name"].astype(str).str.contains(seed, case=False, na=False)
    if mask.any():
        return str(stops.loc[mask, "stop_id"].iloc[0])
    raise ValueError(f"Seed ônibus '{seed}' não encontrado (stop_id/stop_name).")


def build_frequency_index(frequencies: Optional[pd.DataFrame]) -> Dict[str, List[Tuple[int, int, int]]]:
    idx: Dict[str, List[Tuple[int, int, int]]] = {}
    if frequencies is None or frequencies.empty:
        return idx
    df = frequencies.copy()
    if not {"trip_id", "start_time", "end_time", "headway_secs"}.issubset(df.columns):
        return idx
    df["start_sec"] = df["start_time"].astype(str).map(parse_gtfs_time_to_seconds)
    df["end_sec"] = df["end_time"].astype(str).map(parse_gtfs_time_to_seconds)
    df["headway_secs_i"] = df["headway_secs"].astype(int, errors="ignore")
    df = df.dropna(subset=["start_sec", "end_sec", "headway_secs_i"])
    for trip_id, grp in df.groupby("trip_id"):
        idx[str(trip_id)] = [(int(r["start_sec"]), int(r["end_sec"]), int(r["headway_secs_i"])) for _, r in grp.iterrows()]
    return idx


def expected_wait_minutes_for_trip(trip_id: str, dep_sec_at_origin: Optional[int], freq_idx: Dict[str, List[Tuple[int, int, int]]]) -> Optional[float]:
    if dep_sec_at_origin is None:
        return None
    windows = freq_idx.get(str(trip_id))
    if not windows:
        return None
    for start_s, end_s, headway in windows:
        if start_s <= dep_sec_at_origin <= end_s and headway > 0:
            return (headway / 2.0) / 60.0
    return None



def compute_downstream_generalized_times(
    stop_times: pd.DataFrame,
    trips: pd.DataFrame,
    origin_stop_id: str,
    t_bus: float,
    freq_idx: Dict[str, List[Tuple[int, int, int]]],
    departure_window: Optional[Tuple[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Para um stop de origem, calcula o melhor (menor) tempo generalizado para stops a jusante.

    Otimização principal:
    - evita filtrar `stop_times` inteiro para cada trip_id (O(trips * |stop_times|));
      em vez disso, pré-agrupa `stop_times` por trip_id uma vez e consulta O(1).
    """
    if stop_times is None or stop_times.empty:
        return {}

    st = stop_times.copy()
    # normaliza tipos uma vez
    st["trip_id"] = st["trip_id"].astype(str)
    st["stop_id"] = st["stop_id"].astype(str)
    st["arr_sec"] = st["arrival_time"].astype(str).map(parse_gtfs_time_to_seconds)
    st["dep_sec"] = st["departure_time"].astype(str).map(parse_gtfs_time_to_seconds)
    st["stop_sequence_i"] = st["stop_sequence"].astype(int)

    st = st.dropna(subset=["dep_sec", "arr_sec", "stop_sequence_i"])
    st = st.sort_values(["trip_id", "stop_sequence_i"])

    origin_rows = st[st["stop_id"] == str(origin_stop_id)].copy()
    if origin_rows.empty:
        raise ValueError(f"Origin stop_id '{origin_stop_id}' não aparece em stop_times.")

    if departure_window is not None:
        start_s = parse_gtfs_time_to_seconds(departure_window[0])
        end_s = parse_gtfs_time_to_seconds(departure_window[1])
        if start_s is not None and end_s is not None:
            origin_rows = origin_rows[(origin_rows["dep_sec"] >= start_s) & (origin_rows["dep_sec"] <= end_s)]

    if origin_rows.empty:
        return {}

    # pega apenas a primeira passagem por trip (reduz iteração)
    origin_rows = origin_rows.sort_values("dep_sec").groupby("trip_id", as_index=False).head(1)

    trips_ix = trips.copy()
    if "trip_id" in trips_ix.columns:
        trips_ix["trip_id"] = trips_ix["trip_id"].astype(str)
        trips_ix = trips_ix.set_index("trip_id", drop=False)
    else:
        trips_ix = trips_ix.set_index(pd.Index([], name="trip_id"))

    # pré-indexação: trip_id -> tabela de stop_times já ordenada
    stop_times_by_trip: Dict[str, pd.DataFrame] = {tid: grp for tid, grp in st.groupby("trip_id", sort=False)}

    best: Dict[str, Dict[str, Any]] = {}

    for _, origin in origin_rows.iterrows():
        trip_id = str(origin["trip_id"])
        seq0 = int(origin["stop_sequence_i"])
        dep0 = int(origin["dep_sec"])

        wait_min = expected_wait_minutes_for_trip(trip_id, dep0, freq_idx)
        wait_min = float(wait_min) if wait_min is not None else 0.0

        direction_id = None
        trip_headsign = None
        route_id = None
        if trip_id in trips_ix.index:
            tr = trips_ix.loc[trip_id]
            direction_id = str(tr.get("direction_id")) if "direction_id" in tr else None
            trip_headsign = str(tr.get("trip_headsign")) if "trip_headsign" in tr else None
            route_id = str(tr.get("route_id")) if "route_id" in tr else None

        trip_tbl = stop_times_by_trip.get(trip_id)
        if trip_tbl is None or trip_tbl.empty:
            continue

        trip_rows = trip_tbl[trip_tbl["stop_sequence_i"] > seq0]
        if trip_rows.empty:
            continue

        # iterrows é ok aqui porque já reduzimos drasticamente o volume (trip_rows é um recorte curto)
        for _, r in trip_rows.iterrows():
            sid = str(r["stop_id"])
            arr = int(r["arr_sec"])
            in_vehicle = (arr - dep0) / 60.0
            if in_vehicle <= 0:
                continue
            if in_vehicle > float(t_bus):
                continue

            gen_time = float(in_vehicle) + wait_min
            prev = best.get(sid)
            if prev is None or gen_time < float(prev["min_gen_time"]):
                best[sid] = {
                    "min_gen_time": float(gen_time),
                    "min_in_vehicle": float(in_vehicle),
                    "min_wait": float(wait_min),
                    "direction_id": direction_id,
                    "trip_id": trip_id,
                    "trip_headsign": trip_headsign,
                    "route_id": route_id,
                }

    return best


def bucketize_best(best: Dict[str, Dict[str, Any]], step_minutes: int) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[int, Tuple[str, Dict[str, Any]]] = {}
    step = max(step_minutes, 1)
    for sid, info in best.items():
        dt = float(info["min_gen_time"])
        b = int(math.floor(dt / step))
        if b not in buckets or dt < float(buckets[b][1]["min_gen_time"]):
            buckets[b] = (sid, info)
    return {sid: info for sid, info in buckets.values()}


def cap_best(best: Dict[str, Dict[str, Any]], k_max: int) -> Dict[str, Dict[str, Any]]:
    if k_max <= 0 or len(best) <= k_max:
        return best
    items = sorted(best.items(), key=lambda x: float(x[1]["min_gen_time"]))[:k_max]
    return dict(items)


def dedupe_points_by_distance_utm(points_utm: List[Tuple[str, float, float]], priority: Dict[str, float], radius_m: float) -> List[str]:
    pts = [(pid, x, y, priority.get(pid, float("inf"))) for pid, x, y in points_utm if pid in priority]
    pts.sort(key=lambda t: t[3])

    kept: List[str] = []
    kept_xy: List[Tuple[float, float]] = []
    r2 = radius_m * radius_m

    for pid, x, y, _ in pts:
        ok = True
        for kx, ky in kept_xy:
            dx = x - kx; dy = y - ky
            if dx * dx + dy * dy <= r2:
                ok = False
                break
        if ok:
            kept.append(pid)
            kept_xy.append((x, y))
    return kept


# -------------------------
# Ônibus: cruzamento GTFS ↔ GPKG linhas (enriquecimento)
# -------------------------

def load_bus_lines_gpkg(bus_lines_gpkg: Optional[Path]) -> Optional[pd.DataFrame]:
    if bus_lines_gpkg is None or not bus_lines_gpkg.exists():
        return None
    feats, _ = read_gpkg_features(bus_lines_gpkg, max_features=5000)
    if not feats:
        return None
    props0 = dict(feats[0]["properties"])
    name_k = guess_prop_key(props0, ["ln_nome", "nome", "nm_linha", "linha"])
    rows = []
    for f in feats:
        pr = f["properties"]
        rows.append({
            "ln_nome": str(pr.get(name_k, "")),
        })
    df = pd.DataFrame(rows).drop_duplicates()
    df["ln_nome_norm"] = df["ln_nome"].map(normalize_text)
    return df


def build_route_to_busline_map(routes: pd.DataFrame, buslines_df: Optional[pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
    """
    Cria um mapa route_id (GTFS) -> metadados da linha no GPKG (GeoSampa).

    Correção importante:
    - A versão anterior fazia `cand = series or series`, o que dispara:
      "ValueError: The truth value of a Series is ambiguous".
    - Aqui, evitamos qualquer avaliação booleana de Series e selecionamos
      explicitamente o primeiro match.

    Estratégia de matching (best-effort, sem depender de um ID comum):
    1) Normaliza nomes (`ln_nome_norm`) e tenta match exato com `route_long_name` e `route_short_name`.
    2) Fallback: match por contenção (substring) quando não houver exato.
    3) Se houver múltiplos registros com mesmo nome normalizado, usa o primeiro.
    """
    out: Dict[str, Dict[str, Any]] = {}
    if buslines_df is None or buslines_df.empty:
        return out

    # Garante coluna normalizada
    if "ln_nome_norm" not in buslines_df.columns:
        buslines_df = buslines_df.copy()
        buslines_df["ln_nome_norm"] = buslines_df["ln_nome"].astype(str).map(normalize_text)

    # Mapa nome_norm -> índice do primeiro registro (evita Series ambígua)
    first_idx_by_name: Dict[str, int] = {}
    for idx, n in buslines_df["ln_nome_norm"].items():
        if isinstance(n, str) and n and n not in first_idx_by_name:
            first_idx_by_name[n] = int(idx)

    def pick_by_norm_name(name_norm: str) -> Optional[pd.Series]:
        if not name_norm:
            return None
        idx = first_idx_by_name.get(name_norm)
        if idx is None:
            return None
        return buslines_df.loc[idx]

    # Prelista de nomes para fallback por substring
    name_norm_list = list(first_idx_by_name.keys())

    for _, r in routes.iterrows():
        rid = str(r.get("route_id", ""))
        if not rid:
            continue

        long_name = normalize_text(r.get("route_long_name", ""))
        short_name = normalize_text(r.get("route_short_name", ""))

        cand: Optional[pd.Series] = None

        # match exato por long/short
        cand = pick_by_norm_name(long_name)
        if cand is None and short_name:
            cand = pick_by_norm_name(short_name)

        # fallback por substring
        if cand is None and long_name:
            for n in name_norm_list:
                if n and (n in long_name or long_name in n):
                    cand = buslines_df.loc[first_idx_by_name[n]]
                    break

        if cand is not None:
            out[rid] = {
                "busline_name": str(cand.get("ln_nome", "")),
            }

    return out


# -------------------------
# Trilhos via GeoSampa (grafo)
# -------------------------

def build_rail_graph_from_geosampa(
    metro_stations_gpkg: Path,
    train_stations_gpkg: Path,
    metro_lines_gpkg: Path,
    train_lines_gpkg: Path,
    transfer_walk_m: float,
    transfer_penalty_min: float,
    walk_speed_mps: float,
    rail_speed_kmh: float,
    snap_dist_m: float = 80.0,
) -> Tuple[nx.Graph, List[Tuple[str, float, float]], Dict[str, Tuple[float, float]], Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    m_feats, _ = read_gpkg_features(metro_stations_gpkg)
    t_feats, _ = read_gpkg_features(train_stations_gpkg)

    m_props0 = dict(m_feats[0]["properties"]) if m_feats else {}
    t_props0 = dict(t_feats[0]["properties"]) if t_feats else {}

    m_id_key = guess_prop_key(m_props0, ["cd_identificador", "cd_identificador_estacao_metro", "id", "codigo"]) 
    t_id_key = guess_prop_key(t_props0, ["cd_identificador", "cd_identificador_estacao_trem", "id", "codigo"]) 
    m_name_key = guess_prop_key(m_props0, ["nm_estacao_metro_trem", "nm_estacao", "nome"]) 
    t_name_key = guess_prop_key(t_props0, ["nm_estacao_metro_trem", "nm_estacao", "nome"]) 
    m_line_key = guess_prop_key(m_props0, ["nm_linha_metro_trem", "nm_linha", "nr_nome_linha"]) 
    t_line_key = guess_prop_key(t_props0, ["nm_linha_metro_trem", "nm_linha", "nr_nome_linha"]) 

    stations_utm: List[Tuple[str, float, float]] = []
    stations_wgs: Dict[str, Tuple[float, float]] = {}
    stations_meta: Dict[str, Dict[str, str]] = {}
    lines_meta: Dict[str, Dict[str, str]] = {}

    to_wgs = Transformer.from_crs(EPSG_UTM_SP, EPSG_WGS84, always_xy=True)

    def add_station_feats(feats: List[Dict[str, Any]], prefix: str, id_key: str, name_key: str, line_key: str) -> None:
        for f in feats:
            geom = shape(f["geometry"])
            if geom.is_empty:
                continue
            pid = str(f["properties"].get(id_key, "")).strip()
            if not pid:
                continue
            node_id = f"{prefix}:{pid}"
            x, y = float(geom.x), float(geom.y)
            stations_utm.append((node_id, x, y))
            lon, lat = to_wgs.transform(x, y)
            stations_wgs[node_id] = (float(lon), float(lat))
            stations_meta[node_id] = {
                "nm_estacao_metro_trem": str(f["properties"].get(name_key, "")),
                "nm_linha_metro_trem": str(f["properties"].get(line_key, "")),
            }

    add_station_feats(m_feats, "M", m_id_key, m_name_key, m_line_key)
    add_station_feats(t_feats, "T", t_id_key, t_name_key, t_line_key)

    point_geoms = [Point(x, y) for _, x, y in stations_utm]
    point_ids = [nid for nid, _, _ in stations_utm]
    pt_tree = STRtree(point_geoms)
    geom_to_id: Dict[int, str] = {id(g): pid for g, pid in zip(point_geoms, point_ids)}

    metro_lines, _ = read_gpkg_features(metro_lines_gpkg)
    train_lines, _ = read_gpkg_features(train_lines_gpkg)

    ml_props0 = dict(metro_lines[0]["properties"]) if metro_lines else {}
    tl_props0 = dict(train_lines[0]["properties"]) if train_lines else {}
    ml_id_key = guess_prop_key(ml_props0, ["cd_identificador_linha_metro", "cd_identificador_linha", "id", "codigo", "cd_linha", "cod_linha", "nm_linha", "nome"])
    tl_id_key = guess_prop_key(tl_props0, ["cd_identificador_linha_trem", "cd_identificador_linha", "id", "codigo", "cd_linha", "cod_linha", "nm_linha", "nome"])
    # Colunas reais nos seus GPKGs (prioridade):
    # - nm_linha_metro_trem: nome da linha (metrô/trem)
    # - nr_nome_linha: nome/identificador curto (aparece no metrô v4)
    ml_nm_key = guess_prop_key(ml_props0, ["nm_linha_metro_trem", "nm_linha", "nome", "no_linha", "ds_linha"])
    tl_nm_key = guess_prop_key(tl_props0, ["nm_linha_metro_trem", "nm_linha", "nome", "no_linha", "ds_linha"])
    ml_nr_key = guess_prop_key(ml_props0, ["nr_nome_linha", "nr_nome", "nr_linha", "linha", "sigla"])
    # No trem pode não existir nr_nome_linha; se não existir, usamos None
    tl_nr_key = (guess_prop_key(tl_props0, ["nr_nome_linha", "nr_nome", "nr_linha", "linha", "sigla"]) if tl_props0 else None)

    speed_mps = (rail_speed_kmh * 1000.0) / 3600.0
    G = nx.Graph()

    def add_edges_from_line_feats(line_feats: List[Dict[str, Any]], line_id_key: str, nm_key: str, nr_key: Optional[str], prefix: str) -> None:
        for f in line_feats:
            geom = shape(f["geometry"])
            if geom.is_empty:
                continue
            raw_id = str(f["properties"].get(line_id_key, "LINE"))
            line_id = f"{prefix}:{raw_id}"
            nm_linha = str(f["properties"].get(nm_key, raw_id))
            nr_nome = str(f["properties"].get(nr_key, "")) if nr_key else ""
            lines_meta[line_id] = {"nm_linha_metro_trem": nm_linha, "nr_nome_linha": nr_nome}
            buf = geom.buffer(snap_dist_m)
            cand_pts = pt_tree.query(buf)
            near: List[Tuple[str, Point, float]] = []
            for p_obj in cand_pts:
                # Shapely STRtree pode retornar geometrias (Shapely>=2) ou índices (Shapely<2 / builds específicas)
                if isinstance(p_obj, (int, np.integer)):
                    p = point_geoms[int(p_obj)]
                else:
                    p = p_obj
                if p.distance(geom) <= snap_dist_m:
                    pid = geom_to_id.get(id(p))
                    if pid is None:
                        continue
                    near.append((pid, p, float(geom.project(p))))
            if len(near) < 2:
                continue
            near.sort(key=lambda t: t[2])
            for i in range(len(near) - 1):
                a, pa, _ = near[i]
                b, pb, _ = near[i + 1]
                dist_m = float(pa.distance(pb))
                w = (dist_m / max(speed_mps, 0.1)) / 60.0
                if w <= 0:
                    continue
                if G.has_edge(a, b):
                    if w < G[a][b]["weight"]:
                        G[a][b]["weight"] = w
                        G[a][b]["line_id"] = line_id
                        G[a][b]["nm_linha_metro_trem"] = nm_linha
                        G[a][b]["nr_nome_linha"] = nr_nome
                else:
                    G.add_edge(a, b, weight=w, line_id=line_id, nm_linha_metro_trem=nm_linha, nr_nome_linha=nr_nome)

    add_edges_from_line_feats(metro_lines, ml_id_key, ml_nm_key, ml_nr_key, prefix='M')
    add_edges_from_line_feats(train_lines, tl_id_key, tl_nm_key, None, prefix='T')

    r = float(transfer_walk_m)

    def walk_w(dist_m: float) -> float:
        return (dist_m / max(walk_speed_mps, 0.1)) / 60.0 + float(transfer_penalty_min)

    for (nid, x, y), p in zip(stations_utm, point_geoms):
        buf = p.buffer(r)
        cand = pt_tree.query(buf)
        for q_obj in cand:
            if isinstance(q_obj, (int, np.integer)):
                q = point_geoms[int(q_obj)]
            else:
                q = q_obj
            if q is p:
                continue
            dist = float(p.distance(q))
            if dist > r:
                continue
            other = geom_to_id.get(id(q))
            if other is None:
                continue
            a, b = (nid, other) if nid < other else (other, nid)
            w = walk_w(dist)
            if G.has_edge(a, b):
                if w < G[a][b]["weight"]:
                    G[a][b]["weight"] = w
                    G[a][b]["line_id"] = "TRANSFER"
            else:
                G.add_edge(a, b, weight=w, line_id="TRANSFER", nm_linha_metro_trem="TRANSFER", nr_nome_linha="")

    return G, stations_utm, stations_wgs, stations_meta, lines_meta


def resolve_rail_seed(station_ids: List[str], seed: str) -> str:
    if seed in station_ids:
        return seed
    seed_low = seed.lower()
    for sid in station_ids:
        if seed_low in sid.lower():
            return sid
    raise ValueError(f"Seed trilhos '{seed}' não encontrado (use --list-rail-stations).")



def find_nearest_rail_station_by_coord(
    lat: float,
    lon: float,
    stations_wgs: Dict[str, Tuple[float, float]],
    stations_name: Optional[Dict[str, str]] = None,
    max_dist_m: float = 1200.0,
) -> Optional[Tuple[str, str, float]]:
    """
    Retorna a estação de trilhos mais próxima de (lat, lon).

    Saída:
      (node_id, display_name, dist_m)

    - stations_wgs: node_id -> (lon, lat)
    - stations_name: node_id -> nome amigável
    - max_dist_m: se a mais próxima estiver acima disso, retorna None
    """
    if not stations_wgs:
        return None

    to_utm = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)
    x0, y0 = to_utm.transform(float(lon), float(lat))

    best_id: Optional[str] = None
    best_d2 = float("inf")

    for nid, (slon, slat) in stations_wgs.items():
        x, y = to_utm.transform(float(slon), float(slat))
        dx = x - x0
        dy = y - y0
        d2 = dx * dx + dy * dy
        if d2 < best_d2:
            best_d2 = d2
            best_id = nid

    if best_id is None:
        return None

    dist_m = float(best_d2 ** 0.5)
    if dist_m > float(max_dist_m):
        return None

    name = best_id
    if stations_name and best_id in stations_name:
        name = stations_name[best_id]
    return best_id, name, dist_m



def load_rail_assets(
    metro_st_gpkg: Path,
    train_st_gpkg: Path,
    metro_ln_gpkg: Path,
    train_ln_gpkg: Path,
    transfer_walk_m: float,
    transfer_penalty_min: float,
    walk_speed_mps: float,
    rail_speed_kmh: float,
) -> Tuple[nx.Graph, List[Tuple[str, float, float]], Dict[str, Tuple[float, float]], Dict[str, Dict[str, str]], Dict[str, Dict[str, str]], List[str]]:
    """
    Carrega grafo de trilhos e dicionários auxiliares (WGS + nomes).
    Retorna: (G, stations_utm, stations_wgs, stations_name, rail_ids)
    """
    G, stations_utm, stations_wgs, stations_meta, lines_meta = build_rail_graph_from_geosampa(
        metro_stations_gpkg=metro_st_gpkg,
        train_stations_gpkg=train_st_gpkg,
        metro_lines_gpkg=metro_ln_gpkg,
        train_lines_gpkg=train_ln_gpkg,
        transfer_walk_m=float(transfer_walk_m),
        transfer_penalty_min=float(transfer_penalty_min),
        walk_speed_mps=float(walk_speed_mps),
        rail_speed_kmh=float(rail_speed_kmh),
    )
    rail_ids = [nid for nid, _, _ in stations_utm]
    return G, stations_utm, stations_wgs, stations_meta, lines_meta, rail_ids


# -------------------------
# Export
# -------------------------

def write_geojson(path: Path, rows: List[ZoneRow], geoms_wgs: List[Any]) -> None:
    features = []
    for row, geom in zip(rows, geoms_wgs):
        props = {
            "zone_id": row.zone_id,
            "mode": row.mode,
            "seed_id": row.seed_id,
            "source_point_id": row.source_point_id,
            "travel_time_from_seed_minutes": row.travel_time_from_seed_minutes,
            "centroid_lon": row.centroid_lon,
            "centroid_lat": row.centroid_lat,
            "flood_intersection_ratio": row.flood_intersection_ratio,
            "score": row.score,
            "trace": row.trace,
        }
        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
    fc = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")


def final_dedup_by_centroid(rows: List[ZoneRow], geoms_wgs: List[Any], radius_m: float) -> Tuple[List[ZoneRow], List[Any]]:
    to_utm = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)
    rows_sorted = sorted(zip(rows, geoms_wgs), key=lambda x: x[0].score, reverse=True)

    kept_rows: List[ZoneRow] = []
    kept_geoms: List[Any] = []
    kept_xy: List[Tuple[float, float]] = []
    r2 = float(radius_m) ** 2

    for row, geom in rows_sorted:
        c = geom.centroid
        x, y = to_utm.transform(float(c.x), float(c.y))
        ok = True
        for kx, ky in kept_xy:
            dx = x - kx; dy = y - ky
            if dx * dx + dy * dy <= r2:
                ok = False
                break
        if ok:
            kept_rows.append(row)
            kept_geoms.append(geom)
            kept_xy.append((x, y))
    return kept_rows, kept_geoms


# -------------------------
# Pipelines (bus / rail)
# -------------------------

def run_bus_pipeline(
    seeds_bus: List[str],
    stops: pd.DataFrame,
    trips: pd.DataFrame,
    stop_times: pd.DataFrame,
    routes: pd.DataFrame,
    frequencies: Optional[pd.DataFrame],
    flood_tree: STRtree,
    buffer_m: float,
    t_bus: float,
    bus_step: int,
    bus_kmax: int,
    dedupe_radius_m: float,
    departure_window: Optional[Tuple[str, str]],
    bus_lines_gpkg: Optional[Path],
) -> Tuple[List[ZoneRow], List[Any]]:
    freq_idx = build_frequency_index(frequencies)
    buslines_df = load_bus_lines_gpkg(bus_lines_gpkg)
    route_to_busline = build_route_to_busline_map(routes, buslines_df)

    # stops com coords
    stops_xy = stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]].copy()
    stops_xy["stop_id"] = stops_xy["stop_id"].astype(str)
    stops_xy["stop_lat"] = stops_xy["stop_lat"].astype(float)
    stops_xy["stop_lon"] = stops_xy["stop_lon"].astype(float)

    to_utm = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)
    stops_xy["x_utm"], stops_xy["y_utm"] = zip(*[
        to_utm.transform(float(lon), float(lat)) for lon, lat in zip(stops_xy["stop_lon"], stops_xy["stop_lat"])
    ])

    rows: List[ZoneRow] = []
    geoms: List[Any] = []

    for seed in seeds_bus:
        origin_stop_id = resolve_bus_seed_stop_id(stops, seed)
        print(f"[BUS] Expandindo seed stop_id={origin_stop_id}")

        best = compute_downstream_generalized_times(
            stop_times=stop_times,
            trips=trips,
            origin_stop_id=origin_stop_id,
            t_bus=float(t_bus),
            freq_idx=freq_idx,
            departure_window=departure_window,
        )
        if not best:
            print("[BUS] Nenhuma parada posterior dentro do tempo.")
            continue

        best = bucketize_best(best, bus_step)
        best = cap_best(best, bus_kmax)

        prio = {sid: float(info["min_gen_time"]) for sid, info in best.items()}
        cand = stops_xy[stops_xy["stop_id"].isin(list(best.keys()))].copy()
        points_utm = [(str(r["stop_id"]), float(r["x_utm"]), float(r["y_utm"])) for _, r in cand.iterrows()]
        kept = dedupe_points_by_distance_utm(points_utm, prio, float(dedupe_radius_m))
        best = {k: best[k] for k in kept if k in best}

        if not best:
            continue

        selected = stops_xy[stops_xy["stop_id"].isin(list(best.keys()))].copy()
        selected["gen_time"] = selected["stop_id"].map(lambda x: float(best[str(x)]["min_gen_time"]))
        selected["in_vehicle"] = selected["stop_id"].map(lambda x: float(best[str(x)]["min_in_vehicle"]))
        selected["wait_min"] = selected["stop_id"].map(lambda x: float(best[str(x)]["min_wait"]))
        selected["direction_id"] = selected["stop_id"].map(lambda x: best[str(x)]["direction_id"])
        selected["trip_id"] = selected["stop_id"].map(lambda x: best[str(x)]["trip_id"])
        selected["trip_headsign"] = selected["stop_id"].map(lambda x: best[str(x)]["trip_headsign"])
        selected["route_id"] = selected["stop_id"].map(lambda x: best[str(x)]["route_id"])

        points_wgs = [(str(r["stop_id"]), float(r["stop_lon"]), float(r["stop_lat"])) for _, r in selected.iterrows()]
        bufs_utm, bufs_wgs = buffers_from_points(points_wgs, float(buffer_m))
        flood_ratios = flood_ratio_for_buffers_utm(bufs_utm, flood_tree)

        for i, (_, r) in enumerate(selected.iterrows()):
            gen_t = float(r["gen_time"])
            fr = float(flood_ratios[i])
            sc = score_simple(gen_t, fr)

            geom_wgs = bufs_wgs[i]
            cx, cy = centroid_lonlat(geom_wgs)

            route_id = str(r["route_id"]) if pd.notna(r["route_id"]) else None
            bus_meta = route_to_busline.get(route_id, {}) if route_id else {}

            zid = stable_hash("bus", origin_stop_id, str(r["stop_id"]), str(buffer_m), str(r.get("direction_id")))
            rows.append(
                ZoneRow(
                    zone_id=zid,
                    mode="bus",
                    seed_id=str(origin_stop_id),
                    source_point_id=str(r["stop_id"]),
                    travel_time_from_seed_minutes=float(r["in_vehicle"]),
                    centroid_lon=cx,
                    centroid_lat=cy,
                    flood_intersection_ratio=fr,
                    score=sc,
                    trace={
                        "seed_bus_stop_id": origin_stop_id,
                        "downstream_stop_id": str(r["stop_id"]),
                        "stop_name": str(r["stop_name"]),
                        "generalized_time_min": gen_t,
                        "in_vehicle_min": float(r["in_vehicle"]),
                        "expected_wait_min": float(r["wait_min"]),
                        "direction_id": r.get("direction_id"),
                        "trip_id": str(r.get("trip_id")),
                        "trip_headsign": r.get("trip_headsign"),
                        "route_id": route_id,
                        **bus_meta,
                    },
                )
            )
            geoms.append(geom_wgs)

    return rows, geoms


def run_rail_pipeline(
    seeds_rail: List[str],
    rail_inputs_ok: bool,
    flood_tree: STRtree,
    buffer_m: float,
    t_rail: float,
    dedupe_radius_m: float,
    G_rail: nx.Graph,
    rail_stations_utm: List[Tuple[str, float, float]],
    rail_stations_wgs: Dict[str, Tuple[float, float]],
    rail_stations_meta: Dict[str, Dict[str, str]],
    rail_lines_meta: Dict[str, Dict[str, str]],
    rail_ids: List[str],
) -> Tuple[List[ZoneRow], List[Any]]:
    """
    Pipeline de trilhos usando grafo/pré-cálculos já carregados no main().
    """
    if not seeds_rail:
        return [], []
    if not rail_inputs_ok:
        print("[WARN] Trilhos indisponíveis/ilegíveis — ignorando seeds rail.")
        return [], []

    rows: List[ZoneRow] = []
    geoms: List[Any] = []

    for seed in seeds_rail:
        origin_node = resolve_rail_seed(rail_ids, seed)
        if origin_node not in G_rail:
            continue

        times = nx.single_source_dijkstra_path_length(G_rail, origin_node, cutoff=float(t_rail), weight="weight")
        times = {k: float(v) for k, v in times.items() if k != origin_node}
        if not times:
            continue

        cand_utm = [(nid, x, y) for nid, x, y in rail_stations_utm if nid in times]
        kept = dedupe_points_by_distance_utm(cand_utm, times, float(dedupe_radius_m))
        times = {k: times[k] for k in kept if k in times}

        points_wgs = [(nid, rail_stations_wgs[nid][0], rail_stations_wgs[nid][1]) for nid in times.keys()]
        nid_order = [nid for nid, _, _ in points_wgs]
        bufs_utm, bufs_wgs = buffers_from_points(points_wgs, float(buffer_m))
        flood_ratios = flood_ratio_for_buffers_utm(bufs_utm, flood_tree)

        for i, nid in enumerate(nid_order):
            dt = float(times[nid])
            path_nm_list: List[str] = []
            path_nr_list: List[str] = []
            try:
                path = nx.shortest_path(G_rail, origin_node, nid, weight='weight')
                for u, v in zip(path[:-1], path[1:]):
                    data = G_rail.get_edge_data(u, v) or {}
                    nm = str(data.get('nm_linha_metro_trem') or '')
                    nr = str(data.get('nr_nome_linha') or '')
                    if nm and (not path_nm_list or path_nm_list[-1] != nm):
                        path_nm_list.append(nm)
                    if nr and (not path_nr_list or path_nr_list[-1] != nr):
                        path_nr_list.append(nr)
            except Exception:
                pass
            fr = float(flood_ratios[i])
            sc = score_simple(dt, fr)

            geom_wgs = bufs_wgs[i]
            cx, cy = centroid_lonlat(geom_wgs)

            zid = stable_hash("rail", origin_node, nid, str(buffer_m))
            rows.append(
                ZoneRow(
                    zone_id=zid,
                    mode="rail",
                    seed_id=str(origin_node),
                    source_point_id=str(nid),
                    travel_time_from_seed_minutes=dt,
                    centroid_lon=cx,
                    centroid_lat=cy,
                    flood_intersection_ratio=fr,
                    score=sc,
                    trace={
                        "seed_rail_node": origin_node,
                        "seed_nm_estacao_metro_trem": rail_stations_meta.get(origin_node, {}).get("nm_estacao_metro_trem",""),
                        "seed_nm_linha_metro_trem": rail_stations_meta.get(origin_node, {}).get("nm_linha_metro_trem",""),
                        "reachable_node": nid,
                        "reachable_nm_estacao_metro_trem": rail_stations_meta.get(nid, {}).get("nm_estacao_metro_trem",""),
                        "reachable_nm_linha_metro_trem": rail_stations_meta.get(nid, {}).get("nm_linha_metro_trem",""),
                        "time_min": dt,
                        "path_nm_linha_metro_trem": path_nm_list,
                        "path_nr_nome_linha": path_nr_list,
                    },
                )
            )
            geoms.append(geom_wgs)

    return rows, geoms



def export_outputs(
    out_dir: Path,
    run_id: str,
    cache_dir: Path,
    params: Dict[str, Any],
    rows: List[ZoneRow],
    geoms_wgs: List[Any],
) -> None:
    ensure_dir(out_dir / "outputs")

    geojson_path = out_dir / "outputs" / "zones.geojson"
    write_geojson(geojson_path, rows, geoms_wgs)

    df = pd.DataFrame([r.__dict__ for r in rows]).sort_values("score", ascending=False)
    csv_path = out_dir / "outputs" / "ranking.csv"
    df.to_csv(csv_path, index=False)

    trace_path = out_dir / "outputs" / "trace.json"
    trace_path.write_text(
        json.dumps(
            {"run_id": run_id, "cache_dir": str(cache_dir), "params": params, "zones_generated": int(len(rows))},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[OK] Zonas geradas: {len(rows)}")
    print(f"[OK] GeoJSON: {geojson_path}")
    print(f"[OK] Ranking: {csv_path}")
    print(f"[OK] Trace: {trace_path}")


# -------------------------
# CLI / orchestration
# -------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gera zonas candidatas a partir do data_cache local (GTFS + GeoSampa).")
    p.add_argument("--cache-dir", required=True, help="Diretório data_cache (contendo gtfs/ e geosampa/).")

    p.add_argument("--seed-bus", action="append", default=[], help="Seed ônibus: stop_id ou trecho de stop_name (pode repetir).")
    p.add_argument("--seed-rail", action="append", default=[], help="Seed trilhos: 'M:<id>'/'T:<id>' ou substring (pode repetir).")
    p.add_argument("--seed-bus-coord", default=None, help="Seed ônibus por coordenadas 'lat,lon' (ex.: -23.58,-46.67).")
    p.add_argument("--auto-rail-seed", action="store_true", help="Quando usar seed por coordenadas/smoke-test, escolhe automaticamente a estação de trem/metrô mais próxima como seed_rail.")
    p.add_argument("--no-auto-rail-seed", action="store_true", help="Desliga a escolha automática de seed_rail mesmo no smoke-test.")

    p.add_argument("--buffer-m", type=float, default=600.0)
    p.add_argument("--t-bus", type=float, default=25.0)
    p.add_argument("--t-rail", type=float, default=25.0)
    p.add_argument("--seed-bus-max-dist-m", type=float, default=250.0)
    p.add_argument("--seed-rail-max-dist-m", type=float, default=1200.0)

    p.add_argument("--bus-step", type=int, default=2, help="Δt_bus (min) para amostragem por bucket")
    p.add_argument("--bus-kmax", type=int, default=60, help="K_bus máximo de paradas por seed")
    p.add_argument("--dedupe-radius-m", type=float, default=50.0)

    p.add_argument("--departure-window-start", default=None, help="Ex.: 07:00:00")
    p.add_argument("--departure-window-end", default=None, help="Ex.: 09:00:00")

    p.add_argument("--transfer-walk-m", type=float, default=500.0)
    p.add_argument("--transfer-penalty-min", type=float, default=4.0)
    p.add_argument("--walk-speed-mps", type=float, default=1.25)
    p.add_argument("--rail-speed-kmh", type=float, default=45.0)

    p.add_argument("--out-dir", default=None)
    p.add_argument("--progress", action="store_true", help="Mostra progresso (estágios/contagens).")
    p.add_argument("--no-tqdm", action="store_true", help="Desliga barra tqdm mesmo se instalada.")

    p.add_argument("--list-bus-stops", action="store_true", help="Lista exemplos de stops do GTFS.")
    p.add_argument("--list-rail-stations", action="store_true", help="Lista exemplos de estações (node_id). (Requer trilhos legíveis)")
    p.add_argument("--smoke-test", action="store_true", help="Roda teste padrão com coordenadas fixas se nenhum seed for informado.")

    return p.parse_args()


def load_inputs(cache_dir: Path) -> Dict[str, Any]:
    gtfs_dir = cache_dir / "gtfs"
    geo_dir = cache_dir / "geosampa"

    gtfs = load_gtfs_tables(gtfs_dir)

    metro_st_gpkg = geo_dir / "geoportal_estacao_metro_v2.gpkg"
    train_st_gpkg = geo_dir / "geoportal_estacao_trem_v2.gpkg"
    metro_ln_gpkg = geo_dir / "geoportal_linha_metro_v4.gpkg"
    train_ln_gpkg = geo_dir / "geoportal_linha_trem_v2.gpkg"
    flood_gpkg = geo_dir / "geoportal_mancha_inundacao_25.gpkg"

    # Linhas ônibus GPKG: tenta padrões e fallback por keywords
    bus_lines_gpkg: Optional[Path] = None
    for cand in [geo_dir / "geoportal_linha_onibus.gpkg", geo_dir / "SIRGAS_GPKG_linhaonibus.gpkg"]:
        if cand.exists():
            bus_lines_gpkg = cand
            break
    if bus_lines_gpkg is None:
        bus_lines_gpkg = find_gpkg_by_keywords(geo_dir, ["linha_onibus", "linhaonibus", "onibus"])

    rail_ok = all(p.exists() and can_open_gpkg(p) for p in [metro_st_gpkg, train_st_gpkg, metro_ln_gpkg, train_ln_gpkg])
    flood_ok = flood_gpkg.exists() and can_open_gpkg(flood_gpkg)

    # confirmação de abertura
    print_open_confirmation(
        gtfs_dir=gtfs_dir,
        geo_dir=geo_dir,
        gtfs=gtfs,
        gpkg_paths=[
            ("bus_lines_gpkg", bus_lines_gpkg),
            ("metro_stations", metro_st_gpkg),
            ("train_stations", train_st_gpkg),
            ("metro_lines", metro_ln_gpkg),
            ("train_lines", train_ln_gpkg),
            ("flood", flood_gpkg),
        ],
    )

    flood_tree = load_flood_tree(flood_gpkg) if flood_ok else STRtree([])

    return {
        "gtfs_dir": gtfs_dir,
        "geo_dir": geo_dir,
        "gtfs": gtfs,
        "bus_lines_gpkg": bus_lines_gpkg,
        "metro_st_gpkg": metro_st_gpkg,
        "train_st_gpkg": train_st_gpkg,
        "metro_ln_gpkg": metro_ln_gpkg,
        "train_ln_gpkg": train_ln_gpkg,
        "flood_gpkg": flood_gpkg,
        "rail_ok": rail_ok,
        "flood_ok": flood_ok,
        "flood_tree": flood_tree,
    }


def resolve_seeds(args: argparse.Namespace, stops: pd.DataFrame) -> Tuple[List[str], List[str]]:
    seeds_bus = list(args.seed_bus or [])
    seeds_rail = list(args.seed_rail or [])

    # smoke test: usa coordenadas padrão se nada foi fornecido
    if (not seeds_bus) and (args.seed_bus_coord is None) and (not seeds_rail) and args.smoke_test:
        args.seed_bus_coord = "-23.58485466804386, -46.69066793521605"
        print("[SMOKE TEST] Usando seed por coordenadas:", args.seed_bus_coord)

    # seed por coordenadas -> stop_id
    if args.seed_bus_coord:
        lat_s, lon_s = [x.strip() for x in args.seed_bus_coord.split(",")]
        lat = float(lat_s); lon = float(lon_s)
        seed_stop, dist_m = find_nearest_stop_id_by_coord(
            stops,
            lat=lat,
            lon=lon,
            max_dist_m=float(args.seed_bus_max_dist_m),
        )
        print(f"[BUS] Seed por coord → stop_id={seed_stop} (dist={dist_m:.1f} m)")
        seeds_bus.append(seed_stop)

    # dedupe seeds (preserva ordem)
    seen = set()
    seeds_bus2 = []
    for s in seeds_bus:
        if s not in seen:
            seeds_bus2.append(s); seen.add(s)
    return seeds_bus2, seeds_rail


def main() -> int:
    args = parse_args()
    prog = Progress(enabled=bool(args.progress or args.smoke_test), use_tqdm=(not args.no_tqdm))
    cache_dir = Path(args.cache_dir)

    inputs = load_inputs(cache_dir)
    gtfs = inputs["gtfs"]

    stops = gtfs["stops"].copy()
    trips = gtfs["trips"].copy()
    stop_times = gtfs["stop_times"].copy()
    routes = gtfs["routes"].copy()
    frequencies = gtfs.get("frequencies")

    # Pré-carrega trilhos (para listagem e auto-seed)
    G_rail = None
    rail_stations_utm: List[Tuple[str, float, float]] = []
    rail_stations_wgs: Dict[str, Tuple[float, float]] = {}
    rail_stations_meta: Dict[str, Dict[str, str]] = {}
    rail_lines_meta: Dict[str, Dict[str, str]] = {}
    rail_ids: List[str] = []
    if bool(inputs.get("rail_ok")):
        prog.stage("Construindo grafo de trilhos (metrô+trem + integrações)")
        G_rail, rail_stations_utm, rail_stations_wgs, rail_stations_meta, rail_lines_meta, rail_ids = load_rail_assets(
            metro_st_gpkg=inputs["metro_st_gpkg"],
            train_st_gpkg=inputs["train_st_gpkg"],
            metro_ln_gpkg=inputs["metro_ln_gpkg"],
            train_ln_gpkg=inputs["train_ln_gpkg"],
            transfer_walk_m=float(args.transfer_walk_m),
            transfer_penalty_min=float(args.transfer_penalty_min),
            walk_speed_mps=float(args.walk_speed_mps),
            rail_speed_kmh=float(args.rail_speed_kmh),
        )
        prog.info(f"Trilhos: nós={len(rail_ids):,} | arestas={G_rail.number_of_edges():,}")


    # lista stops
    if args.list_bus_stops:
        print(stops[["stop_id", "stop_name"]].head(120).to_string(index=False))
        return 0

    seeds_bus, seeds_rail = resolve_seeds(args, stops)

    # Auto seed rail: default ON no smoke-test (a menos que --no-auto-rail-seed)
    auto_rail_enabled = bool(args.auto_rail_seed) or (bool(args.smoke_test) and not bool(args.no_auto_rail_seed))
    if auto_rail_enabled and (not seeds_rail) and bool(inputs.get("rail_ok")) and rail_stations_wgs:
        # tenta usar a coordenada de seed de ônibus (smoke-test / seed-bus-coord)
        coord = getattr(args, "seed_bus_coord", None)
        if coord:
            try:
                lat_s, lon_s = coord.split(",")
                lat0 = float(lat_s.strip()); lon0 = float(lon_s.strip())
                nearest = find_nearest_rail_station_by_coord(
                    lat=lat0,
                    lon=lon0,
                    stations_wgs=rail_stations_wgs,
                    stations_name={k:v.get('nm_estacao_metro_trem','') for k,v in rail_stations_meta.items()},
                    max_dist_m=float(args.seed_rail_max_dist_m),
                )
                if nearest is not None:
                    nid, nm, dist_m = nearest
                    seeds_rail = [nid]
                    prog.info(f'rail seed escolhido: {nm} ({nid}) (dist={dist_m:.1f} m)')
                else:
                    prog.warn('Nenhuma estação de trilhos dentro do raio para auto seed.')
            except Exception as e:
                prog.warn(f'Falha ao escolher seed de trilhos automaticamente: {e}')

    # (opcional) listar estações
    if args.list_rail_stations:
        if not inputs["rail_ok"] or G_rail is None:
            print("[WARN] Trilhos indisponíveis/ilegíveis. Não é possível listar estações.")
            return 0
        print("\n".join(rail_ids[:300]))
        return 0

    flood_tree: STRtree = inputs["flood_tree"]
    if not inputs["flood_ok"]:
        print("[WARN] Arquivo de inundação indisponível/ilegível — flood_ratio será 0.0.")

    departure_window = None
    if args.departure_window_start and args.departure_window_end:
        departure_window = (args.departure_window_start, args.departure_window_end)

    run_id = now_id()
    out_dir = Path(args.out_dir) if args.out_dir else Path("./runs") / run_id

    all_rows: List[ZoneRow] = []
    all_geoms: List[Any] = []

    # BUS
    if seeds_bus:
        r_bus, g_bus = run_bus_pipeline(
            seeds_bus=seeds_bus,
            stops=stops,
            trips=trips,
            stop_times=stop_times,
            routes=routes,
            frequencies=frequencies,
            flood_tree=flood_tree,
            buffer_m=float(args.buffer_m),
            t_bus=float(args.t_bus),
            bus_step=int(args.bus_step),
            bus_kmax=int(args.bus_kmax),
            dedupe_radius_m=float(args.dedupe_radius_m),
            departure_window=departure_window,
            bus_lines_gpkg=inputs["bus_lines_gpkg"],
        )
        all_rows.extend(r_bus); all_geoms.extend(g_bus)

    # RAIL
    if seeds_rail:
        r_rail, g_rail = run_rail_pipeline(
            seeds_rail=seeds_rail,
            rail_inputs_ok=bool(inputs["rail_ok"]),
            flood_tree=flood_tree,
            buffer_m=float(args.buffer_m),
            t_rail=float(args.t_rail),
            dedupe_radius_m=float(args.dedupe_radius_m),
            G_rail=G_rail,
            rail_stations_utm=rail_stations_utm,
            rail_stations_wgs=rail_stations_wgs,
            rail_stations_meta=rail_stations_meta,
            rail_lines_meta=rail_lines_meta,
            rail_ids=rail_ids,
        )
        all_rows.extend(r_rail); all_geoms.extend(g_rail)

    if not all_rows:
        prog.warn("Nenhuma zona gerada. Verifique seeds/tempos/janela.")
        prog.done("Execução finalizada (sem zonas)")
        return 0

    kept_rows, kept_geoms = final_dedup_by_centroid(all_rows, all_geoms, radius_m=float(args.dedupe_radius_m))

    params = {
        "buffer_m": args.buffer_m,
        "t_bus": args.t_bus,
        "t_rail": args.t_rail,
        "bus_step": args.bus_step,
        "bus_kmax": args.bus_kmax,
        "dedupe_radius_m": args.dedupe_radius_m,
        "departure_window": [args.departure_window_start, args.departure_window_end],
        "transfer_walk_m": args.transfer_walk_m,
        "transfer_penalty_min": args.transfer_penalty_min,
        "walk_speed_mps": args.walk_speed_mps,
        "rail_speed_kmh": args.rail_speed_kmh,
        "seeds_bus": seeds_bus,
        "seeds_rail": seeds_rail,
        "bus_lines_gpkg": str(inputs["bus_lines_gpkg"]) if inputs["bus_lines_gpkg"] else None,
        "rail_ok": bool(inputs["rail_ok"]),
        "flood_ok": bool(inputs["flood_ok"]),
    }

    export_outputs(out_dir=out_dir, run_id=run_id, cache_dir=cache_dir, params=params, rows=kept_rows, geoms_wgs=kept_geoms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
