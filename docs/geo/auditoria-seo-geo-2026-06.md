# Auditoria SEO + GEO — camada de conteúdo BetterPlace

**Data:** 2026-06-15
**Escopo:** `apps/content` (camada pública Astro SSG) — páginas `/bairros`, `/comparar`, `/guias`, `/relatorios`, `/dados`, `/metodologia`.
**Base normativa:** `PRD_MKT_GEO.md`, `docs/geo/content-guidelines.md`.
**Skills consultadas:** `/seo-audit`, `/ai-seo`.
**Método:** auditoria do código + pesquisa de comparadores reais (QuintoAndar, Loft, Portas, ZAP/VivaReal).

---

## Diagnóstico em uma frase

A fundação técnica está **boa** (Astro SSG, HTML sem JS, canonical, `llms.txt`, robots liberando bots de IA, JSON-LD, CTAs rastreáveis). O que trava conversão via SEO/GEO são **três lacunas**:

1. **Formato não-extraível por IA/Google** — sem resposta-direta no topo, H2s genéricos em vez de perguntas, tabela comparativa fraca, sem listicles para as queries de maior volume.
2. **Faltam sinais de citação e compartilhamento** — sem `og:image`, sem `BreadcrumbList`, `Place` sem coordenadas, sem ano/frescor nos títulos.
3. **CTA vaza conversão** — manda todos para a raiz do app, sem contexto do bairro/comparativo que a pessoa estava lendo. (O app é SPA hash-routed e não tem rotas `/bairros/{slug}`; deep-link real exige leitura de query param no app.)

---

## Benchmark — o que os comparadores fazem e nós não

| Tática vencedora | QuintoAndar | Loft | Portas | ZAP | BetterPlace |
|---|:--:|:--:|:--:|:--:|:--:|
| Listicle "melhores/mais seguros bairros de SP" (1 página por intenção) | ✅ | — | ✅ | ✅ | ❌ (só 1 guia) |
| Tabela de dados com coluna "vs média de SP" | — | ✅ | ✅ | — | ⚠️ (score relativo, sem baseline) |
| H2 em forma de pergunta natural | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| Resposta direta auto-contida no topo | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Ano no título + re-datação | ✅ | ✅ | ✅ | — | ❌ |
| Relatório serializado/branded | — | ✅ | — | — | ⚠️ (existe, sem marca citável) |
| Página head-to-head "X vs Y" | ❌ | ❌ | ❌ | ❌ | ✅ **(diferencial — explorar)** |
| `Dataset` schema | ❌ | ❌ | ❌ | ❌ | ✅ **(diferencial)** |

**Whitespace nosso:** comparativos `/comparar` e `Dataset` schema (ninguém faz). **Onde perdemos:** listicles por intenção e formato extraível.

**Substrato de citação por IA (queries de SP):** ITBI (transações), IBGE/SEADE (demografia/renda) e SSP-SP (segurança) são as fontes públicas que IAs confiam. Listicles de 4-8 itens, frases-definição e blocos FAQ são os formatos mais citados.

---

## Achados priorizados

### 🔴 P1 — Alto impacto, corrigir primeiro

**1. CTA não é contextual / não faz deep-link**
- Evidência: `apps/content/src/components/Cta.astro` — todo CTA aponta para a raiz `/` do app.
- Restrição: app (`apps/web`) é SPA hash-routed, sem rotas `/bairros/{slug}`. Deep-link por path quebra.
- Fix (não-quebrável): microcópia contextual por página + query param `?bairro=slug`/`?comparar=slug` (hook forward-compatible). Pré-seleção real depende de o app ler o param (tarefa app-side separada).

**2. H2s genéricos em vez de perguntas (mata extração por IA)**
- Evidência: `bairros/[slug].astro` usa `Transporte`, `Áreas verdes`, `Segurança pública`.
- Fix: H2 em linguagem de query — "Como é o transporte público na Vila Mariana?", "A Vila Mariana é um bairro seguro?", abrindo cada seção com resposta direta.

**3. Bloco "Resposta rápida" no topo (TL;DR auto-contido para AI Overview/Perplexity)**
- Evidência: `lead` é o resumo, mas não é um bloco factual auto-suficiente de 40-60 palavras.
- Fix: bloco curto logo após o H1 com scores + perfil + frescor.

**4. Listicles por intenção (maior lacuna de conteúdo)**
- Evidência: só existe `/guias/bairros-perto-do-itaim-bibi-para-morar`.
- Fix: gerar 5-8 guias-listicle a partir dos scores existentes (ranqueando bairros publicados), H1 numerado + ano. Ex.: "Os 10 bairros com melhor transporte público em São Paulo (2026)".

### 🟠 P2 — Alto impacto, esforço médio

**5. Sem `og:image` / Twitter Cards** — links compartilhados sem preview. Fix: OG dinâmica por página (Satori/`astro-og-canvas`) + tags `twitter:card`.

**6. Sem `BreadcrumbList`** — perde breadcrumb no SERP e estrutura para IA. Fix: JSON-LD + breadcrumb visível.

**7. Títulos longos (>70 chars) e sem padrão de query/ano** — truncam no SERP. Fix: "Morar na Vila Mariana: transporte, segurança e custo (2026)".

**8. `Place` schema sem coordenadas** — temos os polígonos. Fix: `AdministrativeArea` + `geo` (centroide) + `containedInPlace`.

**9. Coluna "vs média de SP" ausente** — score isolado não é interpretável fora de contexto. Fix: média da cidade ao lado de cada barra.

### 🟡 P3 — Refinos

**10. Tabela comparativa usa `colspan`** — perde extração por entidade. Fix: valor de cada bairro em sua coluna + marca de vencedor.

**11. `robots` meta sem diretiva de snippet** — Fix: `<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">`.

