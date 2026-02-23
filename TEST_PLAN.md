# Plano Completo de Testes — MVP Imovel Ideal

Data: 2026-02-20
Escopo: validar cada parte da implementação do pipeline local (API, orquestração, adapters, consolidação, detalhamento, scraping, finalização e UI).

## 1) Objetivo do plano

Garantir que cada bloco funcional do MVP entregue resultado correto, reproduzível, seguro e com desempenho mínimo definido no PRD.

Critério de sucesso global:
- 100% dos testes críticos (P0) aprovados.
- Pipeline E2E smoke com taxa de sucesso $\ge 95\%$ em dados de referência fixos.
- Nenhum vazamento de credencial/segredo em logs e artifacts.

## 2) Mapa de componentes e cobertura

### Backend API
- [app/main.py](app/main.py)
- [app/schemas.py](app/schemas.py)

### Persistência e estado de execução
- [app/store.py](app/store.py)

### Orquestrador de pipeline
- [app/runner.py](app/runner.py)

### Adapters de scripts externos
- [adapters/candidate_zones_adapter.py](adapters/candidate_zones_adapter.py)
- [adapters/zone_enrich_adapter.py](adapters/zone_enrich_adapter.py)
- [adapters/streets_adapter.py](adapters/streets_adapter.py)
- [adapters/pois_adapter.py](adapters/pois_adapter.py)
- [adapters/listings_adapter.py](adapters/listings_adapter.py)

### Núcleo de lógica geoespacial e ranking
- [core/consolidate.py](core/consolidate.py)
- [core/zone_ops.py](core/zone_ops.py)
- [core/listings_ops.py](core/listings_ops.py)

### Segurança pública (SSP + CEM)
- [cods_ok/segurancaRegiao.py](cods_ok/segurancaRegiao.py)

### Frontend
- [ui/src/App.jsx](ui/src/App.jsx)

### Infra local
- [docker-compose.yml](docker-compose.yml)
- [docker/api.Dockerfile](docker/api.Dockerfile)
- [docker/ui.Dockerfile](docker/ui.Dockerfile)

## 3) Estratégia por nível de teste

1. Unitários (rápidos, determinísticos): funções puras e regras de negócio.
2. Integração (IO real local): leitura/escrita de arquivos, endpoints API, integração com dados em cache.
3. Contrato de adapters: argumentos corretos para subprocess e tratamento de erro.
4. E2E (pipeline): fluxo completo por `run_id` do início ao output final.
5. UI flow (browser automation): ações do usuário do botão 1 ao 6.
6. Segurança pública: coleta de ocorrências, comparativo região vs cidade e DPs mais próximas.
7. NFR: performance, resiliência, idempotência, segurança mínima.

## 4) Ambientes e dados de teste

### 4.1 Ambiente base
- Python com dependências de [requirements.txt](requirements.txt).
- UI com dependências de [ui/package.json](ui/package.json).
- Containers via [docker-compose.yml](docker-compose.yml).

### 4.2 Dataset controlado
- Reutilizar `data_cache` do projeto.
- Definir 2 conjuntos fixos de pontos:
  - Dataset A (smoke): 1 ponto de referência.
  - Dataset B (regressão): 2–3 pontos com zonas sobrepostas para validar consolidação.

### 4.3 Isolamento
- Cada execução em `runs/<run_id>` novo.
- Limpeza de artifacts entre execuções de teste de regressão.

### 4.4 Regra obrigatória para Playwright
- Qualquer etapa que use Playwright (direta ou indiretamente, ex.: `realestate_meta_search.py`) deve executar dentro do container `api` via Docker.
- Não executar Playwright no host local para validação oficial do plano.

## 5) Casos por componente

## 5.1 API (contrato + validação)

### Endpoints críticos
- `GET /health`, `GET /health/ready`
- `POST /runs`
- `GET /runs/{run_id}/status`
- `GET /runs/{run_id}/zones`
- `GET /runs/{run_id}/security`
- `POST /runs/{run_id}/zones/select`
- `POST /runs/{run_id}/zones/{zone_uid}/detail`
- `POST /runs/{run_id}/zones/{zone_uid}/listings`
- `POST /runs/{run_id}/finalize`
- `GET /runs/{run_id}/final/listings(.csv|.json)`

### Cenários
- Happy path completo.
- `run_id` inexistente retorna 404.
- Payload inválido em `RunCreateRequest` e `ZoneSelectionRequest` retorna 422.
- `finalize` sem seleção retorna 400.
- `zones`/`final` antes da etapa pronta retorna 404.

### Evidência
- Status code, corpo e schema conforme `pydantic`.
- Tempos médios e p95 para `status` e `zones` conforme NFR do PRD.

## 5.2 Store (`RunStore`)

### Cenários
- `create_run` cria diretórios, `status.json` e `input.json`.
- `run_id` contém timestamp + hash curto.
- `append_stage` adiciona histórico sem perder estados anteriores.
- `update_status` atualiza `updated_at`.
- `get_status` com run inexistente retorna `None`.

### Validações
- Formato ISO em timestamps.
- Integridade de arquivos JSON.

