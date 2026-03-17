# Análise técnica e de produto do projeto **find-ideal-estate** e proposta de reformulação

## Escopo da análise

Esta análise foi feita com base na inspeção do repositório atual, com foco especial em:

- `app/main.py`
- `app/runner.py`
- `app/store.py`
- `core/listings_ops.py`
- `core/public_safety_ops.py`
- `core/consolidate.py`
- `adapters/candidate_zones_adapter.py`
- `adapters/zone_enrich_adapter.py`
- `adapters/listings_adapter.py`
- `ui/src/App.tsx`
- `ui/src/api/client.ts`
- `ui/src/api/schemas.ts`
- `docker-compose.yml`
- `README.md`
- `ARQUITETURA-SISTEMA.md`
- `MIGRATION_PLAN.md`

Também considerei a documentação oficial atual de Mapbox e Better Auth para avaliar limites, restrições e adequação arquitetural. A revisão final também confronta a implementação real de POIs no repositório, que hoje usa Mapbox Search Box API (Category Search) via `adapters/pois_adapter.py` e `cods_ok/pois_categoria_raio.py`.

---

## Resumo executivo

O projeto atual **já provou viabilidade funcional**, o que é valioso. Ele consegue sair de um ponto de referência, gerar zonas, enriquecer dados, detalhar zona, coletar imóveis e consolidar resultado final. Isso significa que a parte mais difícil de um produto geoespacial desse tipo já foi parcialmente vencida: **o conhecimento de domínio está no repositório**.

O problema é que a aplicação ainda está organizada como um **MVP local orientado a execução por pasta (`run_id`)**, com forte dependência de arquivos em disco, subprocessos e um frontend concentrado em um único componente muito grande. Isso funciona para demonstração, mas não é a base correta para um produto multiusuário, observável, resiliente e evolutivo.

A principal conclusão é esta:

> A melhor reformulação **não** é um rewrite total para Node/Fastify/TypeScript como sugerido em parte da documentação atual, e **também não** é uma migração intermediária para SQLite.
>
> A melhor reformulação é um **monólito modular com backend principal em Python**, persistência em **PostgreSQL + PostGIS desde o início**, **Redis** para fila/cache/locks, **workers desacoplados** para tarefas pesadas, **SSE para progresso em tempo real**, **cache geoespacial de imóveis com stale-while-revalidate por zona/interseção**, e um frontend React organizado por shell de mapa + painéis por etapa.

Em termos de produto, a aplicação deve ser reconstruída em torno de três princípios:

1. **o mapa é o centro absoluto da experiência**;
2. **processamento pesado nunca pode bloquear interação**;
3. **a jornada do usuário precisa ser persistida e reentrante**, com reaproveitamento de resultados e navegação livre entre etapas.

---

# 1. Diagnóstico do projeto atual

## 1.1 O que o projeto já tem de bom

Há acertos importantes que merecem ser preservados.

### A. O pipeline já foi fatiado em estágios de negócio

Mesmo de forma ainda simples, o fluxo já separa:

- validação;
- segurança pública;
- geração de zonas por ponto de referência;
- enriquecimento das zonas;
- consolidação;
- detalhamento de zona;
- coleta de imóveis;
- finalização.

Isso é um bom sinal porque a futura arquitetura assíncrona pode nascer a partir dessa decomposição.

### B. Existe o conceito de `run_id`

O `run_id` atual é rudimentar, mas representa algo muito útil: uma unidade de execução do usuário. Conceitualmente, isso já é quase a futura entidade de **journey**, **job** ou **sessão analítica**.

### C. Já existem contratos na borda

O backend usa Pydantic e o frontend usa Zod. Isso é uma boa base para formalizar contratos, reduzir regressões e evoluir API com mais segurança.

### D. Existe cuidado inicial com smoke/E2E e logs por execução

Para um MVP, isso é acima da média. Vale reaproveitar o espírito disso na nova solução.

### E. O domínio geoespacial já está materializado em scripts e adapters

Os scripts em `cods_ok/` e os adapters atuais representam conhecimento operacional acumulado. Seria um erro desprezar isso e reescrever tudo sem necessidade.

---

## 1.2 Problemas estruturais de arquitetura

## A. O sistema real ainda não é o “monólito modular” descrito na documentação

A documentação fala em:

- Next.js;
- Node.js + Fastify + TypeScript;
- Redis;
- BullMQ;
- Stripe;
- Postgres/PostGIS;
- módulos bem delimitados.

Mas o código observado ainda é essencialmente:

- **FastAPI** como camada HTTP;
- lógica relevante distribuída entre `app/main.py`, `core/*`, `adapters/*` e scripts externos;
- armazenamento em **arquivos por run**;
- orquestração com `asyncio.create_task(...)` e `asyncio.to_thread(...)`;
- frontend React/Vite concentrado em `ui/src/App.tsx`.

Ou seja: a documentação descreve um destino, mas **não descreve o estado atual do produto**. Isso é importante porque várias decisões sugeridas ali partem de uma base que ainda não existe.

## B. A camada HTTP ainda concentra regra de negócio demais

`app/main.py` está grande e acumula responsabilidades que deveriam pertencer a serviços de domínio. Os endpoints fazem mais do que adaptar request/response; eles decidem fluxos, tratam arquivos, montam respostas detalhadas e coordenam partes do pipeline.

Isso gera três efeitos ruins:

- aumenta o acoplamento;
- dificulta testes unitários reais;
- faz a API virar o lugar onde tudo acontece.

## C. O backend é orientado a filesystem, não a estado persistido de produto

Hoje a unidade de verdade do sistema é a pasta:

- `runs/<run_id>/status.json`
- `runs/<run_id>/input.json`
- `runs/<run_id>/logs/events.jsonl`
- artefatos derivados em subpastas.

Isso foi adequado para provar o pipeline, mas é frágil para:

- multiusuário;
- autorização por dono da execução;
- cancelamento robusto;
- auditoria;
- recuperação transacional;
- listagem de histórico do usuário;
- reaproveitamento de partes já processadas.

## D. O sistema ainda depende fortemente de subprocessos e scripts externos

Os adapters chamam scripts Python via `subprocess.run(...)`. Isso introduz:

- custo de processo por etapa;
- controle precário de timeout;
- cancelamento difícil;
- observabilidade ruim;
- tratamento de erro limitado;
- complexidade para paralelismo controlado.

Para um MVP local isso é aceitável. Para produção, isso precisa virar uma camada de execução mais previsível.

## E. O modelo atual de execução assíncrona é insuficiente para produção

Hoje a criação da run dispara `asyncio.create_task(runner.run_pipeline(run_id))`. Isso não é uma fila de jobs de produção. Faltam:

- persistência robusta do job;
- retomada confiável após crash do processo;
- separação entre API e worker;
- cancelamento cooperativo com estado transacional;
- limitação de concorrência por tipo de tarefa;
- retries estruturados;
- DLQ ou estratégia de erro terminal.

---

## 1.3 Problemas de organização de código

## A. O frontend está excessivamente concentrado

`ui/src/App.tsx` tem mais de **3.300 linhas**. Isso é um indicador objetivo de acoplamento excessivo.

Ele concentra ao mesmo tempo:

- shell da tela;
- inicialização do mapa;
- estado de fluxo;
- controle de camadas;
- polling de backend;
- progresso de execução;
- seleção de zonas;
- detalhamento;
- listagem de imóveis;
- renderização de painéis.

Isso torna a evolução perigosa. Cada melhoria visual ou comportamental vira uma alteração de alto risco.

## B. Há estado de domínio misturado com estado visual

No frontend atual, estados de negócio e de UI convivem no mesmo nível:

- `runId`
- `runStatus`
- `zonesCollection`
- `selectedZoneUid`
- `zoneDetailData`
- `finalListings`
- `layerVisibility`
- `isPanelMinimized`
- `isLayerMenuOpen`
- `loadingText`
- `executionProgress`

Esse desenho dificulta rastrear dependências, invalidação de dados e reaproveitamento entre etapas.

## C. Ainda existem sinais de dívida de limpeza

A própria documentação de migração aponta arquivos mortos e divergências de configuração. Isso é um sinal claro de que o repositório já começou a acumular entropia.

## D. Configuração ainda está dispersa

Há leitura de ambiente ad hoc, caminhos fixos e dependência de estrutura local (`data_cache`, `cache`, `profiles`, `cods_ok`). Isso aumenta risco de drift entre ambientes.

---

## 1.4 Problemas de escalabilidade

## A. Escalabilidade horizontal é praticamente inexistente no desenho atual

Como o estado da execução vive no disco local e o job nasce dentro do processo da API, escalar horizontalmente a aplicação fica problemático:

- instância A cria a run;
- instância B não necessariamente enxerga o mesmo filesystem;
- cancelamento e progresso ficam acoplados à instância original;
- um restart pode perder o job em execução.

## B. O pipeline não está modelado para resultados parciais ricos

O usuário quer ver progresso detalhado e resultados intermediários. Hoje isso ainda está muito mais próximo de “run em andamento + consulta de status” do que de um fluxo incremental por evento.

## C. O custo de chamadas externas tende a crescer de forma ruim

Há uso atual ou previsto de APIs externas para:

- autocomplete/geocoding;
- POIs;
- Tilequery/ruas;
- imagens de mapa;
- possivelmente scraping assistido;
- eventualmente autenticação e pagamentos.

Sem uma política rígida de cache, deduplicação, fallback e orçamento por operação, esse custo vai subir de forma desorganizada.

## D. O uso de SQLite como etapa intermediária seria um desvio ruim

A proposta no `MIGRATION_PLAN.md` de usar SQLite como passo intermediário pode até parecer barata, mas para este produto ela atrasa a solução correta.

O sistema precisa desde cedo de:

- concorrência razoável;
- dados geoespaciais ricos;
- joins analíticos fortes;
- versionamento de datasets;
- histórico de preço;
- jobs multiusuário.

Isso aponta para **PostgreSQL + PostGIS**, não para SQLite.

---

## 1.5 Problemas de UX/UI e produto

## A. A UX atual ainda gira em torno do pipeline, não da jornada do usuário

A aplicação atual ainda “cheira” a orquestração técnica:

- create run;
- poll status;
- load zones;
- select zone;
- detail;
- listings;
- finalize.

A nova UX precisa inverter isso. O usuário não pensa em “run”. Ele pensa em:

- escolher origem;
- escolher ponto de transporte;
- comparar zonas;
- explorar critérios;
- buscar imóveis;
- decidir onde morar.

## B. O progresso exibido no frontend ainda é parcialmente artificial

O componente atual usa progresso visual com ETA esperada. Isso ajuda no MVP, mas não resolve o requisito novo. O usuário quer mensagens reais do backend, como:

- analisando área verde;
- processando segurança pública;
- calculando zonas;
- procurando imóveis no QuintoAndar;
- consolidando anúncios duplicados.

Isso exige **eventos de progresso reais**, não apenas cronômetro sintético no cliente.

## C. A navegação entre etapas ainda não parece modelada como jornada persistida

Você quer que o usuário navegue livremente entre etapas concluídas, sem recomputação desnecessária. Isso exige uma modelagem explícita de:

- dependências entre etapas;
- snapshots dos parâmetros;
- cache de resultados por fingerprint;
- invalidação seletiva.

Hoje isso ainda não está maduro.

## D. O fluxo de transporte ainda não está no nível de clareza exigido

Seu requisito é muito específico:

- selecionar um único ponto de transporte elegível;
- ver distância até cada um;
- ver linhas que passam;
- ver trajeto a pé até cada ponto;
- só então gerar zonas.

Esse fluxo precisa ser tratado como uma etapa de produto autônoma, não como um detalhe da geração de zonas.

## E. O painel lateral ainda precisa virar um sistema de navegação de verdade

Ele não pode ser apenas um contêiner de formulários. Ele precisa atuar como:

- wizard reentrante;
- painel contextual do mapa;
- painel de progresso;
- painel comparativo;
- painel analítico;
- painel de imóveis.

---

## 1.6 Gargalos de performance e riscos técnicos

## A. Polling como mecanismo principal de atualização

Polling é simples, mas não é a melhor base para o nível de interatividade exigido. Para status bruto ele serve. Para progresso detalhado e resultados parciais, ele é inferior a SSE.

## B. Dependência de GeoJSON grande no cliente

Para manter o mapa fluido, é perigoso depender demais de grandes blobs GeoJSON em memória. O ideal é:

- usar GeoJSON apenas para seleção ativa e pequenos subconjuntos;
- usar vector tiles/PMTiles para camadas pesadas;
- limitar o que entra no cliente por viewport e por etapa.

## C. Falta de cancelamento real

Hoje não há base robusta para cancelar subprocessos em cascata, marcar job como cancelado e encerrar processamento cooperativamente.

## D. Logging de corpo completo de request

Há middleware logando corpo da requisição. Em desenvolvimento isso ajuda. Em produção, isso pode vazar:

- endereços pesquisados;
- parâmetros sensíveis;
- identificadores;
- eventualmente dados pessoais.

Isso precisa ser sanitizado ou removido no ambiente produtivo.

## E. Dependência mal distribuída de APIs externas

O problema não é usar API externa em si. Em várias consultas geoespaciais ela é necessária porque o dado operacional ou autoritativo pertence ao provedor responsável pela malha, geocodificação, rota ou isócrona. O erro seria transformar essas chamadas na espinha dorsal síncrona de toda a experiência.

O caso mais crítico continua sendo POI, porque a implementação real já depende da Mapbox Search Box API para essa camada. O risco não é “usar Mapbox”, e sim usar sem governança. Se a aplicação tratar a Search Box como se fosse dataset permanente da cidade, ela fica:

- mais cara;
- mais sujeita a limite;
- mais vulnerável a mudanças de produto/licença;
- menos previsível em custo.

A reformulação correta é esta:

- usar a Mapbox onde o repositório já provou que ela é a origem operacional dos POIs;
- manter ruas/grafo/dados locais na infraestrutura própria;
- responder primeiro com cache efêmero quando houver;
- revalidar em background apenas dentro da janela curta definida para POIs.

---

# 2. Conflitos de requisitos identificados

Antes da arquitetura alvo, há conflitos importantes.

## Conflito 1 — Navegação livre entre etapas vs invalidação por mudança upstream

Você quer que o usuário possa voltar a etapas anteriores sem perder tudo. Mas, se ele muda:

- ponto principal;
- ponto de transporte;
- raio da zona;
- tempo máximo;
- critérios de análise;

parte dos resultados posteriores deixa de ser válida.

### Solução

Modelar a jornada como **grafo de dependências**:

- cada etapa gera um snapshot de entrada e um snapshot de saída;
- ao alterar uma entrada upstream, o sistema marca etapas descendentes como **stale**;
- resultados antigos continuam navegáveis para comparação;
- ações que dependem do estado novo pedem reprocessamento apenas do necessário.

## Conflito 2 — Mapa extremamente fluido vs grande volume de dados analíticos

Você quer muitas camadas, POIs, zonas, rotas, imóveis e dashboard. Isso pode destruir a fluidez se tudo for empurrado ao cliente.

### Solução

Separar:

- **camadas base e pesadas** em vector tiles/PMTiles;
- **seleção ativa** em GeoJSON pequeno;
- **dados textuais/analíticos** no painel;
- **rotas detalhadas sob demanda**, não tudo pré-renderizado.

## Conflito 3 — Custo controlado vs uso intenso de APIs de terceiros

Seu produto depende de mapa, busca, rotas, POI e scraping. Sem cuidado, o custo cresce antes da base de usuários.

### Solução

Reduzir chamadas externas ao mínimo estritamente necessário sem negar seu papel quando a fonte autoritativa é externa. O núcleo analítico e persistente deve ficar em infraestrutura própria, enquanto consultas operacionais devem seguir um fluxo com cache, persistência, fingerprint e revalidação em background:

- mapas analíticos próprios;
- base local para ruas/apoio geoespacial e Mapbox Search Box API para POIs;
- GTFS/OTP e bases próprias para o que puder ser internalizado;
- APIs externas apenas para dados transitórios ou autoritativos do provedor;
- proxy server-side;
- quotas;
- stale-while-revalidate por tipo de informação.

## Conflito 4 — Monólito sem microserviços vs necessidade de processamento pesado

Isso não é realmente um conflito, desde que se entenda a diferença entre:

- **arquitetura de produto**;
- **processos auxiliares de infraestrutura**.

### Solução

O produto continua sendo um **monólito modular**. Ele pode ter:

- API;
- worker;
- scheduler;

sem virar microserviços. São processos do mesmo sistema, no mesmo repositório, com o mesmo domínio e o mesmo banco.

---

# 3. Arquitetura recomendada

## 3.1 Decisão principal

A arquitetura alvo recomendada é:

## **Monólito modular com backend principal em Python + frontend React/Next + Postgres/PostGIS + Redis + workers assíncronos + SSE**

### Por que esta é a melhor opção

Porque ela equilibra:

- baixo volume inicial;
- custo controlado;
- crescimento futuro;
- observabilidade;
- manutenção;
- aderência ao domínio geoespacial já existente no repositório.

---

## 3.2 O que eu recomendo manter e o que eu recomendo rejeitar

## Manter

- backend principal em Python;
- reaproveitamento gradual dos scripts geoespaciais existentes;
- conceito de `run` como embrião de `journey/job`;
- contratos de API tipados;
- foco em monólito modular.

## Rejeitar

- rewrite total imediato para Node/Fastify;
- SQLite como etapa de persistência intermediária;
- dependência estrutural de polling para progresso rico;
- tratar POIs da Mapbox como se fossem dataset-base persistido da cidade;
- crescimento do frontend em um único componente gigante.

---

## 3.3 Arquitetura alvo em alto nível

```text
[Vercel — CDN global]
  React/Next.js App Router
  Map shell + painéis por etapa
  TanStack Query + Zustand
  SSE para progresso / eventos
          |
          v
[Hostinger — topologia inicial: 1× VPS KVM 4]
  Reverse proxy + TLS
  API Monolith - Python/FastAPI
  worker-general
  worker-scheduler
  PostgreSQL + PostGIS
  Redis
  Valhalla
  OTP 2
  worker-scrape-browser (Playwright)
          |
          v
[Cloudflare R2]
  relatórios
  artefatos exportáveis
```

**Topologia inicial fechada:** um único **Hostinger VPS KVM 4** concentra `api`, `worker-general`, `worker-scheduler`, PostgreSQL/PostGIS, Redis, Valhalla, OTP e `worker-scrape-browser`.

**Topologia de escala fechada:** quando houver contenção medida, a infraestrutura passa para dois VPS ainda na Hostinger:
- **VPS APP/DATA**: `api`, `worker-general`, `worker-scheduler`, PostgreSQL/PostGIS, Redis;
- **VPS GEO/SCRAPE**: Valhalla, OTP e `worker-scrape-browser`.

