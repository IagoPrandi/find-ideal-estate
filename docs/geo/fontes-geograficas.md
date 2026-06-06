# Fontes Geográficas — BetterPlace GEO & AI Visibility

**Milestone:** M2 — Base de dados geográfica e métricas mínimas  
**Versão:** 1.0  
**Data:** 2026-06-06  
**Status:** Implementado

> Este documento descreve as fontes geográficas que definem as zonas de análise do
> BetterPlace. É a referência canônica para desenvolvedores, revisores de pipeline e
> qualquer pessoa que precise entender de onde vêm os limites territoriais usados nas
> métricas e páginas públicas.

---

## 1. Camada base: distritos municipais oficiais

### 1.1 Arquivo fonte

| Campo         | Valor                                                                 |
|---------------|-----------------------------------------------------------------------|
| Arquivo       | `data/geo/raw/geoportal_distrito_municipal_v2.gpkg`                   |
| Formato       | GeoPackage (OGC)                                                      |
| Layer         | `distrito_municipal_v2`                                               |
| Origem        | PMSP — Prefeitura Municipal de São Paulo (GeoSampa / GeoPrefeitura)   |
| CRS original  | **EPSG:31983** — SIRGAS 2000 / UTM zone 23S (projetado, metros)       |
| CRS no banco  | **EPSG:4326** — WGS 84 (reprojetado na ingestão)                      |
| Geometria     | Polygon (não MultiPolygon)                                            |
| Total         | **96 distritos municipais** de São Paulo                              |

### 1.2 Por que este arquivo

- É o limite oficial da PMSP: cada polígono corresponde a um distrito municipal legal,
  com código e nome normatizados.
- Cobre todo o município de São Paulo sem lacunas ou sobreposições.
- Substitui o fecho convexo (`ssp_point_hull_v1`) que era usado como boundary provisório
  — prática proibida pelo `CLAUDE.md` ("nunca use fallbacks que escondam problemas").

### 1.3 Colunas relevantes

| Coluna GeoPackage         | Coluna no banco (`neighborhood_boundaries`) | Descrição                                   |
|---------------------------|----------------------------------------------|---------------------------------------------|
| `cd_distrito_municipal`   | `neighborhood_code`, `district_code`         | Código do distrito (ex.: `"62"`)            |
| `nm_distrito_municipal`   | `neighborhood_name`, `district_name`         | Nome oficial (ex.: `"PINHEIROS"`)           |
| `sg_distrito_municipal`   | `neighborhood_abbreviation`                  | Abreviação (ex.: `"PIN"`)                   |
| `qt_area_quilometro`      | `area_km2`                                   | Área em km²                                 |
| `cd_identificador_distrito` | `gpkg_identifier`                          | ID numérico único do GeoPackage             |
| `cd_regiao_05`            | `region_5_code`                              | Código da macrorregião (1=Centro…5=Sul)     |
| `nm_regiao_05`            | `region_5_name`                              | Nome da macrorregião (Centro/Norte/Sul/…)   |
| `geometry` (EPSG:31983)   | `geometry` (EPSG:4326)                       | Polígono reprojetado na ingestão            |

---

## 2. Zonas de análise

Cada um dos **96 distritos** do GeoPackage é tratado como uma **zona de análise
independente**. Isso significa:

- Toda agregação de dados geoespaciais (áreas verdes, zonas de alagamento, paradas de
  transporte, pontos de interesse) é recortada pelos polígonos desses 96 distritos.
- Cada distrito gera uma linha em `neighborhood_boundaries` com `neighborhood_code`
  igual ao `cd_distrito_municipal` do GeoPackage.
- Cada distrito elegível gera uma página pública em `/bairros/{slug}` (critério de
  publicação: ≥ 4 métricas com dados — ver `content-guidelines.md` §9.1).

---

## 3. Pipeline de ingestão

### 3.1 Passo 1 — ingestão do GeoPackage

```bash
python scripts/ingest_distritos_municipais.py \
  --gpkg data/geo/raw/geoportal_distrito_municipal_v2.gpkg \
  --city-code SAO_PAULO
```

O script:
1. Lê o GeoPackage com `geopandas`.
2. Reprojeta de EPSG:31983 → EPSG:4326.
3. Gera o `slug` a partir de `nm_distrito_municipal` (ex.: "RIO PEQUENO" → `rio-pequeno`).
4. Faz upsert idempotente em `neighborhood_boundaries` usando
   `ON CONFLICT (neighborhood_code) DO UPDATE`.
5. Valida: nenhum slug nulo, nenhuma geometria inválida — encerra com erro se falhar.

### 3.2 Passo 2 — agregação de métricas

```bash
python scripts/aggregate_geo_metrics.py --city-code SAO_PAULO
```

Intersecta cada polígono de distrito contra as camadas GeoSampa brutas:

| Métrica          | Camada GeoSampa                         | Operação espacial               |
|------------------|-----------------------------------------|---------------------------------|
| Áreas verdes     | `geosampa_vegetacao_significativa`      | `ST_Intersection` → área (m²)  |
| Risco de inundação | `geosampa_mancha_inundacao`           | `ST_Intersection` → área (m²)  |
| Transporte       | estações metro/trem, paradas, terminais, corredores | `ST_Contains` / `ST_Intersects` |
| Acesso a POIs    | proxy via densidade de paradas de ônibus | `ST_Contains`                 |

### 3.3 Passo 3 — validação

```bash
python scripts/validate_geo_data.py --city-code SAO_PAULO
```

Verifica slugs únicos, geometrias válidas, view materializada populada, cobertura de
métricas e ausência de dados de preço imobiliário (restrição do MVP).

### 3.4 Migrations necessárias (Alembic)

```bash
alembic upgrade head
# Aplica:
# 20260606_0042 — tabelas de métricas, scores, cobertura, view urban_metrics_by_district
# 20260606_0043 — colunas de metadados do GeoPackage (abbreviation, region_5, gpkg_identifier)
```

---

## 4. Distribuição regional

Os 96 distritos se distribuem pelas 5 macrorregiões da PMSP:

| Macrorregião (`nm_regiao_05`) | Distritos |
|-------------------------------|-----------|
| Centro                        | 8         |
| Norte                         | 18        |
| Leste                         | 33        |
| Oeste                         | 15        |
| Sul                           | 22        |

---

## 5. Limitações declaradas

- **Granularidade:** o recorte é por **distrito municipal**, não por bairro popular ou
  subprefeitura. Algumas regiões menores como Consolação (2,7 km²) terão poucos dados
  brutos; a flag `coverage_level` declarará isso.
- **Atualização:** o GeoPackage é uma foto estática. Se os limites distritais forem
  atualizados pela PMSP, o arquivo fonte deve ser substituído e o script re-executado.
- **CRS:** os dados GeoSampa brutos armazenados no PostGIS estão em EPSG:4326.
  A conversão de área é feita em EPSG:3857 (projeção de Mercator) via `ST_Transform`
  no momento da agregação — não no polígono armazenado.

---

## 6. Próximas fontes (M5+)

| Fonte | Dado | Milestone |
|-------|------|-----------|
| GeoSampa — Subprefeituras | Recorte administrativo alternativo | M5 |
| IBGE — Setores censitários | Densidade demográfica | M5 |
| OSM (Overpass API) | POIs reais (farmácias, mercados, escolas) | M5 |
| SSP-SP | Crime (atualização periódica, já parcial) | M2 (existente) |
| Preço imobiliário agregado | m² médio por distrito | M10 |
