# PRD Técnico — Agente de IA do Find Ideal Estate

**Projeto:** Find Ideal Estate
**Baseado em:** `PRD.md` v2.2 e estado atual do repositório
**Data de revisão:** 2026-04-25
**Status:** Revisado — pronto para iniciar M0

---

## Índice

1. [Contexto e visão](#1-contexto-e-visão)
2. [Alinhamento com o projeto atual — gap analysis](#2-alinhamento-com-o-projeto-atual--gap-analysis)
3. [Decisões de escopo fechadas](#3-decisões-de-escopo-fechadas)
4. [Usuários-alvo e casos de uso](#4-usuários-alvo-e-casos-de-uso)
5. [Requisitos funcionais](#5-requisitos-funcionais)
6. [Requisitos não funcionais](#6-requisitos-não-funcionais)
7. [Estrutura do módulo no backend existente](#7-estrutura-do-módulo-no-backend-existente)
8. [Skills do agente e enum de intents](#8-skills-do-agente-e-enum-de-intents)
9. [Memória](#9-memória)
10. [Harness engineering](#10-harness-engineering)
11. [Modelo de dados adicional](#11-modelo-de-dados-adicional)
12. [Contratos das tools](#12-contratos-das-tools)
13. [Orquestração técnica](#13-orquestração-técnica)
14. [Políticas de ranking](#14-políticas-de-ranking)
15. [Integração com créditos existentes](#15-integração-com-créditos-existentes)
16. [Segurança e guardrails](#16-segurança-e-guardrails)
17. [Camada multi-provider LLM e BYOK](#17-camada-multi-provider-llm-e-byok)
18. [Milestones](#18-milestones)
19. [Roadmap por ondas](#19-roadmap-por-ondas)
20. [Critérios de sucesso](#20-critérios-de-sucesso)
21. [Questões resolvidas e decisões registradas](#21-questões-resolvidas-e-decisões-registradas)

---

## 1. Contexto e visão

### 1.1 Estado atual do produto

O Find Ideal Estate já possui o núcleo analítico completo:

- jornada guiada por endereço de referência;
- geração de zonas por isócrona (transit, walking, car) com Valhalla + OTP;
- enriquecimento urbano com segurança, verde, alagamento e POIs via Mapbox;
- scraping e deduplicação de imóveis (QuintoAndar, Zap, VivaReal);
- dashboard com preço, histórico e comparação de zonas;
- autenticação email/senha com sessão HTTP-only;
- favoritos de imóveis (`user_listing_favorites`) e de zonas (`user_zone_favorites`);
- créditos por operação com ledger auditável;
- SSE granular com reconexão via `Last-Event-ID`.

### 1.2 O que falta para o agente

O agente não é apenas uma interface conversacional sobre o que já existe. Requer:

1. memória persistente de destinos nomeados do usuário;
2. facts analíticos materializados em nível de imóvel (benchmark, mobilidade, POI);
3. tools determinísticas internas que o LLM chama para calcular respostas;
4. harness de orquestração: parse → contexto → plano → execução → verificação → resposta;
5. camada de eficiência de tokens: caching de prompt, roteamento por modelo, paralelismo de tools;
6. SSE do agente seguindo o mesmo padrão SSE já implementado no produto;
7. camada multi-provider para não amarrar o produto a um único vendor de LLM.

### 1.3 Visão

Criar um **copiloto imobiliário conversacional e explicável** que permita ao usuário consultar, comparar, ranquear e interpretar imóveis e zonas com base em critérios de rotina real, preço e contexto urbano.

**Princípio central:** o LLM interpreta, decompõe, planeja, chama tools e redige a resposta. Quem calcula números é o backend determinístico. O LLM nunca inventa métricas.

### 1.4 Exemplos de perguntas-alvo

- "Quais imóveis salvos custam menos de R$ 2.000 e ficam a menos de 30 minutos de ônibus do meu trabalho?"
- "Qual imóvel salvo tem a melhor relação de preço e segurança abaixo de R$ 2.500?"
- "Esse imóvel salvo está quanto abaixo da média do bairro?"
- "Quais dos meus imóveis salvos têm mais linhas de ônibus para chegar ao trabalho?"
- "Compare minhas zonas salvas e diga quais 2 fazem mais sentido para morar perto do trabalho."

---

## 2. Alinhamento com o projeto atual — gap analysis

### 2.1 O que já existe e o agente pode usar diretamente

| Recurso existente | Tabela / módulo | Como o agente usa |
|---|---|---|
| Imóveis salvos | `user_listing_favorites` | escopo principal de consulta; `listing_key` é a chave opaca |
| Zonas salvas | `user_zone_favorites` | escopo de comparação; `zone_fingerprint` = `zones.fingerprint` |
| Dados de enriquecimento de zona | `zones` (`green_area_m2`, `flood_area_m2`, `safety_incidents_count`, `badges`) | `GetZoneFactsTool` lê direto |
| Imóveis e snapshots | `properties` + `listing_ads` + `listing_snapshots` | base para `listing_agent_facts` |
| Auth + sessão | `users` + `user_sessions` | agente rejeita requests não autenticados |
| Créditos | `user_credits` + `credit_ledger` | `CreditsPolicyTool` consulta; novos `CreditOperation` adicionados |
| SSE | Redis pub/sub + `job_events` | agente emite eventos no mesmo canal; schema novo definido na seção 10.7 |
| Módulo de módulos | `apps/api/src/modules/` | agente vive em `modules/agent/` |

### 2.2 O que ainda não existe e precisa ser construído

| Componente | Tabela / módulo | Milestone |
|---|---|---|
| Destinos nomeados do usuário | `saved_destinations` (nova) | M1 |
| Preferências declaradas do agente | `user_agent_preferences` (nova) | M1 |
| Sessões e mensagens do agente | `agent_chat_sessions` + `agent_chat_messages` (novas) | M1 |
| Log estruturado de execução | `agent_query_logs` (nova) | M1 |
| Facts materializados por imóvel | `listing_agent_facts` (nova) | M2 |
| Benchmark de mercado por escopo | `market_benchmark_snapshots` (nova) | M2 |
| Comparações salvas | `saved_comparisons` (nova) | M2 |
| Facts de POI por imóvel | `listing_poi_facts` (nova) | M3 |
| Facts de mobilidade imóvel → destino | `listing_destination_commute_stats` (nova) | M4 |
| Tool layer determinístico | `modules/agent/tools/` (novo) | M5 |
| Harness (orchestrator + skills) | `modules/agent/` (novo) | M6 |
| UI conversacional + SSE + ações | `apps/web/src/features/agent/` (novo) | M7 |
| Integração com ReportGenerationTool | extensão do módulo `reports/` | M8 |
| Runtime LLM multi-provider | `modules/agent/providers/` (novo) | M10 |
| BYOK + chaves do usuário | `user_model_keys` + `platform_model_keys` (novas) | M11 |
| Model registry + capability guard | `llm_providers` + `llm_models` (novas) | M12 |
| Model picker no harness | extensão `modules/agent/` | M13 |
| Governança de billing BYOK | extensão créditos + billing | M14 |

### 2.3 Novos `CreditOperation` a adicionar ao `CREDIT_COSTS` existente

```python
# Adicionar ao CREDIT_COSTS em apps/api/src/modules/usage_limits/credit_costs.py
CreditOperation.AGENT_QUERY_CLASS_B:       1   # composição de fatos persistidos
CreditOperation.AGENT_QUERY_CLASS_C:       3   # cálculo novo necessário
CreditOperation.AGENT_BENCHMARK_REFRESH:   2   # re-materializar benchmark desatualizado
CreditOperation.AGENT_COMMUTE_REFRESH:     3   # recalcular mobilidade
CreditOperation.AGENT_POI_REFRESH:         2   # refresh de proximidade a POIs
CreditOperation.AGENT_REPORT_PREMIUM:      5   # relatório comparativo de salvos
```

Classes A (Classe A — Barata) são sempre gratuitas: usam apenas fatos já materializados.

---

## 3. Decisões de escopo fechadas

### 3.1 V1 cobre apenas imóveis/zonas salvos + contexto da UI atual

O agente V1 responde perguntas sobre:
- imóveis na lista `user_listing_favorites` do usuário;
- zonas na lista `user_zone_favorites` do usuário;
- o imóvel ou zona **atualmente selecionado na UI** (via `ui_context`);
- destinos nomeados salvos (`trabalho`, `escola`, `academia`, `família`).

O agente V1 **não responde** sobre:
- imóveis listados em resultados de jornada que não foram salvos;
- imóveis de outras plataformas fora do produto;
- recomendações fora do universo de salvos.

**Justificativa:** simplificar o escopo de dados e garantir que o agente trabalhe exclusivamente com dados que o usuário já avaliou e escolheu manter. Resultados de sessão como escopo de consulta entram na V2, quando a camada de facts for madura.

### 3.2 Resposta numérica só pode vir de tool

Nenhum número, percentual, distância, tempo ou ranking pode aparecer na resposta final sem ter passado por uma tool determinística. O LLM escreve a resposta, não calcula.

### 3.3 Provider inicial: Anthropic direto

A V1 usa apenas `claude-sonnet-4-6` (Sonnet) e `claude-haiku-4-5` (Haiku) via Anthropic API. OpenRouter e BYOK são implementados no M10–M14, sem bloquear M0–M9.

---

## 4. Usuários-alvo e casos de uso

### 4.1 Usuários-alvo

**Primário:** pessoa buscando imóvel para morar com 2 a 10 imóveis e/ou zonas em avaliação.

**Secundário:** investidor individual; corretor ou consultor; usuário recorrente que compara áreas com frequência.

### 4.2 Casos de uso prioritários V1

| UC | Nome | Descrição |
|---|---|---|
| UC-01 | Filtro composto sobre imóveis salvos | Encontrar salvos que atendam preço, mobilidade e proximidade de POIs |
| UC-02 | Ranking explicável de imóveis salvos | Ordenar por critérios como segurança, preço e tempo de deslocamento |
| UC-03 | Benchmark de mercado | Comparar imóvel salvo com a mediana da zona ou bairro |
| UC-04 | Ranking de mobilidade | Identificar imóveis com maior variedade de linhas, menos baldeações |
| UC-05 | Comparação entre zonas salvas | Comparar zonas por preço, segurança, verde, alagamento e transporte |
| UC-06 | Relatório acionável | Gerar resumo comparativo com insights e conclusão |

### 4.3 Fora do escopo

- Chat aberto sobre qualquer tema imobiliário.
- Recomendações jurídicas, tributárias ou financeiras personalizadas.
- Forecast de valorização com modelos proprietários.
- Negociação, visitas ou mensagens externas.
- Agente autônomo de scraping.

---

## 5. Requisitos funcionais

O agente deve:

1. entender referências implícitas como `meu trabalho`, `essa zona`, `esse imóvel`, `meus salvos`;
2. suportar filtros compostos de preço, metragem, condomínio, zona, bairro, POI, mobilidade e categoria;
3. responder com números e critérios verificáveis vindos de tools;
4. informar quando usa snapshot antigo, cache recente ou cálculo novo;
5. expor por que determinado imóvel ou zona ficou em primeiro lugar;
6. oferecer ações na resposta: abrir mapa, abrir card, comparar, salvar visão, gerar relatório;
7. respeitar entitlements de grátis, créditos e assinatura;
8. emitir eventos SSE progressivos durante o pipeline de execução;
9. responder com fallback claro quando faltarem dados, contexto ou créditos.

---

## 6. Requisitos não funcionais

### 6.1 Latência

| Classe de consulta | Latência ideal | Com feedback progressivo |
|---|---|---|
| Classe A — só dados persistidos | 1–4 s | N/A (direto) |
| Classe B — composição de fatos | 3–8 s | SSE: etapas visíveis |
| Classe C — cálculo novo | 8–20 s | SSE: tool em progresso |
| Classe D — dado faltante | < 1 s | fallback imediato |

### 6.2 Confiabilidade

- Nenhuma resposta analítica pode depender apenas do texto do LLM.
- Toda afirmação numérica precisa sair de tool determinística.
- Fallback estruturado sempre que tool falhar ou dado faltar.

### 6.3 Explicabilidade

- Sem score opaco por padrão.
- Rankings mostram filtros aplicados, critérios e desempates.
- Benchmark informa tamanho da amostra e data do snapshot.

### 6.4 Observabilidade

- Toda execução registra: plano interpretado, tools usadas, duração por etapa, fallback e resultado.
- Métricas: intent accuracy, tool accuracy, factual accuracy, latência p50/p95, taxa de fallback.

---

## 7. Estrutura do módulo no backend existente

O agente vive inteiramente dentro do monorepo existente, como um novo módulo em `apps/api/src/modules/agent/`. Não há novo serviço ou processo separado na V1 — o agente executa dentro do processo `api` (FastAPI), com as tools chamando o banco e os módulos de domínio existentes via DTOs de `packages/contracts/`.

```
apps/api/src/modules/agent/
  __init__.py
  gateway.py            # endpoints HTTP/SSE do agente
  orchestrator.py       # harness principal (pipeline 7 etapas)
  memory.py             # resolução das 4 camadas de memória
  skills/
    intent_parser.py    # LLM skill: query → IntentPlan
    context_resolver.py # LLM skill: resolve refs implícitas
    constraint_normalizer.py
    tool_planner.py     # seleciona tools e ordem/paralelismo
    rank_reasoner.py    # LLM skill: resultado → explicação
    answer_writer.py    # LLM skill: escreve resposta final
    fallback_handler.py
    action_router.py    # anexa chips de ação à resposta
  tools/
    resolve_user_context.py
    list_saved_listings.py
    list_saved_zones.py
    get_listing_facts.py
    get_zone_facts.py
    poi_proximity.py
    commute_analysis.py
    market_benchmark.py
    explainable_rank.py
    credits_policy.py
    report_generation.py
  providers/            # M10+ (camada multi-provider)
    base.py
    anthropic.py
    openrouter.py
  registry.py           # model registry (M12)
  schemas.py            # DTOs internos do agente
```

### 7.1 Regras de dependência

O módulo `agent` segue as mesmas regras do `apps/api`:

```
modules/agent  → modules/usage_limits  (créditos)
modules/agent  → modules/listings      (facts de imóvel)
modules/agent  → modules/zones         (facts de zona)
modules/agent  → modules/pois          (POI proximity)
modules/agent  → modules/reports       (geração de relatório)
modules/agent  → packages/contracts    (DTOs)
modules/agent  NÃO importa de api/routes
```

### 7.2 Endpoints do gateway

```
POST /agent/sessions
  → criar sessão de chat; retorna session_id

GET  /agent/sessions/{session_id}
  → estado da sessão + histórico resumido

POST /agent/sessions/{session_id}/messages
  → enviar mensagem; inicia pipeline; retorna message_id

GET  /agent/sessions/{session_id}/stream
  → SSE stream do pipeline em andamento (reconectável via Last-Event-ID)

DELETE /agent/sessions/{session_id}
  → encerrar sessão

GET  /agent/destinations
POST /agent/destinations
DELETE /agent/destinations/{id}
  → CRUD de destinos nomeados do usuário
```

---

## 8. Skills do agente e enum de intents

As skills são unidades especializadas de prompt + schema de saída + política de erro. Cada skill resulta em uma ou mais chamadas LLM independentes. O harness monta o pipeline chamando skills na sequência correta.

### 8.1 `intent_parser`

**Objetivo:** traduzir linguagem natural em intenção estruturada.
**Input:** mensagem do usuário + contexto de tela.
**Output:** `IntentPlan` (ver 8.9).
**Modelo:** `claude-haiku-4-5` (parse leve; não precisa de raciocínio profundo).
**max_tokens:** 512.

### 8.2 `context_resolver`

**Objetivo:** resolver referências implícitas.
**Resolve:** `meu trabalho`, `esse imóvel`, `essa zona`, `meus salvos`, `mercado da região`.
**Modelo:** `claude-haiku-4-5`.
**max_tokens:** 256.

### 8.3 `constraint_normalizer`

**Objetivo:** padronizar unidades e termos.
**Exemplos:**
- `2 mil reais` → `2000 BRL`
- `30 min de ônibus` → `modal=bus`, `time<=30`
- `pilates` → categoria canônica de POI: `fitness`
- `academia` → `gym`

### 8.4 `tool_planner`

**Objetivo:** decidir quais tools chamar e em que ordem, respeitando o menor plano suficiente.
**Regra:** priorizar tools já materializadas; só disparar cálculo novo quando necessário.
**Modelo:** `claude-haiku-4-5`.
**max_tokens:** 512.
**Output:** `ExecutionPlan` com lista de `ToolCall[]`, incluindo flag `parallel: true` quando aplicável.

### 8.5 `rank_reasoner`

**Objetivo:** transformar resultado de ranking em explicação legível.
**Regra:** nunca inventar pesos que o backend não informou.
**Modelo:** `claude-sonnet-4-6`.
**max_tokens:** 800.

### 8.6 `answer_writer`

**Objetivo:** responder em linguagem natural, curta e útil.
**Estrutura obrigatória da resposta:**
1. conclusão direta (1–2 frases);
2. critérios usados;
3. limitações / frescor dos dados;
4. próxima ação sugerida.

**Modelo:** `claude-sonnet-4-6`.
**max_tokens:** 1024.
**Idioma:** português brasileiro.

### 8.7 `fallback_handler`

**Objetivo:** responder bem quando faltar dado ou contexto.
**Exemplos:**
- "Você ainda não salvou um destino chamado trabalho. Quer configurar agora?"
- "Posso comparar seus imóveis salvos, mas esse ainda não tem benchmark calculado. Quer que eu calcule? (2 créditos)"

### 8.8 `action_router`

**Objetivo:** anexar ações disponíveis à resposta.
**Ações disponíveis:**
- `open_map`: abrir imóvel ou zona no mapa
- `open_card`: abrir card de imóvel ou dashboard de zona
- `open_comparison`: abrir comparador
- `save_view`: salvar comparação atual
- `generate_report`: iniciar geração de relatório
- `configure_destination`: abrir formulário de destino nomeado
- `request_refresh`: solicitar recálculo com confirmação de crédito

### 8.9 Enum de intents V1

```python
class AgentIntent(str, Enum):
    # Consultas sobre imóveis salvos
    FILTER_SAVED_LISTINGS    = "filter_saved_listings"     # filtro composto
    RANK_SAVED_LISTINGS      = "rank_saved_listings"       # ranking com critérios
    BENCHMARK_LISTING        = "benchmark_listing"         # comparar com mercado
    RANK_COMMUTE             = "rank_commute"              # ranking por mobilidade
    LISTING_POI_PROXIMITY    = "listing_poi_proximity"     # proximidade a categoria de POI

    # Consultas sobre zonas salvas
    COMPARE_SAVED_ZONES      = "compare_saved_zones"       # comparação direta entre zonas
    RANK_SAVED_ZONES         = "rank_saved_zones"          # ranking de zonas por critério
    ZONE_BENCHMARK           = "zone_benchmark"            # zona vs mediana do produto

    # Consultas mistas imóvel + zona
    LISTING_ZONE_FIT         = "listing_zone_fit"          # imóvel bem alinhado à zona
    COMPOSITE_ANALYSIS       = "composite_analysis"        # múltiplos critérios combinados

    # Ações
    GENERATE_REPORT          = "generate_report"           # relatório de comparação
    SAVE_COMPARISON          = "save_comparison"           # salvar visão atual

    # Fora do escopo ou ambíguo
    NEEDS_CLARIFICATION      = "needs_clarification"       # agente pede mais detalhes
    OUT_OF_SCOPE             = "out_of_scope"              # fora do domínio do produto
```

### 8.10 Schema `IntentPlan` (output do intent_parser)

```json
{
  "intent": "rank_saved_listings",
  "target_scope": "saved_listings",
  "filters": [
    {"field": "price", "op": "<=", "value": 2500},
    {"field": "poi_canonical_category", "op": "=", "value": "fitness"},
    {"field": "commute_modal", "op": "=", "value": "bus"},
    {"field": "commute_time_minutes", "op": "<=", "value": 30}
  ],
  "sort": {
    "type": "explainable_rank",
    "primary": "security_value_asc",
    "secondary": "price_asc",
    "tie_breaker": "commute_time_asc"
  },
  "context_refs": {
    "destination_label": "trabalho"
  },
  "freshness_policy": "prefer_cached",
  "response_mode": "list_with_explanations",
  "query_class": "C",
  "requires_tools": ["ListSavedListingsTool", "CommuteAnalysisTool", "POIProximityTool", "ExplainableRankTool"]
}
```

---

## 9. Memória

### 9.1 Tipos de memória

#### A. Memória de sessão
Curta duração, vinculada ao chat atual. Armazenada em Redis com TTL de 2h.

Guarda:
- último `listing_key` citado;
- último `zone_key` citado;
- último `destination_label` citado;
- filtros transitórios da conversa;
- último `IntentPlan` produzido;
- último ranking gerado (top-3 com razões).

#### B. Memória persistente de conta
Longa duração, vinculada ao usuário. Armazenada no banco.

Guarda:
- `user_listing_favorites` (existente);
- `user_zone_favorites` (existente);
- `saved_destinations` (nova — ver seção 11.1);
- `user_agent_preferences` (nova — ver seção 11.2);
- `saved_comparisons` (nova — ver seção 11.10).

#### C. Memória analítica
Facts derivados persistidos para acelerar e padronizar respostas. Jamais recalculados ao vivo sem solicitação explícita.

Guarda:
- `listing_agent_facts` — benchmark, score urbano, freshness;
- `listing_poi_facts` — distâncias a POIs por categoria;
- `listing_destination_commute_stats` — mobilidade por imóvel → destino;
- `market_benchmark_snapshots` — mediana de mercado por escopo.

#### D. Memória de contexto da UI
Efêmera, enviada pelo frontend a cada mensagem.

```json
{
  "selected_listing_key": "string|null",
  "selected_zone_key": "string|null",
  "current_panel": "dashboard|listings|map|agent",
  "journey_id": "uuid|null"
}
```

### 9.2 Política de memória

| Camada | Armazenamento | TTL / política |
|---|---|---|
| Sessão | Redis | 2h; renova a cada mensagem |
| UI context | request payload | efêmero; não persiste |
| Preferências | PostgreSQL | opt-in explícito; sem TTL |
| Facts analíticos | PostgreSQL | freshness por `computed_at`; recálculo sob demanda |
| Histórico de mensagens | PostgreSQL (`agent_chat_messages`) | retido; compactado após 10 turnos |

### 9.3 Política de compactação de histórico

Quando o histórico de uma sessão acumular mais de 10 turnos ou a estimativa de tokens de entrada (histórico + system prompt + tools) ultrapassar 8.000 tokens:

1. Gerar um sumário dos turnos anteriores com `claude-haiku-4-5` (max 300 tokens).
2. Substituir os turnos compactados por uma mensagem `role: system` com o sumário.
3. Manter os últimos 3 turnos verbatim.
4. Registrar a compactação em `agent_chat_messages` com `role: "summary"`.

Isso garante que o contexto de entrada nunca ultrapasse ~4.000 tokens de histórico efetivo, independentemente do tamanho da sessão.

---

## 10. Harness engineering

### 10.1 Pipeline do harness (7 etapas)

```
RECEIVED
  → [Etapa 1] NORMALIZED      — limpar, extrair unidades, marcar ambiguidades
  → [Etapa 2] PARSED          — IntentPlan estruturado + query_class
  → [Etapa 3] CONTEXT_RESOLVED — referências implícitas resolvidas
  → [Etapa 4] PLAN_BUILT      — ExecutionPlan: tools + ordem + flags parallel
  → [Etapa 5] TOOLS_RUNNING   — execução determinística (sequencial + paralelo)
  → [Etapa 6] VERIFIED        — sanity checks antes de redigir
  → [Etapa 7] ANSWER_READY
  → DELIVERED
```

**Saídas alternativas:**
- `FALLBACK_MISSING_CONTEXT` — referência não resolvida (ex: destino não cadastrado)
- `FALLBACK_MISSING_DATA` — fact não existe e não há crédito para recalcular
- `DENIED_BY_CREDITS_POLICY` — usuário confirmou ou negou recálculo custoso
- `FAILED_TOOL_EXECUTION` — tool retornou erro após retry interno

### 10.2 Classes de consulta

| Classe | Característica | Exemplo | Custo de crédito |
|---|---|---|---|
| A | Só fatos já persistidos | "Qual salvo é mais barato?" | 0 |
| B | Composição de fatos existentes | "Qual tem melhor relação preço/segurança?" | 1 |
| C | Exige cálculo novo (commute, POI refresh, benchmark) | "Quais têm mais linhas de ônibus até meu trabalho?" | 2–3 |
| D | Dado faltante estrutural | Usuário nunca cadastrou `trabalho` | fallback imediato |

### 10.3 Regras do planner

1. Priorizar tools sobre fatos já materializados (`computed_at` recente).
2. Só disparar cálculo novo quando necessário; consultar `CreditsPolicyTool` antes.
3. Quando o usuário confirmar crédito, registrar e executar; quando negar, retornar `DENIED_BY_CREDITS_POLICY`.
4. Jamais responder benchmark, mobilidade ou ranking com heurística inventada.
5. Em caso de ambiguidade crítica, usar contexto da UI; se não bastar, cair em `NEEDS_CLARIFICATION`.
6. Máximo de 4 tools por plano na V1.

### 10.4 Execução paralela de tools

O `tool_planner` deve marcar ferramentas com `parallel: true` quando não há dependência de dados entre elas. O orchestrator executa esses grupos em paralelo usando `asyncio.gather`.

**Grupos paralelizáveis:**

| Consulta | Grupo sequencial | Grupo paralelo |
|---|---|---|
| Rank por mobilidade + POI | `ListSavedListingsTool` | `CommuteAnalysisTool` + `POIProximityTool` em paralelo |
| Benchmark + rank | `ListSavedListingsTool` | `GetListingFactsTool` (batch) + `MarketBenchmarkTool` em paralelo |
| Comparação de zonas | `ListSavedZonesTool` | `GetZoneFactsTool` em batch paralelo |

**Regra:** tools que recebem as mesmas `listing_keys` como input e não dependem umas das outras são sempre candidatas ao grupo paralelo.

**max_concurrent_tool_calls:** 4 (evita saturar DB em lote grande de salvos).

### 10.5 Estratégia de eficiência de tokens

#### 10.5.1 Prompt caching (Anthropic)

O system prompt do agente e as especificações das tools são estáticos por sessão. Devem ser enviados com `cache_control: {"type": "ephemeral"}` no primeiro request de cada sessão. O Anthropic SDK reutiliza esse cache por até 5 minutos, economizando ~60% dos tokens de entrada em conversas multi-turno.

```python
# Estrutura do request com cache
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}   # cacheado
            },
            {
                "type": "text",
                "text": tools_spec_json,
                "cache_control": {"type": "ephemeral"}   # cacheado
            },
            {
                "type": "text",
                "text": user_message                     # não cacheado
            }
        ]
    }
]
```

#### 10.5.2 Roteamento por modelo e por stage

| Stage | Modelo | Justificativa |
|---|---|---|
| `intent_parser` | `claude-haiku-4-5` | parse leve; alta velocidade |
| `context_resolver` | `claude-haiku-4-5` | resolução de referências simples |
| `constraint_normalizer` | `claude-haiku-4-5` | normalização léxica |
| `tool_planner` (Classe A/B) | `claude-haiku-4-5` | plano simples |
| `tool_planner` (Classe C) | `claude-sonnet-4-6` | plano com dependências |
| `rank_reasoner` | `claude-sonnet-4-6` | raciocínio sobre critérios |
| `answer_writer` | `claude-sonnet-4-6` | qualidade de linguagem |
| `fallback_handler` | `claude-haiku-4-5` | resposta rápida |
| `summarizer` (compactação) | `claude-haiku-4-5` | sumarização de histórico |

#### 10.5.3 Orçamento de tokens por classe de consulta

| Classe | Input estimado | Output max | Modelo primário |
|---|---|---|---|
| A | ~600 tokens | 512 tokens | Haiku |
| B | ~1.200 tokens | 800 tokens | Haiku + Sonnet |
| C | ~2.000 tokens | 1.024 tokens | Sonnet |
| D | ~400 tokens | 256 tokens | Haiku |

### 10.6 Verificação pós-tools

Antes de gerar a resposta final, o harness verifica:

- Há números na resposta sem origem em tool? → abortar, pedir reescrita sem número.
- O ranking se refere ao conjunto filtrado correto? → verificar `entity_ids` contra filtros.
- O destino foi resolvido (não `null`)? → fallback se necessário.
- O benchmark tem amostra mínima (`sample_size >= 10`)? → avisar se insuficiente.
- Todos os `listing_keys` do resultado pertencem ao `user_id` da sessão? → rejeitar se não.

### 10.7 Schema SSE do agente

O agente emite eventos SSE seguindo o mesmo padrão do produto (Redis pub/sub → canal `agent:{session_id}`). O frontend assina via `GET /agent/sessions/{id}/stream`.

```json
// Início do pipeline
{"event": "agent.pipeline.started", "data": {"stage": "parsing", "message": "Entendendo sua pergunta..."}}

// Progresso entre etapas
{"event": "agent.pipeline.progress", "data": {"stage": "context_resolved", "message": "5 imóveis salvos encontrados."}}

// Tool em execução
{"event": "agent.tool.started", "data": {"tool": "CommuteAnalysisTool", "message": "Calculando deslocamento para 5 imóveis..."}}

// Tool concluída
{"event": "agent.tool.completed", "data": {"tool": "CommuteAnalysisTool", "items_processed": 5}}

// Escrevendo resposta
{"event": "agent.answering", "data": {"message": "Preparando resposta..."}}

// Resposta completa (streaming de texto)
{"event": "agent.text.delta", "data": {"text": "O imóvel na Rua..."}}

// Ações disponíveis
{"event": "agent.actions", "data": {"actions": [{"type": "open_card", "label": "Ver imóvel", "entity_id": "listing_123"}]}}

// Pipeline finalizado
{"event": "agent.done", "data": {"query_class": "C", "tools_used": ["CommuteAnalysisTool", "ExplainableRankTool"], "credits_consumed": 3}}

// Fallback
{"event": "agent.fallback", "data": {"reason": "missing_destination", "message": "Você ainda não salvou um destino chamado 'trabalho'.", "action": {"type": "configure_destination", "label": "Configurar agora"}}}

// Crédito necessário (aguarda confirmação do usuário)
{"event": "agent.credits_required", "data": {"cost": 3, "reason": "Recalcular mobilidade para 5 imóveis", "confirm_endpoint": "/agent/sessions/{id}/confirm-credit"}}
```

### 10.8 Guardrails

- Nunca inventar números.
- Nunca ocultar ausência de dado.
- Nunca usar score opaco por padrão.
- Sempre informar frescor quando o dado for sensível ao tempo.
- Sempre explicar o critério do ranking.
- Quando houver empate ou aproximação, dizer explicitamente.
- Nunca misturar dados de usuários diferentes.
- Nunca usar resultado de tool de outro `user_id`.

### 10.9 Avaliação e observabilidade

#### Logs obrigatórios em `agent_query_logs`

- `raw_query` — pergunta original;
- `normalized_query` — após `constraint_normalizer`;
- `parsed_plan` — `IntentPlan` JSON;
- `resolved_context` — contexto resolvido;
- `tool_trace` — tools chamadas com input/output e duração;
- `result_summary` — resumo da resposta;
- `fallback_reason` — causa de fallback (se houver);
- `confidence_score` — 0–1 baseado em cobertura de tools;
- `credits_check` — resultado de `CreditsPolicyTool`;
- `latency_ms` — duração total.

#### Métricas de avaliação

- intent accuracy;
- tool selection accuracy;
- factual accuracy (zero tolerância a números sem tool);
- fallback correctness (respostas úteis vs vazias);
- latência p50/p95 por classe;
- taxa de consumo indevido de crédito;
- taxa de sessões com compactação ativada.

#### Suite de avaliação inicial (M0 entregável)

- 20 queries simples (Classe A);
- 20 queries compostas (Classe B);
- 10 queries com cálculo novo (Classe C);
- 10 queries ambíguas (espera `NEEDS_CLARIFICATION`);
- 10 com dado faltante (espera fallback correto);
- 10 de benchmark de mercado;
- 10 de mobilidade.

Total: 90 queries com resposta esperada definida manualmente.

---

## 11. Modelo de dados adicional

Todas as tabelas abaixo são novas (não existem no `PRD.md` atual). As migrações usam Alembic, seguindo o padrão existente em `infra/migrations/`.

### 11.1 `saved_destinations`

Destinos nomeados pelo usuário (trabalho, escola, academia, família, etc.).

```sql
CREATE TABLE saved_destinations (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label            TEXT NOT NULL,
  normalized_label TEXT NOT NULL,
  point            GEOMETRY(Point, 4326) NOT NULL,
  address_text     TEXT,
  default_modal    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, normalized_label)
);
CREATE INDEX idx_saved_destinations_user_id ON saved_destinations(user_id);
CREATE INDEX idx_saved_destinations_point_gist ON saved_destinations USING GIST(point);
```

`normalized_label` armazena termos como `trabalho`, `escola`, `familia`, `academia`.

---

### 11.2 `user_agent_preferences`

Preferências declaradas para o agente.

```sql
CREATE TABLE user_agent_preferences (
  user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  max_budget_brl           NUMERIC(12,2),
  preferred_modal          TEXT,
  preferred_commute_max_min INT,
  safety_priority          TEXT,   -- 'high' | 'medium' | 'low'
  greenery_priority        TEXT,
  flood_risk_tolerance     TEXT,
  notes                    JSONB,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### 11.3 `agent_chat_sessions`

Sessão de conversa com o agente.

```sql
CREATE TABLE agent_chat_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  journey_id       UUID REFERENCES journeys(id) ON DELETE SET NULL,
  title            TEXT,
  state            TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'archived'
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_chat_sessions_user_id ON agent_chat_sessions(user_id, created_at DESC);
```

---

### 11.4 `agent_chat_messages`

Mensagens e contexto resumido de cada sessão.

```sql
CREATE TABLE agent_chat_messages (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID NOT NULL REFERENCES agent_chat_sessions(id) ON DELETE CASCADE,
  role             TEXT NOT NULL,   -- 'user' | 'assistant' | 'tool' | 'summary'
  content          TEXT NOT NULL,
  content_json     JSONB,           -- para mensagens estruturadas (tool results, actions)
  ui_context       JSONB,           -- snapshot do contexto da UI enviado pelo frontend
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_chat_messages_session_id ON agent_chat_messages(session_id, created_at);
```

---

### 11.5 `agent_query_logs`

Log estruturado de cada execução do harness.

```sql
CREATE TABLE agent_query_logs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        UUID REFERENCES agent_chat_sessions(id) ON DELETE SET NULL,
  user_id           UUID REFERENCES users(id) ON DELETE SET NULL,
  raw_query         TEXT NOT NULL,
  normalized_query  TEXT,
  parsed_plan       JSONB,
  resolved_context  JSONB,
  tool_trace        JSONB,
  result_summary    JSONB,
  fallback_reason   TEXT,
  confidence_score  NUMERIC(5,2),
  credits_check     JSONB,
  query_class       TEXT,           -- 'A' | 'B' | 'C' | 'D'
  intent            TEXT,
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at       TIMESTAMPTZ,
  latency_ms        INT
);
CREATE INDEX idx_agent_query_logs_user_id ON agent_query_logs(user_id, started_at DESC);
CREATE INDEX idx_agent_query_logs_session_id ON agent_query_logs(session_id, started_at DESC);
```

---

### 11.6 `listing_agent_facts`

Facts materializados por imóvel. A chave `listing_key` é a mesma de `user_listing_favorites.listing_key`.

```sql
CREATE TABLE listing_agent_facts (
  listing_key          TEXT PRIMARY KEY,
  property_id          UUID REFERENCES properties(id) ON DELETE SET NULL,
  zone_fingerprint     TEXT,
  city                 TEXT,
  neighborhood         TEXT,
  search_type          TEXT,   -- 'rental' | 'sale'
  usage_type           TEXT,
  price                NUMERIC(12,2),
  condo_fee            NUMERIC(12,2),
  iptu                 NUMERIC(12,2),
  area_m2              NUMERIC(10,2),
  price_per_m2         NUMERIC(12,2),
  bedrooms             INT,
  bathrooms            INT,
  parking_spaces       INT,
  security_value       NUMERIC(12,4),
  greenery_value       NUMERIC(12,4),
  flood_risk_value     NUMERIC(12,4),
  market_delta_pct     NUMERIC(12,4),    -- desconto/prêmio vs benchmark
  market_position_band TEXT,             -- 'below_median' | 'median' | 'above_median'
  source_snapshot_at   TIMESTAMPTZ,
  computed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_listing_agent_facts_zone_fingerprint ON listing_agent_facts(zone_fingerprint);
CREATE INDEX idx_listing_agent_facts_price ON listing_agent_facts(price);
```

Job de materialização: disparado quando o usuário salva um imóvel (`user_listing_favorites`) e diariamente para atualizar `computed_at` dos salvos existentes.

---

### 11.7 `listing_destination_commute_stats`

Facts de mobilidade por imóvel → destino.

```sql
CREATE TABLE listing_destination_commute_stats (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_key           TEXT NOT NULL,
  destination_id        UUID NOT NULL REFERENCES saved_destinations(id) ON DELETE CASCADE,
  modal                 TEXT NOT NULL,
  avg_time_min          NUMERIC(10,2),
  min_time_min          NUMERIC(10,2),
  itinerary_count       INT,
  distinct_lines_count  INT,
  transfers_median      NUMERIC(10,2),
  best_departure_window JSONB,
  computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (listing_key, destination_id, modal)
);
CREATE INDEX idx_commute_stats_listing_key ON listing_destination_commute_stats(listing_key);
CREATE INDEX idx_commute_stats_destination_id ON listing_destination_commute_stats(destination_id);
```

---

### 11.8 `listing_poi_facts`

Facts de proximidade a POIs por categoria por imóvel.

```sql
CREATE TABLE listing_poi_facts (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_key             TEXT NOT NULL,
  canonical_category      TEXT NOT NULL,
  nearest_poi_name        TEXT,
  nearest_distance_m      NUMERIC(10,2),
  nearest_walk_time_min   NUMERIC(10,2),
  poi_count_within_250m   INT,
  poi_count_within_500m   INT,
  source_provider         TEXT,   -- 'mapbox'
  computed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (listing_key, canonical_category)
);
CREATE INDEX idx_listing_poi_facts_listing_key ON listing_poi_facts(listing_key);
CREATE INDEX idx_listing_poi_facts_category ON listing_poi_facts(canonical_category);
```

Taxonomia canônica de categorias V1 (alinhada com as do produto — Mapbox Search Box):
`supermarket`, `gym`, `park`, `pharmacy`, `restaurant`, `school`, `bus_stop`, `metro_station`.

---

### 11.9 `market_benchmark_snapshots`

Snapshots de benchmark por escopo.

```sql
CREATE TABLE market_benchmark_snapshots (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type           TEXT NOT NULL,   -- 'zone' | 'neighborhood' | 'citywide_bucket'
  scope_key            TEXT NOT NULL,   -- zone_fingerprint ou nome normalizado de bairro
  search_type          TEXT NOT NULL,
  usage_type           TEXT NOT NULL,
  median_price         NUMERIC(12,2),
  median_price_per_m2  NUMERIC(12,2),
  p25_price_per_m2     NUMERIC(12,2),
  p75_price_per_m2     NUMERIC(12,2),
  listing_count        INT,
  computed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (scope_type, scope_key, search_type, usage_type, computed_at)
);
CREATE INDEX idx_market_benchmark_scope ON market_benchmark_snapshots(scope_type, scope_key, computed_at DESC);
```

Amostra mínima para resposta confiável: `listing_count >= 10`. Abaixo disso, o agente avisa.

---

### 11.10 `saved_comparisons`

Comparações persistidas.

```sql
CREATE TABLE saved_comparisons (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  comparison_type  TEXT NOT NULL,   -- 'listings' | 'zones'
  title            TEXT,
  payload          JSONB NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_saved_comparisons_user_id ON saved_comparisons(user_id, created_at DESC);
```

---

## 12. Contratos das tools

As tools são funções Python internas do módulo `modules/agent/tools/`. Não são chamadas pelo LLM diretamente — o harness as chama após `tool_planner` decidir o plano. Contratos versionados em `packages/contracts/agent/`.

### 12.1 `ResolveUserContextTool`

```python
# Input
class ResolveUserContextInput(BaseModel):
    user_id: UUID
    ui_context: UIContext              # selected_listing_key, selected_zone_key, journey_id
    refs: list[str]                   # ["meu trabalho", "esse imóvel", "meus salvos"]

# Output
class ResolveUserContextOutput(BaseModel):
    resolved: dict[str, str | None]   # label → id ou key resolvida
    missing: list[str]                # refs que não puderam ser resolvidas
```

---

### 12.2 `ListSavedListingsTool`

```python
class ListSavedListingsInput(BaseModel):
    user_id: UUID
    filters: ListingFilters           # max_price, zone_keys, search_type, etc.
    sort: SortSpec
    limit: int = 50

class ListSavedListingsOutput(BaseModel):
    items: list[SavedListingItem]     # listing_key, price, address, zone_key, platform
    total: int
```

---

### 12.3 `ListSavedZonesTool`

Output: `zone_key`, `zone_fingerprint`, `summary_metrics`, `snapshot_at`, `badges`.

---

### 12.4 `GetListingFactsTool`

Suporta batch: `listing_keys: list[str]`.

```python
class GetListingFactsInput(BaseModel):
    listing_keys: list[str]

class ListingFacts(BaseModel):
    listing_key: str
    price: Decimal
    price_per_m2: Decimal
    security_value: float
    greenery_value: float
    flood_risk_value: float
    market_delta_pct: float | None
    market_position_band: str | None
    zone_fingerprint: str
    snapshot_at: datetime

class GetListingFactsOutput(BaseModel):
    items: list[ListingFacts]
    missing_keys: list[str]           # listing_keys sem facts materializados
```

---

### 12.5 `GetZoneFactsTool`

Output: métricas de dashboard; preço mediano; histórico resumido; badges; segurança; verde; alagamento; POIs; `snapshot_at`.

---

### 12.6 `POIProximityTool`

```python
class POIProximityInput(BaseModel):
    listing_keys: list[str]
    canonical_category: str
    freshness_policy: Literal["prefer_cached", "require_fresh"] = "prefer_cached"

class POIProximityItem(BaseModel):
    listing_key: str
    nearest_distance_m: float
    nearest_walk_time_min: float
    nearest_poi_name: str | None
    poi_count_within_500m: int
    computed_at: datetime
    used_fresh_compute: bool

class POIProximityOutput(BaseModel):
    items: list[POIProximityItem]
    credits_consumed: int
```

---

### 12.7 `CommuteAnalysisTool`

```python
class CommuteAnalysisInput(BaseModel):
    listing_keys: list[str]
    destination_id: UUID
    modal: str                        # 'bus' | 'subway' | 'walking' | 'car'
    freshness_policy: Literal["prefer_cached", "require_fresh"] = "prefer_cached"

class CommuteAnalysisItem(BaseModel):
    listing_key: str
    avg_time_min: float
    min_time_min: float
    itinerary_count: int
    distinct_lines_count: int
    transfers_median: float
    computed_at: datetime
    used_fresh_compute: bool

class CommuteAnalysisOutput(BaseModel):
    items: list[CommuteAnalysisItem]
    credits_consumed: int
```

---

### 12.8 `MarketBenchmarkTool`

```python
class MarketBenchmarkInput(BaseModel):
    listing_key: str
    benchmark_scope: Literal["zone", "neighborhood", "citywide_bucket"]
    metric: Literal["price_per_m2", "price"]

class MarketBenchmarkOutput(BaseModel):
    listing_key: str
    benchmark_scope: str
    benchmark_key: str
    listing_value: Decimal
    median_value: Decimal
    delta_pct: float
    position_band: str                # 'below_median' | 'median' | 'above_median'
    sample_size: int
    computed_at: datetime
    sample_sufficient: bool           # sample_size >= 10
```

---

### 12.9 `ExplainableRankTool`

```python
class RankingRule(BaseModel):
    primary: str                      # ex: "security_value_asc"
    secondary: str
    tie_breaker: str | None

class ExplainableRankInput(BaseModel):
    entity_type: Literal["saved_listings", "saved_zones"]
    entity_ids: list[str]
    filters: dict
    ranking_rule: RankingRule

class RankedItem(BaseModel):
    entity_id: str
    rank: int
    reasons: list[str]               # frases explicativas geradas pelo backend
    score_breakdown: dict            # valores brutos dos critérios

class ExplainableRankOutput(BaseModel):
    ranked_items: list[RankedItem]
    applied_filters: dict
    filtered_out_count: int
```

---

### 12.10 `CreditsPolicyTool`

```python
class CreditsPolicyInput(BaseModel):
    user_id: UUID
    requested_operations: list[str]  # lista de CreditOperation.value

class CreditsPolicyOutput(BaseModel):
    allowed: bool
    requires_credit: bool
    estimated_credit_cost: int
    current_balance: int
    reason: str
```

---

### 12.11 `ReportGenerationTool`

Integra com `modules/reports/` existente. Enfileira job `report_generate` no Dramatiq via fila `reports`.

```python
class ReportGenerationInput(BaseModel):
    user_id: UUID
    report_type: Literal["comparison", "single_listing", "zone_summary"]
    entity_ids: list[str]
    include_map_snapshots: bool = True
    include_charts: bool = True
    include_conclusion: bool = True

class ReportGenerationOutput(BaseModel):
    report_id: UUID
    job_id: UUID
    status: Literal["queued"]
```

---

## 13. Orquestração técnica

### 13.1 Fluxo de execução — exemplo Classe C

**Pergunta:** "Quais imóveis salvos têm mais linhas de ônibus para chegar ao meu trabalho?"

```
1. intent_parser        → intent=RANK_COMMUTE, target=saved_listings, destination_label="trabalho"
2. context_resolver     → destination_id=<uuid de "trabalho" cadastrado>
3. CreditsPolicyTool    → estimated_cost=3, balance=8, allowed=true
   → SSE: agent.credits_required (aguarda confirmação do usuário)
4. ListSavedListingsTool → [listing_123, listing_124, listing_125]
5. CommuteAnalysisTool  → modal=bus, destination_id=<uuid>  ← paralelo com step 5b
   POIProximityTool     → (não necessário para esta query)
6. ExplainableRankTool  → sort by distinct_lines_count DESC, tie_breaker=transfers_median ASC
7. rank_reasoner        → explicações por imóvel
8. answer_writer        → resposta final em PT-BR
9. action_router        → chips: [open_card, open_map, generate_report]
```

### 13.2 Fluxo de execução — exemplo Classe A

**Pergunta:** "Qual imóvel salvo é mais barato?"

```
1. intent_parser        → intent=FILTER_SAVED_LISTINGS, sort=price_asc, limit=1
2. context_resolver     → scope=saved_listings (sem refs implícitas adicionais)
3. ListSavedListingsTool → [listing_123, listing_124, listing_125]
4. ExplainableRankTool  → sort=price_asc, limit=1
5. answer_writer        → resposta direta: "Seu imóvel mais barato é..."
6. action_router        → chips: [open_card]
```

Crédito: 0. Duração esperada: < 3 s.

### 13.3 Estratégia de verificação

Após as tools, o harness verifica:
- Há afirmações numéricas sem origem em tool? → reescrever sem o número.
- O ranking cobre o conjunto filtrado correto? → verificar `entity_ids` vs `applied_filters`.
- Houve filtro antes da ordenação? → não é possível ranquear sem filtrar primeiro.
- O destino foi resolvido (não `null`)? → fallback `FALLBACK_MISSING_CONTEXT`.
- O benchmark tem `sample_sufficient=true`? → avisar se `false`.

---

## 14. Políticas de ranking

### 14.1 Estratégias permitidas na V1

- Ordenação lexicográfica simples.
- Filtros com desempates explícitos e mostrados ao usuário.
- Score composto somente quando todos os critérios são expostos e a fórmula mostrada.

### 14.2 Regras de ranking canônicas

**Regra por preço e segurança:**
1. filtrar `price <= max_price`
2. ordenar por `security_value ASC` (menor ocorrências = melhor)
3. desempatar por `price ASC`
4. desempatar por `avg_commute_time ASC`

**Regra por mobilidade:**
1. filtrar imóveis com `commute_time <= max_minutes` (se especificado)
2. ordenar por `distinct_lines_count DESC`
3. desempatar por `transfers_median ASC`
4. desempatar por `min_time_min ASC`

**Regra por custo-benefício:**
1. filtrar `price <= max_price`
2. normalizar `price_per_m2` e `security_value` para [0,1]
3. score = 0.6 × (1 - price_per_m2_norm) + 0.4 × (1 - security_value_norm)
4. expor a fórmula e os valores individuais na resposta

---

## 15. Integração com créditos existentes

O agente integra com a infraestrutura de créditos já existente em `modules/usage_limits/`. O fluxo usa `check_and_consume_credits()` existente, com os novos `CreditOperation` definidos na seção 2.3.

### 15.1 O que é gratuito

- Perguntar sobre imóvel/zona salvo com facts já materializados (Classe A).
- Comparar fatos já calculados (Classe B com `freshness_policy=prefer_cached`).
- Explicar benchmark já calculado.
- Perguntas sobre zonas salvas com `zone_payload` existente.

### 15.2 O que consome crédito

| Operação | Custo |
|---|---|
| Composição de fatos existentes (Classe B) | 1 crédito |
| Recalcular mobilidade (Classe C) | 3 créditos |
| Recalcular proximidade a POIs | 2 créditos |
| Re-materializar benchmark desatualizado | 2 créditos |
| Gerar relatório comparativo de salvos | 5 créditos |

### 15.3 Comportamento do agente com créditos insuficientes

1. Agente detecta via `CreditsPolicyTool` que a operação requer créditos.
2. Emite `agent.credits_required` via SSE com custo estimado.
3. Aguarda confirmação via `POST /agent/sessions/{id}/confirm-credit`.
4. Se confirmado: executa e registra no `credit_ledger`.
5. Se negado ou sem saldo: retorna `DENIED_BY_CREDITS_POLICY` com alternativa gratuita (se existir).

---

## 16. Segurança e guardrails

- Nunca retornar endereço ou dado sensível de imóvel sem usuário autenticado.
- Nunca misturar dados de usuários diferentes em um mesmo plano ou resposta.
- Nunca inferir `trabalho` ou `casa` sem destino salvo explícito pelo usuário.
- Nunca confirmar que um imóvel existe sem buscar em `user_listing_favorites` do `user_id` autenticado.
- Nunca responder benchmark com amostra insuficiente sem avisar.
- Anonimizar logs de query que contenham endereços ou dados de localização precisos.
- Tools retornam apenas dados do `user_id` da sessão ativa — verificação obrigatória em toda query.
- Rate limiting no gateway: 30 mensagens/hora por usuário (ajustável por plano).

---

## 17. Camada multi-provider LLM e BYOK

Esta seção define a arquitetura para suporte a múltiplos provedores de LLM, seleção de modelo pelo usuário e uso de chave própria (BYOK). Implementada nos milestones M10–M14, **sem bloquear M0–M9**.

### 17.1 Objetivo

Adicionar uma camada de execução de modelos semelhante ao GitHub Copilot Chat:
- seleção de provedor (Anthropic, OpenRouter);
- seleção de modelo;
- chave da plataforma ou chave própria (BYOK);
- harness independente do vendor.

### 17.2 Provedores suportados

**Anthropic (direto):**
- Uso da API de mensagens nativa.
- Suporte a prompt caching.
- Billing direto no workspace Anthropic.

**OpenRouter:**
- Agregador multi-provider.
- Catálogo dinâmico de modelos.
- Billing centralizado.

### 17.3 Interface interna única

```typescript
interface LlmExecutionRequest {
  provider: 'anthropic' | 'openrouter';
  model: string;                        // ex: 'claude-sonnet-4-6'
  apiKeyRef: string;
  mode: 'chat' | 'agent';
  messages: NormalizedMessage[];
  systemPrompt?: string;
  tools?: NormalizedToolSpec[];
  responseFormat?: 'text' | 'json';
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
  cacheControl?: boolean;               // ativar prompt caching
  metadata?: Record<string, string | number | boolean>;
}

interface LlmExecutionResult {
  provider: 'anthropic' | 'openrouter';
  model: string;
  outputText?: string;
  outputJson?: unknown;
  toolCalls?: NormalizedToolCall[];
  finishReason?: string;
  usage?: {
    inputTokens?: number;
    outputTokens?: number;
    cacheReadTokens?: number;
    cacheWriteTokens?: number;
    estimatedCostUsd?: number;
  };
}
```

### 17.4 Adapter interface

```typescript
interface ProviderAdapter {
  validateKey(input: { apiKey: string }): Promise<ValidateKeyResult>;
  execute(input: LlmExecutionRequest): Promise<LlmExecutionResult>;
  stream(input: LlmExecutionRequest): AsyncIterable<NormalizedLlmChunk>;
}
```

### 17.5 Model registry — tabelas

#### `llm_providers`
```sql
CREATE TABLE llm_providers (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug               TEXT UNIQUE NOT NULL,         -- 'anthropic' | 'openrouter'
  display_name       TEXT NOT NULL,
  base_url           TEXT NOT NULL,
  auth_scheme        TEXT NOT NULL,                -- 'x-api-key' | 'bearer'
  supports_byok      BOOLEAN NOT NULL DEFAULT true,
  supports_streaming BOOLEAN NOT NULL DEFAULT true,
  is_active          BOOLEAN NOT NULL DEFAULT true,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `llm_models`
```sql
CREATE TABLE llm_models (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id               UUID REFERENCES llm_providers(id) NOT NULL,
  model_id                  TEXT NOT NULL,              -- ex: 'claude-sonnet-4-6'
  display_name              TEXT NOT NULL,
  family                    TEXT,                       -- 'claude' | 'gpt' | 'gemini'
  vendor_name               TEXT,
  is_active                 BOOLEAN NOT NULL DEFAULT true,
  is_hidden                 BOOLEAN NOT NULL DEFAULT false,
  supports_chat             BOOLEAN NOT NULL DEFAULT true,
  supports_tools            BOOLEAN NOT NULL DEFAULT false,
  supports_structured_json  BOOLEAN NOT NULL DEFAULT false,
  supports_vision           BOOLEAN NOT NULL DEFAULT false,
  supports_prompt_caching   BOOLEAN NOT NULL DEFAULT false,
  context_window_tokens     INT,
  max_output_tokens         INT,
  pricing_input_per_mtok    NUMERIC(12,6),
  pricing_output_per_mtok   NUMERIC(12,6),
  sort_order                INT NOT NULL DEFAULT 100,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_llm_models_provider_model UNIQUE (provider_id, model_id)
);
```

#### `llm_model_capability_profiles`
```sql
CREATE TABLE llm_model_capability_profiles (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  llm_model_id     UUID REFERENCES llm_models(id) NOT NULL,
  profile_slug     TEXT NOT NULL,    -- 'agent-safe' | 'chat-fast' | 'json-strict'
  is_default       BOOLEAN NOT NULL DEFAULT false,
  allowed_modes    TEXT[] NOT NULL,
  disabled_reasons TEXT[],
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_llm_capability_profile UNIQUE (llm_model_id, profile_slug)
);
```

### 17.6 Regras de compatibilidade de modo

| Modo | Requisitos do modelo |
|---|---|
| `chat` | `supports_chat = true` |
| `agent` | `supports_chat = true` + `supports_tools = true` + perfil `agent-safe` |
| `json-strict` | `supports_structured_json = true` |

### 17.7 Chaves API — tabelas

#### `user_model_keys`
```sql
CREATE TABLE user_model_keys (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  provider_id      UUID REFERENCES llm_providers(id) NOT NULL,
  label            TEXT,
  key_ciphertext   BYTEA NOT NULL,
  key_fingerprint  TEXT NOT NULL,
  last4_hint       TEXT,
  is_default       BOOLEAN NOT NULL DEFAULT false,
  status           TEXT NOT NULL DEFAULT 'active',   -- 'active' | 'invalid' | 'revoked'
  validated_at     TIMESTAMPTZ,
  last_used_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_user_model_keys UNIQUE (user_id, provider_id, key_fingerprint)
);
```

#### `platform_model_keys`
```sql
CREATE TABLE platform_model_keys (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id      UUID REFERENCES llm_providers(id) NOT NULL,
  environment_slug TEXT NOT NULL,
  key_ciphertext   BYTEA NOT NULL,
  key_fingerprint  TEXT NOT NULL,
  is_default       BOOLEAN NOT NULL DEFAULT false,
  status           TEXT NOT NULL DEFAULT 'active',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_platform_model_keys UNIQUE (provider_id, environment_slug, key_fingerprint)
);
```

**Regras de segurança:**
- Chaves criptografadas em repouso (AES-256).
- Nunca logar chave, prefixo completo ou header raw.
- Frontend exibe apenas `provider`, `label` e `last4_hint`.
- Validar chave com chamada de baixo custo antes de aceitar como ativa.

**Prioridade de resolução:**
1. chave explicitamente escolhida pelo usuário;
2. chave padrão do usuário para aquele provider;
3. chave padrão da plataforma;
4. erro de configuração.

### 17.8 Preferências de modelo do usuário

```sql
CREATE TABLE user_model_preferences (
  id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                    UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  default_agent_provider_id  UUID REFERENCES llm_providers(id),
  default_agent_model_id     UUID REFERENCES llm_models(id),
  prefer_user_keys           BOOLEAN NOT NULL DEFAULT true,
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_user_model_preferences UNIQUE (user_id)
);
```

### 17.9 Telemetria de execução LLM

```sql
CREATE TABLE agent_llm_runs (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id              UUID REFERENCES agent_chat_sessions(id) ON DELETE CASCADE NOT NULL,
  provider_id             UUID REFERENCES llm_providers(id),
  model_id                UUID REFERENCES llm_models(id),
  key_scope               TEXT NOT NULL,   -- 'platform' | 'user'
  mode                    TEXT NOT NULL,
  stage                   TEXT NOT NULL,   -- 'intent_parser' | 'answer_writer' | etc.
  status                  TEXT NOT NULL DEFAULT 'started',
  input_tokens            INT,
  output_tokens           INT,
  cache_read_tokens       INT,
  cache_write_tokens      INT,
  estimated_cost_usd      NUMERIC(12,6),
  latency_ms              INT,
  finish_reason           TEXT,
  error_code              TEXT,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at            TIMESTAMPTZ
);
CREATE INDEX idx_agent_llm_runs_session_id ON agent_llm_runs(session_id, created_at DESC);
```

### 17.10 Endpoints multi-provider

```
GET  /ai/providers
GET  /ai/models?provider=anthropic&mode=agent
POST /ai/keys/validate
POST /ai/keys
GET  /ai/keys
DELETE /ai/keys/{key_id}
GET  /ai/preferences
PUT  /ai/preferences
POST /internal/ai/models/sync/anthropic
POST /internal/ai/models/sync/openrouter
```

---

## 18. Milestones

### M0 — Foundations e contratos
**Objetivo:** definir tudo antes da implementação.

**Entregáveis:**
- este documento aprovado por backend, frontend e produto;
- enum de intents V1 (`AgentIntent`) codificado em `packages/contracts/`;
- 90 queries de referência com resposta esperada (suite de avaliação);
- schema JSON do `IntentPlan` validado;
- contratos de todas as tools revisados;
- ADR para estratégia de ranking explicável;
- ADR para prompt caching e roteamento por modelo.

**Critério de aceite:**
- 10 perguntas de referência convertidas para `IntentPlan` manualmente, sem LLM;
- equipe concorda com os contratos das tools e com os campos das tabelas novas.

**Dependência no projeto existente:** nenhuma — trabalho de definição.

---

### M1 — Memória persistente e contexto do usuário
**Objetivo:** tornar o agente capaz de entender `meu trabalho`, `meus salvos`, `essa zona`.

**Entregáveis:**
- migrations Alembic: `saved_destinations`, `user_agent_preferences`, `agent_chat_sessions`, `agent_chat_messages`, `saved_comparisons`;
- endpoints CRUD para destinos salvos (`/agent/destinations`);
- `ResolveUserContextTool` — resolução de referências implícitas;
- transporte do `ui_context` via header ou body para cada mensagem do agente;
- `agent_query_logs` — estrutura de log.

**Dependência no projeto existente:** auth funcionando (✅ concluído).

**Critério de aceite:**
- usuário consegue cadastrar `trabalho` e `escola`;
- `ResolveUserContextTool` resolve corretamente essas referências em 95% dos testes internos.

---

### M2 — Facts analíticos em nível de imóvel
**Objetivo:** sair de analytics só por zona para analytics por imóvel.

**Entregáveis:**
- migrations: `listing_agent_facts`, `market_benchmark_snapshots`;
- job Dramatiq `listing_facts_materialize` (fila `enrichment`): dispara ao salvar imóvel e diariamente para salvos existentes;
- job `market_benchmark_compute`: calcula benchmark por `zone_fingerprint` e bairro;
- `GetListingFactsTool` e `MarketBenchmarkTool`.

**Dependência no projeto existente:**
- `user_listing_favorites` (✅ existe);
- `properties` + `listing_snapshots` (✅ existem);
- `zones` com `zone_fingerprint` (✅ existe).

**Critério de aceite:**
- 1 imóvel salvo responde: `price_per_m2`, `market_delta_pct`, `zone_fingerprint`, `snapshot_at`.

---

### M3 — Facts de POI por imóvel
**Objetivo:** permitir perguntas sobre proximidade a serviços.

**Entregáveis:**
- migration: `listing_poi_facts`;
- taxonomia canônica de 8 categorias iniciais;
- job `listing_poi_enrich`: usa Mapbox Search Box (mesmo endpoint do produto);
- `POIProximityTool`.

**Dependência no projeto existente:**
- Mapbox Search Box integrado (✅ já usado no `modules/pois/`);
- `user_listing_favorites` com `listing_key` (✅ existe).

**Critério de aceite:**
- perguntas sobre distância a academia, mercado, escola e parque funcionam sobre imóveis salvos.

---

### M4 — Facts de mobilidade por imóvel → destino
**Objetivo:** permitir perguntas sobre deslocamento.

**Entregáveis:**
- migration: `listing_destination_commute_stats`;
- job `listing_commute_compute`: usa OTP (já disponível no produto);
- policy de cache/freshness;
- `CommuteAnalysisTool`.

**Dependência no projeto existente:**
- OTP disponível no Hostinger VPS (✅ Fase 3 do PRD.md);
- `saved_destinations` (M1);
- `user_listing_favorites` (✅ existe).

**Critério de aceite:**
- para 1 conjunto de 10 imóveis salvos, responde ranking de mobilidade até `trabalho` com tempo, linhas e baldeações.

---

### M5 — Tool layer determinística completa
**Objetivo:** consolidar o backend consultável pelo agente.

**Entregáveis:**
- `ListSavedListingsTool`;
- `ListSavedZonesTool`;
- `GetZoneFactsTool`;
- `ExplainableRankTool`;
- `CreditsPolicyTool` (estende `check_and_consume_credits` existente com novos `CreditOperation`);
- suite de 20 queries canônicas resolvidas via plano manual + tools (sem LLM).

**Dependência no projeto existente:**
- `user_zone_favorites` (✅ existe);
- `zones` com enriquecimento (✅ Fase 4 concluída);
- `user_credits` + `credit_ledger` (✅ existe).

**Critério de aceite:**
- 20 queries canônicas resolvidas sem LLM, apenas com plano manual + tools;
- nenhuma tool retorna dado de outro `user_id`.

---

### M6 — Harness do agente
**Objetivo:** ligar interpretação e execução.

**Entregáveis:**
- `intent_parser`, `context_resolver`, `constraint_normalizer`;
- `tool_planner` com suporte a execução paralela;
- `rank_reasoner`, `answer_writer`, `fallback_handler`, `action_router`;
- prompt caching implementado para system prompt e tool specs;
- roteamento por modelo (Haiku para parse/planner, Sonnet para raciocínio/resposta);
- compactação de histórico após 10 turnos;
- `agent_query_logs` populado;
- SSE do agente seguindo schema da seção 10.7.

**Dependência no projeto existente:**
- M1–M5 completos;
- SSE Redis pub/sub (✅ existe — mesmo padrão de `job_events`).

**Critério de aceite:**
- 80%+ de intent accuracy na suite de 90 queries;
- nenhuma resposta numérica sem origem em tool;
- p95 Classe A < 4 s; p95 Classe B < 8 s.

---

### M7 — UI conversacional e ações
**Objetivo:** colocar o agente no app.

**Entregáveis:**
- painel do agente em `apps/web/src/features/agent/`;
- streaming SSE com progressive rendering;
- chips de ação (open_card, open_map, generate_report, configure_destination);
- deep links para mapa, dashboard, favoritos e comparador;
- formulário inline de destino nomeado;
- indicador de crédito e confirmação de recálculo.

**Dependência no projeto existente:**
- M6 completo;
- FE8 (auth + favoritos) no frontend (🔄 em progresso).

**Critério de aceite:**
- usuário pergunta, recebe resposta streamada, clica em chip e abre o resultado no mapa ou comparador.

---

### M8 — Relatórios e monetização integrada
**Objetivo:** transformar perguntas em relatórios e upgrade.

**Entregáveis:**
- `ReportGenerationTool` integrado com `modules/reports/` existente;
- novos `CreditOperation` para agente no `CREDIT_COSTS`;
- paywall contextual do agente (mensagem com custo e CTA de compra);
- franquia mensal para assinantes.

**Dependência no projeto existente:**
- `modules/reports/` + job `report_generate` (✅ Fase 6 do PRD.md);
- Stripe (🔄 Fase 8 pendente — M8 depende de créditos/Stripe funcionando).

**Critério de aceite:**
- usuário entende quando a resposta é grátis, quando usa crédito e quando faz sentido comprar.

---

### M9 — Avaliação, qualidade e rollout gradual
**Objetivo:** reduzir risco antes de abrir para todos.

**Entregáveis:**
- suite de avaliação automatizada com as 90 queries + métricas;
- dashboard de observabilidade (intent accuracy, factual accuracy, latência por classe);
- rollout interno → beta → público;
- replay de queries para regressão.

**Critério de aceite:**
- factual accuracy estável (0 respostas com números inventados);
- fallback correto em 100% das queries com dado faltante;
- p95 aceitável por classe de consulta.

---

### M10 — Fundação do runtime LLM multi-provider
**Objetivo:** criar abstração comum para providers.

**Entregáveis:**
- tabelas `llm_providers`, `llm_models`, `platform_model_keys`;
- `ProviderAdapter` interface;
- `AnthropicAdapter` (extrai o uso direto da API que já existe no M6);
- `OpenRouterAdapter` inicial;
- endpoints `GET /ai/providers`, `GET /ai/models`;
- streaming normalizado via adapter.

**Critério de aceite:**
- backend responde à mesma mensagem via Anthropic e via OpenRouter usando a mesma interface.

---

### M11 — BYOK e segurança
**Objetivo:** permitir chave própria do usuário.

**Entregáveis:**
- tabela `user_model_keys`;
- validação de chave (chamada de baixo custo antes de aceitar);
- criptografia em repouso;
- UI de cadastro/remoção de chave;
- alternância entre chave da plataforma e BYOK.

**Critério de aceite:**
- usuário autenticado consegue cadastrar chave válida e fazer conversa usando apenas essa chave.

---

### M12 — Registry e capability guard
**Objetivo:** impedir combinações inválidas de modo e modelo.

**Entregáveis:**
- tabela `llm_model_capability_profiles`;
- tabela `user_model_preferences`;
- filtro de modelos por modo `chat` e `agent`;
- ocultação de modelos instáveis ou incompatíveis.

**Critério de aceite:**
- modelos sem `supports_tools` não aparecem no picker do modo agente.

---

### M13 — Integração do model picker com o harness
**Objetivo:** conectar seleção de modelo ao runtime do agente.

**Entregáveis:**
- `agent_chat_sessions` com `selected_provider_id` e `selected_model_id`;
- tabela `agent_llm_runs` (telemetria por stage);
- seleção persistida na sessão;
- fallback quando modelo não suportar tools.

**Critério de aceite:**
- usuário troca de modelo sem alterar execução das tools do agente.

---

### M14 — Monetização e governança BYOK
**Objetivo:** compatibilizar BYOK com plano, créditos e limite de uso.

**Entregáveis:**
- política por plano (grátis usa chave da plataforma com limites; assinante pode usar BYOK);
- regra de billing: ferramentas premium ainda exigem créditos mesmo com BYOK;
- UI de aviso de cobrança externa quando BYOK ativo;
- métricas por provider/modelo.

**Critério de aceite:**
- sistema diferencia corretamente custos da plataforma e uso via chave do usuário.

---

## 19. Roadmap por ondas

| Onda | Milestones | Objetivo |
|---|---|---|
| Onda 1 — Definição | M0 | Contratos, intents, queries de referência |
| Onda 2 — Memória e fatos | M1 + M2 + M3 + M4 | Infraestrutura de dados necessária ao agente |
| Onda 3 — Backend consultável | M5 | Tool layer determinística testada sem LLM |
| Onda 4 — Inteligência | M6 + M7 | Harness + UI conversacional |
| Onda 5 — Monetização | M8 + M9 | Relatórios, créditos, qualidade e rollout |
| Onda 6 — Multi-provider | M10–M14 | BYOK, registry, governance |

**Bloqueios entre ondas:**
- Onda 3 bloqueia Onda 4.
- M8 depende de Stripe/créditos (Fase 8 do PRD.md).
- Onda 6 é totalmente independente das ondas 1–5 e pode iniciar em paralelo com Onda 5.

---

## 20. Critérios de sucesso

O agente será considerado bem-sucedido quando:

- aumentar o uso de imóveis salvos e zonas salvas;
- reduzir o tempo até decisão comparativa;
- gerar aumento de abertura de dashboards e relatórios a partir de respostas do agente;
- aumentar upgrade para pacotes de crédito ou assinatura;
- manter factual accuracy em 100% (zero números inventados em produção).

### KPIs sugeridos

| KPI | Meta V1 |
|---|---|
| % usuários autenticados que usam o agente | > 20% em 60 dias pós-lançamento |
| Média de perguntas por sessão | > 3 |
| % de perguntas com ação subsequente | > 40% |
| % de perguntas resolvidas sem fallback | > 70% |
| Taxa de geração de relatório após conversa | > 10% |
| Factual accuracy (zero números inventados) | 100% |
| Conversão crédito/assinatura a partir do agente | > 5% dos usuários do agente |

---

## 21. Questões resolvidas e decisões registradas

### Questão 1 — Benchmark padrão
**Decisão:** `zone_fingerprint` como escopo primário. Fallback para bairro normalizado quando a amostra de zona for insuficiente (`listing_count < 10`). Fallback secundário para bucket citywide quando bairro também for insuficiente. O agente sempre informa o escopo usado e o tamanho da amostra.

### Questão 2 — Listings sem coordenada confiável
**Decisão:** `listing_agent_facts` só é materializado para imóveis com `property_id` não nulo e `location` não nula em `properties`. Imóveis sem coordenada ficam disponíveis para filtros de preço mas não para mobilidade, POI ou benchmark geoespacial. O agente informa a limitação quando relevante.

### Questão 3 — Categorias canônicas de POI na V1
**Decisão:** 8 categorias: `supermarket`, `gym`, `park`, `pharmacy`, `restaurant`, `school`, `bus_stop`, `metro_station`. Alinhadas com as já usadas no produto (Mapbox Search Box). Expansão na V2.

### Questão 4 — Escopo: só salvos ou também resultados da sessão atual?
**Decisão (seção 3.1):** V1 cobre apenas imóveis/zonas salvos + contexto da UI atual (`ui_context.selected_listing_key`). Resultados de jornada não salvos entram na V2, quando a camada de facts for madura.

### Questão 5 — Comparação entre imóvel salvo e não salvo
**Decisão:** não na V1. O usuário deve salvar o imóvel antes de comparar. O agente pode sugerir salvar o imóvel da UI atual se `ui_context.selected_listing_key` estiver presente e o imóvel não estiver nos salvos.

### Questão 6 — Política exata de recálculo pago vs gratuito
**Decisão (seção 15):** consulta com fatos existentes = grátis. Recálculo de commute = 3 créditos. Recálculo de POI = 2 créditos. Benchmark refresh = 2 créditos. Relatório = 5 créditos. Composição de fatos persistidos = 1 crédito.

### Questão 7 — Segurança explicável em nível de imóvel
**Decisão:** o campo `security_value` em `listing_agent_facts` herda da zona (`zones.safety_incidents_count` normalizado pelo total de zonas do produto). Não há dado policial por endereço preciso na V1 — o agente explica que o valor reflete a zona isócrona, não o endereço exato. Dado de endereço preciso é investigado para a V2.
