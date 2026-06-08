# docs/geo — Fundação editorial GEO & AI Visibility

Artefatos da estratégia pública de conteúdo do BetterPlace (PRD: `../../PRD_MKT_GEO.md`).

## Índice

- **[content-guidelines.md](content-guidelines.md)** — fonte única de verdade editorial
  (marca, posicionamento, tom, termos, CTAs, thresholds de copy, destinos de conversão,
  tracking, critérios de publicação). Entregável central do **M0**.
- **[fontes-geograficas.md](fontes-geograficas.md)** — camada geográfica base: 96 distritos
  municipais oficiais de São Paulo (`geoportal_distrito_municipal_v2.gpkg`), pipeline de
  ingestão, recorte espacial, metodologia de scores e camada imobiliária simplificada. Entregável central do **M2**.
- **[bairros-prioritarios.md](bairros-prioritarios.md)** — lista inicial de bairros (17).
- **[comparativos-prioritarios.md](comparativos-prioritarios.md)** — lista inicial de pares (10).
- **templates/**
  - [template-bairro.md](templates/template-bairro.md) — página `/bairros/{slug}` (M3) — inclui segurança pública e panorama imobiliário
  - [template-comparativo.md](templates/template-comparativo.md) — `/comparar/{a}-vs-{b}` (M4)
  - [template-relatorio.md](templates/template-relatorio.md) — `/relatorios/{ano-mes}` (M6)
  - [template-post-comunidade.md](templates/template-post-comunidade.md) — comunidade própria (M9)
- **[AI_VISIBILITY_GEO_PLAN.md](../AI_VISIBILITY_GEO_PLAN.md)** — plano técnico-estratégico (contexto).

## Métricas por página de bairro (M3 — estado atual)

| Métrica | Score | Fonte | Cobertura |
|---|---|---|---|
| Transporte público | 0–100 | GeoSampa (metrô, trem, ônibus, terminais, corredores) | completa |
| Áreas verdes | 0–100 | GeoSampa `vegetacao_significativa` | completa |
| Risco de alagamento | 0–100 ↓ | GeoSampa `mancha_inundacao` | completa |
| Segurança pública | 0–100 ↓ | SSP-SP via **join espacial geométrico** sobre `neighborhood_boundaries` (ponto-hull SSP) — nenhuma filtragem por nome/city_code | parcial (sub-registro estrutural) |
| Acesso a serviços | 0–100 | Proxy: densidade de paradas de ônibus (OSM M5) | completa (proxy) |
| Panorama imobiliário | — | base imobiliária interna exige pipeline geoespacial e agregação estado/cidade/bairro/lista | **pendente (M8)** |

## Regra de integridade de dados (OBRIGATÓRIA)

**Toda métrica exposta nas páginas públicas DEVE ser derivada de uma operação geoespacial
real no banco de dados PostGIS.**

- Nunca filtrar dados por nome de cidade, bairro ou código string quando o recorte correto
  é por geometria. Use `ST_Intersects`, `ST_Within`, `ST_Contains` ou `ST_Intersection`
  para identificar quais registros pertencem a cada polígono distrital.
- Nunca inserir valores estimados ou inventados em `bairros.ts` ou nas tabelas de score.
- Se um dado não existir no banco, declarar como lacuna (`lacunas[]` em `Bairro`).
- O campo `realEstateMetrics` só pode ser preenchido quando houver pipeline geoespacial
  e/ou chaves canônicas validadas que agreguem a base imobiliária interna por estado,
  cidade, bairro e lista (previsto M8).
- O pipeline de segurança usa join espacial puro: `ST_Intersects(pmsp.geometry, ssp.geometry)`
  sem qualquer filtro de nome ou `city_code` dos bairros SSP.

## Status dos milestones

| Milestone | Status |
|---|---|
| M0 — Marca e fundação editorial | ✅ Concluído |
| M1 — Site SSR/SSG indexável | ✅ Concluído |
| M2 — Base de dados geográfica | ✅ Concluído |
| M3 — Páginas de bairro | ✅ Concluído (12 páginas · 6 métricas) |
| M4+ | Pendente |
</content>