**12. `dateModified`/`datePublished` inconsistentes no JSON-LD** — `Place`/`FAQPage` sem data; `<meta name="date">` é ignorado pelo Google. Fix: padronizar nos JSON-LD + `lastmod` no sitemap.

**13. Linkagem interna de cluster rasa** — adicionar "Comparativos com este bairro" e "Guias que incluem este bairro" em todas as páginas de bairro.

**14. E-E-A-T: autor sempre "Organization"** — considerar autoria nomeada / metodologista (como Loft cita especialistas).

---

## Plano de ação (ordem)

1. **Semana 1 (conversão + extração):** #1 CTA contextual, #2 H2-perguntas, #3 resposta-rápida, #11 robots snippet. *(= "bloco P1")*
2. **Semana 2 (citabilidade/share):** #5 og:image, #6 BreadcrumbList, #8 geo no Place, #12 datas.
3. **Semana 3 (volume orgânico):** #4 listicles, #7 títulos com ano, #9 baseline "vs SP".
4. **Semana 4 (refino):** #10 tabela por entidade, #13 cluster interno, #14 E-E-A-T.

Tudo usa **dados que já existem** (scores, polígonos, agregados imobiliários) — sem informação inventada, em linha com o PRD e o CLAUDE.md.

---

## Registro de implementação

- **2026-06-15** — Bloco P1 implementado: #2, #3, #11 e a versão não-quebrável de #1. Detalhes no commit/PR correspondente.
- **2026-06-15** — **Semana 2 (parcial):** #6 BreadcrumbList (JSON-LD + nav visível, centralizado no `Base.astro`, aplicado a bairro/comparar/guia/relatório/dados/metodologia), #8 `Place`→`['Place','AdministrativeArea']` + `containedInPlace` (cidade→estado→país) + `dateModified`, com hook opcional `centroide` para o pipeline preencher o `geo` (coordenadas NÃO inventadas — GeoJSON publicado tem `geometry: null`), #12 `dateModified` no `Place` + `lastmod` por página no sitemap (datas reais de `bairros/comparativos/guias`). Infra de #5 (og:image + Twitter Cards) adicionada ao `Base.astro` via prop `ogImage`. Validado por build (107 páginas).
- **2026-06-15** — **Semana 2 (conclusão): #5 OG dinâmico.** Geração de imagens Open Graph 1200×630 por página via `satori` + `@resvg/resvg-js` (`src/lib/og.ts`), com fonte Inter lida localmente do `@fontsource/inter` (sem rede no build). Endpoints `src/pages/og/bairros/[slug].png.ts` e `src/pages/og/comparar/[slug].png.ts` (prerender, cache imutável). Páginas de bairro e comparativo passam `ogImage`; `twitter:card` vira `summary_large_image`. Endpoints `.png` não entram no sitemap. Validado por build (PNG RGBA 1200×630, og:image apontando para URL canônica). Demais tipos (home, guias, relatórios, dados) seguem com `twitter:card=summary` até receberem OG próprio.
- **2026-06-15** — **Semana 3 (volume orgânico):**
  - **#4 listicles por intenção** — novo sistema `/listas`: `src/data/listas.ts` (defs por métrica), `src/lib/baseline.ts` (média dos distritos analisados), `listas/[slug].astro` + `listas/index.astro`. 3 rankings honestos (top 5 entre os 12 distritos publicados, **não** "toda SP"): transporte público, áreas verdes, proteção a alagamento. JSON-LD `Article` + `ItemList` (ItemListOrderDescending) + `FAQPage`, breadcrumbs, resposta-rápida dinâmica, metodologia e limitações declaradas. **Ranking de "mais seguros" deliberadamente omitido** (termo proibido §7.4 + sub-registro SSP-SP). Ligado a nav, home e `llms.txt`.
  - **#7 títulos com ano** — bairro: `Morar em {nome}: transporte, segurança e custo ({ano})` (ano derivado de `dataAtualizacao`, ~58 chars); listicles com `({ano})` no `<title>` e H1.
  - **#9 baseline "vs média"** — `méd. {N}` em cada barra da página de bairro e em cada item dos rankings. Rótulo honesto: **"média dos N distritos analisados"** (não "média de SP" — só temos 12 dos 96 scores normalizados).
  - Validado por build (111 páginas; ordem do ranking conferida via ItemList).
- **2026-06-15** — **Correção de bug (item dedicado): semântica invertida do `floodRiskScore`.**
  - **Fonte de verdade confirmada:** `scripts/aggregate_geo_metrics.py::compute_scores` calcula `flood_risk` com `invert=True` (100 = menor risco). Concordam: `export_open_dataset.py`, `dicionario-campos.json`, comentário de tipo em `bairros.ts`, `relatorios.ts` (`topN`) e `comparativos.ts`.
  - **Bug:** a renderização em `apps/content/src/pages/bairros/[slug].astro` (prosa, FAQ, JSON-LD, cor da barra, "menor é melhor") e o guia tratavam o score como risco direto (baixo = seguro), invertendo a leitura. Causava contradição entre a página de bairro e o comparativo do mesmo par.
  - **Causa-raiz nos specs:** thresholds `flood_risk_score <= 30 → menor exposição` em `PRD §12.3`, `content-guidelines.md §4.3`, skill `geo-content` e `template-bairro.md`.
  - **Correção:** thresholds invertidos para `>= 70 / >= 45 / < 45`; barra renomeada para "Proteção contra alagamento"; cor alinhada a `safetyScore` (maior = melhor); remoção do `↓` enganoso; legendas e specs atualizados. Validado por build (107 páginas) — Vila Mariana e Pinheiros (flood 100) agora exibem "menor exposição", coerentes com os comparativos.
</content>
</invoke>
