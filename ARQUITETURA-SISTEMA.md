# Plataforma de Análise Imobiliária Urbana
**Documento de Arquitetura · v2.0 · Monolito Modular**

Arquitetura completa do sistema — monolito modular preparado para escalar sem retrabalho, com monetização progressiva via venda de relatórios.

---

## 01 — Visão Geral

O usuário define um ponto de origem (trabalho, escola ou qualquer endereço). O sistema calcula áreas de cobertura a partir das paradas de ônibus e estações de trem próximas a esse ponto, e dentro dessas áreas entrega: imóveis disponíveis agregados de múltiplas plataformas, análise de qualidade da área (arborização, segurança, risco de alagamento, transporte), e pontos de interesse (mercados, restaurantes, academias, farmácias).

O produto para o usuário final é um **relatório de área** — um documento completo e acionável que ele pode comprar avulsamente, usar créditos, ou acessar via assinatura.

> **Princípio central:** O usuário só encontra fricção no momento do pagamento. Antes disso, a experiência é fluida, gratuita e já entrega valor parcial suficiente para justificar a compra.

---

## 02 — Arquitetura Geral

### Monolito modular

O sistema é construído como um **monolito modular** — um único processo deployado, organizado internamente em módulos com fronteiras bem definidas e contratos explícitos entre si. Isso elimina a complexidade operacional de microserviços (deploy distribuído, latência de rede interna, tracing entre serviços) enquanto mantém a organização que permite escalar o time e, futuramente, extrair módulos se necessário.

> **Princípio do monolito modular:** Cada módulo é tratado como se fosse um serviço independente — com sua própria pasta, suas próprias interfaces TypeScript exportadas e zero acesso direto ao banco de dados de outro módulo. A comunicação entre módulos ocorre por chamada de função, não por HTTP. Isso mantém a performance de um monolito com a organização de microserviços.

### Diagrama de arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js)                          │
│   Mapbox GL JS · Deck.gl · Busca · Preview gratuito · CTA · Auth │
└────────────────────────────────┬────────────────────────────────┘
                                 │ HTTPS / REST + Server Actions
