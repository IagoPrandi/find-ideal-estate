#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zapImoveis.py — parser dedicado (ZAP Imóveis)

Este módulo segue o modelo dos parsers existentes para VivaReal e QuintoAndar.
O objetivo principal é ler os artefatos de uma execução gerados pelo
``realestate_meta_search`` (por exemplo, ``replay_zapimoveis_glue_listings_p*.json``)
e produzir uma lista padronizada de imóveis extraídos do payload da API
``glue-api.zapimoveis.com.br``.  Cada item retornado contém campos
compatíveis com o esquema unificado utilizado pelos demais parsers:

    {schema_version, platform, listing_id, url, lat, lon, price_brl,
     area_m2, bedrooms, bathrooms, parking, address}

Assim como o parser do VivaReal, este módulo assume que o portal ZAP
utiliza o mesmo serviço "glue" para retornar resultados.  Em testes
manuais o domínio ``glue-api.zapimoveis.com.br`` requer o cabeçalho
``x-domain`` configurado para ``www.zapimoveis.com.br`` e a estrutura
de resposta observada é semelhante à do VivaReal, trazendo a lista de
imóveis em ``search.result.listings``.  Por isso, a lógica de
extração reutiliza a mesma heurística empregada para o VivaReal.

Se o payload capturado apresentar campos adicionais ou nomes
ligeiramente diferentes, adapte as funções auxiliares a seguir.

Uso:

    python zapImoveis.py --dir runs/run_x/zapimoveis --out saida.json

Nota: este parser não realiza nenhuma chamada HTTP direta; ele apenas
trabalha com os arquivos salvos localmente pelo ``realestate_meta_search``.

"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Versão do esquema de saída.  Incrementar se houver alteração
# incompatível na estrutura retornada.
STD_SCHEMA_VERSION = 1


class ZapImoveisError(RuntimeError):
    """Erro genérico do parser ZAP Imóveis."""


class ZapImoveisCloudflareError(ZapImoveisError):
    """Indica que o payload é um bloqueio do Cloudflare, não JSON de listagens."""


class ZapImoveisNoListingsError(ZapImoveisError):
    """Indica que não foi possível encontrar a lista de imóveis no payload do Glue."""


def _is_cloudflare_block(payload: Any) -> bool:
    """Detecta se o replay contém uma página de bloqueio do Cloudflare.

    O ZAP pode retornar HTTP 403 com HTML ("Attention Required! | Cloudflare").
    O parser não tenta contornar o bloqueio — apenas evita interpretar HTML
    como JSON de listagens e, assim, não polui o `compiled_listings.csv`.
    """
    try:
        if isinstance(payload, dict):
            body = payload.get("body") or payload.get("html") or payload.get("text")
            if isinstance(body, str):
                s = body.lower()
                if "cloudflare" in s and "attention required" in s:
                    return True
                if "cf-ray" in s or "__cf" in s:
                    return True
            msg = payload.get("error") or payload.get("message")
            if isinstance(msg, str):
                s = msg.lower()
                if "cloudflare" in s and "attention required" in s:
                    return True
        if isinstance(payload, str):
            s = payload.lower()
            if "cloudflare" in s and "attention required" in s:
                return True
    except Exception:
        return False
    return False


def get_by_path(obj: Any, path: str) -> Any:
    """Acessa um caminho com pontos dentro de um objeto aninhado.

    O caminho pode conter índices numéricos para acessar listas.
    Se qualquer parte do caminho não existir, retorna None.
    """
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
    """Converte valores diversos em inteiro, tratando strings com
    separadores de milhares e vírgula como decimal.
    Retorna None quando não for possível converter.
    """
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
    """Converte valores diversos em float, tratando strings com
    separadores de milhares e vírgula como decimal.  Retorna None
    quando não for possível converter."""
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
    """Procura a melhor URL disponível para um imóvel.

    Alguns payloads trazem múltiplos campos com URL, por isso este
    helper percorre alguns candidatos em ordem.  Quando a URL for
    relativa (iniciada com '/'), ela será prefixada com o domínio
    ``www.zapimoveis.com.br``.
    """
    for k in ("url", "uri", "canonicalUrl", "canonicalURI", "href"):
        v = listing.get(k)
        if isinstance(v, str) and v.strip():
            if v.startswith("http"):
                return v
            if v.startswith("/"):
                return "https://www.zapimoveis.com.br" + v
    link = listing.get("link")
    if isinstance(link, dict):
        for k in ("href", "url", "uri"):
            v = link.get(k)
            if isinstance(v, str) and v.strip():
                if v.startswith("http"):
                    return v
                if v.startswith("/"):
                    return "https://www.zapimoveis.com.br" + v
    return None


def _format_address(addr: dict) -> Optional[str]:
    """Formata os componentes de endereço em uma string legível.

    A estrutura de endereço observada nas respostas do Glue API do
    ZAP Imóveis é muito semelhante à do VivaReal, contendo chaves
    como ``street``, ``neighborhood``, ``city`` e ``state``.  Este
    helper monta uma string unindo os componentes quando presentes.
    """
    if not isinstance(addr, dict):
        return None
    parts = []
    for k in ("street", "neighborhood", "city", "state"):
        v = addr.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return ", ".join(parts) if parts else None


