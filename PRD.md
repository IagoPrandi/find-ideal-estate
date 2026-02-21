# PRD (MVP Local) — Imóvel Ideal (Integrado aos scripts)
**Mapa → Pontos de referência → Zonas (ônibus+trem/metrô) → Enriquecimento (alagamento+verde) → Consolidação multi-ponto → Seleção de zonas → Ruas+POIs+Transporte → Imóveis por rua → Distâncias + Ranking → Output final (lista de imóveis + contexto da região)**

**Versão:** 1.3  
**Data:** 2026-02-20  
**Execução:** Local (sem deploy online nesta fase)

> os códigos python citados ao longo do documento estão na pasta **cods_ok**

---
## Progress Tracker

- 2026-02-20 — Revisão de qualidade/usabilidade/segurança aplicada ao PRD (v1.3).
- 2026-02-20 — Documentos obrigatórios abertos: `PRD.md`, `BEST_PRACTICES.md`, `skills_README.md`.
- 2026-02-20 — Skill utilizada (primária): `security-threat-checklist`.
- 2026-02-20 — M0 implementado (estrutura base, Docker, `.env.example`).
- 2026-02-20 — Skill utilizada (primária): `release-config-management`.
- 2026-02-20 — M1 implementado (FastAPI `/runs` + status, store, runner básico).
- 2026-02-20 — Skill utilizada (primária): `security-threat-checklist`.
- 2026-02-20 — M2 implementado (adapters zones + enrich, artifacts por ref).
- 2026-02-20 — M3 implementado (consolidação de zonas + endpoint `/runs/{run_id}/zones`).
- 2026-02-20 — Skill utilizada (primária): `security-threat-checklist`.
- 2026-02-20 — M4 implementado (UI de zonas: lista, filtro, seleção múltipla e ação de detalhamento).
- 2026-02-20 — M5 implementado (adapters de ruas/POIs + recorte de transporte por zona).
- 2026-02-20 — M6 implementado (adapter de scraping por rua com limites e cache por `street_slug`).
- 2026-02-20 — M7 implementado (distâncias, score, exports finais e UI de cards/mapa/export).
- 2026-02-20 — Skill utilizada (primária): `develop-web-game`.
- 2026-02-20 — Skill utilizada (primária): `playwright`.
- 2026-02-20 — Plano completo de testes criado para validar cada parte da implementação (unitário, integração, E2E, NFR e segurança).
- 2026-02-20 — Execução de testes baseada no TEST_PLAN concluída (componentes, contratos de adapters, integração smoke, build/UI smoke, NFR smoke e validação de compose).
- 2026-02-20 — Script E2E (Dataset A) executado; identificado bloqueio em `zones_enrich` por `TopologyException` (geometria inválida) e aplicado ajuste no adapter de zonas para `--seed-bus-coord=<lat,lon>`.
- 2026-02-20 — Regra operacional definida: qualquer fluxo que use Playwright deve rodar via Docker (`api` container), não no host local.
- 2026-02-20 — E2E Dataset A concluído com sucesso em Docker (`RUN_ID=20260221032857_47f4384b`, `FINAL_COUNT=413`) após correções de robustez em adapters/listings/finalização e tratamento de geometrias inválidas no enriquecimento.


## 0) Objetivo do MVP (o que o usuário consegue fazer)
Rodando 100% local, o usuário:

1. Marca **1+ pontos de referência** no mapa (ex.: “Trabalho”, “Faculdade”, “Metrô X”).
2. O sistema gera **zonas candidatas** (buffers) alcançáveis por **ônibus** (GTFS) e por **trilhos** (GeoSampa).
3. As zonas são **enriquecidas** com métricas de **alagamento** e **área verde**.
4. O sistema **consolida** zonas duplicadas geradas por múltiplos pontos de referência.
5. O usuário seleciona 1 / várias / todas as zonas.
6. Para cada zona selecionada, o sistema coleta:
   - **ruas** (Mapbox Tilequery),
   - **POIs por categoria** (Mapbox Search Box Category),
   - **paradas de ônibus e estações** (cache local),
   - **imóveis por rua** (meta scraping: QuintoAndar + VivaReal).
7. Cada imóvel é enriquecido com:
   - **preço, área (m²), endereço, quartos, banheiros, vaga** (quando disponíveis),
   - **distâncias** até transporte e POIs.