Essa transição preserva o monólito, mantém Vercel no frontend e evita saltar cedo para uma topologia mais cara do que o projeto precisa.

---

### Observação de performance da topologia inicial

Valhalla self-hosted tende a entregar latência local competitiva para rotas a pé, e as isócronas mais caras são persistidas por fingerprint no PostGIS. Isso significa que o custo computacional pesado fica concentrado na primeira geração e depois é amortizado por reaproveitamento e cache.

## 3.4 Estrutura do monólito

## Repositório

```text
find-ideal-estate/
  apps/
    web/
    api/
  packages/
    contracts/
    design-system/
  infra/
    docker/
    migrations/
    seeds/
  docs/
```

## Backend (`apps/api`)

```text
apps/api/src/
  core/
    config.py
    logging.py
    security.py
    db.py
    redis.py
    sse.py
    errors.py
  modules/
    auth/
    users/
    journeys/
    jobs/
    transport/
    zones/
    urban_analysis/
    pois/
    listings/
    deduplication/
    reports/
    usage_limits/
    datasets/
  adapters/
    mapbox/
    otp/
    osm/
    scraping/
    legacy_scripts/
  workers/
    queue.py
    handlers/
  api/
    routes/
    schemas/
```

## Frontend (`apps/web`)

```text
apps/web/src/
  app/
  features/
    map/
    search/
    transport-selection/
    zones/
    listings/
    reports/
    dashboard/
  components/
    shell/
    panel/
    map-controls/
    cards/
    charts/
    feedback/
  state/
    ui-store.ts
    journey-store.ts
    map-store.ts
  lib/
    api/
    sse/
    formatters/
    validators/
```

### Observação importante

Isto continua sendo **monólito**. Não há múltiplos serviços de negócio autônomos. Há um único sistema com módulos internos bem definidos.

### Regras de dependência entre módulos

Módulos seguem dependência unidirecional estrita. Sem essa regra, o monólito degenera em spaghetti code mesmo com a estrutura de pastas correta:

```
Permitido:  api/routes  → módulos de domínio → módulos de infraestrutura
Proibido:   módulos de domínio importando de api/routes
Proibido:   módulos de infraestrutura importando de domínio
```

Mapa de dependências permitidas para este projeto:

```
api/routes/*          → pode importar de qualquer módulo de domínio
modules/journeys      → pode importar de transport, zones, listings
modules/listings      → pode importar de deduplication, usage_limits
modules/zones         → pode importar de urban_analysis, pois, transport
modules/transport     → NÃO importa de zones, listings, journeys
modules/deduplication → NÃO importa de listings (recebe dados, não busca)
```

### Contratos entre módulos via DTOs

Módulos nunca importam modelos internos uns dos outros. A comunicação acontece por DTOs explícitos definidos em `packages/contracts/`:

```python
# Errado — acoplamento direto de modelo interno
from modules.listings.models import ListingAd
from modules.zones.service import ZoneService

# Correto — DTO compartilhado
from contracts.listings import ListingAdDTO
from contracts.zones import ZoneSummaryDTO
```

A pasta `packages/contracts/` já aparece na estrutura do repositório — ela deve ser populada desde o início, não depois.

### Injeção de dependência

Serviços de domínio recebem dependências pelo construtor, nunca importam globais. Isso permite testes unitários sem banco ou Redis:

```python
class ListingsService:
    def __init__(
        self,
        repo: ListingsRepository,      # interface, não implementação concreta
        cache: CachePort,
        scraper_factory: ScraperFactory,
        usage_limits: UsageLimitsPort,
    ):
        ...
```

Os `Port` são protocolos Python (`typing.Protocol`) — a implementação real é injetada pelo container de dependências. Em testes, uma implementação fake é injetada sem modificar o serviço.

**Documentação viva das dependências:**
Cada `modules/<nome>/__init__.py` deve conter um comentário declarando quais módulos ele pode e não pode importar. Isso serve de guardrail para revisão de código.

---

## 3.5 Tecnologias recomendadas

## Backend

- **Python 3.12+**
- **FastAPI**
- **SQLAlchemy 2 + Alembic**
- **PostgreSQL 16 + PostGIS**
- **Redis**
- **Dramatiq** para jobs — escolhido sobre RQ pela política de retry nativa por tipo de job via middleware, pelo `StubBroker` que permite testes unitários sem Redis real, e pela consistência com o padrão de injeção por construtor. RQ exigiria código manual para replicar os backoffs distintos definidos em `JobRetryPolicy`.
- **fastapi-users** para autenticação — magic link por email nativo, OAuth social integrado, suporte a SQLAlchemy 2 documentado. Elimina o risco de implementar rotação de sessão e timing-safe comparison manualmente.
- **SSE** para progresso em tempo real
- **Pydantic v2**

## Frontend

- **React + Next.js App Router** — hospedado no Vercel (plano gratuito na fase inicial)
- **MapLibre GL JS** — escolhido sobre Mapbox GL JS por ser open source (sem cobrança por map load, sem lock-in de licença), compatível com PMTiles via plugin oficial, e com API ~95% idêntica ao Mapbox v1.
- **TanStack Query** para estado servidor
- **Zustand** para estado de UI/mapa/jornada
- **shadcn/ui** — escolhido sobre design system próprio. Componentes copiados para o repositório (código 100% visível e modificável), sem custo de partir do zero. Os tokens de cor e tipografia da seção 9.1 são configurados uma vez no `tailwind.config.ts`. Customizações imediatas: cores de marca, raio de borda mais suave, sombra dos cards flutuantes sobre o mapa, variante de badge para estados de frescor (`fresh`, `stale_but_usable`, `revalidating`).
- **Recharts** para gráficos — escolhido sobre ECharts. Os casos de uso do produto (série histórica de preço, histograma de faixa, bar charts de métricas) não justificam a API imperativa e o bundle do ECharts. Recharts é composicional e idiomático no ecossistema React. Cuidado de performance: limitar séries históricas a 365 pontos máximos e usar `dot={false}` acima de 90 pontos.

## Infra auxiliar

- **OpenTripPlanner 2** para transporte público baseado em GTFS
- **Valhalla self-hosted** para rotas a pé e isócronas (walking, transit, car) — endpoints `/route` e `/isochrone`, retorna GeoJSON direto para PostGIS. ~4GB RAM para grafo walking SP; ~8GB com carro. Container Docker oficial disponível.
- **MapTiler** como provedor de tiles base — **provedor único de tiles para todo o ciclo de vida do produto**. Tier gratuito (100k map loads/mês) cobre a fase inicial; upgrade de plano no painel MapTiler quando o volume justificar, sem nenhuma mudança de código ou infraestrutura.
- **OSM local para grafo/apoio geoespacial** e **Mapbox Search Box API** para POIs
- **Cloudflare R2** para relatórios e tiles exportados

## Deploy

- **Vercel** para o frontend Next.js — plano gratuito na fase inicial, deploy automático por push, CDN global incluso, preview deployments por branch. Desenvolvido pela mesma equipe do Next.js — suporte nativo a App Router, Server Components e middleware.
- **Hostinger VPS único — KVM 4** como topologia inicial do backend: `api`, `worker-general`, `worker-scheduler`, PostgreSQL/PostGIS, Redis, Valhalla, OTP, OSM/GTFS e `worker-scrape-browser` (concorrência 1).
- **Escalação na própria Hostinger:** separar a stack em dois VPS apenas quando houver contenção medida entre app, geoespacial e scraping.

## Injeção de dependência

- **Composição manual** no `lifespan` do FastAPI para as Fases 0–3 (até ~5 módulos ativos).
- **dependency-injector** a partir da Fase 4 — integração com FastAPI documentada, modelo de Container/Provider explícito e auditável. Migração incremental por módulo, iniciando quando o domínio de transporte e zonas estiver ativo.

---

## 3.6 Decisões arquiteturais centrais

## A. PostGIS desde o início

Essa é uma decisão-chave. Seu produto é geoespacial por natureza. Colocar SQLite no meio do caminho cria retrabalho.

Com PostGIS você resolve corretamente:

- interseção entre zonas e polígonos;
- indexação espacial;
- filtros por raio;
- enriquecimento por proximidade;
- consultas por bounding box;
- versionamento de datasets;
- materialized views para zonas e dashboards.

## B. Redis como infraestrutura pequena, mas muito valiosa

Redis deve ser usado para:

- fila de jobs;
- rate limiting por usuário/IP/operação;
- locks para deduplicação de execução;
- cache curto de consultas externas;
- fan-out simples de eventos para SSE.

## C. SSE no lugar de WebSocket como mecanismo principal de progresso

Para este produto, o fluxo é predominantemente **server → client**. O usuário não precisa de troca bidirecional contínua de baixa latência. Ele precisa de:

- progresso real;
- mensagens de etapa;
- resultados parciais;
- conclusão/falha/cancelamento.

Por isso, SSE é melhor que WebSocket para a primeira versão robusta:

- mais simples;
- mais barato;
- mais fácil de operar;
- ótimo para streaming de eventos;
- excelente compatibilidade com proxies.

Use REST para comandos e SSE para eventos.

## D. Jobs cooperativos e granulares

Em vez de um job monolítico “gerar tudo”, o sistema deve quebrar o trabalho em subjobs. Um **job** é definido como a menor unidade que satisfaz simultaneamente:

1. **Pode ser retentado de forma idempotente** sem efeitos colaterais indesejados;
2. **Tem resultado próprio persistível** que pode ser consultado independentemente;
3. **Tem duração esperada acima de 5 segundos** — abaixo disso não justifica overhead de fila.

### Tabela de granularidade

| Operação | É um job? | Justificativa |
|---|---|---|
| Geocodificar endereço | Não | < 1s, vai para cache Redis diretamente |
| Buscar pontos de transporte elegíveis | Sim | PostGIS + GTFS, 3–10s |
| Calcular rota a pé até cada ponto | Não | Vai junto do job de transporte |
| Gerar isócrona de uma zona (walking/transit) | Sim | Valhalla `/isochrone`, 150–500ms; resultado persistido por fingerprint |
| Gerar isócrona de uma zona (car — plano Pro) | Sim | Valhalla `/isochrone` perfil carro, 400–1500ms; resultado persistido por fingerprint |
| Enriquecer zona com área verde | Sim | PostGIS ST_Intersection, 5–15s |
| Enriquecer zona com alagamento | Sim | PostGIS ST_Intersection, 5–15s |
| Enriquecer zona com segurança | Sim | PostGIS + agregação, 5–15s |
| Enriquecer zona com POIs | Sim | Mapbox Search Box API (Category Search) + normalização/cache efêmero, 5–20s |
| Scraping de imóveis por plataforma | Sim | Playwright em worker dedicado, 20–60s, falha isolada por plataforma |
| Deduplicar imóveis da zona | Sim | Após todos scrapers concluírem |
| Gerar relatório PDF | Sim | Renderização + object storage, 5–20s |

### Política de retry por tipo de job

```python
class JobRetryPolicy:
    TRANSPORT_SEARCH = dict(max_retries=2, backoff_seconds=[5, 30])
    ZONE_GENERATION  = dict(max_retries=1, backoff_seconds=[10])
    ENRICHMENT       = dict(max_retries=2, backoff_seconds=[5, 15])
    SCRAPING         = dict(max_retries=3, backoff_seconds=[10, 30, 60])
    DEDUPLICATION    = dict(max_retries=2, backoff_seconds=[5, 10])
    REPORT           = dict(max_retries=1, backoff_seconds=[15])
```

Scraping tem mais retries porque falha transitória é comum (timeout, rate limit momentâneo). Zone generation tem retry menor porque Valhalla é local — falhas persistentes indicam problema sério que retry não resolve.

### Concorrência por fila

```python
DRAMATIQ_QUEUES = {
    "transport":      {"concurrency": 4},  # leve, PostGIS local
    "zones":          {"concurrency": 2},  # Valhalla CPU-bound; isócrona de carro usa ~1GB RAM temporária
    "enrichment":     {"concurrency": 4},  # PostGIS, paralelizável por zona
    "scrape_browser": {"concurrency": 1},  # Playwright no VPS; 1 browser por vez; ~300MB RAM
    "deduplication":  {"concurrency": 2},  # CPU + DB
    "reports":        {"concurrency": 1},  # WeasyPrint usa 400–600MB RAM por relatório
}
```

`zones` com concorrência 2 porque isócronas de carro usam ~1GB de RAM temporária no Valhalla — com 4 simultâneas o VPS único (16GB KVM 4) pode ter OOM. `reports` com concorrência 1 pelo mesmo motivo com WeasyPrint. `scrape_browser` com concorrência 1 porque o baseline inicial do produto preserva o comportamento atual baseado em browser automation: cada coleta abre contexto Playwright dedicado, consome mais RAM que `httpx` e é a parte mais sensível a bloqueio e vazamento de memória.

**Decisão fechada:** no alvo arquitetural imediato, os três scrapers atuais (**QuintoAndar, Zap Imóveis e VivaReal**) executam na fila `scrape_browser`, em worker Dramatiq próprio no **Hostinger VPS** (São Paulo), separado do worker geral. Scraping HTTP (via `httpx`, sem browser) é uma abordagem válida para plataformas que o permitam — quando implementado, também roda no Hostinger VPS na mesma camada de scraping, em fila própria (`scrape_http`).

Se scraping virar gargalo com mais usuários, o primeiro movimento é subir outra máquina do **mesmo worker dedicado** consumindo só a fila `scrape_browser`, mantendo concorrência 1 por processo. Isso preserva isolamento sem afetar as outras filas.

### Benefícios da granularidade correta

- progresso real e granular via SSE;
- resultados parciais disponíveis antes do pipeline completo;
- retries localizados sem re-executar etapas já concluídas;
- cancelamento mais limpo com estado parcial reaproveitável;
- melhor uso de cache por fingerprint de entrada.


### Execução do scraping browser

O scraping com browser fica **fisicamente isolado** em um processo/grupo de máquinas próprio no **Hostinger VPS** (São Paulo):

- `api` — recebe comandos e transmite SSE (Hostinger);
- `worker-general` — transporte, zonas, enriquecimento, deduplicação e relatórios (Hostinger);
- `worker-scrape-browser` — somente Playwright (Hostinger).

A imagem Docker do `worker-scrape-browser` deve incluir Playwright e browsers instalados. O processo consome exclusivamente a fila `scrape_browser`.

**Bright Data é escape hatch, não base da arquitetura.** O fluxo padrão é:

1. scraper roda com Playwright no `worker-scrape-browser`, sem proxy residencial;
2. métricas por plataforma monitoram taxa de sucesso, taxa de resultado vazio, tempo e bloqueios;
3. se uma plataforma entrar em degradação sustentada, o worker passa a usar Bright Data **apenas para aquela plataforma**, por configuração;
4. quando a degradação cessar, o proxy pode ser desligado sem alteração de código.

Para eliminar ambiguidade operacional, o gatilho inicial fica definido assim:

- habilitar Bright Data para uma plataforma quando, na janela móvel de 24h:
  - `success_rate < 85%`, **ou**
  - `empty_result_rate > 20%` em zonas com cobertura historicamente não vazia, **ou**
  - houver evidência manual de bloqueio/CAPTCHA;
- desabilitar Bright Data quando, por 72h consecutivas, `success_rate >= 95%` e `empty_result_rate <= 10%`.

Esses limiares podem ser recalibrados no futuro, mas a **decisão de infraestrutura da versão alvo fica fechada**: Playwright isolado na Hostinger; Bright Data somente como escape hatch por plataforma.

---

# 4. Estratégia de frontend

## 4.1 Princípio de UX

A nova interface deve ser tratada como um **map-first analytical workspace**.

Não é uma página com mapa. É um **ambiente de decisão imobiliária guiado por mapa**.

---

## 4.2 Estrutura visual recomendada

## Layout base desktop

- mapa ocupando 100% da tela como plano principal;
- painel lateral direito visível por padrão;
- trilho superior com botão de recolher/expandir painel;
- busca de endereço flutuante no canto superior esquerdo;
- botão de camadas flutuante no canto inferior direito, alinhado ao estado do painel;
- legenda flutuante no canto inferior esquerdo;
- controles extras de mapa agrupados sem competir com o painel.

## Larguras recomendadas

- painel aberto padrão: **420 px**
- painel expandido na etapa de imóveis: **560–640 px**
- painel recolhido: **64 px**

## Responsividade mobile/tablet

- mapa continua principal;
- painel vira bottom sheet arrastável;
- controles de camada e legenda refluem para bottom sheet ou FAB menu;
- cards de imóvel e dashboard ficam em abas dentro do painel.

---

## 4.3 Shell de interação

## Componentes principais

- `MapShell`
- `AddressSearchBox`
- `RightJourneyPanel`
- `LayerControlFab`
- `LegendCard`
- `PanelToggleButton`
- `StepBreadcrumb`
- `ExecutionStatusRail`

## Regras importantes

- o mapa nunca some;
- o painel nunca “reinicia” o fluxo sem explicação;
- toda mudança upstream marca estados downstream como stale com aviso explícito;
- o usuário sempre consegue entender em que etapa está e o que já foi aproveitado.

---

## 4.4 Fluxo de etapas do frontend

## Etapa 1 — Configuração inicial

### Objetivo
Definir origem, filtros iniciais e o recorte analítico.

### Painel
Campos:

- ponto de referência principal;
- ponto secundário opcional — marcador de referência pessoal (trabalho, escola, academia). Não afeta geração de zonas nem isócronas. Aparece no detalhe da zona com distância a pé e tempo via Valhalla, e no relatório PDF na seção de Mobilidade. Campo: texto com autocomplete de endereço, label livre, pode ser adicionado ou removido a qualquer momento sem invalidar resultados já gerados. Persistido como `secondary_reference_point` (ponto geográfico + label) em `journeys`.
- aluguel/compra;
- raio da zona;
- modal de transporte (transporte público / a pé disponível para todos; isócrona de carro disponível apenas para plano Pro — aparece no painel com lock e CTA de upgrade se o usuário for gratuito);
- tempo máximo;
- distância até seed de transporte;
- checkboxes de análise;
- selecionar/desselecionar todos;
- botão “achar pontos de transporte”.

### Comportamento
- ao entrar em modo de seleção do ponto principal, cursor vira pin **somente sobre o mapa**;
- clique no mapa fixa o ponto;
- busca textual e clique no mapa são equivalentes como origem.

---

## Etapa 2 — Seleção do ponto de transporte

### Objetivo
Escolher **um único** ponto de transporte elegível a partir do ponto principal.

