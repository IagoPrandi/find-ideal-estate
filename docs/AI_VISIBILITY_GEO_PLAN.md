# Plano de Visibilidade em IA (GEO) — Find Ideal Estate

**Versão:** 2.0 (revisão fundamentada no código)
**Data:** 2026-06-05
**Status:** Proposta
**Documentos abertos:** `PRD.md`, `SKILLS_README.md`
**Skill usada:** nenhuma (não há skill aplicável a GEO/marketing no catálogo)

> Esta versão substitui a v1.0. A v1.0 e um plano alternativo avaliado partiam de
> suposições que **não se sustentam contra o repositório**. As correções estão na §2.

---

## 0. Objetivo

Fazer Claude, ChatGPT, Perplexity, Google AI Overviews/Gemini, Copilot e Grok **citarem o
produto de forma recorrente** quando alguém pergunta sobre **aspectos qualitativos de lugares
no Brasil para morar** (transporte, segurança, área verde, alagamento, preço, deslocamento),
convertendo citação em tráfego qualificado e autoridade de marca.

---

## 1. Como uma IA decide citar (modelo mental correto)

Duas superfícies, atacadas em paralelo:

- **Recuperação ao vivo (RAG):** Perplexity, ChatGPT Search, AI Overviews, Copilot, Gemini
  buscam na web e citam o que recuperam. Controlado por: indexação (Bing p/ ChatGPT-Copilot;
  Google p/ Gemini-Overviews), **bots de IA conseguirem ler o HTML**, e match de intenção.
  → citação **pontual**.
- **Corpus + consenso da web:** modelos citam por padrão quem aparece **repetido em muitas
  fontes independentes** (Wikipedia/Wikidata, imprensa, Reddit, datasets). Conquistado por
  **menções de terceiros**. → citação **recorrente** (o objetivo real).

**Fato técnico decisivo:** os crawlers de IA (`GPTBot`, `OAI-SearchBot`, `ClaudeBot`,
`PerplexityBot`, `CCBot`) **não executam JavaScript** — leem HTML cru. Bing renderiza JS de
forma limitada; só o Googlebot renderiza bem (em duas ondas). Logo, **num SPA o conteúdo é
invisível para os exatos motores-alvo**.

---

## 2. Correções (por que o "senso comum" falha aqui) — verificado no código

| Premissa comum | Realidade no repositório | Consequência |
|---|---|---|
| "robots/sitemap/llms.txt já dá pra colocar" | Não existe `apps/web/public/` — nada é servido | É build, não config |
| "basta expor o pipeline" | Front é **SPA Vite/React** sem SSR/rotas (`apps/web/index.html`) | Conteúdo invisível p/ GPTBot/ClaudeBot/PerplexityBot |
| "páginas /bairro saem do banco" | Só **crime** é agregado por bairro (`public_safety/neighborhood_analytics.py`); verde/alagamento/POI/preço **não** | Backing de dados precisa ser construído |
| "relatório gerado por `modules/reports`" | Não existe `reports`/`urban_analysis`/`datasets` | Relatório e `/dados` são build do zero |
| "ZAP, OLX, Viva Real, Loft, QuintoAndar" | **OLX não tem scraper**; há zap/vivareal/loft/quintoandar | Não prometer cobertura inexistente |
| "llms.txt — IAs já leem" | Proposta sem adoção confirmada de Claude/GPT/Perplexity | Fazer (barato), mas **não orçar impacto** |
| "Schema.org gera citação" | Ajuda entidade/rich-result no Google; efeito em LLM não comprovado | Fazer pela trilha Google, não como alavanca de citação |
| "~4.600 páginas /comparar é ativo" | C(96,2)=4.560, maioria com ~zero demanda → *doorway pages* | **Passivo de SEO**; gerar só com porta de demanda |

**Dois alertas adicionais:**
- ~~O boundary de bairro hoje é fecho convexo de pontos da SSP (`ssp_point_hull_v1`).~~
  **Resolvido (M2):** os limites agora são os 96 polígonos oficiais da PMSP, importados de
  `data/geo/raw/geoportal_distrito_municipal_v2.gpkg`. Ver `docs/geo/fontes-geograficas.md`.
- O app se chama **"BetterPlace"** no `index.html`, não "Find Ideal Estate". **Definir 1 nome
  canônico** — entidade ambígua mata o objetivo de virar entidade reconhecida. (**Resolvido em M0.**)

---

## 3. Cadeia de bloqueio (ordem obrigatória)

```
Nome canônico + domínio
        │
        ▼
Superfície de conteúdo server-rendered  ◄── BLOQUEADOR #1 (sem isto, nada é citável)
        │
        ▼
Backing de dados por bairro (polígono oficial + agregação)
        │
        ▼
Páginas com porta de demanda (/bairro, /comparar)
        │
        ▼
Motor de recorrência (relatório, dataset aberto)
        │
        ▼
Distribuição/autoridade (Reddit, imprensa, Wikidata)
        │
        ▼
Medição (painel de prompts + referrer + logs de bot)
```

---

## 4. Arquitetura buildável (o que existe vs. o que construir)