8. Entrega final:
   - ranking de zonas,
   - ranking de imóveis por zona,
   - **lista final de imóveis com informações do imóvel e da região**, exportável (CSV/JSON) e visual no mapa.

**Fora do MVP:** login/multiusuário, monetização, compartilhamento, deploy, atualização automática do `data_cache`.

---

## 1) A visão “produto”: o que é “região” neste MVP
Para um imóvel, “região” = contexto mensurável ao redor do imóvel e da zona:
- **risco/impacto**: alagamento (área/ratio em buffer) e área verde (área/ratio em buffer),
- **infra de transporte**: distância ao ponto de ônibus e à estação mais próximos,
- **serviços**: proximidade a POIs por categoria (mercado, farmácia, parque, restaurante, academia etc.),
- **acessibilidade aos pontos de referência**: tempo/score da zona por ponto de referência (e agregado).

---

## 2) Escopo do MVP (local)

### 2.1 Dentro
- UI web local com mapa (Mapbox GL JS).
- Backend local (FastAPI) orquestrando scripts, consolidação, distâncias e ranking.
- Persistência por arquivos (`runs/`), com cache de respostas externas.
- Execução em etapas com status e logs por `run_id`.

### 2.2 Fora
- Deploy online, multiusuário, auth, pagamentos, alertas.
- Atualização automática de GTFS/GPKG (manual nesta fase).

### 2.3 Requisitos não-funcionais (NFR) do MVP
- **Confiabilidade:** taxa de sucesso do pipeline E2E (smoke) ≥ 95% com dados de teste fixos.
- **Performance API:**
  - `GET /runs/{run_id}/status` com p95 < 300ms.
  - `GET /runs/{run_id}/zones` com p95 < 800ms para até 2.000 features consolidadas.
- **Resiliência:** retries com backoff apenas em chamadas externas idempotentes (Mapbox/scraping), com limite e jitter.
- **Idempotência:** reexecução do mesmo `run_id` não duplica artifacts finais.
- **Observabilidade mínima:** logs estruturados por etapa com `run_id` e erro classificado.
- **Segurança:** nenhuma credencial em código, logs ou artifacts exportados.

---

## 3) Dependências e insumos (o que precisa existir localmente)

### 3.1 Data cache local (obrigatório)
Estrutura mínima:
- `data_cache/gtfs/*.txt` (stops, trips, stop_times, frequencies…)  
- `data_cache/geosampa/*.gpkg` com:
  - estações/linhas (metrô/trem),
  - mancha de inundação,
  - vegetação significativa (verde).

### 3.2 Chaves/API (obrigatório)
- `MAPBOX_ACCESS_TOKEN` (usado por ruas e POIs)

### 3.3 Navegação automatizada (meta scraping)
- Playwright instalado e navegadores baixados (requisito do `realestate_meta_search.py`).
- Rodar em modo `headless` por padrão; fallback manual se bloqueios.

### 3.4 Docker (infra local padronizada)
- **Docker Desktop / Docker Engine** instalado.
- Execução recomendada via **Docker Compose** (API + UI), mantendo o host “limpo” de dependências.
- Variáveis em `.env` (ex.: `MAPBOX_ACCESS_TOKEN`).
- Volumes montados:
  - `./data_cache:/app/data_cache:ro` (dados GTFS/GPKG)
  - `./runs:/app/runs` (artefatos do pipeline)
  - `./cache:/app/cache` (cache de Mapbox/geocode)
  - `./profiles:/app/profiles` (perfil persistente do navegador para o VivaReal, opcional)
- Observação: o meta scraping usa Playwright; a imagem do **serviço API** deve incluir **deps de navegador**.

---

## 4) Componentes e responsabilidades (arquitetura local)

### 4.1 Frontend (UI local)
- Seleciona pontos no mapa.
- Mostra:
  - zonas (polígonos),
  - pins de POIs, ônibus e estações,
  - cards de imóveis e ranking.
- Acompanha progresso por `run_id` (polling).