def _extract_listings_array(glue_json: dict) -> List[dict]:
    """Localiza a lista de imóveis dentro do payload do Glue.

    Tenta alguns caminhos estritos; se nenhum contiver uma lista, lança erro.
    """
    if not isinstance(glue_json, dict):
        raise ZapImoveisNoListingsError("Payload do Glue do ZAP não é um objeto JSON (dict).")

    # 1) Caminhos clássicos de busca (mesma convenção do Glue usado pelo VivaReal)
    candidate_paths = [
        "search.result.listings",
        "search.result",   # em alguns cenários a lista pode vir diretamente em `result`
        "listings",        # caminho direto na raiz (mais raro)
    ]

    for path in candidate_paths:
        listings = get_by_path(glue_json, path)
        if isinstance(listings, list) and listings:
            return listings

    # 2) Estrutura de recomendações do ZAP:
    #    recommendations[].scores[].listing.listing
    recs = glue_json.get("recommendations")
    if isinstance(recs, list) and recs:
        flattened: List[dict] = []
        for rec in recs:
            if not isinstance(rec, dict):
                continue
            scores = rec.get("scores")
            if not isinstance(scores, list):
                continue
            for s in scores:
                if not isinstance(s, dict):
                    continue
                lst = s.get("listing")
                if isinstance(lst, dict):
                    inner = lst.get("listing")
                    if isinstance(inner, dict):
                        flattened.append(inner)
                    else:
                        flattened.append(lst)
        if flattened:
            return flattened

    # Nenhuma lista encontrada em caminhos esperados
    # Expor as chaves de topo e de `search`/`result` para facilitar o debug.
    top_keys = sorted(list(glue_json.keys()))
    search_obj = glue_json.get("search") if isinstance(glue_json.get("search"), dict) else None
    search_keys = sorted(list(search_obj.keys())) if isinstance(search_obj, dict) else []
    result_obj = search_obj.get("result") if isinstance(search_obj, dict) and isinstance(search_obj.get("result"), dict) else None
    result_keys = sorted(list(result_obj.keys())) if isinstance(result_obj, dict) else []

    msg = (
        "Não foi possível localizar a lista de imóveis no payload do Glue do ZAP. "
        f"Caminhos testados: {', '.join(candidate_paths + ['recommendations[*].scores[*].listing'])}. "
        f"Chaves de topo: {top_keys}. "
        f"Chaves de search: {search_keys}. "
        f"Chaves de search.result: {result_keys}."
    )
    raise ZapImoveisNoListingsError(msg)