### 4.1 Superfície de conteúdo (BLOQUEADOR #1)
**Não** migrar o app inteiro (FE3). Subir um **site de conteúdo dedicado**, estático/SSR,
separado do app interativo, consumindo uma **API de leitura pública** (views materializadas):
- **Recomendação:** Astro (zero-JS por padrão, ideal para páginas de dados) ou Next.js SSG.
- Rotas: `/bairro/{slug}`, `/comparar/{a}-vs-{b}`, `/relatorio/{aaaa-mm}`, `/dados`.
- `robots.txt` liberando bots de IA + `sitemap.xml` gerado das views + `<link rel=canonical>` + `dateModified` visível + JSON-LD (`Place`, `Dataset`, `FAQPage`, `Article`, `Organization`).
- `llms.txt` na raiz (custo baixo; sem expectativa de impacto direto).

### 4.2 Backing de dados por bairro

**Boundaries oficiais — resolvido (M2).**  
A camada base é `data/geo/raw/geoportal_distrito_municipal_v2.gpkg` (PMSP/GeoSampa),
layer `distrito_municipal_v2` — **96 distritos municipais de São Paulo**, polígonos
oficiais em EPSG:31983, ingeridos em `neighborhood_boundaries` (EPSG:4326) via
`scripts/ingest_distritos_municipais.py`. Cada distrito = uma zona de análise.
Detalhes: `docs/geo/fontes-geograficas.md`.

- **Agregar por distrito, em batch (sem jornada do usuário):** verde (`geosampa_vegetacao_significativa`),
  alagamento (`geosampa_mancha_inundacao`), POIs e acesso a transporte (GTFS/metrô/trem)
  → `ST_Intersection` / `ST_Contains` contra os polígonos do GeoPackage.
  Pipeline: `scripts/aggregate_geo_metrics.py`.
- **Crime:** `public_safety_neighborhood_metrics`, religado aos polígonos oficiais do GeoPackage.
- **Acesso por isócrona:** métrica em batch (ex.: paradas/área e % alcançável em 30 min de
  hubs fixos) via Valhalla/OTP — job novo, porém limitado a um conjunto fixo de referências.
- **Preço:** **fora do MVP de conteúdo.** Cobertura por bairro exige job de scraping novo
  (custo) e tem exposição de ToS/jurídica (republicar agregados de terceiros). Entra depois,
  só com agregação (nunca anúncio individual), atribuição e respeito a robots das fontes.

### 4.3 Páginas com porta de demanda (anti-doorway)
- Gerar `/bairro/{slug}` **apenas** para distritos com dados suficientes (cobertura mínima
  por métrica declarada).
- Gerar `/comparar/{a}-vs-{b}` **apenas** para pares com demanda real (keyword research +
  perguntas reais às IAs), nunca o produto cartesiano.
- Cada página precisa passar num **piso de unicidade**: dados diferentes e resumo citável
  próprio. Onde falta dado, **declarar a lacuna** — não preencher com proxy.

### 4.4 Motor de recorrência (build do zero, alto valor)
- **Relatório mensal/trimestral** a partir das views agregadas (HTML+PDF+CSV+JSON, todos
  indexáveis). É o que a imprensa e o Reddit citam → gera citação recorrente de terceiros.
- **Dataset aberto** dos agregados (CSV/GeoJSON) com licença e metodologia → backlinks
  acadêmicos/jornalísticos.

### 4.5 Distribuição/autoridade (depende de 4.1–4.4 existirem e estarem corretos)
- Wikidata/Wikipedia (entidade); presença genuína em Reddit/fóruns (r/saopaulo, r/brasil);
  data PR dos estudos; Product Hunt/HN no lançamento; YouTube (transcrição indexada).
- Instagram/TikTok: marca, **não** GEO (baixo retorno para citação em LLM de texto).

---

## 5. Roadmap sequenciado (com honestidade de esforço)

| Fase | Entregas | Natureza | Pré-requisito |
|---|---|---|---|
| **P0 — Fundação** | Nome canônico; site de conteúdo SSR/SSG; robots+sitemap+JSON-LD; API de leitura; medição | **Build** | — |
| **P1 — Dados por bairro** | Polígonos oficiais; views agregadas (verde/alagamento/POI/transporte/crime); 1ª leva de `/bairro` com porta de demanda | **Build** (reusa datasets existentes) | P0 |
| **P2 — Recorrência** | Relatório mensal automatizado; `/dados` aberto; `/comparar` com demanda | **Build** | P1 |
| **P3 — Autoridade** | Wikidata, Reddit, data PR, PH/HN, YouTube | Operação contínua | P1+P2 |
| **P4 — Preço (opcional)** | Job de cobertura + agregados de preço, com postura jurídica | **Build + risco** | P2 + aval jurídica |

---

## 6. Medição (honesta sobre não-determinismo)
- **Painel de prompts:** conjunto fixo de perguntas-alvo rodado mensalmente em ChatGPT,
  Claude, Perplexity, Gemini → taxa e posição de citação (respostas variam; medir tendência).
- **Tráfego de referência de IA:** segmento por referrer (`chatgpt.com`, `perplexity.ai`,
  `gemini.google.com`, `copilot.microsoft.com`).
- **Crawl de bots:** hits de GPTBot/ClaudeBot/PerplexityBot nos logs.
- **Indexação e autoridade:** páginas indexadas (Search Console/Bing); domínios de referência;
  menções na imprensa; status no Wikidata.

---

## 7. Riscos / decisões a tomar
1. **SSR é pré-requisito inegociável** — sem ele o resto é desperdício.
2. **Boundaries oficiais antes de publicar crime por bairro** (integridade metodológica).
3. **Preço público = decisão jurídica** (ToS das fontes, agregado-apenas).
4. **Geração com porta de demanda** para não criar passivo de doorway pages.
5. **Nome canônico único** (BetterPlace × Find Ideal Estate).
```