┌────────────────────────────────▼────────────────────────────────┐
│               MONOLITO (Node.js + Fastify + TypeScript)          │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │   /search   │  │  /analysis   │  │       /payment         │  │
│  │─────────────│  │──────────────│  │────────────────────────│  │
│  │ Agregador   │  │ Qualidade    │  │ Stripe Pix             │  │
│  │ de imóveis  │  │ de área      │  │ Créditos / Assinatura  │  │
│  │ Normaliz.   │  │ POIs (OSM)   │  │ Webhooks               │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬─────────────┘  │
│         │                │                      │                │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌──────────▼─────────────┐  │
│  │  /scraping  │  │    /gis      │  │        /reports        │  │
│  │─────────────│  │──────────────│  │────────────────────────│  │
│  │ Workers     │  │ OTP client   │  │ PDF Generator          │  │
│  │ BullMQ fila │  │ Valhalla cli.│  │ BullMQ fila            │  │
│  │ Retry/back. │  │ pg_tileserv  │  │ Entrega email          │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
│                                                                  │
│  ┌──────────────────┐  ┌────────────────────────────────────┐   │
│  │      /cache      │  │           /core                    │   │
│  │──────────────────│  │────────────────────────────────────│   │
│  │ H3 cache Redis   │  │ Auth · Logger · EventBus · DB      │   │
│  │ Invalidação evt. │  └────────────────────────────────────┘   │
│  └──────────────────┘                                           │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                    SERVIÇOS GIS INTERNOS (Docker)                │
│                                                                  │
│  OpenTripPlanner                  Valhalla                       │
│  ├─ Consome GTFS (ônibus/trem)    ├─ Consome OSM (.pbf)          │
│  ├─ Tempo real por trans. público ├─ Isócronas a pé e carro      │
│  └─ Considera horário de pico     └─ POI alcançável por imóvel   │
│                                                                  │
│  pg_tileserv                      ETL Pipeline (cron)            │
│  ├─ Vector tiles do PostGIS       ├─ Processa bases públicas ~1GB │
│  ├─ Rotas, estações, polígonos    ├─ GTFS · SSP · CEMADEN · OSM  │
│  └─ Consumido pelo Mapbox GL JS   └─ Normaliza → PostGIS         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                               │
│                                                                  │
│  PostgreSQL + PostGIS              Redis (Upstash)               │
│  ├─ Particionamento por data       ├─ Cache H3 de áreas          │
│  ├─ Dados GIS ingeridos pelo ETL   ├─ Isócronas cacheadas 30d    │
│  └─ Índices geoespaciais (GIST)    └─ Filas BullMQ               │
│                                                                  │
│  Cloudflare R2                     Cloudflare CDN                │
│  ├─ PDFs com URL assinada          ├─ Assets e frontend          │
│  └─ Vector tiles estáticos (.pbf)  └─ Tiles servidos na borda    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      SERVIÇOS EXTERNOS                           │
│  Stripe · Google Places (POI) · Browserless · CEMADEN · SSP      │
│  Mapbox GL JS (render) · GTFS público (SPTrans e similares)      │
└─────────────────────────────────────────────────────────────────┘
```

### Estrutura de pastas do monolito

```
src/
├── modules/
│   ├── search/          # Agregação e normalização de imóveis
│   │   ├── index.ts     # Interface pública do módulo
│   │   ├── aggregator.ts
│   │   └── sources/     # ZAP, OLX, QuintoAndar
│   ├── scraping/        # Workers de scraping isolados
│   │   ├── index.ts
│   │   ├── queue.ts     # BullMQ workers
│   │   └── scrapers/
│   ├── gis/             # Toda lógica geoespacial centralizada
│   │   ├── index.ts     # Interface pública do módulo
│   │   ├── otp.ts       # Cliente OpenTripPlanner (tempo de viagem)
│   │   ├── valhalla.ts  # Cliente Valhalla (isócronas a pé/carro)
│   │   ├── tiles.ts     # Geração e serving de vector tiles
│   │   └── h3.ts        # Utilitários H3 (indexação, vizinhança)
│   ├── etl/             # Pipeline de ingestão de bases públicas
│   │   ├── index.ts
│   │   ├── gtfs.ts      # Processa GTFS → PostGIS
│   │   ├── cemaden.ts   # Processa polígonos de alagamento
│   │   ├── ssp.ts       # Processa dados de segurança
│   │   └── osm.ts       # Processa OpenStreetMap .pbf
│   ├── analysis/        # Qualidade de área e POIs
│   │   ├── index.ts
│   │   ├── urban.ts     # Orquestra scores usando dados do PostGIS
│   │   └── poi.ts       # POI via Google Places + OSM
│   ├── reports/         # Geração de PDF e entrega
│   │   ├── index.ts
│   │   ├── generator.ts
│   │   └── queue.ts
│   ├── payment/         # Stripe, webhooks, créditos
│   │   ├── index.ts
│   │   ├── stripe.ts
│   │   └── webhooks.ts
│   └── cache/           # H3 cache com invalidação por evento
│       ├── index.ts
│       └── invalidation.ts
├── core/
│   ├── db.ts            # Prisma client singleton
│   ├── redis.ts         # Redis client singleton
│   ├── event-bus.ts     # EventEmitter interno entre módulos
│   ├── logger.ts        # Pino logger estruturado
│   └── config.ts        # Env vars validadas com Zod
└── api/
    └── routes/          # Fastify routes → chamam módulos
```

---

## 03 — Frontend

### Stack

**Next.js 14 (App Router):** SSR para SEO em páginas de área. Client Components para o mapa interativo. React Server Components para carregamento rápido inicial.

**Mapbox GL JS + Deck.gl:** Mapbox GL JS como base map e consumidor de vector tiles. Deck.gl sobreposto para visualizações complexas: heatmaps de segurança, hexágonos H3 de densidade de imóveis, fluxos de rotas de ônibus. Separar as responsabilidades resolve a limitação visual do Mapbox padrão sem trocar de plataforma.

### Camadas visuais no mapa

**Mapbox GL JS — camadas base:** Polígonos de área de cobertura (isócronas) · Rotas de ônibus e trilhos via vector tiles do pg_tileserv · Marcadores de paradas e estações · Marcadores de imóveis e POIs.

**Deck.gl — camadas analíticas:** `HexagonLayer` com H3 para densidade de imóveis · `HeatmapLayer` para índice de segurança · `ScatterplotLayer` para POIs com encoding por categoria · `PathLayer` para isócronas de caminhada com gradiente de tempo.

### Jornada do usuário — baixa fricção

```
[Digita endereço] → [Mapa carrega preview parcial] → [Explora dados] → [CTA "Ver relatório completo"] → [Pix · recebe relatório < 2min]
  Autocomplete        Gratuito, sem login              Gera desejo       Primeiro paywall
