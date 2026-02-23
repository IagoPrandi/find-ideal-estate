from __future__ import annotations

import os
import re
import math
import time
import json
import zipfile
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Playwright só é usado se realmente precisarmos descobrir a URL do XLSX na SSP
# Playwright é importado sob demanda (apenas se precisarmos descobrir o link do XLSX na SSP)

# =========================
# Config
# =========================
CKAN_BASE = "https://dadosabertos.sp.gov.br/api/3/action"
RESOURCE_CONSULTAS_ID = "228ab9f3-0b6b-41fd-b839-dde5ca8cb92f"  # CONSULTAS

CEM_DPS_ZIP_URL = "https://centrodametropole.fflch.usp.br/pt-br/file/18904/download?token=5-jX54Ss"

USER_AGENT = "imovel-ideal-crime-client/2.0"

# Arquivos de cache
XLSX_NAME = "dados_criminais_{ano}.xlsx"
PQ_NAME = "dados_criminais_{ano}.parquet"
XLSX_URL_CACHE = "dados_criminais_{ano}.url.json"

CEM_ZIP_NAME = "CEM_DistritosPoliciais_Delegacias.zip"
CEM_EXTRACT_DIR = "_cem_extract"
CEM_DPS_PQ = "cem_delegacias.parquet"

CITY_COL_CANDIDATES = [
    "MUNICIPIO_CIRCUNSCRICAO",
    "MUNICIPIO_ELABORACAO",
    "MUNICIPIO_FATO",
    "MUNICIPIO",
    "CIDADE",
    "NOME_MUNICIPIO",
]


DATE_COL_CANDIDATES = [
    "DATA_FATO",
    "DATA_OCORRENCIA",
    "DATA_REGISTRO",
    "DATA_BO",
    "DATA_ELABORACAO",
    "DATAHORA_FATO",
    "DATA_HORA_FATO",
    "DATA",
]

# Colunas mínimas necessárias do XLSX SSP (inclui coluna de município, se existir)
WANTED_COLS = [
    "LATITUDE",
    "LONGITUDE",
    "NATUREZA_APURADA",
    "NOME_DELEGACIA_CIRCUNSCRICAO",
    *CITY_COL_CANDIDATES,
    *DATE_COL_CANDIDATES,
]

# =========================
# Logging
# =========================
LOG = logging.getLogger("segurancaRegiao")


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    lvl = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parquet_engine() -> Optional[str]:
    """Retorna o engine preferido para Parquet (pyarrow), se disponível."""
    try:
        import pyarrow  # noqa: F401

        return "pyarrow"
    except Exception:
        return None


# =========================
# Utilidades

def pick_city_column(df: pd.DataFrame) -> Optional[str]:
    """Retorna o nome da coluna de município, se existir no dataframe."""
    for c in CITY_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def pick_date_column(df: pd.DataFrame) -> Optional[str]:
    """Retorna o nome da coluna de data, se existir no dataframe."""
    for c in DATE_COL_CANDIDATES:
        if c in df.columns:
            return c
    return None


def parse_date_series(s: pd.Series) -> pd.Series:
    """Converte uma coluna de data/hora para datetime (normalizado para dia)."""
    # tenta parsing robusto (muitos formatos possíveis)
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)
    # algumas bases podem vir como string com hora -> normaliza para dia
    return dt.dt.floor("D")

def normalize_city_name(s: str) -> str:
    """Normaliza nomes de município para comparação simples (sem dependências)."""
    s = str(s or "").strip().upper()
    # cobre 'SÃO PAULO' e casos próximos
    s = (
        s.replace("Ã", "A")
        .replace("Á", "A")
        .replace("À", "A")
        .replace("Â", "A")
        .replace("Ä", "A")
        .replace("Õ", "O")
        .replace("Ó", "O")
        .replace("Ò", "O")
        .replace("Ô", "O")
        .replace("Ö", "O")
        .replace("Ç", "C")
    )
    return s

# =========================