### 4.2 Backend (orquestrador)
Responsável por:
- executar scripts existentes (subprocess) com parâmetros consistentes,
- consolidar zonas multi-ponto (criar `zone_uid`),
- coletar ruas/POIs/transporte por zona,
- executar meta scraping por rua,
- compilar e enriquecer imóveis,
- calcular distâncias e score final,
- exportar outputs finais (CSV/JSON + GeoJSON).

### 4.3 Scripts existentes (não mudar lógica; apenas “wrap”)
- Zonas: `candidate_zones_from_cache_v10_fixed2.py`
- Enriquecimento: `zone_enrich_green_flood_v3.py`
- Ruas: `encontrarRuasRaio.py`
- POIs: `pois_categoria_raio.py`
- Meta scraping: `realestate_meta_search.py` + parsers `quintoAndar.py`, `vivaReal.py`

### 4.4 Infraestrutura com Docker (topologia local)
**Objetivo:** rodar o MVP com um comando, com dependências previsíveis.

**Serviços (Docker Compose):**
- `api`: FastAPI + orquestrador + scripts + Playwright (scraping).
- `ui`: frontend (Mapbox GL) consumindo a API.

**Rede e portas (default):**
- UI: `http://localhost:5173`
- API: `http://localhost:8000`

**Persistência:** volumes para `runs/`, `cache/`, `profiles/` e mount do `data_cache/`.

---

## 5) Fluxo integrado (E2E) — regras, entradas e saídas

### 5.1 Entidade central: `Run`
Tudo acontece dentro de um `run_id`, determinístico e “replayável”.

**run_id** = timestamp + hash curto dos pontos e principais parâmetros.  
**Diretório**: `runs/<run_id>/`

---

### 5.2 Etapa A — Pontos de referência → Zonas por ponto (rodadas independentes)
**Por que?** O script de zonas trabalha com uma seed por execução. Logo: 1 ponto de referência = 1 execução.

Para cada `reference_point[i]`:
1) executar `candidate_zones_from_cache_v10_fixed2.py`  
2) salvar artifacts em:
```
runs/<run_id>/zones/by_ref/ref_<i>/raw/outputs/
  zones.geojson
  ranking.csv
  trace.json
```

---

### 5.3 Etapa B — Enriquecimento por ref (alagamento + verde)
Para cada ref:
1) executar `zone_enrich_green_flood_v3.py` apontando para o `raw/outputs`  
2) salvar em:
```
runs/<run_id>/zones/by_ref/ref_<i>/enriched/
  zones_enriched.geojson
  ranking_enriched.csv
```

---

### 5.4 Etapa C — Consolidação multi-ponto (cria o “catálogo de zonas” do run)
**Solução do MVP:** gerar `zone_uid` via cluster espacial dos centróides.
1) juntar todas as features `zones_enriched.geojson` (todas as refs)
2) converter centroid para UTM (EPSG:31983)
3) clusterizar por proximidade (DBSCAN ou greedy) com `eps = zone_dedupe_m` (ex.: 50m)
4) para cada cluster:
   - `zone_uid = sha256(round(cx,1m)+round(cy,1m)+buffer_m)[:16]`
   - `zone_geom`: escolher a geometria do melhor score do cluster
   - tempos:
     - `time_by_ref[ref_i] = min(travel_time_from_seed_minutes no cluster)`
     - `time_agg` = `max(time_by_ref)` (default)

Artifacts:
```
runs/<run_id>/zones/consolidated/
  zones_consolidated.geojson
  zones_consolidated.csv
```

---

### 5.5 Etapa D — Seleção de zonas (UI)
UI carrega `zones_consolidated.geojson` e lista ordenada.

---

### 5.6 Etapa E — Detalhar zona (ruas + POIs + transporte)
Para cada `zone_uid` selecionada:

**E1) Ruas**
- executar `encontrarRuasRaio.py` usando centroid da zona
- salvar:
```
runs/<run_id>/zones/detail/<zone_uid>/streets.json
```

**E2) POIs**
- executar `pois_categoria_raio.py` usando centroid da zona
- salvar:
```
runs/<run_id>/zones/detail/<zone_uid>/pois.json
```

**E3) Transporte (cache local)**
- carregar paradas/estações do `data_cache` e recortar
- salvar:
```
runs/<run_id>/zones/detail/<zone_uid>/transport.json
```

---