def parse_zap_glue_to_std(glue_json: dict) -> List[dict]:
    """Extrai uma lista padronizada de imóveis a partir do payload do Glue.

    O Glue API retorna um objeto JSON onde a lista de imóveis está em
    ``search.result.listings``.  Cada item dessa lista pode possuir
    uma camada interna ``listing``.  Este método itera por todos os
    itens, normaliza os campos principais e retorna um dicionário
    com a estrutura padronizada.

    Caso a estrutura esperada não seja encontrada, um erro explícito é
    lançado em vez de retornar lista vazia.
    """
    # Se for bloqueio do Cloudflare (HTML), não há listagens válidas.
    if _is_cloudflare_block(glue_json):
        raise ZapImoveisCloudflareError(
            "Payload do ZAP identificado como página de bloqueio do Cloudflare. "
            "Nenhuma listagem pôde ser extraída."
        )

    listings = _extract_listings_array(glue_json)
    out: List[dict] = []
    for it in listings:
        listing = it.get("listing") if isinstance(it, dict) and isinstance(it.get("listing"), dict) else it
        if not isinstance(listing, dict):
            continue
        # Identificador único do imóvel.  O Glue costuma retornar um campo
        # ``id`` mas também aceita variações como ``listingId``.
        lid = listing.get("id") or listing.get("listingId") or listing.get("listing_id")
        if lid is None:
            continue
        lid = str(lid)

        # Preço: o Glue para aluguel geralmente traz os preços em
        # ``pricingInfos`` (lista) ou ``pricingInfo`` (objeto).  Vamos
        # priorizar o primeiro elemento da lista e converter para int.
        price = None
        pi = listing.get("pricingInfos")
        if isinstance(pi, list) and pi:
            # Pode haver campos ``price`` ou ``rentalTotalPrice``
            price = _as_int(pi[0].get("price") or pi[0].get("rentalTotalPrice") or pi[0].get("monthlyCondoFee"))
        if price is None and isinstance(listing.get("pricingInfo"), dict):
            price = _as_int(listing["pricingInfo"].get("price") or listing["pricingInfo"].get("rentalTotalPrice"))

        # Área pode vir como lista (usableAreas) ou número (usableArea/area/...)
        raw_area = listing.get("usableAreas")
        if isinstance(raw_area, list) and raw_area:
            area = _as_float(raw_area[0])
        else:
            area = _as_float(listing.get("usableArea") or listing.get("area") or listing.get("totalAreas") or listing.get("totalArea"))
        bedrooms = _as_int(listing.get("bedrooms") or listing.get("bedroomCount"))
        bathrooms = _as_int(listing.get("bathrooms") or listing.get("bathroomCount"))
        parking = _as_int(listing.get("parkingSpaces") or listing.get("parking") or listing.get("garageSpaces"))

        address = listing.get("address") if isinstance(listing.get("address"), dict) else {}

        # Coordenadas: no ZAP/Glue podem vir em address.point.{lat,lon},
        # address.point.{approximateLat,approximateLon}, ou address.geoLocation.location
        lat = lon = None
        point = address.get("point") if isinstance(address.get("point"), dict) else None
        if isinstance(point, dict):
            lat = _as_float(point.get("lat") or point.get("latitude") or point.get("approximateLat"))
            lon = _as_float(point.get("lon") or point.get("longitude") or point.get("approximateLon"))

        if lat is None or lon is None:
            gl = address.get("geoLocation") if isinstance(address.get("geoLocation"), dict) else None
            loc = gl.get("location") if isinstance(gl, dict) and isinstance(gl.get("location"), dict) else None
            if isinstance(loc, dict):
                lat = lat if lat is not None else _as_float(loc.get("lat") or loc.get("latitude"))
                lon = lon if lon is not None else _as_float(loc.get("lon") or loc.get("longitude"))

        url = _pick_first_url(listing) or f"https://www.zapimoveis.com.br/imovel/{lid}/"

        out.append({
            "schema_version": STD_SCHEMA_VERSION,
            "platform": "zapimoveis",
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
    """Lê todos os arquivos JSON de replay do Glue para o ZAP Imóveis.

    A função procura arquivos no padrão ``replay_zapimoveis_glue_listings_p*.json``
    dentro do diretório fornecido (que corresponde a ``runs/run_x/zapimoveis``).
    Para cada arquivo encontrado, carrega o JSON e passa pela função
    ``parse_zap_glue_to_std``.  Imóveis duplicados (baseados em
    ``platform`` e ``listing_id``) são desconsiderados.
    """
    p = Path(platform_dir)
    if not p.exists():
        raise ZapImoveisError(f"Diretório da plataforma ZAP não existe: {p}")

    # Localiza arquivos de replay específicos do Zap.  Segue o mesmo
    # padrão utilizado pelo VivaReal (ex.: replay_vivareal_glue_listings_p1.json).
    files: List[str] = []
    files.extend(sorted(glob.glob(str(p / "replay_zapimoveis_glue_listings_p*.json"))))
    files.extend(sorted(glob.glob(str(p / "replay_zapimoveis_*.json"))))
    # Remove duplicados preservando ordem.
    seen_files = set()
    files = [f for f in files if not (f in seen_files or seen_files.add(f))]

    # Quando não há arquivos com o padrão de replay, usamos todos os .json do diretório.
    if not files:
        files = sorted(glob.glob(str(p / "*.json")))

    if not files:
        raise ZapImoveisError(
            f"Nenhum arquivo JSON do ZAP foi encontrado em {p}. "
            "Verifique se a captura do realestate_meta_search gerou os artefatos esperados."
        )

    out: List[dict] = []
    seen = set()
    last_no_listings_error: Optional[Exception] = None

    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                raise ZapImoveisError(f"Falha ao carregar JSON do arquivo '{fp}': {e}") from e

        # Se o arquivo for um bloqueio do Cloudflare, não há motivo para continuar silenciosamente.
        if _is_cloudflare_block(data):
            raise ZapImoveisCloudflareError(
                f"Arquivo de replay do ZAP parece conter apenas página de bloqueio do Cloudflare: {fp}"
            )

        try:
            parsed_items = parse_zap_glue_to_std(data)
        except ZapImoveisNoListingsError as e:
            # Guarda o último erro estrutural; se nenhum arquivo produzir listagens,
            # ele será propagado ao final.
            last_no_listings_error = e
            continue

        for item in parsed_items:
            key = (item.get("platform"), item.get("listing_id"))
            if key in seen:
                continue
            seen.add(key)
            out.append(item)

    if not out:
        if last_no_listings_error is not None:
            raise last_no_listings_error
        raise ZapImoveisNoListingsError(
            f"Nenhuma listagem do ZAP foi extraída a partir dos arquivos em {p}. "
            "Verifique se o payload do Glue contém `search.result.listings` ou estrutura compatível."
        )

    return out


def main() -> None:
    """Interface de linha de comando para testar o parser.

    Permite apontar para um diretório de run e opcionalmente salvar
    o JSON resultante em um arquivo.  Se nenhum arquivo de saída
    for informado, imprime os primeiros itens no stdout.
    """
    ap = argparse.ArgumentParser(description="Parser dedicado ZAP Imóveis (a partir do run do realestate_meta_search).")
    ap.add_argument("--dir", required=True, help="Diretório da plataforma, ex.: runs/run_x/zapimoveis")
    ap.add_argument("--out", default="", help="Arquivo JSON de saída (opcional).")
    args = ap.parse_args()

    items = parse_run_dir(args.dir)
    if args.out:
        Path(args.out).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(items[:3], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()