def file_ok(path: str, min_bytes: int = 1024) -> bool:
    try:
        return os.path.exists(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def atomic_download(url: str, out_path: str, force: bool = False, min_bytes: int = 50_000) -> bool:
    """Baixa um arquivo apenas se necessário. Usa escrita atômica (Windows-safe)."""
    if not force and file_ok(out_path, min_bytes=min_bytes):
        LOG.info("Cache hit (download): %s", out_path)
        return False

    ensure_dir(os.path.dirname(out_path))
    tmp_path = out_path + ".part"
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    LOG.info("Baixando: %s -> %s", url, out_path)
    t0 = time.time()
    with requests.get(url, stream=True, timeout=180, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    # troca atômica
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
    os.replace(tmp_path, out_path)

    dt = time.time() - t0
    try:
        LOG.info("Download concluído: %.1f MB em %.1fs", os.path.getsize(out_path) / (1024 * 1024), dt)
    except OSError:
        LOG.info("Download concluído em %.1fs", dt)
    return True


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# =========================
# CKAN
# =========================
@dataclass
class CKANClient:
    api_key: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        h = {"User-Agent": USER_AGENT}
        if self.api_key:
            h["Authorization"] = self.api_key
        return h

    def resource_show(self, resource_id: str) -> dict:
        url = f"{CKAN_BASE}/resource_show"
        resp = requests.get(url, params={"id": resource_id}, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"CKAN resource_show falhou: {data}")
        return data["result"]


# =========================
# SSP: descobrir URL do XLSX (somente se necessário)
# =========================

def find_ssp_xlsx_url_playwright(ssp_consultas_url: str, ano: int) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError(
            "Playwright não está instalado. Instale com: pip install playwright && python -m playwright install chromium"
        ) from e

    year_pat = re.compile(rf"\b{ano}\b")

    def score_link(href: str, text: str) -> int:
        h = (href or "").lower()
        t = (text or "").lower()
        s = 0
        if ".xlsx" in h:
            s += 5
        if "crim" in h or "crim" in t:
            s += 3
        if "dados criminais" in t or "dados criminais" in h:
            s += 4
        if year_pat.search(h) or year_pat.search(t):
            s += 8
        return s

    LOG.info("SSP: resolvendo link do XLSX %s via Playwright", ano)
    t0 = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(ssp_consultas_url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(3500)

        anchors = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(a => ({href: a.href, text: (a.innerText||'').trim()}))",
        )

        candidates = []
        for a in anchors:
            href = a.get("href", "")
            text = a.get("text", "")
            if ".xlsx" in href.lower():
                candidates.append((score_link(href, text), href))

        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            url = candidates[0][1]
            browser.close()
            LOG.info("SSP: link do XLSX encontrado: %s (%.1fs)", url, time.time() - t0)
            return url

        # tentativa de clique
        try:
            page.get_by_text("Dados criminais", exact=False).first.click(timeout=5000)
            page.get_by_text(str(ano), exact=False).first.click(timeout=5000)
            page.wait_for_timeout(3500)

            anchors = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(a => ({href: a.href, text: (a.innerText||'').trim()}))",
            )
            candidates = []
            for a in anchors:
                href = a.get("href", "")
                text = a.get("text", "")
                if ".xlsx" in href.lower():
                    candidates.append((score_link(href, text), href))

            if candidates:
                candidates.sort(reverse=True, key=lambda x: x[0])
                url = candidates[0][1]
                LOG.info("SSP: link do XLSX encontrado após clique: %s (%.1fs)", url, time.time() - t0)
                return url
        finally:
            browser.close()

    raise RuntimeError("Playwright não encontrou link .xlsx na página da SSP.")


def resolve_ssp_xlsx_url(cache_dir: str, ano: int, api_key: Optional[str]) -> str:
    """Resolve e cacheia a URL do XLSX do ano via CKAN -> SSP. Só chamado quando não há XLSX local."""
    cache_path = os.path.join(cache_dir, XLSX_URL_CACHE.format(ano=ano))
    if file_ok(cache_path, min_bytes=20):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                js = json.load(f)
            if js.get("ano") == ano and js.get("xlsx_url"):
                LOG.info("SSP: URL do XLSX em cache: %s", js["xlsx_url"])
                return js["xlsx_url"]
        except Exception:
            pass

    ckan = CKANClient(api_key=api_key)
    resource = ckan.resource_show(RESOURCE_CONSULTAS_ID)
    ssp_consultas_url = resource.get("url")
    if not ssp_consultas_url:
        raise RuntimeError("CKAN resource_show não retornou 'url' para CONSULTAS.")

    xlsx_url = find_ssp_xlsx_url_playwright(ssp_consultas_url, ano)
    ensure_dir(cache_dir)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"ano": ano, "xlsx_url": xlsx_url, "ssp_consultas_url": ssp_consultas_url}, f, ensure_ascii=False)
    except Exception:
        pass
    return xlsx_url


# =========================
# Leitura e cache das ocorrências
# =========================