### 5.7 Etapa F — Imóveis por rua (meta scraping) + padronização
Para cada rua (até `max_streets_per_zone`):
- executar `realestate_meta_search.py all`
- salvar por rua:
```
runs/<run_id>/zones/detail/<zone_uid>/streets/<street_slug>/listings/
  compiled_listings.json
  compiled_listings.csv
  (subpastas das plataformas + logs)
```

---

### 5.8 Etapa G — Output final (o que faltava): enriquecer e rankear imóveis
Para cada listing completo:
- distâncias até transporte e POIs (Haversine)
- anexar contexto da zona (alagamento/verde + tempo)
- calcular `score_listing`

Artifacts finais:
```
runs/<run_id>/final/
  listings_final.json
  listings_final.csv
  listings_final.geojson
  zones_final.geojson
```

### 5.9 Regras operacionais (idempotência, timeout e falha parcial)
- Cada etapa grava `status.json` local (`pending|running|success|failed`) com timestamps.
- Cada chamada externa deve ter timeout explícito e erro padronizado por categoria.
- Falhas por rua/plataforma não derrubam o run inteiro; a execução continua com degradação controlada.
- Reprocessamento deve reaproveitar cache e sobrescrever artifact da mesma etapa sem duplicar linhas finais.
- `run_id` é a chave de correlação de logs, métricas e artifacts.

---

## 6.1) Docker — como rodar o MVP localmente (recomendado)

### Estrutura sugerida do repo
```
.
├─ app/                      # backend (FastAPI)
├─ ui/                       # frontend (Vite/React)
├─ adapters/                 # wrappers p/ scripts (subprocess)
├─ core/                     # consolidação, distâncias, ranking, schemas
├─ data_cache/               # GTFS + GPKG (montado como read-only)
├─ runs/                     # outputs por run_id (volume)
├─ cache/                    # cache Mapbox/geocode (volume)
├─ profiles/                 # perfil persistente (VivaReal) (volume opcional)
├─ docker/
│  ├─ api.Dockerfile
│  └─ ui.Dockerfile
├─ docker-compose.yml
└─ .env
```

### `docker-compose.yml` (base)
```yaml
services:
  api:
    build:
      context: .
      dockerfile: docker/api.Dockerfile
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - ./data_cache:/app/data_cache:ro
      - ./runs:/app/runs
      - ./cache:/app/cache
      - ./profiles:/app/profiles
    shm_size: "1gb"   # evita crash do Chromium (Playwright)
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

  ui:
    build:
      context: .
      dockerfile: docker/ui.Dockerfile
    environment:
      - VITE_API_BASE=http://localhost:8000
    ports:
      - "5173:5173"
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

networks:
  default:
    name: imovel-ideal
```

### `docker/api.Dockerfile` (com Playwright)
> Sugestão: base da Microsoft Playwright para reduzir dor com dependências.

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Dependências Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY app ./app
COPY core ./core
COPY adapters ./adapters
COPY *.py ./

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
```

### `docker/ui.Dockerfile` (Vite)
```dockerfile
FROM node:20-alpine
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui ./
EXPOSE 5173
```

### Como rodar
```bash
docker compose up --build
```

### Observações práticas (scraping)
- Se algum site bloquear o headless, manter um modo `headful` como fallback (por flag/config) e/ou usar o diretório `profiles/` para cookies persistentes.
- Se o Chromium ficar instável, aumentar `shm_size` e reduzir paralelismo (número de ruas/plataformas em paralelo).

---

## 6) Fluxograma visual (processo completo)

```mermaid
flowchart TD
  A[UI: usuário marca pontos de referência] --> B[Backend: cria run_id e pasta runs/run_id]
  B --> C{Para cada ponto de referência}
  C --> D[Zonas: candidate_zones_from_cache<br/>-> zones.geojson + ranking.csv + trace.json]
  D --> E[Enriq: zone_enrich_green_flood<br/>-> zones_enriched.geojson + ranking_enriched.csv]
  E --> F[Backend: juntar zonas de todas refs]
  F --> G[Backend: consolidar zonas (cluster) -> zone_uid]
  G --> H[UI: mostra zonas consolidadas + ranking]
  H --> I{Usuário seleciona zonas}
  I --> J[Ruas: encontrarRuasRaio (Tilequery) -> streets.json]
  I --> K[POIs: pois_categoria_raio (SearchBox) -> pois.json]
  I --> L[Transporte: cache local -> transport.json]
  J --> M{Para cada rua (limitada)}
  M --> N[Imóveis: realestate_meta_search all<br/>-> compiled_listings.csv/json]
  N --> O[Backend: enriquecer listings<br/>(distâncias + contexto da zona)]
  O --> P[Export final<br/>listings_final.csv/json/geojson]
  P --> Q[UI: mapa + cards + export]