## 5.3 Runner (`run_pipeline`)

### Cenários
- Ordem de estágios: `validate` → `zones_by_ref` → `zones_enrich` → `zones_consolidate`.
- Falha em adapter interrompe pipeline e mantém rastreabilidade em status/log.
- Múltiplos `reference_points` geram `ref_0..n`.
- Etapa de segurança pública (quando habilitada no M1) executa sem quebrar o pipeline principal.

### Técnica
- Mock dos adapters para teste de ordem/chamadas.
- Integração real com scripts em smoke diário.

## 5.4 Adapters (subprocess contract)

Para cada adapter, validar:
- comando montado corretamente;
- parâmetros opcionais quando presentes;
- falha de subprocess propagada corretamente.

Arquivos alvo:
- [adapters/candidate_zones_adapter.py](adapters/candidate_zones_adapter.py)
- [adapters/zone_enrich_adapter.py](adapters/zone_enrich_adapter.py)
- [adapters/streets_adapter.py](adapters/streets_adapter.py)
- [adapters/pois_adapter.py](adapters/pois_adapter.py)
- [adapters/listings_adapter.py](adapters/listings_adapter.py)

## 5.5 Consolidação de zonas

Arquivo alvo: [core/consolidate.py](core/consolidate.py)

### Cenários
- Sem input enriquecido deve falhar com mensagem clara.
- Clusterização respeita `zone_dedupe_m`.
- `zone_uid` estável para mesmo centróide/buffer.
- `time_by_ref` usa mínimo por referência e `time_agg` usa máximo.
- CSV e GeoJSON de saída são gerados e consistentes.

## 5.6 Operações de zona

Arquivo alvo: [core/zone_ops.py](core/zone_ops.py)

### Cenários
- `haversine_m` com pares conhecidos (teste de precisão com tolerância).
- `get_zone_feature` encontra `zone_uid` e falha para ausente.
- `zone_centroid_lonlat` prioriza `centroid_lon/lat` quando disponível.
- `build_zone_detail` gera `streets.json`, `pois.json`, `transport.json`.
- Recorte de transporte limita por raio e ordena por distância.

## 5.7 Listings e finalização

Arquivo alvo: [core/listings_ops.py](core/listings_ops.py)

### Cenários
- `scrape_zone_listings` respeita `max_streets_per_zone`.
- `compiled_listings` copiado para destino final da rua.
- `finalize_run` gera:
  - `listings_final.json`
  - `listings_final.csv`
  - `listings_final.geojson`
  - `zones_final.geojson`
- Score de listing responde a pesos `w_price`, `w_transport`, `w_pois`.
- Listings sem coordenada são ignorados sem quebrar run.
- Listings sem endereço válido contendo tipo de logradouro brasileiro (ex.: `rua`, `avenida`, `alameda`, `travessa`, `estrada`, `rodovia`, `praça`) são ignorados na saída final.

## 5.8 Frontend (fluxo funcional)

Arquivo alvo: [ui/src/App.jsx](ui/src/App.jsx)

### Cenários
- Fluxo dos 6 botões em ordem.
- Filtro por `zone_uid`.
- Seleção múltipla de zonas.
- Renderização de cards de imóveis e mini-mapa.
- Links de export (GeoJSON/CSV/JSON) válidos quando final pronto.

### Automação
- Usar Playwright CLI para smoke UI diário:
  1) abrir UI,
  2) criar run,
  3) carregar zonas,
  4) selecionar zona,
  5) detalhar,
  6) buscar imóveis,
  7) finalizar,
  8) validar mensagem e presença de cards/export links.
- Observação obrigatória: quando o fluxo acionar scraping com Playwright, a API deve estar rodando em Docker (`docker compose up api`) para garantir paridade de ambiente.

## 5.9 Script E2E (API) — Dataset A (1 ponto)

Objetivo: executar o fluxo completo com 1 ponto inicial, selecionar 1 zona aleatória, e obter a saída final de imóveis.

Regras operacionais do smoke (M8):
- Selecionar **apenas 1 zona** por execução de `run_id`.
- Em caso de falha, repetir em novo `run_id` (não iterar várias zonas no mesmo run).
- Emitir logs de progresso por etapa (`create_run`, `wait_zones`, `select_zone`, `detail_zone`, `listings`, `finalize`, `validate_output`, `done`).

Ponto inicial (lat, lon): $(-23.585068145112295, -46.690640014541714)$

Script (PowerShell):