def _to_float_safe(x: Any) -> float:
    if pd.isna(x):
        return float("nan")
    s = str(x).strip().replace("\u00a0", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return pd.to_numeric(s, errors="coerce")


def add_dp_num(df: pd.DataFrame) -> pd.DataFrame:
    # Vetorizado: extrai número do DP da string
    extracted = (
        df["NOME_DELEGACIA_CIRCUNSCRICAO"]
        .astype(str)
        .str.lower()
        .str.extract(r"\b(\d{1,3})\s*(?:o|º|ª)?\s*(?:dp|d p|d\.p|distrito)\b")[0]
    )
    df["DP_NUM"] = pd.to_numeric(extracted, errors="coerce").astype("Int64")
    return df


def load_crime_data_from_xlsx(xlsx_path: str) -> pd.DataFrame:
    LOG.info("Lendo XLSX de ocorrências: %s", xlsx_path)
    t0 = time.time()

    frames = []
    with pd.ExcelFile(xlsx_path, engine="openpyxl") as xls:
        sheets = [s for s in xls.sheet_names if "campos" not in s.lower()]
        LOG.info("Abas encontradas: %d", len(xls.sheet_names))
        for sheet in sheets:
            LOG.info("Lendo aba: %s", sheet)
            df = pd.read_excel(xls, sheet_name=sheet, usecols=lambda c: c in WANTED_COLS)
            frames.append(df)

    if not frames:
        raise RuntimeError("Nenhuma aba de dados foi lida do XLSX.")

    data = pd.concat(frames, ignore_index=True)
    LOG.info("Linhas brutas (concat): %d", len(data))

    data = data.dropna(subset=["NATUREZA_APURADA", "NOME_DELEGACIA_CIRCUNSCRICAO"])
    data["LATITUDE"] = data["LATITUDE"].map(_to_float_safe)
    data["LONGITUDE"] = data["LONGITUDE"].map(_to_float_safe)
    data = data.dropna(subset=["LATITUDE", "LONGITUDE"])

    # DATA_DIA (para métricas por dia)
    date_col = pick_date_column(data)
    if date_col:
        data["DATA_DIA"] = parse_date_series(data[date_col])
    else:
        data["DATA_DIA"] = pd.NaT

    # DP_NUM pré-calculado
    data = add_dp_num(data)

    LOG.info(
        "Linhas com coords válidas: %d | DPs distintas: %d | Tempo: %.1fs",
        len(data),
        data["DP_NUM"].nunique(dropna=True),
        time.time() - t0,
    )
    return data


def load_occurrences(cache_dir: str, ano: int, api_key: Optional[str]) -> Tuple[pd.DataFrame, str]:
    """
    Carrega ocorrências priorizando Parquet. Retorna (df, origem_url).

    Regra:
    - Se Parquet existir e contiver colunas mínimas + alguma coluna de município + alguma coluna de data (ou DATA_DIA),
      usa ele.
    - Se Parquet existir mas faltar município e/ou data, reconstrói a partir do XLSX e sobrescreve o Parquet.
      (isso acontece quando você gerou o cache antigo sem as colunas de município/data)
    """
    xlsx_path = os.path.join(cache_dir, XLSX_NAME.format(ano=ano))
    pq_path = os.path.join(cache_dir, PQ_NAME.format(ano=ano))

    base_cols = [
        "LATITUDE",
        "LONGITUDE",
        "NATUREZA_APURADA",
        "NOME_DELEGACIA_CIRCUNSCRICAO",
    ]

    def has_any_city_col(df: pd.DataFrame) -> bool:
        return any(c in df.columns for c in CITY_COL_CANDIDATES)

    def has_any_date_col(df: pd.DataFrame) -> bool:
        # DATA_DIA já vale como "tem data"
        if "DATA_DIA" in df.columns:
            return True
        # ou qualquer coluna candidata de data que seu pick_date_column reconheça
        return pick_date_column(df) is not None

    eng = parquet_engine()

    # 1) Parquet (preferência)
    if file_ok(pq_path, min_bytes=10_000):
        LOG.info("SSP: usando Parquet em cache: %s", pq_path)
        t0 = time.time()

        # NÃO passe columns=[...] aqui, porque caches antigos podem não ter colunas novas
        df = pd.read_parquet(pq_path, engine=eng) if eng else pd.read_parquet(pq_path)

        missing_base = [c for c in base_cols if c not in df.columns]
        need_rebuild = False

        if missing_base:
            LOG.warning("Parquet em cache está incompleto (faltando %s). Vou reconstruir via XLSX.", missing_base)
            need_rebuild = True
        if not has_any_city_col(df):
            LOG.warning("Parquet em cache não tem coluna de município. Vou reconstruir via XLSX.")
            need_rebuild = True
        if not has_any_date_col(df):
            LOG.warning("Parquet em cache não tem coluna de data/DATA_DIA. Vou reconstruir via XLSX.")
            need_rebuild = True

        if not need_rebuild:
            # garante DP_NUM
            changed = False
            if "DP_NUM" not in df.columns:
                LOG.info("Parquet sem DP_NUM. Construindo DP_NUM...")
                df = add_dp_num(df)
                changed = True

            # garante DATA_DIA
            if "DATA_DIA" not in df.columns:
                date_col = pick_date_column(df)
                if date_col:
                    LOG.info("Parquet sem DATA_DIA. Construindo DATA_DIA a partir de '%s'...", date_col)
                    df["DATA_DIA"] = parse_date_series(df[date_col])
                    changed = True

            # se alterou, regrava o parquet
            if changed:
                LOG.info("Regravando Parquet atualizado: %s", pq_path)
                if eng:
                    df.to_parquet(pq_path, index=False, engine=eng)
                else:
                    df.to_parquet(pq_path, index=False)

            LOG.info("Parquet carregado: %d linhas em %.1fs", len(df), time.time() - t0)
            return df, "(cache parquet)"

        # se chegou aqui: vai reconstruir via XLSX (continua fluxo abaixo)

    # 2) XLSX local (se existe)
    if file_ok(xlsx_path, min_bytes=50_000):
        LOG.info("SSP: usando XLSX em cache: %s", xlsx_path)
        df = load_crime_data_from_xlsx(xlsx_path)

        # garante DP_NUM
        df = add_dp_num(df)

        # garante DATA_DIA
        if "DATA_DIA" not in df.columns:
            date_col = pick_date_column(df)
            if not date_col:
                raise RuntimeError(
                    "O XLSX não contém colunas de data reconhecidas; não dá para comparar média diária com a cidade de São Paulo. "
                    f"Colunas disponíveis: {list(df.columns)}"
                )
            df["DATA_DIA"] = parse_date_series(df[date_col])

        if not has_any_city_col(df):
            raise RuntimeError(
                "O XLSX não contém colunas de município reconhecidas; não dá para comparar média diária com a cidade de São Paulo. "
                f"Colunas disponíveis: {list(df.columns)}"
            )

        LOG.info("SSP: salvando Parquet cache (com município + data): %s", pq_path)
        if eng:
            df.to_parquet(pq_path, index=False, engine=eng)
        else:
            df.to_parquet(pq_path, index=False)
        return df, "(cache xlsx)"

    # 3) Precisamos baixar XLSX (via CKAN + Playwright)
    xlsx_url = resolve_ssp_xlsx_url(cache_dir, ano, api_key)
    atomic_download(xlsx_url, xlsx_path, force=False, min_bytes=50_000)

    df = load_crime_data_from_xlsx(xlsx_path)
    if (not has_any_city_col(df)) or (not has_any_date_col(df)):
        raise RuntimeError(
            "O XLSX baixado não contém colunas de município e/ou data reconhecidas; não dá para comparar média diária com a cidade de São Paulo. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    LOG.info("SSP: salvando Parquet cache (com município): %s", pq_path)
    if eng:
        df.to_parquet(pq_path, index=False, engine=eng)
    else:
        df.to_parquet(pq_path, index=False)
    return df, xlsx_url
   
# =========================
# Métricas
# =========================

def occurrences_by_crime_within_radius(df: pd.DataFrame, ref_lat: float, ref_lon: float, radius_km: float) -> Dict[str, int]:
    """Mantido por compatibilidade. Use filter_occurrences_within_radius para evitar recomputação."""
    within_df, _ = filter_occurrences_within_radius(df, ref_lat, ref_lon, radius_km)
    return within_df["NATUREZA_APURADA"].value_counts().to_dict()


def filter_occurrences_within_radius(
    df: pd.DataFrame, ref_lat: float, ref_lon: float, radius_km: float
) -> Tuple[pd.DataFrame, np.ndarray]:
    """Filtra ocorrências dentro de um raio (km) de forma vetorizada.

    Retorna (within_df, mask_bool).
    """
    LOG.info("Calculando ocorrências por delito no raio: %.2f km", radius_km)
    t0 = time.time()

    lat = df["LATITUDE"].to_numpy(dtype="float64")
    lon = df["LONGITUDE"].to_numpy(dtype="float64")

    R = 6371.0088
    phi1 = np.radians(ref_lat)
    phi2 = np.radians(lat)
    dphi = np.radians(lat - ref_lat)
    dlmb = np.radians(lon - ref_lon)

    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlmb / 2) ** 2
    d = 2 * R * np.arcsin(np.sqrt(a))

    mask = d <= radius_km
    within = df.loc[mask]
    LOG.info("Ocorrências dentro do raio: %d (%.2fs)", int(mask.sum()), time.time() - t0)
    return within, mask



def build_regiao_vs_cidade_sp_media_diaria(
    region_df: pd.DataFrame,
    city_df: pd.DataFrame,
    radius_km: float,
    top_n: int = 30,
) -> Dict[str, Any]:
    """Comparativo Região vs Cidade de São Paulo baseado em *média diária de ocorrências* (mesmo período).

    Retorna:
    - periodo_inicio, periodo_fim, num_dias
    - regiao_total, cidade_total
    - regiao_media_dia, cidade_media_dia, delta_abs_por_dia, delta_pct_vs_cidade
    - itens_por_delito (top_n por qtd na região), cada item com:
        - regiao_qtd, cidade_qtd
        - regiao_media_dia, cidade_media_dia
        - share_da_cidade (regiao_qtd / cidade_qtd)
        - delta_pct_media_dia (regiao_media_dia / cidade_media_dia - 1)
    """
    date_col = "DATA_DIA" if "DATA_DIA" in region_df.columns else pick_date_column(region_df)
    if not date_col:
        return {"erro": "Sem coluna de data para calcular média diária."}

    # Normaliza para dia, caso venha como datetime com hora
    reg_dates = parse_date_series(region_df[date_col]) if date_col != "DATA_DIA" else region_df["DATA_DIA"]
    city_dates = parse_date_series(city_df[date_col]) if date_col != "DATA_DIA" else city_df["DATA_DIA"]

    # período comum: usa o intervalo global (min/max) considerando ambos
    min_date = pd.concat([reg_dates, city_dates], ignore_index=True).min()
    max_date = pd.concat([reg_dates, city_dates], ignore_index=True).max()

    if pd.isna(min_date) or pd.isna(max_date):
        return {"erro": "Datas inválidas (NaT) — não foi possível definir o período."}

    num_days = int((max_date - min_date).days) + 1
    if num_days <= 0:
        num_days = 1

    reg_total = int(len(region_df))
    city_total = int(len(city_df))

    reg_mean = reg_total / num_days
    city_mean = city_total / num_days

    delta_abs = reg_mean - city_mean
    delta_pct = (reg_mean / city_mean - 1) if city_mean > 0 else None

    # Por delito (top_n na região)
    reg_counts = region_df["NATUREZA_APURADA"].value_counts()
    city_counts = city_df["NATUREZA_APURADA"].value_counts()

    itens = []
    for crime, reg_qtd in reg_counts.head(top_n).items():
        reg_qtd = int(reg_qtd)
        cid_qtd = int(city_counts.get(crime, 0))

        reg_md = reg_qtd / num_days
        cid_md = (cid_qtd / num_days) if cid_qtd > 0 else 0.0

        share_city = (reg_qtd / cid_qtd) if cid_qtd > 0 else None
        delta_md_pct = (reg_md / cid_md - 1) if cid_md > 0 else None

        itens.append(
            {
                "tipo_delito": crime,
                "regiao_qtd": reg_qtd,
                "cidade_qtd": cid_qtd,
                "regiao_media_dia": reg_md,
                "cidade_media_dia": cid_md if cid_qtd > 0 else None,
                "share_da_cidade": share_city,
                "delta_pct_media_dia": delta_md_pct,
            }
        )

    return {
        "cidade": "S.PAULO",
        "periodo_inicio": str(min_date.date()),
        "periodo_fim": str(max_date.date()),
        "num_dias": num_days,
        "raio_km": float(radius_km),
        "regiao_total": reg_total,
        "cidade_total": city_total,
        "regiao_media_dia": reg_mean,
        "cidade_media_dia": city_mean,
        "delta_abs_por_dia": delta_abs,
        "delta_pct_vs_cidade": delta_pct,
        "itens_por_delito": itens,
    }


def read_text_with_fallback(path: str) -> str:
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "rb") as f:
        return f.read().decode("latin-1", errors="ignore")