### Mapa
- círculo de alcance com raio configurado;
- pontos elegíveis destacados;
- trajetos a pé até cada ponto;
- popup contextual ao selecionar ponto;
- destaque visual forte do item ativo.

### Painel
Lista com:

- distância a pé;
- tipo do ponto;
- quantidade de linhas;
- linhas disponíveis;
- botão “gerar zonas a partir desse ponto”.

### UX recomendada
- lista ordenada por prioridade relevante: menor tempo a pé, maior conectividade, aderência ao modal escolhido;
- cada item mostra mini-resumo, não texto excessivo;
- no hover da lista, o ponto correspondente acende no mapa.

---

## Etapa 3 — Geração de zonas

### Objetivo
Executar processamento pesado sem travar a navegação.

### Painel
Mostrar:

- barra de progresso real;
- etapa corrente;
- eventos recentes;
- subtarefas concluídas;
- botão cancelar;
- indicação de resultados já disponíveis.

### Mapa
- continua navegável;
- já pode mostrar zonas assim que surgirem;
- usuário pode inspecionar o que estiver pronto.

### Regra de UX
O usuário nunca deve sentir que a tela “parou”.

---

## Etapa 4 — Visualização e comparação de zonas

### Painel
- lista ordenada por `travel_time_minutes` ascendente; empates resolvidos por `walk_distance_meters` ascendente;
- badges de destaque por critério com cálculo incremental (ver regras abaixo);
- filtros por critério ativo;
- detalhes contextuais da zona selecionada;
- grupos de POIs por categoria clicáveis;
- CTA “buscar imóveis na zona”.

### Regras de ordenação e badges

**Ordenação primária:**
A lista de zonas deve ser sempre ordenada por `travel_time_minutes` ascendente. Empates resolvidos por `walk_distance_meters` ascendente. A ordenação nunca deve variar entre sessões com os mesmos dados — qualquer variação gera desconfiança.

**Badges — cálculo incremental em quatro fases:**

Os badges não esperam o enriquecimento de todas as zonas, nem são calculados por um worker sequencial ao final. O cálculo acontece progressivamente no backend à medida que cada zona é enriquecida:

- **Fase 1 — zona enriquecida individualmente:** assim que uma zona conclui seu enriquecimento, o backend calcula badges provisórios comparando-a com a mediana das zonas já enriquecidas até aquele momento. A mediana é parcial e os badges são marcados como provisórios.
- **Fase 2 — SSE notifica frontend:** o backend emite `zone.badges.updated` com badges provisórios e contexto de comparação (`based_on_zones`, `total_zones_expected`).
- **Fase 3 — frontend exibe badge provisório:** o card da zona exibe o badge imediatamente com label discreto `"baseado em X de Y zonas analisadas"`.
- **Fase 4 — recálculo final:** quando todas as zonas forem enriquecidas, o backend recalcula com a mediana definitiva e emite `zones.badges.finalized`. O frontend atualiza todos os badges com transição suave de 300ms e remove o label provisório.

```python
class ZoneBadgeRule:
    SAFETY: relative_threshold = -0.20  # 20% menos ocorrências que a mediana
    GREEN:  relative_threshold = +0.20  # 20% mais área verde que a mediana
    FLOOD:  relative_threshold = -0.20  # 20% menos área alagável que a mediana
    POIS:   relative_threshold = +0.30  # 30% mais POIs que a mediana

class ZoneBadgeValue(str, Enum):
    BEST    = "best"     # melhor entre as zonas comparadas
    ABOVE   = "above"    # acima da mediana pelo threshold
    NEUTRAL = "neutral"  # dentro da faixa da mediana
    BELOW   = "below"    # abaixo da mediana pelo threshold
```

**Payload SSE de badge provisório:**
```json
{
  "event": "zone.badges.updated",
  "zone_id": "uuid-zona-3",
  "badges": {
    "safety": { "value": "best",    "provisional": true },
    "green":  { "value": "above",   "provisional": true },
    "flood":  { "value": "neutral", "provisional": true },
    "pois":   { "value": "best",    "provisional": true }
  },
  "based_on_zones": 3,
  "total_zones_expected": 7
}
```

**Regra de estabilidade na transição provisório → final:**
Se o badge de uma zona piorar (ex: era `best`, vira `above`), a transição visual deve ser neutra — sem animação chamativa. Se melhorar, pode usar animação levemente positiva. O usuário não deve sentir que o sistema "tirou" algo dele.

**O que nunca fazer:**
Não recalcular badges somente ao final — elimina o feedback incremental. Não criar variável chamada `score`, `rank`, `index` ou `grade` que some critérios com pesos — mesmo que internamente. Não exibir badge definitivo antes da Fase 4 concluir.

### Mapa
- zonas com rótulo numérico diretamente no polígono;
- destaque persistente do ponto de transporte selecionado;
- rotas/linhas de transporte relevantes visíveis;
- POIs sob demanda.

### Regras visuais
- zona ativa com contorno mais forte;
- zonas secundárias atenuadas;
- label sempre legível;
- legenda só mostra camadas visíveis.

---

## Etapa 5 — Busca de imóveis dentro da zona

### Papel do campo de endereço

O campo de endereço da Etapa 5 é um **ponto de referência para a busca nas plataformas**, não um filtro geográfico posterior. As plataformas de scraping (QuintoAndar, Zap Imóveis, VivaReal) recebem endereço ou bairro como parâmetro de busca — é assim que suas APIs internas funcionam. A Etapa 5 existe para que o usuário escolha qual endereço ou bairro dentro da zona vai ser o parâmetro enviado ao scraper.

```
Etapa 5 — o usuário seleciona endereço ou bairro dentro da zona
  ↓
  esse valor vira o parâmetro "location" enviado aos scrapers
  ↓
  resultados retornam imóveis que as plataformas associam àquele endereço/bairro
  ↓
  Etapa 6 aplica filtro geoespacial adicional:
    ST_Within — remove falsos positivos de endereços ambíguos
    apenas imóveis cujas coordenadas estejam dentro do polígono da zona
```

O `search_location_normalized` entra na chave de cache junto com os demais parâmetros — normalizado para evitar duplicatas por variação de grafia.

### Painel
- combobox com autocomplete filtrado para dentro do polígono da zona ativa (`ST_Contains`);
- sugestões ordenadas por: bairros reconhecidos > logradouros > pontos de referência;
- o usuário pode digitar livremente ou selecionar da lista;
- botão "buscar imóveis" habilitado apenas após seleção;
- explicação discreta: "os imóveis serão buscados nesta área e filtrados para dentro da zona".

### Mapa
- endereço selecionado destacado com marcador distinto;
- centralização suave na área selecionada;
- polígono da zona permanece visível para contexto.

---

## Etapa 6 — Imóveis + dashboard da zona

### Painel ampliado
Na etapa de imóveis, o painel precisa crescer. Ele deixa de ser apenas controle e vira área de análise.

> **Diretriz importante:** como o produto não possui fórmula fechada e auditável para pontuações sintéticas, a documentação deve evitar termos como `score`, `nota` ou `índice composto` para avaliação de zonas ou imóveis. Sempre que possível, a interface deve mostrar indicadores objetivos e comparativos, como tempo de viagem, quantidade de POIs, área verde, incidência de alagamento, preço e recência dos dados.

### Organização recomendada
Duas abas fixas no topo do painel:

- `Imóveis`
- `Dashboard da zona`

### Aba Imóveis
Cards com:

- foto principal;
- preço;
- metragem;
- endereço resumido;
- plataforma;
- link externo;
- badge de duplicidade consolidada;
- botão “ver acessibilidade”.

### Filtros
- faixa de preço;
- faixa de metragem;
- tipo de uso: `residencial` ou `comercial`;
- plataforma (seleção múltipla dentro das plataformas permitidas pelo plano);
- ordenar por preço, tamanho, proximidade ao transporte e data/recência de coleta.

**Seleção de plataformas:** o usuário escolhe quais plataformas incluir na busca. Plataformas implementadas: QuintoAndar, Zap Imóveis e VivaReal. A disponibilidade no painel depende do plano:

- plano gratuito: QuintoAndar e Zap Imóveis selecionáveis; VivaReal aparece com lock e CTA de upgrade;
- plano Pro: todas as três disponíveis.

A restrição é computacional — três plataformas geram mais jobs de scraping, mais deduplicação e mais uso de cache — não uma limitação de implementação. Os três adapters estão disponíveis.

### Resultado parcial inteligente
A etapa de imóveis deve suportar **resultado preliminar com stale-while-revalidate**:

- se a zona já tiver cache válido para a mesma configuração, mostrar os imóveis imediatamente;
- se houver apenas interseção aproveitável com zona já cacheada, mostrar apenas os imóveis geometricamente contidos na zona-alvo;
- o usuário deve ver badge de `resultado preliminar` ou `resultado anterior` nos cards que vieram do cache;
- o scraping fresco continua em background sem bloquear mapa nem painel;
- novos imóveis entram com animação discreta;
- imóveis preliminares não confirmados na revalidação devem ser marcados como `não encontrado nesta busca`.

### Regra de qualidade do preliminar

Não exibir preliminar parcial quando a cobertura for enganosa. Os limiares mínimos obrigatórios são:

```python
class PreliminaryResultThresholds:
    # Cobertura mínima da zona-alvo pelo polígono de interseção
    MIN_GEOMETRIC_COVERAGE = 0.30  # 30% da área da zona deve estar coberta

    # Quantidade mínima de imóveis na interseção para valer exibir
    MIN_PROPERTIES_RENTAL  = 5    # aluguel: mercado mais denso, exige mais
    MIN_PROPERTIES_SALE    = 3    # compra: mercado menos denso, limiar menor

    # Idade máxima do cache para ser usado como preliminar
    MAX_CACHE_AGE_RENTAL   = 12   # horas
    MAX_CACHE_AGE_SALE     = 24   # horas
```

**Justificativa dos valores:**
- 30% de cobertura geométrica evita usar uma zona tangencialmente adjacente como se fosse a mesma área;
- 5 imóveis para aluguel porque abaixo disso a amostra não é representativa e pode induzir conclusão errada sobre disponibilidade;
- 3 imóveis para compra porque o mercado de compra tem naturalmente menos densidade de anúncios.

**Condições obrigatórias adicionais:**
- mesma configuração de busca: tipo de busca, modal, plataformas e `usage_type`;
- cache dentro do TTL por tipo de busca (ver `MAX_CACHE_AGE_*`).

**Contexto obrigatório no payload:**
O backend deve retornar `coverage_ratio` e `preliminary_count`. O frontend deve exibir discretamente: `"Mostrando 8 imóveis da área de sobreposição (47% da zona)"`. O usuário tem contexto suficiente para interpretar o resultado sem ser enganado.

### Aba Dashboard da zona
- preço médio atual;
- preço médio histórico;
- distribuição por faixa;
- segurança;
- área verde;
- área alagável;
- contagem de POIs;
- resumo do acesso ao transporte.

### No mapa
Ao abrir “ver acessibilidade” em um imóvel:

- destacar melhor rota a pé até cada categoria principal de POI;
- destacar melhor rota até o transporte;
- permitir alternância entre categorias sem recarregar tudo.

---

## 4.5 Estado do frontend

## Separar em três tipos

### A. Estado de UI
Exemplos:

- painel aberto/fechado;
- aba ativa;
- layer menu aberto;
- popups;
- item em hover.

### B. Estado de jornada
Exemplos:

- ponto principal;
- ponto de transporte escolhido;
- zona selecionada;
- imóvel selecionado;
- parâmetros da busca;
- etapas concluídas;
- etapas stale.

### C. Estado servidor
Exemplos:

- zonas;
- métricas;
- pontos elegíveis;
- imóveis;
- histórico de preço;
- progresso de jobs.

### Ferramentas
- **Zustand** para UI e jornada;
- **TanStack Query** para server state;
- **SSE bridge** para invalidar queries e atualizar progresso.

---

## 4.6 Estratégia para manter o mapa responsivo

## Regras técnicas

- evitar renderizar grandes GeoJSON em memória quando a camada for pesada;
- usar vector tiles/PMTiles para camadas de base pesada;
- usar GeoJSON apenas para seleção ativa e pequenos subconjuntos;
- carregar POIs por bounding box e categoria, não tudo ao mesmo tempo;
- manter overlays analíticos server-driven;
- não acoplar renderização do mapa ao render de toda a árvore React.

## Regras de implementação

- o mapa deve viver em componente próprio, com refs estáveis;
- mudanças no painel não devem recriar instância do mapa;
- efeitos de camada devem ser pontuais;
- dados de mapa devem ser atualizados por fontes independentes.

---

# 5. Estratégia de backend e processamento

## 5.1 Modelo de execução

A execução deve ser orientada por duas entidades:

### `journey`
Representa a jornada do usuário.

### `job`
Representa uma tarefa assíncrona associada a uma etapa dessa jornada.

---

## 5.2 Entidades mínimas

### `journeys`
- `id`
- `user_id` ou `anonymous_session_id`
- `state` — ver `JourneyState` abaixo
- `input_snapshot`
- `selected_transport_point_id`
- `selected_zone_id`
- `selected_property_id`
- `last_completed_step`
- `secondary_reference_point` (ponto geo + label — trabalho, escola, etc.)
- `created_at`
- `updated_at`

#### Estados válidos de `journeys`

```python
class JourneyState(str, Enum):
    DRAFT      = "draft"       # criada, ainda sem ponto de transporte selecionado
    ACTIVE     = "active"      # pelo menos um job concluído; navegação livre entre etapas
    PROCESSING = "processing"  # pelo menos um job em execução no momento
    CANCELLED  = "cancelled"   # usuário cancelou a etapa em curso
    COMPLETED  = "completed"   # relatório gerado e disponível para download
    EXPIRED    = "expired"     # sessão anônima expirada por TTL sem migração
```

Transições válidas:
```
DRAFT → ACTIVE (primeiro job concluído)
ACTIVE ↔ PROCESSING (job iniciado / concluído)
ACTIVE | PROCESSING → CANCELLED (cancelamento cooperativo)
CANCELLED → ACTIVE (retomada após cancelamento)
ACTIVE → COMPLETED (relatório gerado)
DRAFT | ACTIVE → EXPIRED (TTL de sessão anônima)
```

### `jobs`
- `id`
- `journey_id`
- `job_type` — ver `JobType` abaixo
- `state` — ver `JobState` abaixo
- `progress_percent`
- `current_stage`
- `cancel_requested_at`
- `started_at`
- `finished_at`
- `worker_id`
- `result_ref`
- `error_code`
- `error_message`

#### Tipos válidos de `jobs`

```python
class JobType(str, Enum):
    TRANSPORT_SEARCH   = "transport_search"
    ZONE_GENERATION    = "zone_generation"
    ZONE_ENRICHMENT    = "zone_enrichment"   # subjob por critério
    LISTINGS_SCRAPE    = "listings_scrape"   # subjob por plataforma
    LISTINGS_DEDUP     = "listings_dedup"
    LISTINGS_PREWARM   = "listings_prewarm"  # scheduler noturno
    REPORT_GENERATE    = "report_generate"
```

#### Estados válidos de `jobs`

```python
class JobState(str, Enum):
    PENDING    = "pending"    # enfileirado, aguardando worker
    RUNNING    = "running"    # worker iniciou execução
    COMPLETED  = "completed"  # concluído com sucesso
    FAILED     = "failed"     # erro não recuperável após retries
    CANCELLED  = "cancelled"  # cancelamento cooperativo confirmado
    RETRYING   = "retrying"   # aguardando próxima tentativa (backoff)
```

Transições válidas:
```
PENDING → RUNNING → COMPLETED
PENDING → RUNNING → FAILED
PENDING → RUNNING → RETRYING → PENDING (até max_retries)
PENDING | RUNNING → CANCELLED (por cancel_requested_at na journey)
```

### `job_events`
- `id`
- `job_id`
- `event_type` — corresponde aos tipos de evento SSE (seção 5.4)
- `stage`
- `message`
- `payload_json`
- `created_at`

Isso substitui `status.json` e `events.jsonl` como fonte de verdade de produto, embora artefatos em arquivo possam continuar existindo como cache/export secundário.

---

## 5.3 Pipeline recomendado por etapa

## A. Descoberta de pontos de transporte

Entrada:

- ponto principal;
- modal;
- distância máxima de seed.

Saída:

- lista de pontos elegíveis;
- rotas a pé até cada ponto;
- ranking local.

## B. Geração de zonas

Entrada:

- ponto de transporte selecionado;
- modal;
- tempo máximo;
- raio da zona.

Saída:

- zonas;
- métricas iniciais;
- ordem por tempo de viagem.

## C. Enriquecimento analítico

Subjobs por critério:

- verde;
- alagamento;
- segurança pública;
- POIs.

Esses subjobs devem rodar independentemente e alimentar a mesma zona progressivamente.

## D. Busca de imóveis

### Verificação de plano antes do enfileiramento

A lógica de scraping é diferente por plano e aplicada **antes** de qualquer job ser enfileirado:

```python
async def request_listings(
    journey_id: UUID,
    zone_id: UUID,
    user: User | None,
    session_id: str | None,
    config: ListingsConfig,
) -> ListingsRequestResult:

    plan  = await plans.get_effective_plan(user=user, session_id=session_id)
    cache = await zone_listing_caches.get(zone_id, config)

    await listing_search_requests.record(
        journey_id=journey_id,
        user_id=user.id if user else None,
        session_id=session_id,
        zone_fingerprint=config.zone_fingerprint,
        search_location_normalized=config.search_location_normalized,
        search_location_label=config.search_location_label,
        search_location_type=config.search_location_type,
        search_type=config.search_type,
        usage_type=config.usage_type,
        platforms_hash=config.platforms_hash,
        result_source=(
            "cache_hit" if cache and cache.is_usable() else "cache_miss"
        ),
    )

    # Plano gratuito — apenas cache, nunca dispara Playwright
    if plan.slug == PlanSlug.FREE:
        if cache and cache.is_usable():
            return ListingsRequestResult(
                source="cache",
                listings=cache.listings,
                cache_age_hours=cache.age_hours,
                freshness_status="stale_but_usable",
            )
        return ListingsRequestResult(
            source="none",
            listings=[],
            freshness_status="queued_for_next_prewarm",
            upgrade_reason="fresh_listings",
            next_refresh_window="03:00–05:30",
        )

    # Plano Pro — dispara Playwright independente do cache
    job = await jobs.enqueue_scraping(
        zone_id=zone_id,
        config=config,
        priority=Priority.USER_REQUEST,   # alta prioridade sobre prewarm
    )
    return ListingsRequestResult(
        source="scraping",
        job_id=job.id,
        freshness_status="scraping_in_progress",
    )
```