```

> **Regra de ouro — zero fricção antes do paywall:** O usuário não precisa criar conta, fazer login nem fornecer email para ver o preview. O cadastro acontece apenas no momento do pagamento, de forma silenciosa (email capturado no Pix). Isso elimina a maior causa de abandono em produtos SaaS.

### Gratuito vs. pago

| Camada | Conteúdo |
|--------|----------|
| **Gratuito (preview)** | Polígono das áreas no mapa · 3 imóveis desfocados com faixa de preço · Score geral da área (ex: 7.4/10) · Contagem de POIs ("12 mercados na área") · Indicadores qualitativos sem detalhe |
| **Pago (relatório completo)** | Lista completa de imóveis com link e localização exata · Todos os POIs com nome, endereço e avaliação · Score detalhado por dimensão · PDF para download e compartilhamento |

---

## 04 — Backend

### Search Service — Agregação de imóveis

O módulo de scraping roda dentro do monolito mas em workers BullMQ isolados do fluxo principal da API. Uma falha no scraping não derruba a API, e os workers escalam independentemente aumentando o número de processos Node.js. O scraping usa Browserless para não manter infraestrutura de Chromium própria. Os dados são normalizados em schema único e persistidos no PostgreSQL, com Redis como camada de cache por célula H3.

| Fonte | Método | Frequência |
|-------|--------|-----------|
| ZAP / Viva Real | Scraping Playwright headless | Cache 6h por polígono |
| OLX | Scraping HTTP direto | Cache 6h por polígono |
| QuintoAndar | API — parceria ou feed | Tempo real via webhook |

### GIS Module — Coração do sistema

> **Toda lógica geoespacial centralizada em `/gis`:** O módulo GIS é o único ponto de contato com OpenTripPlanner, Valhalla e pg_tileserv. Os outros módulos (`analysis`, `search`, `reports`) chamam interfaces do `/gis` — nunca os serviços externos diretamente. Isso permite trocar engines de roteamento no futuro sem tocar nos módulos de negócio.

**OpenTripPlanner — tempo de viagem real:**
Consome os dados GTFS das SPTrans e similares. Calcula tempo porta-a-porta considerando caminhada até a parada, espera pelo veículo (frequência real da linha), tempo de percurso e transferências. Query padrão: *"do endereço de origem até cada parada/estação num raio de 2km, qual o tempo real saindo às 8h numa terça-feira?"* Resultado cacheado por célula H3 + horário do dia por 24h.

**Valhalla — isócronas de caminhada e carro:**
Consome dados do OpenStreetMap (.pbf). Gera isócronas de 5, 10 e 15 minutos a pé a partir de cada imóvel. Em vez de calcular distância imóvel→POI individualmente (N×M cálculos), a query PostGIS `ST_Within(poi, isocrona)` resolve tudo de uma vez. Resultado cacheado por coordenada do imóvel com tolerância de 50m por 30 dias.

> ⚠️ **Por que não Mapbox Directions para transporte público:** O Mapbox Directions não tem dados de transporte público para o Brasil com qualidade suficiente e cobra por chamada. O cálculo por velocidade média × distância ignora frequência de linha, espera e transferências, gerando erros de 10–40 minutos por trajeto. OpenTripPlanner com GTFS resolve isso com precisão de minutos e custo zero por cálculo.

### ETL Pipeline — Ingestão das bases públicas (~1GB)

As bases públicas nunca são lidas em runtime pela aplicação. O pipeline ETL roda via cron fora do horário de pico, baixa e processa os arquivos, e popula diretamente o PostgreSQL/PostGIS. A API apenas faz queries no banco — nunca nos arquivos brutos.

| Fonte | Tamanho típico | Ferramenta de ingestão | Frequência ETL |
|-------|---------------|----------------------|---------------|
| GTFS (SPTrans + outros) | ~200MB | `gtfs-sequelize` ou parser custom | Semanal |
| OpenStreetMap .pbf | ~400MB (SP) | `osm2pgsql` | Mensal |
| CEMADEN (alagamento) | ~50MB | `ogr2ogr` → PostGIS | Mensal |
| SSP (segurança) | ~100MB | Scraping + normalização CSV | Mensal |
| Arborização (prefeituras) | ~50MB | `ogr2ogr` → PostGIS | Trimestral |

### pg_tileserv — Vector tiles para o frontend

O `pg_tileserv` expõe as tabelas geoespaciais do PostgreSQL como vector tiles no padrão Mapbox. O frontend consome esses tiles como source customizada no Mapbox GL JS — rotas de ônibus, linhas de trem, polígonos de risco de alagamento e cobertura verde renderizados diretamente do banco com estilo controlado pelo frontend. Tiles estáticos das camadas que mudam pouco (alagamento, trilhos) são pré-gerados com `tippecanoe` e servidos via Cloudflare R2 + CDN.

### Analysis Service — Scores de qualidade de área

| Dimensão | Fonte | Implementação |
|----------|-------|--------------|
| **Arborização** | OSM via ETL | Query PostGIS calculando área de cobertura verde dentro da célula H3. Sem chamada de API em runtime. |
| **Segurança** | SSP via ETL | Dados normalizados por setor censitário. Score por `ST_Intersects` com célula H3. Cache 24h. |
| **Alagamento** | CEMADEN via ETL | `ST_Intersects` com polígonos de risco retorna nível baixo/médio/alto. Cache 30 dias. |
| **Transporte público** | GTFS via OTP | Número de linhas, frequência no horário de pico, tempo a pé até a parada. Usa horários reais — não velocidade média. |

### POI Service — Pontos de interesse

Google Places como fonte primária para dados ricos: nome, avaliação, horário, foto, categoria detalhada. Cobertura superior no Brasil especialmente fora de SP/RJ. OSM como fonte complementar para categorias que o Places cobre mal (academias pequenas, feiras). **A busca usa as isócronas do Valhalla — não raio circular, não distância euclidiana.** Um POI separado do imóvel por uma via expressa sem travessia não aparece como acessível.

### Report Generator — Geração assíncrona

Quando o pagamento é confirmado, um job entra na fila BullMQ. O gerador compila todos os dados da área (já pré-computados no preview), renderiza em HTML com Puppeteer e converte para PDF. O arquivo é salvo no Cloudflare R2 com URL assinada de 48h. O usuário recebe o link por email e na tela.

```
[Pagamento confirmado] → [Job BullMQ] → [Coleta dados (cache)] → [Renderiza HTML→PDF] → [Upload R2] → [Entrega < 90s]
```

---

## 05 — Sistema de Pagamento

A prioridade é: integração Pix nativa, sem redirecionamento para outro site, ativação imediata após confirmação.

### Fluxo de relatório avulso

```
[Clica "Ver relatório — R$19"] → [Modal inline · solicita só email] → [QR Code Pix · countdown 10min] → [Webhook confirma] → [PDF liberado + email enviado]
```

### Provedores

| Opção | Pix nativo | Taxa | Recomendação |
|-------|-----------|------|-------------|
| **Stripe** | Sim | ~2.9% + R$0,30 | Principal |
| **Mercado Pago** | Sim | ~2.99% | Alternativa |
| **Pagar.me** | Sim | ~1.99% | Se volume alto |

> **Não reinventar a roda:** Stripe e Mercado Pago já entregam geração de QR Code Pix, webhook de confirmação, gestão de chargebacks, compliance PCI-DSS e suporte a créditos/assinatura para as fases seguintes. O custo de ~3% é barato comparado ao custo de manter infraestrutura própria.

### Evolução por fase

**Fase 1 — Relatório avulso:** Pix via QR Code. Preço fixo (R$19–29). Sem conta obrigatória. Email capturado no pagamento.

**Fase 2 — Créditos:** Pacotes de créditos (ex: 5 relatórios por R$69). Stripe Checkout com Pix. Créditos armazenados no banco vinculados ao email.

**Fase 3 — Assinatura:** Stripe Billing com cobrança recorrente. Plano mensal e anual. Portal de autoatendimento via Stripe — sem construir interface própria.

---

## 06 — Modelo de Dados

PostgreSQL com extensão **PostGIS** habilitada desde o início. A tabela `area_cache` é particionada por data para evitar degradação de performance com crescimento de volume.

| Tabela | Campos principais | Propósito |
|--------|------------------|-----------|
| `users` | id, email, created_at, credits, plan | Usuários cadastrados no pagamento |
| `searches` | id, user_id (nullable), origin_address, origin_coords (POINT), h3_cells[], created_at | Histórico de buscas anônimas e autenticadas. Dados proprietários acumulados desde o início. |
| `reports` | id, user_id, search_id, status, pdf_url, expires_at | Relatórios gerados e PDFs no R2 |
| `payments` | id, user_id, report_id, amount, provider, provider_id, status, created_at | Transações com auditoria completa |
| `area_cache` | h3_cell, data_type, payload, updated_at, invalidated_at | Cache persistente por célula H3. **Particionado por `updated_at` (mensal).** Invalidação por evento, não só TTL. |
| `area_prices` | h3_cell, median_price, price_m2, sample_size, captured_at | **Dado proprietário:** histórico de preços por área. Coletado a cada scraping. |
| `area_quality_scores` | h3_cell, safety_score, green_score, flood_risk, transit_score, computed_at | **Dado proprietário:** índice de qualidade por célula. Evolui com novos dados. |
| `sponsors` | id, name, category, area_h3[], priority, active_until | Estabelecimentos patrocinadores (fase futura). Flag visual obrigatório na interface. |
| `cache_invalidation_events` | id, h3_cell, data_type, reason, triggered_at | Log de invalidações de cache para auditoria. |
| `transit_stops` | id, stop_id, name, coords (POINT), routes[] | Paradas de ônibus e estações ingeridas do GTFS |
| `transit_routes` | id, route_id, name, geom (LINESTRING), frequency_peak | Rotas com frequência calculada no horário de pico |
| `flood_risk_zones` | id, risk_level, geom (POLYGON), source, captured_at | Polígonos de risco do CEMADEN |
| `green_coverage` | id, geom (POLYGON), type, area_m2 | Parques, praças e arborização do OSM/INPE |
| `crime_index_by_sector` | id, sector_id, geom (POLYGON), index_value, period | Índice de segurança normalizado por setor (SSP) |

> **H3 — Indexação geográfica:** Todas as áreas são indexadas pelo sistema hexagonal H3 (Uber). Permite cache eficiente por área, cálculo rápido de vizinhança e agregação em múltiplas resoluções (500m, 2km, bairro). PostGIS complementa o H3 para queries de intersecção e proximidade que o H3 não cobre nativamente.

### Cache com invalidação por evento

TTL fixo (6h, 12h) quebra quando há patrocinadores: um estabelecimento que acabou de pagar não pode esperar horas para aparecer. O sistema usa um **EventBus interno** — quando um patrocinador é ativado, novos dados de scraping chegam, ou dados de segurança são atualizados, um evento é emitido e as células H3 afetadas são invalidadas imediatamente no Redis e registradas em `cache_invalidation_events`.

> ⚠️ **Dados proprietários — coletar desde o primeiro usuário:** As tabelas `area_prices` e `area_quality_scores` devem ser populadas desde o MVP, mesmo sem exposição imediata. O histórico de preços por área ao longo do tempo é o ativo que os portais grandes não têm e que protege o produto de ser replicado rapidamente por concorrentes.

---

## 07 — Stack Tecnológica

| Camada | Tecnologia | Justificativa |
|--------|-----------|--------------|
| Frontend — mapa | Mapbox GL JS + Deck.gl | Mapbox para base e tiles. Deck.gl para camadas analíticas (heatmap, H3, fluxos) que o Mapbox padrão não entrega visualmente |
| Roteamento trans. público | OpenTripPlanner + Docker | Tempo real de viagem com GTFS. Elimina cálculo por velocidade média — usa horários reais e considera horário de pico |
| Isócronas a pé / carro | Valhalla + Docker | Polígonos de alcance real. POI alcançável via `ST_Within` na isócrona — não raio circular |
| Tile server | pg_tileserv | Expõe dados PostGIS como vector tiles. Frontend consome rotas e polígonos de risco sem pré-gerar arquivos estáticos |
| ETL geoespacial | ogr2ogr + osm2pgsql + Node.js cron | Ingestão offline das bases públicas (~1GB). Nunca lidas em runtime |
| Frontend | Next.js 14 + Tailwind | SSR, performance, SEO para páginas de área |
| Backend API | Node.js + Fastify + TypeScript | Performance alta, mesma linguagem do frontend |
| Banco de dados | PostgreSQL + PostGIS + Prisma ORM | PostGIS para queries geográficas. `area_cache` particionado por data |
| Cache | Redis + Upstash | Cache de áreas, filas de job, sessões |
| Filas | BullMQ | Geração assíncrona de relatórios e scraping workers |
| Scraping | Playwright + Browserless | Headless escalável sem manter infraestrutura de Chromium |
| PDF | Puppeteer ou React-PDF | Renderização HTML→PDF de alta qualidade |
| Storage | Cloudflare R2 | S3-compatible, sem taxa de egress |
| Pagamento | Stripe | Pix nativo, Checkout, Billing para assinatura |
| Email | Resend | Entrega de relatório por email |
| Containerização | Docker + docker-compose | Portabilidade total — migração de Railway para AWS/GCP é só configuração |
| Infra | Railway ou Render | Deploy simples para MVP. Docker garante migração sem reescrita |
| CDN | Cloudflare | Assets e PDFs servidos na borda — baixa latência em qualquer cidade |
| Erros | Sentry | Stack traces com contexto de módulo, alertas por severidade |
| Analytics de produto | PostHog | Funis de conversão, heatmaps, eventos por módulo |
| Métricas de sistema | Pino logger + Grafana Cloud | Latência por rota, taxa de sucesso do scraping, tamanho de fila BullMQ, custo por relatório |

---

## 08 — Roadmap de Build

### Fase 1 · Semanas 1–4 — MVP de Relatório Avulso

Monolito containerizado com Docker desde o primeiro dia. Busca por endereço → ETL básico com GTFS de SP → OpenTripPlanner calculando tempo real de viagem até paradas → dados de imóveis (ZAP) → análise de área via PostGIS → geração de PDF → pagamento Pix via Stripe. Sem conta de usuário. Coleta de `area_prices` desde o início.

**Objetivo:** validar se alguém paga com dados de qualidade real.

`Next.js` `Mapbox GL` `PostgreSQL+PostGIS` `OTP Docker` `Stripe Pix` `Puppeteer PDF` `Docker`

### Fase 2 · Semanas 5–8 — GIS completo + visualização

Valhalla para isócronas de imóvel → substitui raio circular para POI. ETL completo: CEMADEN, SSP, OSM arborização, todas as cidades cobertas. `pg_tileserv` servindo rotas e polígonos de risco. Deck.gl para camadas analíticas. Scores de qualidade inteiramente via PostGIS. Cache H3 com invalidação por evento. OLX e QuintoAndar no agregador.

`Valhalla Docker` `Deck.gl` `pg_tileserv` `ETL completo` `H3 cache` `Resend` `BullMQ`

### Fase 3 · Semanas 9–12 — Créditos e conta de usuário

Sistema de conta simples (email + senha). Pacotes de créditos via Stripe Checkout. Histórico de relatórios comprados. Painel do usuário minimalista.

`Auth (NextAuth)` `Stripe Credits` `Dashboard`

### Fase 4 · Mês 4+ — Assinatura e patrocínio

Stripe Billing para plano recorrente. Portal de autoatendimento. Módulo de estabelecimentos patrocinadores com flag visual claro. Painel de anunciantes.

`Stripe Billing` `Sponsor module` `B2B dashboard`

---

## 09 — Escalabilidade do Monolito

A escolha pelo monolito modular é deliberada e não implica teto de escala baixo. As decisões arquiteturais permitem crescimento significativo sem reescrita, desde que os princípios de isolamento entre módulos sejam respeitados.

**✓ Escala horizontal simples:** O monolito é stateless — toda sessão e estado ficam no Redis e PostgreSQL, não na memória do processo. Colocar 3, 5 ou 10 instâncias atrás de um load balancer é só configuração de infra.

**✓ Workers de scraping independentes:** O módulo de scraping roda como worker BullMQ separado do processo HTTP principal. Para escalar scraping, aumenta-se o número de worker processes sem tocar na API.

**✓ Cache que protege o banco:** O H3 cache no Redis garante que buscas repetidas para a mesma área não chegam ao PostgreSQL. Com volume alto, o banco recebe apenas escritas de novos dados e queries de relatórios.

**✓ Docker garante portabilidade:** A containerização desde o MVP significa que a migração de Railway para AWS ECS, Google Cloud Run ou qualquer outra infra é apenas configuração de deploy.

### Quando extrair módulos do monolito

> Extrair um módulo como microserviço só vale a pena quando: (1) o módulo tem ciclo de deploy diferente — scraping atualiza a cada hora, API atualiza com cada release; (2) o módulo precisa de linguagem diferente — análise de imagem pode precisar de Python; (3) o módulo tem SLA diferente — relatório aceita latência maior que a API principal. Antes desses gatilhos, a extração adiciona complexidade operacional sem benefício real.

| Módulo | Escala como? | Gatilho para extrair |
|--------|-------------|---------------------|
| `/gis` | OTP e Valhalla escalam como containers Docker independentes | Se análise de imagem ou ML exigir Python/GPU |
| `/search` | Mais instâncias do monolito | Se precisar de NLP em linguagem diferente |
| `/scraping` | Mais worker processes BullMQ | Se ciclo de deploy precisar ser independente da API |
| `/analysis` | Cache H3 absorve a maior parte | Se análise de imagem/ML exigir Python ou GPU |
| `/reports` | Mais workers de fila BullMQ | Se volume de PDF ultrapassar 10k/dia |
| `/payment` | Stateless, escala junto com a API | Raramente — Stripe já abstrai a complexidade |

---

## 10 — Riscos Técnicos

**⚠ Memória do OpenTripPlanner**
OTP com grafo de SP completo (GTFS + OSM) consome 4–8GB de RAM no startup. Mitigação: container dedicado com limite de memória explícito e estratégia de warm-up antes do primeiro request após deploy. Monitorar heap via Grafana.

**⚠ GTFS desatualizado silenciosamente**
SPTrans e outras operadoras publicam GTFS com atrasos ou inconsistências. OTP com feed vencido retorna tempos incorretos sem erro explícito. Mitigação: validação de data de vigência no ETL, alerta quando o feed tem mais de 7 dias sem atualização.

**⚠ Instabilidade do scraping**
ZAP e OLX podem bloquear ou mudar estrutura HTML. Mitigação: workers isolados com retry e backoff exponencial via BullMQ, Browserless para rotação implícita de IP, fallback gracioso sem derrubar a API principal. Monitorar taxa de sucesso por fonte no Grafana.

**⚠ Custo de Google Places**
Google Places cobra por request. Com volume alto, o custo escala rápido. Mitigação: cache H3 agressivo com invalidação por evento, OSM como complemento para categorias de menor valor. Monitorar custo por relatório gerado desde o MVP.

**⚠ Tempo de geração do PDF**
Isócronas do Valhalla e queries PostGIS pesadas podem alongar o tempo. Mitigação: dados pré-computados no preview — o pagamento aciona apenas a montagem final do PDF. Meta: PDF pronto em menos de 90s após confirmação do Pix.

**⚠ Qualidade dos dados de segurança**
Dados do SSP são fragmentados por estado. Mitigação: começar com São Paulo e expandir por estado com demanda validada. Deixar claro no relatório a fonte e data dos dados exibidos.

**⚠ Módulos sem contrato explícito**
O maior risco do monolito modular é a erosão de fronteiras — um módulo acessar o banco de outro diretamente. Mitigação: cada módulo exporta apenas seu `index.ts`. Regra de lint (`ESLint no-restricted-imports`) para enforçar o isolamento automaticamente.

**⚠ Dados proprietários não coletados**
Não coletar histórico de preços desde o início significa perder meses de vantagem competitiva irrecuperável. Mitigação: tabelas `area_prices` e `area_quality_scores` populadas desde o primeiro scraping do MVP, mesmo sem exposição imediata.

---

*Arquitetura v2.0 · Monolito Modular · 2025 · Plataforma de Análise Imobiliária Urbana*