```powershell
$ApiBase = "http://localhost:8000"

# Pré-condição obrigatória: API em Docker (Playwright no container)
# Ex.: docker compose up -d api

$createBody = @{
  reference_points = @(
    @{
      name = "ref_0"
      lat  = -23.585068145112295
      lon  = -46.690640014541714
    }
  )
  params = @{}
}

$run = Invoke-RestMethod -Method Post -Uri "$ApiBase/runs" -ContentType "application/json" -Body ($createBody | ConvertTo-Json -Depth 5)
$runId = $run.run_id

# Aguarda zonas prontas (poll simples)
for ($i = 0; $i -lt 60; $i++) {
  try {
    $zones = Invoke-RestMethod -Method Get -Uri "$ApiBase/runs/$runId/zones"
    if ($zones -and $zones.features -and $zones.features.Count -gt 0) { break }
  } catch { }
  Start-Sleep -Seconds 5
}

# Seleciona 1 zona aleatória
$zoneUid = ($zones.features | Get-Random).properties.zone_uid
Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/zones/select" -ContentType "application/json" -Body (@{ zone_uids = @($zoneUid) } | ConvertTo-Json)

# Detalha e busca imóveis da zona
Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/zones/$zoneUid/detail"
Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/zones/$zoneUid/listings"

# Finaliza e baixa output final
Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/finalize"
$finalListings = Invoke-RestMethod -Method Get -Uri "$ApiBase/runs/$runId/final/listings.json"

# Exibe amostra da saída final
$finalListings | Select-Object -First 5
```

### Evidência
- `run_id` criado e status sem erro.
- Uma zona selecionada e detalhada.
- Saída final disponível em `/final/listings.json`.
- Amostra de 5 itens exibida.
- Logs por etapa com timestamp e `run_id` para acompanhamento do progresso e diagnóstico.

## 5.10 Docker e operação local

Arquivos alvo:
- [docker-compose.yml](docker-compose.yml)
- [docker/api.Dockerfile](docker/api.Dockerfile)
- [docker/ui.Dockerfile](docker/ui.Dockerfile)

### Cenários
- `api` sobe saudável (`/health`).
- `ui` acessa API via `VITE_API_BASE`.
- Volumes montados com permissão esperada (`data_cache` somente leitura).
- Reinício de containers preserva `runs/` e `cache/`.

## 5.11 Segurança pública (M1)

Arquivo alvo: [cods_ok/segurancaRegiao.py](cods_ok/segurancaRegiao.py)

### Cenários
- `run_query` retorna payload com chaves obrigatórias:
  - `ocorrencias_por_tipo_no_raio`
  - `comparativo_regiao_vs_cidade_sp`
  - `duas_delegacias_mais_proximas`
- `load_occurrences` prioriza Parquet em cache e reconstrói a partir de XLSX quando faltar coluna de município.
- `filter_occurrences_within_radius` aplica filtro vetorizado e retorna contagem consistente com o dicionário por delito.
- `build_regiao_vs_cidade_sp_comparativo` calcula `share_da_cidade` e `acima_media_pct` sem divisão inválida.
- `load_delegacias_from_cem` retorna delegacias com coordenadas válidas e `dp_num` coerente.
- Falha de rede/download em SSP/CEM gera erro rastreável sem expor segredo (`SSP_SECRET_KEY`) em logs.

### Evidência
- JSON de saída salvo em artifact por `run_id` (ex.: `runs/<run_id>/security/public_safety.json`).
- Log de etapa com duração e classificação de erro quando ocorrer falha.
- Amostra validada com ao menos 2 delegacias no campo `duas_delegacias_mais_proximas`.

## 6) Testes NFR (não funcionais)

## 6.1 Performance
- Medir p95 em:
  - `GET /runs/{run_id}/status` (meta: $<300ms$)
  - `GET /runs/{run_id}/zones` (meta: $<800ms$ para até 2.000 features)

## 6.2 Resiliência
- Falha de uma rua/plataforma no scraping não deve derrubar run inteiro.
- Timeouts de chamadas externas tratados com erro padronizado.

## 6.3 Idempotência
- Reexecutar finalização sem duplicar linhas de output.
- Reprocessar run com mesmo input sem corrupção de artifacts.

## 6.4 Segurança mínima
- Scan de logs/artifacts para segredos (`MAPBOX_ACCESS_TOKEN`, chaves, cookies).
- Verificar que erros não expõem payload sensível.

## 7) Matriz de prioridade

### P0 (bloqueia release)
- Criação de run, pipeline de zonas, consolidação, seleção, detalhamento, scraping mínimo, finalização, exports.
- Segurança pública integrada ao pipeline (payload mínimo + artifact persistido por `run_id`).

### P1
- Ranking e consistência de score, recorte de transporte, UX de filtro/seleção.

### P2
- Refinos visuais, mensagens secundárias e cenários raros.

## 8) Cadência recomendada

- A cada commit: unitários + contrato de adapters (rápido).
- Diário: smoke E2E local (API + UI).
- Pré-release: regressão completa + NFR + verificação de segurança.

## 9) Template de evidência por execução

Para cada suíte, registrar:
- Data/hora
- Commit/branch
- Dataset usado (A ou B)
- Resultado (pass/fail)
- Tempo de execução
- Artifacts (logs, screenshots UI, paths em `runs/<run_id>`)
- Ações corretivas abertas

## 10) Critério de aprovação final

A implementação está aprovada para uso local quando:
- todos os testes P0 passarem,
- smoke E2E atingir sucesso $\ge 95\%$ em 20 execuções consecutivas,
- NFR de latência cumprido,
- nenhuma evidência de vazamento de segredo em outputs/logs.