**Regra de plataforma:** a restrição de plataforma (QuintoAndar + Zap para gratuito; + VivaReal para Pro) é aplicada dentro da mesma verificação — o worker nunca recebe job de plataforma fora do plano do usuário.

Subjobs por:

- zona;
- endereço/rua selecionada (parâmetro de busca nas plataformas — ver Etapa 5);
- plataforma (um subjob por plataforma permitida pelo plano);
- consolidação/deduplicação;
- revalidação de cache (somente plano Pro).

Os três adapters (QuintoAndar, Zap Imóveis, VivaReal) estão implementados via Playwright.

### Estratégia obrigatória para imóveis
A busca de imóveis deve adotar **cache geoespacial stale-while-revalidate** como comportamento padrão de produto, não como otimização opcional.

#### Caso 1 — hit total
Quando a mesma zona já tiver sido processada com a mesma configuração de busca, o backend retorna imediatamente os imóveis cacheados e agenda revalidação silenciosa em background.

#### Caso 2 — hit parcial por interseção
Quando a zona-alvo ainda não tiver cache próprio, mas houver interseção com zona previamente cacheada, o backend pode devolver um resultado preliminar apenas com os imóveis contidos na interseção geométrica válida da zona-alvo. O restante continua sendo raspado em background.

#### Regra de qualidade
O backend só deve exibir preliminar parcial quando a interseção for útil de verdade. Ver limiares concretos em `PreliminaryResultThresholds` (seção 6.4). Antes de iniciar qualquer scraping, o worker deve tentar adquirir o lock `scraping_lock:{zone_fingerprint}:{config_hash}` no Redis — se outro worker já tiver o lock, aguarda e consulta o cache resultante sem duplicar a operação.

#### Diff de revalidação
Quando o scraping novo terminar:

- remove badge de preliminar dos imóveis confirmados;
- insere imóveis novos com destaque de entrada;
- atualiza preço quando houver mudança;
- marca como indisponível ou não reencontrado aquilo que sumiu da nova coleta.

#### Cancelamento
Se o usuário cancelar a etapa, o sistema preserva o resultado preliminar já exibido e interrompe apenas a revalidação/scraping pendente.

## E. Consolidação

- deduplicação;
- indicadores comparativos explicáveis por critério;
- clusterização de anúncios equivalentes;
- geração das séries históricas.

## F. Relatório

**Gerador de PDF: WeasyPrint** + Jinja2. Escolhido sobre ReportLab (API imperativa) e Puppeteer (dependência Node no worker Python). WeasyPrint renderiza HTML/CSS, suporta SVG para gráficos e `@page` CSS para paginação.

### Fluxo completo de geração do relatório

```
Frontend                     API                          Worker (fila reports)
───────                      ───                          ─────────────────────
1. Usuário clica "Gerar"
2. Captura canvas MapLibre
   map.getCanvas()
   .toDataURL('image/png')
3. POST /reports
   {journey_id,
    zone_id,
    map_image_base64}        4. Valida quota (plano)
                             5. Persiste map_image em R2
                             6. Cria job REPORT_GENERATE
                             7. Retorna {job_id}
8. Abre SSE
   /jobs/{job_id}/events                                  9. Pega job da fila
                                                          10. Busca dados da zona,
                                                              imóveis, histórico
                                                          11. Renderiza template
                                                              Jinja2 → HTML
                                                          12. WeasyPrint HTML→PDF
                                                          13. Upload PDF para R2
                                                          14. Gera signed URL
                                                              (expira em 7 dias)
                                                          15. Publica evento Redis
                                                              report.ready{url}
                             ← SSE: report.ready{url}
16. Exibe botão "Download"
    com a signed URL
```

**Duração esperada:** 5–20s (WeasyPrint ~3–10s + upload ~1–2s).

**Signed URL:** 7 dias de validade. `GET /reports/{report_id}/url` regenera para relatórios do próprio usuário após expiração.

**`preserveDrawingBuffer: true`** na inicialização do MapShell — obrigatório para `getCanvas()` não retornar canvas em branco. Uma captura por relatório, PDF salvo em R2.

**Conteúdo do template:** estrutura definida na seção 12 deste documento.

---

## 5.4 Progresso em tempo real

## Fluxo recomendado

1. usuário aciona uma etapa;
2. API cria job e persiste; retorna `job_id` ao cliente;
3. cliente abre conexão SSE em `GET /jobs/{job_id}/events`;
4. worker processa e publica evento em Redis pub/sub no canal `job:{job_id}`;
5. **todas** as instâncias da API assinam o canal `job:{job_id}` — apenas a instância com a conexão SSE aberta repassa ao cliente;
6. frontend atualiza painel e invalida queries TanStack afetadas.

### Mecanismo de fan-out SSE com múltiplos processos na Hostinger

A topologia inicial usa um único processo público de API, mas manter o pub/sub por `job_id` já prepara o sistema para múltiplos processos sob o mesmo reverse proxy na Hostinger. O worker não precisa saber qual processo está atendendo a conexão SSE — o pub/sub continua broadcast para todos:

```python
# Worker (em qualquer processo Hostinger)
async def publish_event(job_id: UUID, event: JobEvent):
    await redis.publish(f"job:{job_id}", event.model_dump_json())
    await db.insert_job_event(event)   # persiste para reconexão/histórico

# API — endpoint SSE (em qualquer processo da API)
async def job_events_stream(job_id: UUID, request: Request):
    async with redis.subscribe(f"job:{job_id}") as channel:
        async for message in channel:
            if await request.is_disconnected():
                break
            yield f"data: {message}\n\n"
```

**Reconexão:** cliente SSE envia `Last-Event-ID`. A API consulta `job_events` no banco e reenvia eventos perdidos antes de se inscrever no canal Redis — garante zero perda de eventos em desconexões momentâneas.

**Sticky sessions:** não necessárias com esse modelo. Qualquer instância serve qualquer cliente.

**Canal por `job_id`**, não por `user_id` — mais granular, evita vazar eventos de uma jornada para outra e simplifica o cleanup: o canal some quando todos os assinantes desconectam.

## Tipos de evento sugeridos

- `job.started`
- `job.stage.started`
- `job.stage.progress`
- `job.partial_result.ready`
- `zone.badges.updated` — badge provisório após enriquecimento individual de zona
- `zones.badges.finalized` — recálculo final com mediana real de todas as zonas
- `listings.preliminary.ready`
- `listings.diff.applied`
- `job.stage.completed`
- `job.cancelled`
- `job.failed`
- `job.completed`

## Exemplo de mensagens

- `analisando área verde da zona 4`
- `consultando ocorrências de segurança pública`
- `carregando linhas de ônibus do ponto selecionado`
- `coletando anúncios no QuintoAndar`
- `exibindo resultado preliminar da área de sobreposição`
- `deduplicando anúncios equivalentes`
- `aplicando diferenças da revalidação da zona`

---

## 5.5 Cancelamento

Cancelamento precisa ser cooperativo. A seção define o protocolo completo com timing, timeout e watchdog.

### Protocolo de cancelamento cooperativo

```
t=0      Usuário pressiona cancelar
t=0      API: grava cancel_requested_at, responde 202 Accepted imediatamente
t=0–2s   Worker: verifica flag no início de cada subetapa
t=2s     Worker: ao detectar flag, encerra subetapa atual de forma limpa
t=2–5s   Worker: persiste resultado parcial, atualiza status para cancelled_partial
t=5s     Worker: libera lock de scraping se mantiver
t=30s    Timeout: se worker não confirmar cancelamento em 30s,
         API força status para cancelled_partial e libera o lock
```

### O que o worker faz ao detectar o flag

```python
async def check_cancellation(job_id: UUID) -> None:
    job = await db.get_job(job_id)
    if job.cancel_requested_at is not None:
        raise JobCancelledException(
            job_id=job_id,
            partial_result_ref=job.result_ref  # preserva o que foi feito
        )
```

`JobCancelledException` é capturado no orquestrador do job, que persiste o estado parcial e encerra de forma limpa — nunca deixa o job em estado `running` indefinidamente.

### Watchdog

Um job scheduler periódico (a cada 60s) deve detectar jobs com `status = running` sem heartbeat recente (> 2 minutos) e forçá-los para `cancelled_partial`. O worker deve publicar heartbeat a cada 30s enquanto estiver rodando:

```python
async def worker_heartbeat(job_id: UUID) -> None:
    await redis.set(f"job_heartbeat:{job_id}", "alive", ex=120)
```

### Estado da jornada após cancelamento

A jornada não regride de etapa. Ela fica com a última etapa marcada como `cancelled_partial`. O painel deve mostrar o que foi gerado até então com opção explícita de:
- retomar o processamento (dispara novo job a partir do ponto interrompido);
- voltar à etapa anterior e alterar parâmetros.

### Regras adicionais

- subprocessos longos devem ter PID rastreado;
- ao cancelar, o worker encerra subprocesso quando seguro — nunca `SIGKILL` sem antes persistir o estado;
- resultados já produzidos permanecem acessíveis;
- lock de scraping deve ser liberado explicitamente no cancelamento.

---

## 5.6 Scheduler de prewarm noturno

O scheduler noturno é a **única fonte de atualização de imóveis para usuários gratuitos**. Sua falha é um incidente crítico de produto — não silencioso.

### Estratégia única de prewarm

```python
class PrewarmStrategy(str, Enum):
    REQUESTED_SEARCH_LOCATIONS_24H = "requested_search_locations_24h"
```

### Jobs do scheduler

```python
@dramatiq.actor(queue_name="prewarm")  # fila separada, prioridade LOW
async def prewarm_requested_search_locations_24h(lookback_hours: int, limit: int):
    search_keys = await db.get_requested_search_locations_24h(
        lookback_hours=lookback_hours,
        limit=limit,
    )
    for key in search_keys:
        scrape_zone_listings.send_with_options(
            args=[key.zone_fingerprint, key.config],
            priority=Priority.PREWARM,
        )

# Agendamento (APScheduler)
scheduler.add_job(
    prewarm_requested_search_locations_24h,
    trigger="cron",
    hour=3,
    kwargs={"lookback_hours": 24, "limit": 100},
)
```

### Regra fechada de seleção

O prewarm agrega apenas as buscas de imóveis feitas na **Etapa 5** nas últimas 24 horas. Caches sem demanda recente simplesmente expiram e não são revalidados. A ordenação é:

1. maior `COUNT(*)` no período;
2. maior `MAX(requested_at)`;
3. cache mais antigo primeiro.

**Não existe fallback** por:
- zona popular;
- geohash/região;
- cache prestes a vencer sem demanda recente;
- cold start artificial.

Se nenhum endereço/search location foi pesquisado nas últimas 24 horas, o prewarm roda vazio e finaliza como `success_empty`.

### Prioridade e preempção

Jobs de prewarm têm `Priority.PREWARM = 5` (menor prioridade). Jobs disparados por usuário Pro têm `Priority.USER_REQUEST = 0` (maior prioridade). O `worker-scrape-browser` sempre serve um usuário Pro que chegue antes de continuar o prewarm — sem configuração adicional, só pela ordem da fila Redis.

### Capacidade inicial e janela noturna

A capacidade inicial é limitada a **100 endereços/search locations distintas por run**. Esse limite é proposital: ele impede que o prewarm consuma toda a madrugada com scraping de baixa demanda e mantém o comportamento previsível em VPS único.

### Alerta obrigatório de falha

Falha silenciosa do scheduler significa que usuários gratuitos acordam sem dados para os endereços realmente pesquisados. O sistema deve emitir alerta crítico quando:

- o job de prewarm não iniciar dentro de 30 min do horário programado;
- menos de 60% dos endereços-alvo foram processados com sucesso;
- `prewarm_last_run_status = failed` ao final da execução.

### Comportamento para endereço sem cache (usuário gratuito)

Quando o usuário gratuito pesquisa um endereço ainda sem cache, o sistema **registra a demanda** e responde com contexto explícito:

```
┌─────────────────────────────────────────────────┐
│  Este endereço entrou na fila de atualização    │
│  noturna.                                       │
│                                                 │
│  Se houver anúncios disponíveis, eles aparecerão│
│  após a próxima atualização.                    │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │  Ver imóveis agora com o plano Pro      │    │
│  │  R$ 29/mês  →                           │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

O CTA surge no momento de maior frustração — exatamente o momento de maior conversão.

---

## 5.7 Reprocessamento e reaproveitamento

Reprocessamento não deve significar “refazer tudo”.

### Estratégia

Cada etapa gera um **fingerprint de entrada**. Exemplo:

- ponto principal normalizado;
- ponto de transporte selecionado;
- modal;
- tempo máximo;
- raio da zona;
- datasets versionados;
- filtros de análise.

Se o fingerprint já existir e o dataset version continuar válido, a etapa pode ser reaproveitada.

### Benefício

- menos custo;
- menos latência;
- melhor UX;
- mais previsibilidade.

---

## 5.8 Observabilidade

## O mínimo aceitável

- logs estruturados JSON;
- request id;
- correlation id journey/job;
- métricas por etapa;
- tracing entre API, worker e chamadas externas;
- dashboard operacional.

## Métricas de produto essenciais

- tempo para listar pontos de transporte;
- tempo para primeira zona aparecer;
- tempo total por job;
- taxa de cancelamento por etapa;
- cache hit por provedor;
- custo externo por jornada;
- quantidade média de anúncios por zona;
- taxa de duplicidade de imóveis;
- taxa de falha por plataforma de scraping;
- `prewarm_coverage_rate` — % dos endereços demandados nas últimas 24h processados com sucesso no run;
- `prewarm_last_run_status` — sucesso/falha da última execução noturna (alerta crítico se falhar).

---

# 6. Estratégia de dados

## 6.1 Banco principal

## **PostgreSQL + PostGIS**

É o banco correto para este produto.

### O que vai nele

- usuários/sessões;
- jornadas;
- jobs e eventos;
- zonas geradas;
- métricas de zonas;
- caches e resultados derivados de POIs por zona/jornada (não base canônica);
- tabelas de transporte;
- imóveis e histórico;
- uso de APIs;
- datasets versionados.

---

## 6.2 Armazenamento geoespacial

## O que deve ser local e persistido

- estações/paradas/linhas importadas de GTFS;
- vias/endereços relevantes da base local; POIs vindos da Mapbox Search Box API;
- áreas verdes, após ingestão versionada em PostGIS;
- áreas alagáveis;
- grades/índices espaciais;
- geometrias de zonas geradas;
- tiles analíticos ou PMTiles exportados.

## O que não deve ser o coração do produto

- depender de chamadas frias a APIs de busca externas como fonte principal da análise urbana e da navegação do usuário;
- tratar dado autoritativo externo como se precisasse ser sempre consultado em tempo real, sem cache, sem versionamento e sem revalidação controlada.

Para este projeto específico, o repositório já prova outra coisa: **POIs vêm da Mapbox Search Box API**. Então a arquitetura correta não é migrar POIs para OSM/PostGIS como fonte primária, e sim tratar a Mapbox como origem operacional dos POIs, com backend-only, cache efêmero, TTL curto e agregação derivada por zona/jornada. Ruas, grafos e demais estruturas locais continuam em infraestrutura própria.

---

## 6.3 Histórico de preços dos imóveis

Como as plataformas não entregam histórico consolidado, o sistema precisa criá-lo.

## Modelo recomendado

### Tipo de uso — enum formal

Antes do modelo, definir o enum que será usado em todas as tabelas, DTOs e filtros de frontend. Evita nomenclaturas divergentes entre partes do sistema:

```python
class PropertyUsageType(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL  = "commercial"
    MIXED       = "mixed"    # imóvel explicitamente misto (loja + apt)
    UNKNOWN     = "unknown"  # não foi possível determinar
```

**Regra de resolução de conflito:**
Quando `properties.usage_type = unknown` e `listing_ads.advertised_usage_type = residential`, o sistema deve usar o tipo do anúncio como inferência, mas marcar `usage_type_inferred = true` na tabela `properties` para auditoria. Não deve inferir silenciosamente sem registro.

**Regra de filtro no frontend:**
O filtro deve ter três opções: `Residencial`, `Comercial` e `Todos`. O valor `unknown` nunca aparece como opção — imóveis `unknown` entram em `Todos` mas não em nenhum filtro específico.

### `properties`
Representa a identidade deduplicada do imóvel.

Campos típicos:

- id;
- address_normalized;
- lat/lon;
- area_m2;
- bedrooms;
- bathrooms;
- parking;
- usage_type (`PropertyUsageType`);
- usage_type_inferred (bool — verdadeiro quando inferido do anúncio);
- geo_hash;
- fingerprint.

### `listing_ads`
Representa cada anúncio por plataforma.

- id;
- property_id;
- platform;
- platform_listing_id;
- url;
- advertised_usage_type (`PropertyUsageType`) — tipo declarado pela plataforma;
- first_seen_at;
- last_seen_at;
- is_active.

### `listing_snapshots`
Representa cada observação temporal.

- id;
- listing_ad_id;
- observed_at;
- price;
- condo_fee;
- iptu;
- raw_payload;
- availability_state.

### `property_price_rollups`
Agregados calculados periodicamente.

- current_best_price;
- second_best_price;
- price_mean_30d;
- price_mean_90d;
- unavailable_count;
- avg_unavailable_days.

## Regra de consolidação pedida por você

Quando o mesmo imóvel aparecer em mais de um anúncio:

- clusterizar anúncios equivalentes em `property_id`;
- exibir primeiro o menor preço atual (`current_best_price`);
- armazenar também o segundo menor preço para comparação — exibido como referência, nunca como critério de ordenação;
- manter os anúncios originais para auditoria.

**Ordenação padrão de imóveis:** `current_best_price` ascendente. Outros critérios (tamanho, proximidade ao transporte, recência) disponíveis como ordenação secundária escolhida pelo usuário.

---

## 6.3.5 Schema de `zones` e composição do `zone_fingerprint`

A entidade `zones` é o centro do produto — toda isócrona, todo enriquecimento e todo scraping de imóveis é indexado por ela. Schema mínimo:

```sql
zones (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journey_id            UUID REFERENCES journeys(id),
  transport_point_id    UUID REFERENCES transport_points(id),
  modal                 TEXT NOT NULL,        -- 'walking' | 'transit' | 'car'
  max_time_minutes      INT NOT NULL,
  radius_meters         INT NOT NULL,
  fingerprint           TEXT NOT NULL UNIQUE, -- hash SHA-256 dos campos abaixo
  isochrone_geom        GEOMETRY(POLYGON, 4326),
  dataset_version_id    UUID REFERENCES dataset_versions(id),
  state                 TEXT NOT NULL DEFAULT 'pending',
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
)
```

#### Composição do `zone_fingerprint`

O fingerprint é o SHA-256 do JSON canônico (chaves ordenadas, sem espaços) dos seguintes campos:

```python
def compute_zone_fingerprint(
    transport_point_lat: float,   # arredondado para 5 decimais (~1m precisão)
    transport_point_lon: float,
    modal: str,
    max_time_minutes: int,
    radius_meters: int,
    dataset_version_id: str,      # versão da malha OSM/GTFS em uso
) -> str:
    payload = {
        "lat": round(transport_point_lat, 5),
        "lon": round(transport_point_lon, 5),
        "modal": modal,
        "max_time": max_time_minutes,
        "radius": radius_meters,
        "dataset_v": dataset_version_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
```

**Regra de reaproveitamento:** se uma zona com o mesmo fingerprint já existe no banco com `state = complete`, a nova jornada reutiliza a zona existente — nenhum novo cálculo de isócrona é feito. A zona é compartilhada entre jornadas de usuários diferentes.

**O que não entra no fingerprint:** filtros de análise, plataformas de scraping, tipo de imóvel — esses variam por jornada mas não alteram a geometria da zona.

---

## 6.4 Cache, atualização e frescor

## 6.4.1 Princípio geral

A regra correta para o produto não é “evitar API externa a qualquer custo”. A regra correta é:

- usar APIs externas quando elas forem a fonte autoritativa, licenciada ou operacional do dado geoespacial;
- persistir localmente tudo que for estrutural, recorrente ou analítico;
- tratar dado derivado como resultado versionado, nunca como verdade primária;
- responder primeiro com o melhor resultado já disponível;
- revalidar em background sempre que o dado puder envelhecer.

Cada informação do sistema deve cair em um destes grupos:

### A. Dado autoritativo externo consultável

Exemplos:

- geocoding;
- autocomplete;
- rotas a pé;
- isócronas;
- detalhes operacionais de determinados lugares quando a fonte relevante é externa.

### B. Dado persistido e versionado internamente

Exemplos:

- GTFS importado;
- vias/apoio geoespacial locais;
- caches e agregações derivadas de POIs vindos da Mapbox;
- áreas verdes, após ingestão versionada em PostGIS;
- alagamento;
- segurança pública;
- zonas geradas;
- snapshots de imóveis;
- resultados consolidados da jornada.

### C. Dado derivado

Exemplos:

- ranking de zonas;
- badges;
- score de aderência;
- resumo da zona;
- comparação entre alternativas;
- recomendações do chat com base em evidências.

## 6.4.2 Fluxo melhorado seguindo a lógica dos imóveis

O padrão de experiência que já faz sentido para imóveis deve virar regra para o restante da jornada: **mostrar o melhor resultado existente imediatamente, marcar o frescor e revalidar sem bloquear a navegação**.

### Origem e geocodificação

- procurar primeiro no cache por string normalizada ou coordenada aproximada;
- se houver resultado válido, responder imediatamente;
- se não houver, consultar a API externa e persistir o retorno normalizado;
- se o cache estiver vencendo, responder com o resultado recente e revalidar em background.

### Pontos de transporte

- consultar primeiro a visão materializada ou cacheada da área;
- retornar os pontos elegíveis imediatamente quando houver dado utilizável;
- revalidar em background conectividade, linhas e disponibilidade;
- só bloquear o fluxo quando não houver nenhum resultado aproveitável.

### Zonas e isócronas

- reaproveitar geometrias por fingerprint de entrada;
- quando a combinação já existir, devolver de imediato a geometria persistida;
- recalcular apenas se a entrada ou a versão da malha/provedor tiver mudado;
- manter a versão anterior como “última conhecida” até a nova terminar.

### Enriquecimento analítico da zona

- cada enriquecimento vira subresultado independente;
- o frontend não espera tudo para liberar a navegação;
- SSE entrega progresso e payload parcial por domínio analítico;
- badges e comparações são recalculados à medida que os subresultados chegam.

### Imóveis

- manter a lógica já definida de hit total, hit parcial por interseção e miss total;
- preservar resultados parciais em cancelamento;
- aplicar diff incremental quando a revalidação terminar.

## 6.4.3 Política de atualização por tipo de informação

A atualização deve ser diferente conforme a natureza do dado.

### Geocoding e autocomplete

**Natureza:** autoritativo externo e transitório.

**Como atualizar:**

- atualização on demand quando o usuário busca;
- cache curto por string normalizada;
- revalidação silenciosa quando o TTL estiver próximo do vencimento;
- invalidação quando houver mudança do provedor, precisão ou normalização.

### Rotas a pé

**Natureza:** autoritativo externo e operacional.

**Como atualizar:**

- cache por par origem-destino-modo;
- retorno imediato do resultado recente, quando existir;
- recálculo em background se o TTL estiver vencido;
- invalidação quando houver mudança relevante de malha, provedor ou parâmetro da rota.

### Pontos de transporte e linhas

**Natureza:** semi-estrutural, mas com dinâmica operacional.

**Como atualizar:**

- atualização programada por área ou rede, não só por clique do usuário;
- refresh recorrente para regiões ativas;
- revalidação on demand quando a jornada exigir maior precisão;
- fallback para último resultado utilizável com badge de atualização em andamento.

### Isócronas e zonas derivadas

**Natureza:** dado derivado caro de gerar.

**Como atualizar:**

- recalcular apenas quando mudar origem, ponto de transporte, modal, tempo, raio ou versão da malha;
- reaproveitar por fingerprint sempre que a entrada for equivalente;
- manter a geometria anterior enquanto a nova é gerada;
- registrar a versão do dataset/provedor usada em cada zona.

### POIs e detalhes de estabelecimentos

**Natureza:** híbrida. Parte estrutural e parte dinâmica.

**Como atualizar:**

- persistir localmente nome canônico, categoria principal, coordenada e identificador externo;
- revalidar em background campos dinâmicos, como horário, telefone, status operacional e atributos sujeitos a mudança;
- atualizar a ficha do local sem destruir a navegação já aberta;
- preferir atualização sob demanda quando o usuário abre o card detalhado do estabelecimento.

### Camadas analíticas públicas

**Natureza:** estrutural e versionável.

**Como atualizar:**

- ingestão programada por pipeline, nunca por clique do usuário;
- versionamento obrigatório por dataset;
- novas consultas usam a versão mais recente validada;
- análises passadas permanecem auditáveis com a versão antiga registrada.

### Imóveis

**Natureza:** altamente dinâmica e custosa.

**Como atualizar:**

- stale-while-revalidate por zona e configuração;
- hit total, hit parcial por interseção ou miss total;
- preservação de parcial em cancelamento;
- diffs incrementais quando a revalidação terminar;
- TTL distinto para aluguel e compra.

### Resumos, badges e indicadores

**Natureza:** derivada.

**Como atualizar:**

- recalcular sempre que mudar o dado-base;
- exibir estado provisório enquanto nem todos os subresultados chegaram;
- finalizar apenas quando a combinação mínima de evidências estiver completa;
- nunca armazenar sem referência explícita à versão da base e ao momento do cálculo.

## 6.4.4 Metadados mínimos de frescor

Toda resposta relevante do backend deve trazer, além do conteúdo:

- `source_provider`;
- `source_type`;
- `last_updated_at`;
- `freshness_status`;
- `ttl_expires_at`;
- `dataset_version` ou `provider_version`;
- `is_preliminary`;
- `revalidation_in_progress`.

Estados padronizados de frescor:

- `fresh`;
- `stale_but_usable`;
- `revalidating`;
- `expired_unusable`.

## Redis cache curto

Para:

- autocomplete/geocode;
- pontos de transporte elegíveis;
- consulta de POIs por bbox/categoria;
- consultas de rotas;
- resultados transitórios de scraping;
- locks e controle de revalidação concorrente.

## Cache persistido em banco

Para:

- resultados reaproveitáveis de jornadas;
- fingerprints de etapas;
- agregados por zona;
- snapshots de imóveis;
- resultados preliminares e revalidados de zonas imobiliárias;
- geometrias derivadas reaproveitáveis;
- fichas persistidas de lugares com campos dinâmicos revalidáveis.

## Cache geoespacial de imóveis por zona

Aqui entra uma decisão importante: a etapa de imóveis deve ser modelada com **stale-while-revalidate**.

### Chave de cache
A chave precisa considerar, no mínimo:

- fingerprint da zona;
- tipo de busca (`aluguel` ou `compra`);
- modal de isócrona (`walking`, `transit`, `car`);
- plataformas consultadas (lista ordenada para hash determinístico);
- tipo de uso (`residencial` ou `comercial`);
- versão do normalizador/deduplicador.

### Comportamentos suportados
- **hit total**: zona já cacheada para a mesma configuração; retorna imediatamente e revalida em background;
- **hit parcial por interseção**: zona ainda não cacheada, mas com sobreposição suficiente com zona cacheada; retorna apenas imóveis dentro da interseção válida;
- **miss total**: sem preliminar; mostra só progresso rico até a primeira leva real.

### Máquina de estados do cache de zona

O registro `zone_listing_caches` deve seguir uma máquina de estados explícita. Sem isso, race conditions entre workers e cancelamentos deixam o cache em estado indefinido:

```
pending → scraping → partial → complete
                  ↘           ↗
                   failed
                  ↘
                   cancelled_partial  (preserva o que foi coletado)
```

```python
class ZoneCacheStatus(str, Enum):
    PENDING           = "pending"           # aguardando scraping
    SCRAPING          = "scraping"          # scraping em andamento
    PARTIAL           = "partial"           # algumas plataformas responderam
    COMPLETE          = "complete"          # todas as plataformas responderam
    FAILED            = "failed"            # nenhuma plataforma respondeu
    CANCELLED_PARTIAL = "cancelled_partial" # cancelado, preserva parcial
```

### Regra de validade por status

| Status | Pode ser usado como preliminar? | Aciona novo scraping? |
|---|---|---|
| `complete` dentro do TTL | Sim | Não (revalida silenciosamente) |
| `partial` dentro do TTL | Sim, com badge de plataformas ausentes | Sim, para plataformas faltantes |
| `cancelled_partial` | Sim, com badge explícito | Sim, scraping completo |
| `failed` | Não | Sim, scraping completo |
| Qualquer status fora do TTL | Não | Sim, scraping completo |

### Lock de scraping por zona

Sem lock, dois usuários podem disparar scraping idêntico simultaneamente, dobrando o consumo de quota e gerando snapshots inconsistentes:

```python
SCRAPING_LOCK_KEY = "scraping_lock:{zone_fingerprint}:{config_hash}"
LOCK_TTL_SECONDS  = 300  # 5 minutos — tempo máximo esperado de scraping

async def acquire_scraping_lock(zone_fingerprint: str, config_hash: str) -> bool:
    key      = SCRAPING_LOCK_KEY.format(zone_fingerprint=zone_fingerprint,
                                         config_hash=config_hash)
    acquired = await redis.set(key, worker_id, nx=True, ex=LOCK_TTL_SECONDS)
    return acquired is not None
```

Se o lock não for adquirido, o worker aguarda até ele expirar ou ser liberado, e então consulta o cache atualizado — sem duplicar o scraping.

### Regra de falha parcial

Quando o scraping de uma plataforma falha e outras respondem, o cache é salvo como `partial` — nunca descartado. O diff ao final deve indicar por plataforma qual respondeu. O card do imóvel deve exibir `"resultado de 2 de 3 plataformas"` quando aplicável.

### Regras de validade (TTL)

- aluguel: 12 horas;
- compra: 24 horas;
- geometrias derivadas de zona/isócrona: 7 dias;
- rotas a pé auxiliares: 7 dias.

### Modelo recomendado
Persistir pelo menos:

- `zone_listing_caches` (com campo `status: ZoneCacheStatus`)
- `cached_properties`
- `listing_cache_events`

Com índice espacial `GIST` nos pontos de imóvel para consultas `ST_Within` e `ST_Intersects`.

## Cache de tiles e assets

- CDN/object storage para tiles estáticos e relatórios.

---

## 6.5 Versionamento de dados processados

Você precisa versionar datasets, senão não saberá por que um resultado mudou.

### Tabelas recomendadas

- `dataset_versions`
- `dataset_import_runs`
- `zone_analysis_versions`

### Exemplo

Uma zona calculada com:

- GTFS versão X,
- alagamento versão Y,
- segurança pública versão Z,
- OSM snapshot W,

precisa registrar isso.

---

## 6.6 Registro de demanda real para o prewarm

O scheduler noturno não deve selecionar zonas populares nem aplicar fallback de cold start. A única fonte de verdade para prewarm é a demanda observada na Etapa 5.

```sql
listing_search_requests (
  id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  journey_id                 UUID,
  user_id                    UUID,
  session_id                 TEXT,
  zone_fingerprint           TEXT NOT NULL,
  search_location_normalized TEXT NOT NULL,
  search_location_label      TEXT NOT NULL,
  search_location_type       TEXT NOT NULL,   -- 'street' | 'neighborhood' | 'address' | 'landmark'
  search_type                TEXT NOT NULL,
  usage_type                 TEXT NOT NULL,
  platforms_hash             TEXT NOT NULL,
  result_source              TEXT NOT NULL,   -- 'cache_hit' | 'cache_partial' | 'cache_miss' | 'fresh_scrape'
  requested_at               TIMESTAMPTZ DEFAULT NOW()
)
```

Toda vez que o usuário clica em **buscar imóveis**, o backend registra o evento — inclusive quando o plano gratuito só recebe `cache_miss`. Autocomplete, digitação e simples seleção no combobox **não** entram na fila de prewarm. O scheduler agrega apenas as buscas com `requested_at >= now() - interval '24 hours'`, agrupando por `zone_fingerprint + search_location_normalized + search_type + usage_type + platforms_hash`.

**Decisão fechada:**
- não existe fallback por zona popular;
- não existe fallback por geohash/região;
- não existe pré-aquecimento de cold start sem demanda real;
- se nada foi pesquisado nas últimas 24h, o prewarm não raspa nada.

---

## 6.7 Políticas de retenção

## Sugestão prática

- `job_events` detalhados: 30 a 90 dias;
- snapshots brutos de scraping: 30 dias;
- snapshots normalizados de preço: retenção longa;
- relatórios gerados: retenção configurável por usuário/plano;
- caches efêmeros: TTL curto por tipo.

---

## 6.8 GTFS — fonte, frequência e pipeline de ingestão

### Fontes decididas

Feeds obtidos via **Mobility Database** (mobilitydatabase.org) — agregador que consolida GTFS de todas as operadoras de SP em endpoints únicos com webhook de atualização. Substitui o monitoramento direto de 4 URLs distintas por uma única integração.

```python
GTFS_SOURCES = {
    "sao_paulo_municipal": "https://api.mobilitydatabase.org/feeds/mdb-559",  # SPTrans
    "sao_paulo_metro":     "https://api.mobilitydatabase.org/feeds/mdb-560",  # Metrô SP
    # CPTM e EMTU entram na segunda rodada (cobertura RMSP)
}
```

**Por que não APIs de roteamento externas (Google, HERE):** dados retornados não podem ser armazenados (ToS), incompatível com o modelo de cache por fingerprint do produto. Google não tem endpoint de isócrona direta — simular via N chamadas de Directions é inviável financeiramente em escala. OTP Cloud gerenciado (Conveyal) começa em centenas de dólares/mês — inviável para fase inicial.

**Localização do OTP:** roda no Hostinger VPS 1 (São Paulo) junto ao Valhalla. Latência API → OTP: ~5–15ms (mesma cidade). Dados GTFS atualizados via pipeline de ingestão no mesmo VPS.

### Frequência de atualização

```python
GTFS_UPDATE_SCHEDULE = {
    "sao_paulo_municipal": "weekly",   # SPTrans publica com frequência
    "sao_paulo_metro":     "monthly",
}
```

O Mobility Database emite webhook quando há nova versão de um feed. O pipeline dispara automaticamente ao receber a notificação — sem polling de horário fixo.

### Pipeline de ingestão

1. Download do arquivo GTFS (zip) via HTTP;
2. comparação de hash SHA-256 com a versão anterior — se igual, encerra sem processamento;
3. se diferente, carrega em tabelas de staging do PostGIS;
4. valida consistência (shapes, stop_times, trips);
5. substitui tabelas de produção em transação única;
6. registra nova versão em `dataset_versions` com hash e data;
7. invalida cache Redis de pontos de transporte elegíveis por área;
8. zonas geradas com versão anterior **não são invalidadas** — ficam com versão antiga registrada para auditoria.

### Tabelas PostGIS mínimas

```sql
gtfs_stops      (stop_id, stop_name, stop_lat, stop_lon, location GEOMETRY(Point,4326))
gtfs_routes     (route_id, route_short_name, route_long_name, route_type)
gtfs_trips      (trip_id, route_id, shape_id)
gtfs_stop_times (trip_id, stop_id, arrival_time, departure_time, stop_sequence)
gtfs_shapes     (shape_id, shape_pt_sequence, location GEOMETRY(Point,4326))
```

Índice GIST obrigatório em `gtfs_stops.location` — a consulta `ST_DWithin` por raio é a mais frequente do produto e sem índice vira full scan.

**Responsável pela ingestão:** APScheduler rodando no processo da API ou worker scheduler dedicado leve. Mantém a operação dentro do monólito e auditável pelos mesmos logs.

---

# 7. Controle de custos e limites de APIs externas

## 7.1 Princípio geral

Toda chamada externa deve ser tratada como recurso caro e observável. Mas isso não significa tentar eliminar qualquer dependência externa. Em geoespacial, parte das consultas precisa continuar externa porque a autoridade operacional do dado está no provedor.

A regra do sistema deve ser:

- chamar o provedor apenas quando necessário;
- responder com cache ou resultado persistido sempre que houver material utilizável;
- revalidar em background;
- versionar a base usada;
- medir custo e frequência por operação.

Não basta colocar cache. É necessário ter:

- orçamento por operação;
- quota por usuário;
- quota global;
- deduplicação;
- fallback;
- monitoramento;
- política explícita de frescor por tipo de dado.

---

## 7.2 Situação específica de Mapbox e decisão de tiles

### Limites relevantes do Mapbox

- **Search Box API:** inclui POIs, suporta Category Search e não deve ser tratada como base canônica persistente do produto;
- **Tilequery API:** 600 req/min;
- **Static Images API:** ~1.200 req/min;
- cobrança por uso — sem plano ilimitado.

Mapbox não deve ser a espinha dorsal do motor analítico. Token sempre atrás do backend.

### Decisão fechada: MapTiler como provedor único de tiles

**Tiles de fundo:** MapTiler — **provedor único para todo o ciclo de vida do produto**.

**Justificativa:**

Setup zero. Sem custo de download de arquivo `.pmtiles` (~3–4GB), sem gestão de bucket R2 para tiles, sem build de estilo próprio. O tier gratuito (100k map loads/mês) cobre inteiramente a fase de validação. Quando o volume crescer, o upgrade é feito no painel MapTiler — sem alteração de código, de infraestrutura ou de estilo. Estilos são gerenciados no MapTiler Studio e referenciados por URL; camadas analíticas do produto sobrepõem esse estilo base via GeoJSON e vector tiles próprios.

A troca por Protomaps foi descartada: o ganho de custo variável só se materializa em volume alto (acima de ~500k map loads/mês), e o custo operacional de manter um arquivo `.pmtiles` atualizado, servido via R2, com estilo próprio versionado, não se justifica na fase atual nem nas próximas.

**Geocoding continua no Mapbox** (seção 7.3.B) — tiles e geocoding são serviços independentes.
## 7.3 Estratégia recomendada por tipo de operação

## A. Renderização do mapa

### Recomendação

Migrar o front para **MapLibre** com estilo próprio ou provedor menos crítico, e usar tiles analíticos próprios para as camadas do produto.

### Benefício

Reduz dependência e custo variável de map load.

## B. Busca de endereço/autocomplete

### Decisão fechada: Mapbox Search Box API como primário

O repositório já usa `MAPBOX_ACCESS_TOKEN` — a dependência existe e funciona. Trocar o geocoder na Fase 3 seria retrabalho sem benefício.

**Regras obrigatórias de uso:**

- sempre via **proxy backend** (`POST /api/geocode`) — token nunca exposto no cliente;
- **debounce de 300ms** no frontend antes de disparar requisição;
- **cache server-side por string normalizada** no Redis (TTL 24h);
- **persistência auxiliar** no banco dos resultados normalizados;
- **limite por sessão/IP:** máximo 30 req/min via `external_usage_ledger`;
- **fallback para seleção manual no mapa** quando rate limit for atingido.

**Três níveis de fallback em cascata:**

```
1. Cache Redis (string normalizada)  → ~70% das buscas repetidas
2. Banco (histórico persistido)      → ~20% dos casos de rate limit
3. Seleção manual no mapa            → sempre disponível
```

Nominatim self-hosted não entra agora — overhead de manutenção não se justifica enquanto o cache cobrir as falhas. Reavaliar quando custo Mapbox geocoding superar R$50/mês.

**Tiles de fundo:** MapTiler — provedor único, independente do geocoder.
## C. POIs para análise

### Decisão corrigida pela implementação real do repositório

O repositório atual já obtém POIs pela **Mapbox Search Box API (Category Search)**, disparada pelo adapter `pois_adapter.py` e pelo script legado `pois_categoria_raio.py`. Portanto, a arquitetura correta do produto deve assumir **Mapbox como origem operacional dos POIs**.

Isso muda a modelagem correta para:

- consulta de POIs **sob demanda** por categoria e área (raio/bbox);
- normalização do retorno para uso no mapa e nos painéis;
- **cache efêmero** por zona/jornada para reduzir custo e latência;
- agregações derivadas (`poi_counts`, destaques, listas) persistidas apenas como resultado do job;
- nenhum dataset-base canônico da cidade derivado da Search Box API.

Ruas, grafo viário, GTFS e demais estruturas geoespaciais locais continuam em infraestrutura própria. O ajuste aqui é específico para POIs.

## D. Imagens estáticas para relatório

Usar somente no momento da geração do relatório, com cache por bbox/tema, ou gerar imagem a partir de tile próprio.

---

## 7.4 Mecanismos rigorosos de controle

## Tabela `external_usage_ledger`

Campos:

- id;
- provider;
- operation_type;
- user_id/session_id;
- journey_id;
- units;
- estimated_cost;
- created_at;
- cache_hit;
- status.

## Rate limiting em Redis

Por:

- IP;
- sessão anônima;
- usuário autenticado;
- operação.

## Soft limit + hard limit

### Soft limit
- avisa UI;
- ativa fallback;
- reduz granularidade.

### Hard limit
- bloqueia novas chamadas externas daquele tipo;
- mantém fluxo via cache/local/manual.

## Deduplicação

Antes de chamar API externa, consultar cache por fingerprint da requisição. No caso dos imóveis, consultar primeiro o cache por zona/configuração e, se necessário, o cache por interseção geométrica antes de iniciar novo scraping.

## Fallbacks

- autocomplete indisponível → seleção manual no mapa;
- Search Box saturado → geocoder local simplificado ou histórico recente;
- Static map indisponível → render server-side de imagem a partir do próprio tile;
- POI externo indisponível → manter último cache efêmero utilizável ou sinalizar indisponibilidade parcial.

---

# 8. Autenticação e modelo de acesso

## 8.1 Biblioteca de autenticação

**Decisão: fastapi-users.**

Better Auth descartado — é TypeScript-first e exigiria um serviço JS separado só para auth, quebrando a simplicidade do monólito Python. Implementação própria descartada — o risco de erro em borda (rotação de sessão, timing-safe token comparison, magic link com expiração segura) supera qualquer benefício de controle.

`fastapi-users` cobre exatamente o que o produto precisa:

- **magic link por email** como mecanismo primário — zero fricção, sem senha para gerenciar;
- **OAuth social** (Google) configurável depois, sem reescrita;

#### Provedor de email: Resend

**Decisão fechada: Resend** (resend.com).

Justificativa sobre as alternativas:

| Provedor | Por que não |
|---|---|
| AWS SES | Requer configuração de domínio, DKIM, DMARC, aprovação de sending limits, conta AWS separada — overhead desnecessário no início |
| SendGrid | Plano gratuito limitado (100 emails/dia), interface complexa, historicamente com problemas de deliverability em IPs compartilhados |
| Mailgun | Gratuito por 3 meses depois pago, API menos ergonômica |
| **Resend** | API REST simples, SDK Python oficial, 3.000 emails gratuitos/mês, deliverability excelente, dashboard limpo, suporte a React Email para templates |

O produto usa email exclusivamente para magic links — volume muito baixo no início. 3.000 emails/mês cobrem ~3.000 logins únicos, o que é mais do que suficiente para a fase inicial.

```python
# settings.py
RESEND_API_KEY: str  # var de ambiente obrigatória na Fase 8
EMAIL_FROM: str = "noreply@find-ideal-estate.com.br"
```

Template de magic link via React Email — renderizado server-side pelo Resend, sem dependência de serviço de template externo.
- integração nativa com SQLAlchemy 2 e Alembic;
- cookie HTTP-only com rotação automática de sessão.

## 8.2 Modelo de acesso: anônimo com upgrade progressivo

O usuário acessa e usa o produto sem cadastro. A jornada fica associada a um `anonymous_session_id` (cookie de sessão). Autenticação é exigida apenas nos momentos de alto valor percebido:

- **baixar o relatório PDF** de qualquer zona — esse é o momento de maior valor e menor resistência ao cadastro;
- **salvar jornada** para retomar depois;
- **acessar histórico** de análises anteriores.

No momento do cadastro, a jornada anônima é migrada para o usuário recém-criado por `session_id → user_id`. O usuário não perde o que já fez.

**Quotas para sessões anônimas:** rate limiting mais restritivo por IP + session (metade dos limites do plano gratuito), para prevenir abuso sem criar barreira de entrada.

#### Mapa de dependência de auth por fase

A dependência circular entre Fase 6 (imóveis/planos) e Fase 8 (auth) é resolvida assim:

| Feature | Fase | Auth necessária? | Como funciona sem auth |
|---|---|---|---|
| Análise de transporte e zonas | 4 | Não | Sessão anônima com quota por IP |
| Cache de imóveis (FREE) | 6 | Não | Cache servido para sessão anônima; prewarm baseado apenas em endereços pesquisados nas últimas 24h |
| Scraping fresh (PRO) | 8 | **Sim** | Na Fase 6, todo scraping é tratado como FREE; PRO é ativado somente na Fase 8, quando auth estiver integrada |
| Badge de frescor | 6 | Não | Exibe idade do cache para todos |
| Download do relatório PDF | 7 | **Sim** | CTA de cadastro no momento do download |
| Histórico de análises | 7 | **Sim** | Não disponível para sessão anônima |
| Plano Pro / Stripe | 8 | **Sim** | Exige conta criada antes de pagar |
| Quotas por plano | 8 | **Sim** | Antes da Fase 8, só rate limiting por IP/sessão |

**Implementação nas Fases 6 e 7 sem auth completa:**

O schema de `plans`, `usage_quotas` e `user_subscriptions` é criado na Fase 1. Nas Fases 6 e 7 o sistema assume que toda sessão anônima é tratada como plano FREE (slug `'free'`) e aplica as quotas correspondentes via rate limiting por IP. A distinção real FREE/PRO só é ativada na Fase 8 quando fastapi-users estiver integrado.

```python
async def get_effective_plan(user: User | None, session_id: str | None) -> PlanSlug:
    if user and user.has_active_subscription():
        return PlanSlug.PRO
    return PlanSlug.FREE  # anônimo e free recebem o mesmo tratamento
```

Isso elimina a dependência circular: as Fases 6 e 7 entregam valor real (cache de imóveis, relatório) sem bloquear na ausência de auth.

### Edge cases da migração de sessão anônima

**TTL de sessão anônima:** 7 dias de inatividade. Jornadas anônimas não completadas são deletadas após 7 dias sem acesso. Jornadas com relatório gerado ficam persistidas por 30 dias mesmo sem autenticação. A sessão é renovada a cada acesso.

**Dois dispositivos antes do login:** a jornada anônima vive no cookie de sessão — dois dispositivos têm cookies diferentes e portanto jornadas independentes. Se o usuário fizer login no dispositivo B depois de já ter feito no A, a jornada do B é migrada como nova jornada do usuário, sem sobrescrever a do A.

**Atomicidade da migração:**
```sql
BEGIN;
UPDATE journeys
   SET user_id = :new_user_id,
       anonymous_session_id = NULL
 WHERE anonymous_session_id = :session_id
   AND user_id IS NULL;
COMMIT;
```
Se a transação falhar, a jornada continua anônima e a migração é tentada na próxima requisição autenticada. Não há estado parcial.

**Sessão expirada antes do login:** a conta é criada sem jornada prévia — não há o que migrar. O sistema não mostra erro nem aviso; abre a conta vazia. Se o usuário tinha relatório gerado dentro do período de retenção de 30 dias e já havia se identificado por email em algum momento anterior, um endpoint de recuperação permite revinculá-lo.

## 8.3 Modelo de planos

```python
class PlanSlug(str, Enum):
    FREE = "free"
    PRO  = "pro"
```

| | Gratuito | Pro |
|---|---|---|
| Análises de zona por mês | 2 | Ilimitado |
| Modal de isócrona | Transporte público + a pé | + Carro |
| Dados de imóveis | Cache pré-aquecido apenas para endereços pesquisados nas últimas 24h | Scraping fresh sob demanda |
| Tempo para ver imóveis | Imediato quando já houver cache do endereço pesquisado | 30–90s (Playwright rodando) |
| Relatório PDF | 2/mês (exige cadastro para baixar) | Ilimitado |
| Histórico de análises salvas | Não | Sim |
| Plataformas de scraping disponíveis | QuintoAndar + Zap Imóveis | + VivaReal |
| Dashboard histórico de preços | 30 dias | 90 dias |

**Primeiro mecanismo de receita: pay-per-report.** O relatório PDF completo — com histórico de preços, dashboard da zona e imóveis em destaque — é o produto de maior valor percebido. O usuário acabou de investir 10–15 minutos na análise e quer o documento para compartilhar ou arquivar. Cobrar por geração de relatório (ou incluir no plano Pro) é o caminho de menor fricção para a primeira receita.

**Isócrona de carro como diferencial Pro:** Valhalla self-hosted suporta carro nativamente — o custo não é por requisição externa, é computacional. Um grafo de carro para SP consome ~2x mais RAM que walking e gera isócronas maiores, com mais zonas, mais enriquecimento e mais scraping. Esse custo computacional adicional justifica a restrição ao plano pago — não é uma limitação artificial, é proporcional ao uso de recursos.

**Preços decididos:**
- Plano Pro: **R$ 29/mês** ou **R$ 249/ano** (~R$ 20,75/mês, desconto de 28%).
- Relatório avulso: **R$ 9,90 por relatório** — para usuários gratuitos que quiserem relatório extra sem assinar. Três relatórios avulsos equivalem ao plano mensal — argumento natural de upgrade.

**CTAs de upgrade contextualizados (não pitch genérico):**
- ao tentar VivaReal no plano gratuito: `"Adicione VivaReal à sua busca — plano Pro por R$ 29/mês"`;
- ao tentar isócrona de carro: `"Analise deslocamento de carro — plano Pro por R$ 29/mês"`;
- ao baixar terceiro relatório no mês: `"Baixe este relatório por R$ 9,90 ou acesse relatórios ilimitados no plano Pro"`.

**Mecanismo de pagamento: Stripe.** SDK Python (`stripe`), webhooks para eventos de pagamento, portal de cliente para self-service de assinatura.

#### Webhooks Stripe necessários

Lista completa de eventos que o sistema deve tratar no endpoint `POST /webhooks/stripe`:

| Evento | Ação |
|---|---|
| `checkout.session.completed` | Criar `user_subscriptions` com status `active`; ativar plano Pro |
| `invoice.payment_succeeded` | Renovar `current_period_end`; reativar se estava `past_due` |
| `invoice.payment_failed` | Marcar `status = past_due`; enviar email de aviso ao usuário |
| `customer.subscription.updated` | Sincronizar mudanças de plano (upgrade/downgrade) |
| `customer.subscription.deleted` | Marcar `status = cancelled`; rebaixar para plano gratuito |
| `charge.refunded` | Registrar no ledger; não altera plano automaticamente |

**Segurança dos webhooks:** validar assinatura Stripe com `stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)` antes de processar qualquer evento. Retornar 400 em caso de assinatura inválida.

**Idempotência:** usar `stripe_event_id` como chave única na tabela `webhook_events` — Stripe pode reenviar o mesmo evento mais de uma vez.

```sql
webhook_events (
  stripe_event_id  TEXT PRIMARY KEY,
  event_type       TEXT NOT NULL,
  processed_at     TIMESTAMPTZ DEFAULT NOW(),
  payload_json     JSONB
)
```

**Variáveis de ambiente necessárias na Fase 8:**
```
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_ID_PRO_MONTHLY
STRIPE_PRICE_ID_PRO_YEARLY
STRIPE_PRICE_ID_REPORT_AVULSO
```

**Implicação técnica:** a tabela `plans` com os campos de quota precisa existir desde a Fase 1 com os dois planos definidos, mesmo que só o plano gratuito esteja ativo. Isso evita retrabalho quando o plano pago for lançado.

```sql
-- Tabela plans (campos mínimos + Stripe)
plans (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug                    TEXT UNIQUE NOT NULL,  -- 'free' | 'pro'
  zone_analyses_per_month INT,                -- NULL = ilimitado
  modals_allowed          TEXT[],             -- ['walking','transit'] | + 'car'
  reports_per_month       INT,                -- NULL = ilimitado
  history_days            INT,                -- 30 | 90
  platforms_allowed       TEXT[],             -- ['quintoAndar','zap'] | + 'vivaReal'
  stripe_product_id       TEXT,               -- NULL até Fase 8
  stripe_price_id         TEXT                -- NULL até Fase 8
)

-- Tabela user_subscriptions (criar na Fase 1, popular na Fase 8)
user_subscriptions (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID REFERENCES users(id),
  plan_id                 UUID REFERENCES plans(id),
  stripe_customer_id      TEXT,
  stripe_subscription_id  TEXT,               -- NULL para plano gratuito
  status                  TEXT,               -- 'active' | 'cancelled' | 'past_due'
  current_period_end      TIMESTAMPTZ,
  created_at              TIMESTAMPTZ,
  updated_at              TIMESTAMPTZ
)

-- Tabela usage_quotas (rastreia consumo real por usuário por janela mensal)
usage_quotas (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
  plan_id             UUID REFERENCES plans(id),
  quota_type          TEXT NOT NULL,
    -- 'zone_analyses'  → jornadas que chegaram à Etapa 4
    -- 'reports_pdf'    → relatórios gerados
    -- 'api_geocoding'  → chamadas ao geocoder externo
  window_start        TIMESTAMPTZ NOT NULL,   -- date_trunc('month', now())
  window_end          TIMESTAMPTZ NOT NULL,
  consumed            INT NOT NULL DEFAULT 0,
  limit_value         INT,                    -- NULL = ilimitado (plano Pro)
  last_incremented_at TIMESTAMPTZ,
  created_at          TIMESTAMPTZ DEFAULT now(),

  CONSTRAINT uq_user_quota_type_window
    UNIQUE (user_id, quota_type, window_start)
)
```

**Regra de incremento atômica:**
```sql
UPDATE usage_quotas
   SET consumed = consumed + 1,
       last_incremented_at = now()
 WHERE user_id = :user_id
   AND quota_type = :quota_type
   AND window_start = date_trunc('month', now())
   AND (limit_value IS NULL OR consumed < limit_value)
RETURNING *;
-- 0 linhas retornadas = limite atingido → API responde 429
-- {"quota_exceeded": true, "quota_type": "zone_analyses", "limit": 2}
```

`zone_analyses` é incrementado ao **criar o job de geração de zonas** (não ao finalizar) — o consumo é cobrado pela intenção, não pelo sucesso. Janela mensal criada na primeira operação do mês com `consumed = 0`; a do mês anterior fica para auditoria.

---

### Schema de `zone_listing_caches`

Usada em 5.3.D (`zone_listing_caches.get(zone_id, config)`) — precisa estar definida:

```sql
zone_listing_caches (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zone_fingerprint    TEXT NOT NULL,
  config_hash         TEXT NOT NULL,   -- SHA-256 de {platforms, usage_type, search_location_normalized}
  status              TEXT NOT NULL DEFAULT 'pending',  -- ZoneCacheStatus enum
  listings_json       JSONB,           -- resultado consolidado; NULL até COMPLETE ou PARTIAL
  platforms_done      TEXT[],          -- plataformas que já responderam
  platforms_failed    TEXT[],
  scraping_started_at TIMESTAMPTZ,
  scraping_ended_at   TIMESTAMPTZ,
  cache_expires_at    TIMESTAMPTZ,     -- NOW() + 12h para FREE; NOW() + 1h para PRO
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE (zone_fingerprint, config_hash)
)
```

#### Método `is_usable()`

```python
def is_usable(self) -> bool:
    if self.status in (ZoneCacheStatus.COMPLETE, ZoneCacheStatus.PARTIAL):
        return self.cache_expires_at > datetime.utcnow()
    if self.status == ZoneCacheStatus.CANCELLED_PARTIAL:
        return bool(self.listings_json)  # usa o que coletou se tiver algo
    return False
```

#### TTL por plano
- **FREE:** 12h — cache válido para o prewarm noturno que roda às 03:00
- **PRO:** scraping fresh a cada requisição; cache salvo por 1h para deduplicação de cliques rápidos

---

# 9. Plano de reformulação do frontend e funcionamento detalhado

## 9.1 Princípio visual

A aplicação deve comunicar:

- confiança;
- análise séria;
- clareza de decisão;
- foco em território.

Nada de aparência genérica de dashboard corporativo ou formulário pesado.

## Paleta

- base neutra e clara;
- azul como cor de ação primária;
- verde para qualidade positiva;
- roxo/âmbar para risco/alerta;
- contraste alto em textos.

## Tipografia

- sem serifa, moderna, legível;
- hierarquia forte entre título de etapa, bloco analítico e metadados.

## Bordas e superfícies

- bordas suaves;
- cards flutuantes sobre o mapa;
- blur leve apenas onde fizer sentido;
- sombra discreta.

---

## 9.2 Comportamento exato da tela inicial

### Mapa
- ocupa toda a área disponível;
- inicia já focado em São Paulo/RMSP ou última sessão do usuário;
- zoom por scroll apenas sobre o mapa;
- clique no mapa pode selecionar ponto quando o modo estiver ativo.

### Busca
- canto superior esquerdo;
- placeholder claro;
- resultados rápidos;
- ação secundária “usar ponto clicado no mapa”.

### Painel lateral
- visível por padrão;
- cabeçalho com nome da etapa e navegação;
- pode recolher sem destruir estado.

### Legenda
- só mostra camadas visíveis;
- muda dinamicamente;
- não deve listar tudo sempre.

### Camadas
- botão flutuante alinhado ao estado do painel;
- lista com toggle individual;
- botão olho para tudo ligado / tudo desligado;
- quatro presets de contexto no topo do painel de camadas.

**Conteúdo definido de cada preset:**

| Preset | Camadas ativas |
|---|---|
| **Mobilidade** | Pontos de transporte, rotas a pé até cada ponto, linhas de ônibus/metrô relevantes, isócrona da zona selecionada |
| **Riscos** | Áreas alagáveis (gradiente por recorrência), ocorrências de segurança pública (heatmap), polígonos de zona atenuados |
| **Imóveis** | Marcadores de imóveis clusterizados, polígono da zona ativa, endereço de busca marcado |
| **Análise** | Áreas verdes (preenchimento), POIs por categoria (ícones), zona ativa, ponto de transporte selecionado |

**Regras:** ao ativar um preset, o sistema sobrescreve o estado do layer control com as camadas acima. O usuário pode ajustar individualmente depois — o preset não trava nada. A legenda atualiza automaticamente para mostrar só as camadas visíveis.

---

## 9.3 Comportamento da etapa de transporte

### Critério de lista
Cada ponto deve mostrar:

- tempo a pé;
- distância em metros;
- tipo;
- número de linhas;
- principais linhas;
- badge de conectividade.

### Popup do mapa
- nome do ponto;
- tipo;
- linhas;
- distância a pé;
- botão de gerar zonas.

### Regra de seleção
- somente um ponto principal;
- ao selecionar novo ponto, o anterior é descartado como origem de zona.

---

## 9.4 Comportamento da etapa de zonas

### Lista de zonas
Cada item deve mostrar pelo menos:

Nesta etapa, a priorização visual deve ser baseada em métricas transparentes e não em uma pontuação única opaca. O usuário deve entender por que uma zona aparece em destaque.

- número/nome da zona;
- tempo de viagem;
- distância ao desembarque;
- resumo comparativo dos critérios disponíveis;
- badges de destaque por critério (provisórios durante enriquecimento, finais após mediana real — ver seção 4.4);
- estado dos dados disponíveis.

### Detalhe da zona
A área de detalhe deve responder apenas aos critérios que o usuário ativou.

Se POIs não foram incluídos, não mostrar caixa vazia de POIs.

### Mapa
- rótulo numérico no polígono;
- clique no polígono seleciona;
- hover destaca;
- seed e downstream continuam visíveis.

---

## 9.5 Comportamento da etapa de imóveis

### Filtros obrigatórios no painel
- preço;
- tamanho;
- tipo de uso: `Residencial`, `Comercial` ou `Todos` (mapeado de `PropertyUsageType`; imóveis com `unknown` aparecem apenas em `Todos`);
- plataforma (seleção múltipla dentro das permitidas pelo plano; VivaReal com lock no plano gratuito).

Esses filtros devem ser combináveis, persistidos na jornada e refletidos na URL/estado compartilhável quando isso existir.

### Card ideal
- imagem à esquerda/topo;
- preço com destaque máximo;
- metragem e endereço como apoio;
- tipo de uso visível;
- plataforma e link em bloco secundário;
- badges de `menor preço do cluster`, `repetido em 2 plataformas`, `caiu de preço`, `resultado preliminar` quando aplicável.

### Badge de frescor por plano

O painel de imóveis mostra o estado dos dados de forma discreta mas clara, diferente por plano:

**Usuário gratuito — vendo cache de até 12h:**
```
47 imóveis encontrados
● Dados de hoje às 03:40          ← idade do cache, discreta

[cards de imóveis...]

─────────────────────────────────────
Quer ver o que está disponível agora?
Atualize para o plano Pro →
```

**Usuário Pro — scraping em andamento:**
```
Buscando imóveis...  ████░░  2 de 3 plataformas
```

**Usuário Pro — scraping concluído:**
```
47 imóveis encontrados
● Atualizado agora               ← reforça o valor do plano
```

**Usuário gratuito — endereço sem cache (esperado quando ainda não houve demanda nas últimas 24h):**
```
┌─────────────────────────────────────────────────┐
│  Este endereço entrou na fila de atualização    │
│  noturna.                                       │
│  Se houver anúncios disponíveis, eles aparecerão│
│  após a próxima atualização.                    │
│  ┌─────────────────────────────────────────┐    │
│  │  Ver imóveis agora — plano Pro R$29/mês │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### Comportamento com resultado preliminar
Quando houver reaproveitamento por cache:

- o topo do painel informa que a lista está em atualização;
- cards preliminares entram imediatamente;
- o usuário pode filtrar normalmente por preço, tamanho e tipo de uso mesmo antes do scraping terminar;
- a chegada de novos imóveis não pode resetar scroll, filtros ou seleção do usuário;
- a atualização deve aplicar diff incremental, não rerender bruto da lista.

### Painel de detalhe do imóvel
Ao abrir um imóvel:

- mini-histórico de preço;
- disponibilidade/intermitência;
- distâncias a transporte e POIs;
- indicadores de acesso cotidiano, como tempo a pé até transporte e categorias de POI mais próximas;
- links para anúncios equivalentes.

---

# 10. Estratégia de dados e domínio para a nova solução

## 10.1 Módulos de domínio recomendados

## `journeys`
Gerencia a sessão analítica do usuário.

## `transport`
Gerencia pontos elegíveis, linhas, tempos e rotas.

## `zones`
Geração, consolidação, seleção e ranking de zonas.

## `urban_analysis`
Verde, alagamento, segurança pública, métricas derivadas.

## `pois`
Categorias, contagens, detalhes e acessibilidade.

## `listings`
Coleta, normalização, deduplicação, snapshots e histórico.

## `reports`
Geração e exportação.

## `usage_limits`
Quotas, rate limiting e ledger de custo.

## `datasets`
Versionamento e ingestão das bases públicas.

---

## 10.2 Dados que eu recomendo trazer para infraestrutura própria o quanto antes

- ruas;
- POIs de análise;
- linhas/paradas;
- geometrias de risco/alagamento;
- áreas verdes, após ingestão versionada em PostGIS;
- camadas analíticas do mapa.

Quanto mais disso ficar local, melhor ficam:

- custo;
- velocidade;
- previsibilidade;
- conformidade de uso.

---

## 10.3 Estratégia fechada para vegetação e área verde

A camada de vegetação/área verde **não** será preparada ad hoc durante a jornada do usuário. O comportamento alvo fica fechado assim:

- os artefatos atuais de `green_tiles_*` e `tile_index.csv` deixam de ser dependência de runtime;
- preparação, recorte, indexação e validação da base verde viram **pipeline de ingestão de dataset**;
- o resultado validado é materializado em **PostGIS** e versionado em `dataset_versions`;
- o worker de enriquecimento consulta apenas tabelas prontas no banco.

### Pipeline obrigatório

1. obter o dataset fonte de vegetação/área verde;
2. normalizar CRS e geometria;
3. recortar/particionar quando necessário para ingestão eficiente;
4. carregar em tabela de staging;
5. validar geometria, cobertura espacial e hash da versão;
6. promover para tabela ativa;
7. registrar versão em `dataset_versions`.

### Tabelas mínimas

- `green_areas_raw` — staging da versão importada;
- `green_areas_active` — geometria pronta para consulta;
- `dataset_versions` — versão, hash, fonte, período de validade, status.

### Regra de runtime

Durante uma jornada do usuário:

- o job de enriquecimento verde **não** constrói índice;
- **não** gera `tile_index.csv`;
- **não** monta tiles locais on-the-fly;
- apenas consulta `green_areas_active` via PostGIS (`ST_Intersection`, `ST_Area`, índices GIST).

Se o dataset verde estiver desatualizado ou ausente, isso é falha operacional da pipeline de ingestão — nunca trabalho escondido dentro do fluxo do usuário.

Essa decisão fecha o ponto de vegetação: preparação de tiles/índices vira responsabilidade do pipeline de datasets, não da execução interativa.


# 11. Plano de migração

## 11.1 O que reaproveitar

## Reaproveitar quase imediatamente

- scripts geoespaciais já validados em `cods_ok/`, encapsulados primeiro como legado auditável;
- adapters existentes como wrappers temporários, evoluindo para ports/adapters explícitos;
- contrato geral do fluxo de negócio;
- smoke tests existentes;
- semântica das camadas do mapa;
- ideia de `run` e logs por etapa.

## Reaproveitar com refatoração

- `Runner` como embrião dos jobs;
- `RunStore` apenas conceitualmente, migrando para banco;
- `core/*` separando domínio de filesystem;
- frontend atual como referência visual/funcional, não como estrutura final.

## Reescrever

- `ui/src/App.tsx`;
- persistência orientada a arquivo como fonte de verdade;
- polling como mecanismo principal de progresso rico;
- parte da integração de POIs baseada em API comercial (Mapbox Search Box API);
- modelo de autenticação.

---

## 11.1.1 Estratégia fechada de migração do `cods_ok`

A migração do legado **não** será feita por rewrite antecipado. A estratégia oficial fica fechada em três passos, com critérios objetivos.

### Passo 1 — encapsular como legado

Tudo que hoje vem de `cods_ok/` entra na nova arquitetura por adapters explícitos. A regra é:

- preferir **importação direta** de funções/módulos Python quando o código legado permitir;
- manter `subprocess` apenas quando o legado realmente controlar browser, CLI ou side effects difíceis de reproduzir por import;
- nenhum endpoint novo chama `cods_ok` diretamente;
- nenhum componente de UI conhece `cods_ok`;
- toda interação com legado passa por ports/adapters do domínio.

Adapters mínimos obrigatórios:

- `LegacyZoneGeneratorAdapter`
- `LegacyUrbanAnalysisAdapter`
- `LegacyListingsCollectorAdapter`
- `LegacyListingsParserAdapter`

### Passo 2 — definir Protocols de domínio

Os serviços novos dependem de contratos Python (`typing.Protocol`), nunca da implementação concreta do legado. Protocols mínimos obrigatórios:

```python
class ZoneGeneratorPort(Protocol): ...
class UrbanAnalysisPort(Protocol): ...
class ListingsCollectorPort(Protocol): ...
class ListingsParserPort(Protocol): ...
class DatasetIngestorPort(Protocol): ...
```

Cada port deve definir:

- entrada tipada;
- saída tipada;
- erros esperados;
- semântica de cancelamento;
- eventos de progresso emitidos;
- idempotência.

### Passo 3 — reescrever só por razão medida

Uma implementação legado só pode ser reescrita quando houver **razão medida** registrada em ADR ou issue arquitetural. Razões aceitas:

- `p95` de latência incompatível com a UX alvo;
- consumo de memória inviável para o ambiente escolhido;
- falha recorrente em produção;
- impossibilidade prática de observabilidade;
- impossibilidade prática de cancelamento cooperativo;
- dificuldade impeditiva de teste automatizado;
- dependência externa que deixou de existir.

**Razões não aceitas:** “o código é feio”, “seria melhor reescrever tudo”, “queremos padronizar antes de medir”.

### Mecanismo de segurança da migração

A comparação entre legado e nova implementação deve usar **golden runs**: uma coleção pequena de execuções reais representativas, congeladas como fixture. Nenhuma reescrita substitui o legado sem provar equivalência funcional mínima nessas execuções.

Essa decisão elimina o ponto em aberto sobre `cods_ok`: o legado entra primeiro como adapter auditável; a reescrita acontece depois, e apenas quando houver benefício demonstrado.


## 11.2 Roadmap por fases

## Fase 0 — Baseline e observabilidade

- congelar comportamento atual com smoke tests;
- medir tempos por etapa;
- adicionar correlação de logs;
- remover riscos óbvios de produção.

## Fase 1 — Banco e modelo de jornada

- subir Postgres/PostGIS e Redis;
- criar `journeys`, `jobs`, `job_events`, `dataset_versions`;
- criar `plans`, `usage_quotas` com os dois planos definidos (gratuito e Pro) — mesmo que só o plano gratuito esteja ativo, o schema precisa existir antes do primeiro usuário para evitar retrabalho;
- espelhar a run atual no novo modelo sem mudar ainda o algoritmo.

## Fase 2 — Worker e SSE

- introduzir **Dramatiq** como broker de jobs com Redis — `StubBroker` para testes unitários sem Redis real; restrictório `RedisBroker` em produção;
- definir `JobRetryPolicy` por tipo de job (transport, zones, enrichment, scrape, dedup, reports);
- separar API e worker (processo `worker-general` consumindo filas Dramatiq);
- mover pipeline para fila com retry e backoff nativo;
- emitir eventos reais de progresso via SSE;
- manter artefatos em arquivo como suporte temporário.

## Fase 3 — Frontend shell novo

- **migrar o frontend de Vite para Next.js App Router** — Server Components para landing page (SEO), API routes para proxy de chave MapTiler e geocoding Mapbox (tokens nunca expostos no cliente);
- construir mapa shell com MapLibre sobre estilo MapTiler;
- decompor painel por etapas;
- integrar SSE;
- manter backend atual por trás onde possível.

## Fase 4 — Etapa de transporte e zonas

- modelar corretamente seleção de ponto de transporte;
- gerar zonas incrementalmente;
- permitir navegação reentrante.

## Fase 5 — POIs e análise urbana local

- encapsular os POIs da Mapbox em módulo dedicado com cache efêmero e orçamento por operação;
- transformar a base de vegetação em pipeline de ingestão versionada para PostGIS;
- consolidar limites, TTL e reuso da Search Box API sem desviar da implementação funcional atual.

## Fase 6 — Imóveis e histórico

- normalização;
- deduplicação;
- snapshots;
- cache stale-while-revalidate por zona/interseção;
- dashboard histórico;
- filtros por preço, tamanho, plataforma e tipo de uso;
- **toda sessão tratada como plano FREE** — scraping servido do cache noturno para todos; a arquitetura (`plans`, `get_effective_plan`, `usage_quotas`) já existe e está preparada para a distinção FREE/PRO, que só é ativada na Fase 8;
- scheduler de prewarm noturno orientado por `listing_search_requests` das últimas 24h;
- badge de frescor no painel de imóveis (cache_age vs "atualizado agora");
- alerta de monitoramento de falha do prewarm.

## Fase 7 — Relatório final e exportações

- gerar relatório robusto;
- armazenar em object storage;
- disponibilizar download autenticado.

## Fase 8 — Auth, quotas e hardening

- autenticação;
- limites por usuário;
- políticas antiabuso;
- auditoria;
- segurança final.

---

## 11.3 Ordem ideal de implementação

A ordem mais segura é:

1. persistência correta e jobs;
2. progresso em tempo real;
3. frontend shell novo;
4. fluxo correto de transporte e zonas;
5. histórico de imóveis;
6. relatório;
7. autenticação e monetização.

Não recomendo começar por pagamento ou por rewrite de stack.

---

# 12. Relatório final da zona — estrutura recomendada

O relatório precisa ser útil para decisão, não só bonito.

## Estrutura sugerida

## 1. Capa e resumo executivo
- zona analisada;
- data;
- origem considerada;
- ponto de transporte escolhido;
- resumo em 5 linhas.

## 2. Metodologia e parâmetros
- tipo de imóvel;
- raio da zona;
- tempo máximo de deslocamento;
- modal;
- critérios selecionados;
- datasets usados e datas.

## 3. Mapa síntese
- zona destacada;
- ponto principal;
- ponto de transporte;
- linhas relevantes;
- principais POIs.

## 4. Comparação da zona no contexto das demais
- ranking resumido;
- pontos fortes;
- pontos fracos;
- posição relativa em segurança, verde, alagamento, POIs.

## 5. Mobilidade
- tempo até transporte;
- linhas disponíveis;
- leitura prática de conectividade.

## 6. Análise urbana
- segurança;
- área verde;
- risco de alagamento;
- POIs por categoria.

## 7. Mercado imobiliário da zona
- preço médio atual;
- série histórica;
- dispersão de preço;
- principais imóveis encontrados.

## 8. Imóveis em destaque
- cards resumidos com menor preço do cluster;
- comparação entre anúncios duplicados;
- links.

## 9. Acessibilidade a pé
- melhor rota a POIs-chave;
- tempo até transporte.

## 10. Limitações da análise
- data dos datasets;
- observações sobre scraping;
- cobertura e restrições.

---

# 13. Pontos técnicos adicionais que você não citou e que são críticos

## 13.1 Segurança

- autenticação não é suficiente sem autorização por jornada;
- `journey_id` e `job_id` precisam ser privados por usuário/sessão;
- tokens externos nunca no cliente;
- URLs de relatório com assinatura e expiração;
- sanitização de logs;
- proteção contra path traversal e acesso indevido a artefatos.

## 13.2 Testes

### Quatro camadas obrigatórias

**1. Unitários de domínio** — `pytest`, sem dependências externas:
- lógica de cálculo de fingerprint;
- máquina de estados de `journeys` e `jobs`;
- regras de quota e plano;
- cálculo de badges e ranking de zonas;
- deduplicação de imóveis.

**2. Integração de adapters** — `pytest` + banco de testes real (Postgres/PostGIS em Docker):
- adapters de scraping com fixtures de HTML salvo (evita chamadas reais);
- adapter Valhalla com resposta mockada;
- adapter GTFS/OTP com feed de teste mínimo;
- pipeline de ingestão de vegetação (GeoSampa já disponível em `data_cache/`).

**3. Contrato API/frontend** — `pytest` + `httpx` (TestClient FastAPI):
- todos os endpoints com schema de request/response validados;
- cenários de erro (quota excedida, job não encontrado, plano insuficiente);
- autenticação e autorização por jornada.

**4. E2E da jornada real** — Playwright (já em uso no repositório como `e2e_smoke_dataset_a.ps1`):
- fluxo completo: ponto → transporte → zona → imóveis → relatório;
- cancelamento no meio do pipeline;
- retomada de jornada após desconexão SSE;
- usuário anônimo → cadastro → migração da jornada.

### Critério mínimo de cobertura

- unitários de domínio: 80% de cobertura de branches;
- integração: todos os adapters com pelo menos 1 fixture de happy path + 1 de erro;
- E2E: smoke do fluxo principal passa antes de qualquer merge na main.

### Repositório já tem

O `tests/` e `TEST_PLAN.md` do repositório são o ponto de partida. Os smoke tests existentes (`e2e_smoke_dataset_a.ps1`) validam `FINAL_COUNT > 0`, `BAD_COORDS = 0`, `BAD_STATE = 0` — esses critérios de qualidade de output devem ser preservados e expandidos na migração.

## 13.3 Acessibilidade

- o mapa não pode ser único canal de interação;
- seleção de zona também via lista;
- foco de teclado;
- contraste real de camadas;
- alternativas textuais para insights.

## 13.4 Concorrência e multiusuário

- locks por fingerprint de etapa;
- deduplicação de jobs idênticos;
- prevenção de scraping duplicado simultâneo;
- isolamento entre jornadas.

## 13.5 Auditoria

- registrar quem gerou relatório;
- qual dataset foi usado;
- quando foi processado;
- com quais parâmetros.

## 13.6 Compliance e governança de scraping

Esse ponto é sensível e precisa estar no radar desde já.

### Plataformas ativas

Os adapters de **QuintoAndar**, **Zap Imóveis** e **VivaReal** estão implementados. A restrição de plataforma por plano **não é uma limitação de implementação** — é uma restrição computacional e de produto:

- usuários gratuitos têm acesso a QuintoAndar + Zap Imóveis;
- usuários Pro têm acesso às três plataformas, incluindo VivaReal;
- a seleção de plataformas é feita pelo usuário no painel de busca, dentro do que o plano permite;
- plataformas bloqueadas pelo plano aparecem no painel com lock visual e CTA de upgrade.

O `config_hash` do lock de scraping e da chave de cache inclui a lista de plataformas selecionadas. Dois usuários buscando a mesma zona com configurações de plataforma diferentes geram caches separados — correto, porque os resultados são distintos.

Quando houver hit parcial por interseção e o cache disponível tiver sido gerado com menos plataformas que a busca atual, o badge deve indicar quais plataformas estão ausentes no preliminar: `"resultado preliminar — VivaReal ainda sendo consultado"`.

### Recomendações de compliance

- documentar claramente fonte por fonte;
- manter allowlist de plataformas como campo `platforms_allowed` na tabela `plans` — nunca hardcoded no código;
- revisar periodicamente os ToS de cada plataforma; QuintoAndar em particular tem histórico de ação legal contra scrapers;
- adotar backoff com jitter e pacing com limite de requisições por domínio por janela de tempo;
- user-agent realista e respeito a `robots.txt` como linha de base;
- preferir feeds/parcerias sempre que viável;
- guardar prova do dado observado, mas com retenção controlada;
- não construir estratégia dependente de scraping agressivo como único pilar comercial.

### Infraestrutura de scraping

As três plataformas atuais serão operadas, na versão alvo, por **browser automation com Playwright**, porque isso preserva o comportamento já validado no projeto atual e evita uma reengenharia prematura de sessão, cookies, tokens e fluxos renderizados. Portanto, a decisão fica fechada assim:

- **Playwright é o baseline operacional dos três scrapers atuais**;
- o scraping roda em **worker Dramatiq próprio no Hostinger VPS** (São Paulo), separado do worker geral;
- esse worker consome **somente** a fila `scrape_browser`;
- a concorrência inicial por processo é **1**;
- o worker geral da aplicação **não** executa browser automation.

### Modelo operacional sob carga

Playwright consome ~150–300MB de RAM por instância de Chromium. No VPS único com KVM 4 (16GB), o baseline continua sendo concorrência 1: 1 job de scraping por vez. `SCRAPE_BROWSER_CONCURRENCY = 1`. Concorrência mais alta entra apenas como escalação — depois de medir fila, memória e impacto sobre Valhalla/API.

**Impacto real do cache no volume de Playwright:**

| Situação | Playwright ativo |
|---|---|
| Sem prewarm, 20 usuários simultâneos | ~60 browsers (inviável) |
| Com prewarm orientado por endereços pesquisados nas últimas 24h | browsers concentrados apenas em endereços novos ou buscas Pro |
| Com alta repetição dos mesmos endereços | uso de browser cai drasticamente e o cache absorve a maior parte do tráfego FREE |

O cache pré-aquecido é o primeiro e mais eficaz nível de escala. O Playwright sob demanda fica restrito a: (a) usuários Pro buscando qualquer endereço elegível, e (b) usuários gratuitos ou Pro em endereços ainda não atualizados pelo prewarm baseado na demanda das últimas 24h.

**Escalonamento horizontal quando necessário:**

Quando `queue_depth(scrape_browser)` se mantiver consistentemente acima de 10 jobs aguardando: separar o `worker-scrape-browser` em VPS próprio (segundo KVM 2) ou aumentar a concorrência no VPS atual via upgrade de plano. As instâncias consomem a mesma fila Redis sem coordenação adicional.

### Topologia decidida

**Fase inicial — VPS único:**

- `api`, `worker-general`, `worker-scheduler`, `redis` e `postgres/postgis` na **Hostinger**
- `valhalla/otp` + `worker-scrape-browser` também na **Hostinger** na topologia inicial
- `bright-data` opcional apenas como provedor externo de proxy/unblocking

**Plano inicial do VPS único: KVM 4 (16GB RAM).** Concorrência de scraping: 1. O ponto não é maximizar paralelismo cedo, e sim preservar previsibilidade operacional.

**Fase de escalação — VPS separados (somente quando necessário):**

Separar em dois VPS quando houver evidência medida de que o Playwright está degradando a latência do Valhalla. Sinal concreto: `p95` de isócrona walking subindo acima de 500ms em horário de prewarm noturno.

- VPS 1: `api`, `worker-general`, `worker-scheduler`, PostgreSQL/PostGIS, Redis
- VPS 2: `valhalla/otp` + `worker-scrape-browser`, concorrência 1 (aumentar só quando houver folga medida)

**Por que Hostinger VPS para o scraping:**
IP de São Paulo é geograficamente esperado para usuários reais de QuintoAndar, Zap e VivaReal — plataformas brasileiras com base de usuários doméstica. IP estrangeiro pode ativar heurísticas de bot com mais facilidade por ser um padrão menos esperado. A Hostinger também simplifica pagamento em BRL e operação para um projeto solo no Brasil.

**Supervisor no VPS:** `systemd` com `Restart=always`. Deploy por `rsync` + `systemctl restart worker-scrape`. Sem dependência de ferramentas Hostinger no VPS.

```ini
# /etc/systemd/system/worker-scrape.service
[Unit]
Description=find-ideal-estate scrape worker
After=network.target

[Service]
User=deploy
WorkingDirectory=/opt/find-ideal-estate
EnvironmentFile=/opt/find-ideal-estate/.env
ExecStart=dramatiq workers.handlers     --queues scrape_browser     --processes 1 --threads 1
    # --threads = SCRAPE_BROWSER_CONCURRENCY (padrão: 1)
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Dockerfile do worker-scrape-browser:**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y     libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2     libdrm2 libxkbcommon0 libxcomposite1 libxdamage1     libxfixes3 libxrandr2 libgbm1 libasound2     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt --break-system-packages
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .
CMD ["dramatiq", "workers.handlers",      "--queues", "scrape_browser",      "--processes", "1", "--threads", "2"]
```

**Flags obrigatórias do Chromium em container:**

```python
class BaseScraper:
    async def _create_browser(self, p: Playwright) -> Browser:
        return await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",             # obrigatório em container
                "--disable-dev-shm-usage",  # /dev/shm padrão Docker = 64MB
                "--disable-gpu",            # sem GPU em VPS
                "--single-process",         # reduz RAM com concorrência baixa
            ],
            proxy={"server": settings.SCRAPER_PROXY_DEFAULT_URL}
            if settings.SCRAPER_PROXY_DEFAULT_URL else None,
        )
```

### Como o Playwright roda

A imagem do `worker-scrape-browser` deve incluir Playwright e browsers instalados. O job abre um contexto isolado por coleta, com timeout, captura de erro e encerramento explícito ao final. Nenhum outro tipo de job é executado nesse processo.

### Bright Data como escape hatch

Bright Data **não** substitui Hostinger e **não** é a arquitetura padrão. Ele entra apenas como escape hatch por plataforma quando houver degradação comprovada. A configuração é feita por variável de ambiente e chave por plataforma, sem alterar a topologia da aplicação.

```python
# settings.py
SCRAPER_PROXY_DEFAULT_URL: str | None = None
SCRAPER_PROXY_BY_PLATFORM: dict[str, str | None] = {
    "quintoandar": None,
    "zapimoveis": None,
    "vivareal": None,
}
SCRAPE_BROWSER_CONCURRENCY = 1  # aumentar somente ao escalar VPS
```

Regra operacional fechada:

- default: Playwright no `worker-scrape-browser`, sem proxy residencial;
- se uma plataforma cruzar o **limiar de degradação** (definido abaixo), habilitar Bright Data **somente** para ela;
- se a plataforma estabilizar, o proxy pode ser desligado;
- nenhuma plataforma usa Bright Data por padrão no início da operação.

### Limiar de degradação por plataforma

Uma plataforma é considerada degradada quando, em qualquer janela de 30 minutos, **duas ou mais** das seguintes condições forem verdadeiras:

- taxa de erro HTTP ≥ 30% (respostas 4xx/5xx ou timeout);
- taxa de resultado vazio ≥ 50% (scraping concluído mas zero imóveis retornados);
- latência mediana do job ≥ 3× a mediana histórica dos últimos 7 dias.

Quando o limiar for cruzado, o sistema registra em `scraping_degradation_events` e o alerta operacional é emitido. A ativação do Bright Data para aquela plataforma é manual — não automática — para evitar custo desnecessário por degradação momentânea.

```sql
scraping_degradation_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform        TEXT NOT NULL,
  detected_at     TIMESTAMPTZ NOT NULL,
  error_rate      NUMERIC,
  empty_rate      NUMERIC,
  latency_ratio   NUMERIC,
  proxy_enabled   BOOLEAN DEFAULT FALSE,
  resolved_at     TIMESTAMPTZ
)
```

### O que não fazer

- não rodar Playwright no `worker-general`;
- não compartilhar a fila de scraping browser com jobs de zonas, enriquecimento ou relatório;
- não introduzir VM dedicada de scraping como requisito da primeira versão;
- scraping HTTP (`httpx`) roda no Hostinger VPS quando implementado, em fila própria (`scrape_http`); fila `scrape_browser` continua dedicada a Playwright.

Playwright fica isolado em worker próprio na Hostinger. Bright Data é saída de contingência ativada manualmente por degradação medida, não base da infraestrutura.

## 13.7 SEO

SEO faz sentido para:

- landing pages públicas;
- páginas de conteúdo e comparação de regiões;
- páginas públicas de relatório compartilhável, se esse modelo existir.

Não é prioridade para o workspace autenticado do mapa.

## 13.8 Deploy

### Arquitetura de deploy decidida

**Vercel** para o frontend:

- Next.js App Router com deploy automático por push no GitHub;
- CDN global incluso sem configuração;
- Preview deployments por branch — cada PR gera uma URL de preview;
- Plano gratuito cobre a fase inicial completa. Vercel Pro (US$20/mês) apenas quando houver receita real que justifique.

**Hostinger** para toda a infraestrutura backend na fase inicial:

- 1 VPS KVM 4 com `api`, `worker-general`, `worker-scheduler`, PostgreSQL/PostGIS e Redis;
- Valhalla self-hosted e OpenTripPlanner 2 no mesmo ambiente;
- dados OSM/GTFS importados localmente;
- `worker-scrape-browser` (Dramatiq + Playwright + Chromium), fila exclusiva `scrape_browser`;
- supervisão por `systemd`, deploy por `rsync` + `systemctl restart`;
- Cloudflare R2 para relatórios e artefatos.

**Valhalla + OTP + Playwright no mesmo VPS — é seguro?**
Na fase inicial, sim, porque a operação foi desenhada para isso: scraping com concorrência 1, prewarm noturno, cache agressivo e reuso por fingerprint. A separação em dois VPS é a escalação natural quando os picos começarem a colidir — sinal concreto: `p95` de isócrona walking acima de 500ms em horários regulares, degradação perceptível da API ou crescimento sustentado da fila de scraping.

**Custo operacional da topologia inicial:**
- Vercel (frontend): gratuito na fase inicial;
- Hostinger KVM 4: principal custo fixo do backend;
- Bright Data: custo variável, desligado por padrão;
- Cloudflare R2: custo marginal no início.

A lógica financeira da arquitetura fica simples: **um único custo fixo principal na Hostinger** e promoção para dois VPS apenas quando a carga ou a receita justificarem.

**Escalação do scraping:** quando `queue_depth(scrape_browser)` se mantiver consistentemente acima de 10 jobs aguardando, separar o `worker-scrape-browser` em VPS próprio na Hostinger, mantendo a mesma fila Redis e sem alterar o desenho do sistema.

---

# 14. Recomendação final objetiva

## O que eu faria no seu lugar

### 1.
Eu **não** faria rewrite do backend de domínio para Node agora.

### 2.
Eu **não** adotaria SQLite como etapa intermediária.

### 3.
Eu reestruturaria o projeto como **monólito modular com Python + PostGIS + Redis + Dramatiq + SSE**, com Valhalla self-hosted para rotas e isócronas e MapLibre GL JS no frontend. Deploy em duas camadas: Vercel para frontend (gratuito) e Hostinger para toda a infraestrutura backend/geoespacial. A separação em dois VPS ocorre apenas quando houver degradação medida.

### 4.
Eu reescreveria o frontend em torno de um **map shell com painel por etapas**, mantendo o mapa vivo o tempo inteiro, com MapLibre sobre tiles MapTiler (gratuito na fase inicial).

### 5.
Eu manteria **POIs na Mapbox Search Box API**, porque isso já está provado no repositório e é parte do comportamento funcional atual. O que deve sair do centro não é a dependência em si, e sim o uso ingênuo sem cache, sem TTL, sem orçamento e sem encapsulamento. Valhalla + OTP + base local continuam resolvendo o núcleo de rotas, isócronas e dados geoespaciais próprios.

### 6.
Eu trataria o `run_id` atual como embrião da futura `journey`, migrando para persistência real e reaproveitamento por fingerprint.

### 7.
Eu colocaria histórico de imóveis, deduplicação e cache stale-while-revalidate por zona como parte do modelo de dados desde cedo, porque isso muda diretamente o valor do produto.

### 8.
Eu implementaria o modelo de acesso **anônimo com upgrade progressivo** desde o início: zero fricção na entrada, cadastro exigido apenas para baixar o relatório PDF. O plano gratuito com 2 análises/mês e o plano Pro com isócrona de carro e VivaReal precisam estar no schema desde a Fase 1 — não podem ser retrofitados depois sem retrabalho.

### 9.
Eu deixaria os três adapters de scraping (QuintoAndar, Zap, VivaReal) implementados, mas controlaria o acesso a VivaReal por plano — a restrição é computacional (mais jobs, mais cache, mais deduplicação), não artificial. O lock de VivaReal aparece no painel como CTA de upgrade no momento de maior engajamento do fluxo.

---

# 15. Conclusão

O projeto atual já contém o que mais importa: **domínio operacional e validação funcional**. O que falta não é “mais features”; é uma base arquitetural que permita transformar isso em produto de verdade.

A reformulação correta não é jogar tudo fora. É:

- preservar o conhecimento geoespacial já existente;
- trocar filesystem por modelo transacional de jornada e jobs;
- trocar polling simples por eventos de progresso reais;
- trocar frontend monolítico por shell modular centrado no mapa;
- trocar dependência excessiva de terceiros por dados locais versionados;
- trocar improviso operacional por observabilidade, cache, quotas e governança.

Se essa direção for seguida, o sistema passa a atender simultaneamente:

- o cenário pequeno de hoje;
- a evolução futura;
- o controle de custos;
- a experiência fluida que você quer;
- a robustez necessária para crescer sem reescrever tudo de novo.

---

# 16. Fontes externas consultadas

- Mapbox Pricing
- Mapbox Search Box API
- Mapbox Tilequery API
- Mapbox Static Images API
- Better Auth Installation
- Better Auth Database
- Better Auth Session Management
- Better Auth Security
- Mobility Database (mobilitydatabase.org) — feeds GTFS SP
- Bright Data — proxy residencial opcional para contingência de scraping
- WeasyPrint — gerador de PDF Python/CSS
- Stripe — mecanismo de pagamento
- fastapi-users — autenticação Python/FastAPI
- Dramatiq — sistema de filas Python
- shadcn/ui — componentes de UI React
- MapTiler — provedor de tiles base (tier gratuito)
- Valhalla — motor de roteamento e isócrona self-hosted

---

# 17. Histórico de versões

## Histórico resumido de revisão

As versões anteriores deste documento continham iterações intermediárias de infraestrutura (incluindo combinações com outros provedores e topologias de dois VPS como baseline). A versão atual consolida a decisão final para este projeto:

- **frontend no Vercel**;
- **backend, banco, Redis, geoespacial e scraping na Hostinger**;
- **topologia inicial com 1× VPS KVM 4**;
- **escala para 2 VPS apenas por contenção medida**;
- **Bright Data apenas como contingência por plataforma**.