def load_delegacias_from_cem(cache_dir: str) -> pd.DataFrame:
    """Carrega delegacias do CEM. Cacheia em Parquet para não parsear shapefile toda vez."""
    eng = parquet_engine()
    dps_pq = os.path.join(cache_dir, CEM_DPS_PQ)
    if file_ok(dps_pq, min_bytes=2_000):
        LOG.info("CEM/USP: usando delegacias em cache: %s", dps_pq)
        if eng:
            return pd.read_parquet(dps_pq, engine=eng)
        return pd.read_parquet(dps_pq)

    # imports opcionais
    try:
        import shapefile  # pyshp
        from pyproj import CRS, Transformer
        from unidecode import unidecode
    except Exception as e:
        raise RuntimeError("Dependências do CEM ausentes. Instale: pyshp pyproj unidecode") from e

    zip_path = os.path.join(cache_dir, CEM_ZIP_NAME)
    atomic_download(CEM_DPS_ZIP_URL, zip_path, force=False, min_bytes=50_000)

    extract_dir = os.path.join(cache_dir, CEM_EXTRACT_DIR)
    ensure_dir(extract_dir)

    # evita extrair sempre
    shp_existing = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith(".shp"):
                shp_existing.append(os.path.join(root, f))
    if not shp_existing:
        LOG.info("CEM/USP: extraindo ZIP para %s", extract_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    else:
        LOG.info("CEM/USP: extração já existe (%d .shp encontrados)", len(shp_existing))

    # localiza shapefile de pontos
    shp_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith(".shp"):
                shp_files.append(os.path.join(root, f))

    if not shp_files:
        raise RuntimeError("CEM/USP: nenhum .shp encontrado após extração.")

    point_reader = None
    point_shp_path = None

    for shp_path in shp_files:
        LOG.info("CEM/USP: analisando shapefile: %s", os.path.basename(shp_path))

        # tenta encodings comuns (DBF)
        reader = None
        for enc in ("cp1252", "latin1", "utf-8"):
            try:
                reader = shapefile.Reader(shp_path, encoding=enc)
                break
            except UnicodeDecodeError:
                continue

        if reader is None:
            LOG.warning("CEM/USP: não foi possível abrir DBF (encoding) para %s", shp_path)
            continue

        if reader.shapeType in (1, 11, 21):
            point_reader = reader
            point_shp_path = shp_path
            LOG.info("CEM/USP: shapefile de pontos detectado. Registros: %d", len(reader))
            break
        else:
            LOG.info("CEM/USP: ignorando (não é POINT). shapeType=%s", reader.shapeType)

    if point_reader is None or point_shp_path is None:
        raise RuntimeError("CEM/USP: não encontrei shapefile POINT de delegacias no ZIP.")

    fields = [f[0] for f in point_reader.fields[1:]]
    fields_norm = {f: unidecode(str(f).lower()) for f in fields}

    cand_name = None
    cand_code = None
    for f, fn in fields_norm.items():
        if cand_name is None and ("nome" in fn or "deleg" in fn or fn == "dp"):
            cand_name = f
        if cand_code is None and (("cod" in fn and "dp" in fn) or fn in ("dp", "cod_dp", "codigo_dp")):
            cand_code = f

    # CRS via .prj
    base = os.path.splitext(point_shp_path)[0]
    prj_path = base + ".prj"
    transformer = None
    if os.path.exists(prj_path):
        try:
            wkt = read_text_with_fallback(prj_path)
            src = CRS.from_wkt(wkt)
            dst = CRS.from_epsg(4326)
            if src != dst:
                transformer = Transformer.from_crs(src, dst, always_xy=True)
        except Exception:
            transformer = None

    def extract_dp_number(name: str) -> Optional[int]:
        s = unidecode(str(name or "").lower())
        m = re.search(r"\b(\d{1,3})\s*(?:o|º|ª)?\s*(?:dp|d p|d\.p|distrito)\b", s)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    rows = []
    for rec, geom in zip(point_reader.records(), point_reader.shapes()):
        if not geom.points:
            continue
        x, y = geom.points[0]
        if transformer:
            lon, lat = transformer.transform(x, y)
        else:
            lon, lat = x, y

        nome = ""
        dp_num = None

        if cand_name and cand_name in fields:
            nome = str(rec[fields.index(cand_name)] or "").strip()
        if cand_code and cand_code in fields:
            raw = rec[fields.index(cand_code)]
            try:
                dp_num = int(str(raw).strip())
            except Exception:
                dp_num = None
        if dp_num is None and nome:
            dp_num = extract_dp_number(nome)

        rows.append({"dp_num": dp_num, "nome": nome, "lat": float(lat), "lon": float(lon), "fonte": "CEM/USP"})

    dps_df = pd.DataFrame(rows).dropna(subset=["lat", "lon"]).copy()
    if dps_df["dp_num"].notna().any():
        dps_df = dps_df.dropna(subset=["dp_num"]).copy()
        dps_df["dp_num"] = dps_df["dp_num"].astype(int)

    if dps_df.empty:
        raise RuntimeError("CEM/USP: não foi possível extrair pontos de delegacias.")

    LOG.info("CEM/USP: delegacias carregadas: %d", len(dps_df))
    if eng:
        dps_df.to_parquet(dps_pq, index=False, engine=eng)
    else:
        dps_df.to_parquet(dps_pq, index=False)
    return dps_df


# =========================
# Delegacias mais próximas + crimes por DP
# =========================

def nearest_dps_and_crimes(occ_df: pd.DataFrame, dps_df: pd.DataFrame, ref_lat: float, ref_lon: float, k: int = 2) -> Dict[str, Dict[str, Any]]:
    LOG.info("Calculando %d DPs mais próximas do ponto (%.6f, %.6f)", k, ref_lat, ref_lon)

    # DPs são poucas (114), apply ok
    dps = dps_df.copy()
    dps["dist_km"] = dps.apply(lambda r: haversine_km(ref_lat, ref_lon, float(r["lat"]), float(r["lon"])), axis=1)
    nearest = dps.sort_values("dist_km").head(k)

    # Para performance: calcula estatísticas de crimes para as DPs selecionadas em uma única passada.
    dp_nums = [int(x) for x in nearest["dp_num"].tolist() if pd.notna(x)]
    if len(dp_nums) < k:
        raise RuntimeError("CEM retornou DPs sem dp_num suficiente para o cálculo.")

    t0 = time.time()
    filtered = occ_df.loc[occ_df["DP_NUM"].isin(dp_nums), ["DP_NUM", "NATUREZA_APURADA"]]
    totals = filtered["DP_NUM"].value_counts()
    grouped = filtered.groupby(["DP_NUM", "NATUREZA_APURADA"], sort=False).size()
    LOG.debug("Agregação DP_NUM x delito concluída em %.2fs", time.time() - t0)

    out: Dict[str, Dict[str, Any]] = {}
    for _, dp in nearest.iterrows():
        dp_num = int(dp["dp_num"]) if pd.notna(dp.get("dp_num")) else None
        dp_nome = str(dp.get("nome") or "").strip()
        label = dp_nome or (f"DP {dp_num:03d}" if dp_num is not None else "DP (sem id)")
        if dp_num is None:
            raise RuntimeError(f"DP sem dp_num no CEM para label='{label}'.")

        # recupera contagens sem materializar subset grande
        counts_series = grouped.loc[dp_num] if dp_num in grouped.index.get_level_values(0) else pd.Series(dtype="int64")
        out[label] = {
            "dp_num": dp_num,
            "dist_km": float(dp["dist_km"]),
            "coord_dp": (float(dp["lat"]), float(dp["lon"])),
            "fonte_dp": str(dp.get("fonte") or ""),
            "total_ocorrencias": int(totals.get(dp_num, 0)),
            "ocorrencias_por_tipo": counts_series.to_dict(),
        }

    return out


# =========================
# Pipeline
# =========================

def run_query(ref_lat: float, ref_lon: float, radius_km: float, ano: int = 2025) -> Dict[str, Any]:
    setup_logging()
    t_all = time.time()

    load_dotenv()
    api_key = os.getenv("SSP_SECRET_KEY")

    cache_dir = os.path.join(os.path.dirname(__file__), "data_cache")
    ensure_dir(cache_dir)

    LOG.info("Iniciando pipeline | ano=%s | raio=%.2f km | ref=(%.6f, %.6f)", ano, radius_km, ref_lat, ref_lon)

    # 1) Ocorrências (Parquet preferencial)
    occ_df, xlsx_url_used = load_occurrences(cache_dir, ano, api_key)

    # 2) Métrica por raio (e comparativo vs Estado no mesmo período)
    within_df, _ = filter_occurrences_within_radius(occ_df, ref_lat, ref_lon, radius_km)
    crimes_radius = within_df["NATUREZA_APURADA"].value_counts().to_dict()

    
    LOG.info("Calculando comparativo (média diária) Região vs Cidade de São Paulo (ano=%s)", ano)
    t0 = time.time()

    city_col = pick_city_column(occ_df)
    if not city_col:
        raise RuntimeError(
            "Não encontrei coluna de município no XLSX SSP para filtrar 'São Paulo'. "
            "Inclua uma das colunas candidatas em CITY_COL_CANDIDATES ou ajuste WANTED_COLS."
        )

    # Normalização vetorizada (sem apply) para performance
    city_series = (
        occ_df[city_col]
        .astype(str)
        .str.upper()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("ascii")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    # Aceita variações: 'S.PAULO', 'S.PAULO/SP', etc.
    city_mask = city_series.str.contains(r"\bS\.PAULO\b", regex=True, na=False)
    city_df = occ_df.loc[city_mask]

    if city_df.empty:
        top_vals = city_series.value_counts().head(15).to_dict()
        LOG.warning("Filtro de município retornou 0 linhas. Coluna=%s | Top valores=%s", city_col, top_vals)

    comparativo = build_regiao_vs_cidade_sp_media_diaria(
        region_df=within_df,
        city_df=city_df,
        radius_km=radius_km,
        top_n=30,
    )
    LOG.info("Comparativo (média diária) calculado em %.2fs", time.time() - t0)
    # 3) Delegacias reais (CEM) + 2 mais próximas
    dps_df = load_delegacias_from_cem(cache_dir)
    dps_info = nearest_dps_and_crimes(occ_df, dps_df, ref_lat, ref_lon, k=2)

    LOG.info("Pipeline concluído em %.1fs", time.time() - t_all)

    return {
        "ano": ano,
        "ponto_referencia": {"lat": ref_lat, "lon": ref_lon},
        "raio_km": radius_km,
        "xlsx_url_usada": xlsx_url_used,
        "ocorrencias_por_tipo_no_raio": crimes_radius,
        "comparativo_regiao_vs_cidade_sp": comparativo,
        "duas_delegacias_mais_proximas": dps_info,
    }



if __name__ == "__main__":
    # Exemplo: Av. Paulista
    result = run_query(ref_lat=-23.561414, ref_lon=-46.655881, radius_km=1.0, ano=2025)

    print("XLSX:", result["xlsx_url_usada"])
    print("\nTop delitos no raio (até 15):")
    for k, v in list(result["ocorrencias_por_tipo_no_raio"].items())[:15]:
        print(f"  {k}: {v}")

    comp = result.get("comparativo_regiao_vs_cidade_sp") or {}
    itens = comp.get("itens_por_delito") or []

    if comp.get("erro"):
        print("\nComparativo Região vs Cidade de São Paulo (média diária): ERRO:", comp.get("erro"))
    else:
        if comp:
            md_reg = float(comp.get("regiao_media_dia") or 0.0)
            md_cid = float(comp.get("cidade_media_dia") or 0.0)
            delta_pct = comp.get("delta_pct_vs_cidade")

            print("\nComparativo Região vs Cidade de São Paulo (média diária):")
            print(f"  Período: {comp.get('periodo_inicio')} a {comp.get('periodo_fim')} | dias={comp.get('num_dias')}")
            if delta_pct is not None:
                print(f"  Média/dia região: {md_reg:.2f} | cidade: {md_cid:.2f} | delta: {delta_pct*100:+.2f}%")
            else:
                print(f"  Média/dia região: {md_reg:.2f} | cidade: {md_cid:.2f}")

        if itens:
            print("\nTop 10 delitos (média diária e participação na cidade):")
            for it in itens[:10]:
                share_city = it.get("share_da_cidade")
                delta_md = it.get("delta_pct_media_dia")
                share_txt = f"{share_city*100:.2f}%" if share_city is not None else "N/A"
                delta_txt = f"{delta_md*100:+.2f}%" if delta_md is not None else "N/A"
                cid_md = it.get("cidade_media_dia")
                cid_md_txt = f"{cid_md:.2f}" if cid_md is not None else "N/A"
                print(
                    f"  {it['tipo_delito']}: reg={it['regiao_qtd']} ({it['regiao_media_dia']:.2f}/dia) | "
                    f"cidade={it['cidade_qtd']} ({cid_md_txt}/dia) | "
                    f"share_da_cidade={share_txt} | Δ média/dia={delta_txt}"
                )
        else:
            print("\nComparativo Região vs Cidade de São Paulo: (sem itens — verifique filtro de município)")

    print("\nDelegacias mais próximas:")
    for dp, info in result["duas_delegacias_mais_proximas"].items():
        print(f"  - {dp} | ~{info['dist_km']:.2f} km | fonte: {info['fonte_dp']}")