```

---

## 7) Plano de implementação (milestones + checkboxes)

### M0 — Base do repositório, Docker e configuração local
- [x] Estrutura de pastas (`runs/`, `data_cache/`, `app/`, `core/`, `adapters/`, `docker/`, `ui/`)
- [x] `.env` (MAPBOX_ACCESS_TOKEN e configs)
- [x] `docker-compose.yml` + `docker/api.Dockerfile` + `docker/ui.Dockerfile`
- [x] Volumes montados (`data_cache` read-only; `runs/cache/profiles` persistentes)
- [x] Scripts executam **no container** com paths corretos

### M1 — Orquestrador (backend) e artifacts
- [x] FastAPI com `/runs` (create), `/runs/{run_id}/status`
- [x] Camada `store` (criar run, gravar artifacts, logs)
- [x] Runner (ThreadPool/asyncio) com etapas encadeadas

### M2 — Zonas por ponto de referência
- [x] Adapter: `candidate_zones_from_cache...`
- [x] Adapter: `zone_enrich_green_flood...`
- [x] Persistir artifacts por `ref_<i>`

### M3 — Consolidação multi-ponto (zone_uid)
- [x] Clustering por centróide (UTM 31983)
- [x] `zones_consolidated.geojson` + CSV
- [x] Endpoint `/runs/{run_id}/zones`

### M4 — UI: exibir zonas e selecionar
- [x] Render polígono + lista
- [x] Filtros e seleção múltipla
- [x] Ação “Detalhar zonas selecionadas”

### M5 — Detalhe de zona: ruas + POIs + transporte
- [x] Adapter: `encontrarRuasRaio.py` + cache
- [x] Adapter: `pois_categoria_raio.py` + cache
- [x] Transporte do `data_cache` com recorte

### M6 — Imóveis por rua e padronização
- [x] Adapter: `realestate_meta_search.py all`
- [x] Limites (N zonas / N ruas / N páginas)
- [x] Cache por `street_slug`

### M7 — Output final: enriquecer e rankear imóveis
- [x] Distâncias (Haversine)
- [x] Score do imóvel (price/transit/pois)
- [x] Export `listings_final.csv/json/geojson`
- [x] UI: cards + mapa + export

### M8 — Testes E2E e DoD
- [ ] Smoke test: 1 ponto → zonas → 1 zona → 1 rua → imóveis → export
- [ ] Logs por run com erro por etapa
- [ ] README “como rodar”

### Critérios objetivos de aceite por milestone (complementar)
- **M0:** `docker compose up --build` sobe UI+API e health checks retornam OK.
- **M1:** criação de `run_id` + persistência de logs/artifacts por etapa validada por teste de integração.
- **M2:** para 1 ponto, existem artifacts `raw` e `enriched` com contagem de features > 0.
- **M3:** deduplicação gera `zone_uid` estável para mesma entrada e parâmetros.
- **M4:** usuário seleciona múltiplas zonas e a seleção persiste entre refreshes do estado da tela.
- **M5:** `streets.json`, `pois.json` e `transport.json` são gerados por zona selecionada.
- **M6:** ao menos 1 rua retorna `compiled_listings` padronizado sem quebra de schema.
- **M7:** `listings_final` contém score e explicação dos fatores por imóvel.
- **M8:** cenário smoke automatizado passa e gera exports finais válidos.

---

## 8) Definição de pronto (DoD)
O MVP está pronto quando:
- a partir de pontos de referência, o sistema gera e consolida zonas,
- uma zona selecionada produz ruas + POIs + transporte,
- pelo menos 1 rua retorna imóveis padronizados,
- o sistema gera **listings_final.csv/json/geojson** com:
  - dados do imóvel,
  - dados da região (POIs + transporte),
  - dados da zona (alagamento/verde + tempo),
  - score e ranking.

Além disso, para considerar pronto:
- nenhuma credencial exposta em código/logs/artifacts;
- erros críticos rastreáveis por `run_id` com causa e etapa;
- documentação mínima de execução e recuperação de falhas publicada.

---

## 9) Segurança (obrigatório no MVP)

### 9.1 Threat model mínimo (por mudança de superfície)
Documentar para cada mudança relevante:
1. ativos protegidos (token Mapbox, disponibilidade, integridade do ranking, dados de imóveis);
2. entrypoints (API, subprocess wrappers, leitura de cache, scraping);
3. atores (usuário, operador local, atacante externo, site-alvo com anti-bot);
4. fronteiras de confiança (UI→API, API→scripts, API→Mapbox, API→filesystem);
5. top 3 ameaças + mitigação.

### 9.2 Requisitos de segurança aplicáveis
- Validação estrita de payload (schema) em todos os endpoints.
- Sanitização de parâmetros usados em subprocess (allowlist de comandos/flags).
- Normalização de caminhos para bloquear path traversal em `runs/`.
- Segredo apenas via `.env`/runtime; proibido hardcode de tokens.
- Logs com redaction (sem token, sem payload sensível completo).
- CORS restritivo no backend local (origens explicitamente permitidas).
- Rate limit para endpoints custosos (`/runs`, detalhamento por zona, scraping).

### 9.3 Gating mínimo antes de fechar milestone de superfície
- Scan de segredos (ex.: gitleaks) sem findings críticos.
- SCA de dependências sem vulnerabilidade crítica aberta.
- SAST básico sem issue crítica explorável.
- Testes de regressão dos fluxos alterados.

---

## 10) Usabilidade e acessibilidade
- Estados de UI obrigatórios: carregando, vazio, parcial, erro recuperável, erro fatal.
- Cada etapa longa exibe progresso por percentual/contador e ETA aproximada.
- Mensagens de erro sempre acionáveis (“o que ocorreu” + “como corrigir”).
- Explicação do score por imóvel (fatores e pesos) visível no card/detalhe.
- Acessibilidade mínima: navegação por teclado e contraste adequado para camadas no mapa.

---

## 11) Observabilidade e runbook operacional
- Logs estruturados (JSON) com `service`, `run_id`, `zone_uid`, `stage`, `duration_ms`, `error_code`.
- Health endpoints:
  - `/health` (liveness)
  - `/health/ready` (readiness: acesso a cache/runs e dependências mínimas)
- Métricas mínimas:
  - latência e taxa de erro por endpoint;
  - duração por etapa do pipeline;
  - contagem de retries/timeouts externos.
- Runbook mínimo com ações para: timeout Mapbox, bloqueio de scraping, falta de dados no cache, falha de consolidação.

---

## 12) Governança de dados e retenção
- `runs/`: retenção padrão de 30 dias (configurável), com rotina de limpeza.
- `cache/`: retenção de 7 dias para respostas externas (configurável por fonte).
- `profiles/`: uso opcional e local; nunca versionar em git.
- Export final não deve conter credenciais nem metadados sensíveis de execução.

---

## 13) Estratégia de testes e qualidade
- **Unitários:** normalização de dados, score, distância Haversine, geração de `run_id`.
- **Integração:** adapters (scripts) + store de artifacts + consolidação.
- **E2E smoke:** 1 ponto → zonas → seleção 1 zona → 1 rua → export final.
- **Teste de idempotência:** reprocessar mesmo `run_id` sem duplicação.
- **Teste de tolerância:** falha de uma plataforma de scraping sem abortar todo run.

---

## 14) Gestão de configuração e reprodutibilidade
- Definir schema do `.env` com obrigatórios/opcionais e validação no startup.
- Fixar versões de dependências e usar lockfile.
- Docker com tags fixas e build reproduzível.
- Configurações sensíveis separadas por ambiente (local/staging futuro).

---

## 15) Score explicável e versionado
- O cálculo de score deve ter versão explícita (`score_listing_v1`).
- Pesos e fórmula devem estar em configuração auditável.
- Output final deve incluir:
  - score total,
  - contribuição por fator (preço, transporte, POIs, risco/alagamento, verde),
  - versão da fórmula utilizada.
