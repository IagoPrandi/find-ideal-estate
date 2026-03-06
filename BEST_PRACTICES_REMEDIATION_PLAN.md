# Plano de Remediação — Boas Práticas de Código, Segurança e Productização

Data: 2026-03-04  
Escopo: transformar o MVP local em produto interno robusto, aplicando as diretrizes de [BEST_PRACTICES.md](BEST_PRACTICES.md) com **garantia operacional prática de não regressão** (funcional + dados + contrato + performance mínima).

## 1) Contexto e referências obrigatórias abertas

- [PRD.md](PRD.md)
- [BEST_PRACTICES.md](BEST_PRACTICES.md)
- [skills_README.md](skills_README.md)
- Skill primária aplicada nesta análise: `security-threat-checklist` (arquivo: [skills/security-threat-checklist/SKILL.md](skills/security-threat-checklist/SKILL.md)).

## 2) Objetivo deste documento (nível execução)

Este plano define:

1. **o que mudar** (backlog técnico por prioridade);
2. **onde mudar** (arquivos concretos);
3. **como mudar** (estratégia segura e incremental);
4. **como provar que não quebrou** (protocolo de validação obrigatório);
5. **quando reverter** (critérios objetivos de rollback).

> Nota de governança: este plano não promete risco zero absoluto; ele estabelece um processo com evidências para reduzir risco de regressão a nível operacional aceitável.

## 3) Baseline obrigatório antes de qualquer melhoria

Sem baseline congelado, não há como afirmar “continua funcionando”. Portanto, cada ciclo deve começar com:

### 3.1 Baseline funcional

- Executar smoke oficial do pipeline definido em [TEST_PLAN.md](TEST_PLAN.md).
- Salvar `run_id` de referência e manter artifacts completos em `runs/<run_id>`.
- Registrar métricas mínimas do baseline:
  - duração total do pipeline;
  - duração por stage;
  - `listings_count` final;
  - quantidade de `zones` consolidadas.

### 3.2 Baseline de contrato API

- Congelar respostas reais (snapshots) dos endpoints críticos:
  - `POST /runs`
  - `GET /runs/{run_id}/status`
  - `GET /runs/{run_id}/zones`
  - `POST /runs/{run_id}/zones/{zone_uid}/detail`
  - `POST /runs/{run_id}/zones/{zone_uid}/listings`
  - `POST /runs/{run_id}/finalize`
  - `GET /runs/{run_id}/final/listings.json`

### 3.3 Baseline de qualidade de output

- Gerar e guardar checksum dos arquivos finais:
  - `listings_final.json`
  - `listings_final.csv`
  - `listings_final.geojson`
  - `zones_final.geojson`
- Definir invariantes (seção 8) para comparação pós-mudança.

## 4) Diagnóstico resumido do estado atual

### Pontos fortes

- Pipeline por estágios e logs por `run_id` em [app/runner.py](app/runner.py) e [app/store.py](app/store.py).
- Contratos Pydantic em [app/schemas.py](app/schemas.py).
- Contratos Zod no cliente em [ui/src/api/client.ts](ui/src/api/client.ts).
- Plano de testes já existente em [TEST_PLAN.md](TEST_PLAN.md).

### Lacunas que podem causar regressão se não tratadas

1. ausência de gate formal de segurança/dependências por merge;
2. inconsistência de tratamento de erro em endpoints;
3. limites de entrada incompletos para operações pesadas;
4. configuração distribuída e suscetível a drift;
5. governança de dependências Python inconsistente;
6. lacunas de testes backend para falhas de pipeline;
7. ausência de suíte formal de compatibilidade API↔UI.

## 5) Backlog técnico priorizado (o que/onde/como)

## 5.0 Estrutura alvo de diretórios e responsabilidades

Sim, já é possível determinar uma estrutura clara para reduzir acoplamento e duplicação.

### Estrutura proposta (backend)

- app/
  - main.py: camada HTTP (rotas, validação de entrada/saída, mapeamento de erro).
  - schemas.py: contratos de API (request/response) e versionamento de schema.
  - config.py: configuração centralizada e tipada (env + defaults + limites).
  - services/
    - runs_service.py: criação/estado de run e orquestração de alto nível.
    - zones_service.py: leitura de zonas, seleção, detalhe e regras de zona.
    - listings_service.py: scraping por zona, consolidação e finalização.
    - transport_service.py: rotas e paradas de transporte.
  - utils/
    - json_io.py: leitura/escrita JSON segura e consistente.
    - error_map.py: padronização de exceções para códigos HTTP.
    - logging.py: logs estruturados e correlação.

- core/
  - regras de negócio puras e geoespaciais (sem conhecimento de HTTP/FastAPI).
  - sem side-effects de infraestrutura fora de IO explicitamente injetado.

- adapters/
  - integração com scripts externos e subprocess.
  - responsabilidade restrita: montar comando, executar, validar artifacts e retornar paths.

- tests/
  - unit/: lógica pura (core/services/utils).
  - integration/: API + store + adapters com fixtures controladas.
  - contract/: compatibilidade de payload API.
  - e2e/: fluxo completo com datasets A/B/C.

- scripts/
  - automações operacionais reproduzíveis (smoke, coleta de baseline, checks).
  - sem lógica de negócio principal (apenas orquestração de execução).

- docs/
  - runbook operacional, decisões arquiteturais e evidências de rollout.

### Estrutura proposta (frontend)

- ui/src/
  - App.tsx: casca de layout e composição de features.
  - api/: cliente HTTP e schemas de contrato.
  - features/
    - reference/: fluxo de ponto principal/interesses.
    - zones/: lista, seleção, detalhe e filtros de zona.
    - listings/: cards, comparação e ordenação de imóveis.
    - map/: camadas e interações de mapa.
  - hooks/: hooks de efeitos (polling, retries, sincronização de estado).
  - state/: estado global do run e estados derivados.
  - components/: componentes compartilhados sem regra de domínio.
  - utils/: helpers puros de formatação/conversão.

### Regras de ownership por diretório

- app/: não implementa regra de negócio profunda; apenas orquestra serviços.
- core/: não conhece HTTP nem UI.
- adapters/: não decide regra final de negócio; apenas integrações.
- ui/features/: regra de apresentação e UX por domínio, evitando concentração em App.tsx.
- tests/: espelha domínios para rastreabilidade e cobertura por responsabilidade.

## P0 — Segurança e confiabilidade mínima (bloqueia release)

### P0.1 Segredos e configuração segura

- **Onde:** [.env](.env), [.env.example](.env.example), [docker-compose.yml](docker-compose.yml), [README.md](README.md).
- **O que:**
  - garantir `.env` real fora de versionamento;
  - placeholders apenas em `.env.example`;
  - política de rotação de token e redaction de logs;
  - validação de ausência de segredos em artifacts/logs.
- **Como:**
  - checklist de pre-commit/pre-push;
  - scanner de segredos no gate estático;
  - convenção única de env por ambiente (local/dev/internal).

### P0.2 Hardening de endpoints e validação de entrada

- **Onde:** [app/main.py](app/main.py), [app/schemas.py](app/schemas.py).
- **O que:**
  - erro padronizado com `error_code` e mensagem acionável;
  - limites defensivos para `bbox`, `radius_m`, paginação e filtros;
  - eliminação progressiva de `except Exception` sem contexto.
- **Como:**
  - criar schema dedicado para query params críticos;
  - normalizar mapeamento de exceções para status code;
  - manter payloads compatíveis com contratos atuais da UI.

### P0.3 Dependências e build reprodutível

- **Onde:** [pyproject.toml](pyproject.toml), [requirements.txt](requirements.txt), [README.md](README.md).
- **O que:**
  - definir [pyproject.toml](pyproject.toml) como fonte única;
  - tratar `requirements.txt` como arquivo derivado (quando necessário);
  - lockfile obrigatório + scanner SCA.
- **Como:**
  - política de atualização de dependências em lotes pequenos;
  - validação completa da suíte a cada atualização.

## P1 — Organização e manutenção (reduz regressão)

### P1.1 Configuração tipada e centralizada

- **Onde:** [app/main.py](app/main.py), [app/runner.py](app/runner.py), [core/zone_ops.py](core/zone_ops.py), [core/listings_ops.py](core/listings_ops.py).
- **O que:** remover números mágicos e defaults duplicados.
- **Como:** criar módulo de configuração tipada (`app/config.py`) com limites e defaults únicos.

### P1.2 Utilitários compartilhados

- **Onde:** [core/zone_ops.py](core/zone_ops.py), [core/listings_ops.py](core/listings_ops.py), [app/store.py](app/store.py).
- **O que:** consolidar `_load_json`, helpers de escrita segura e logging por run.
- **Como:** introduzir módulo utilitário comum sem alterar contrato externo.

### P1.3 Estabilidade de contrato API↔UI

- **Onde:** [app/main.py](app/main.py), [ui/src/api/client.ts](ui/src/api/client.ts), [ui/src/api/schemas.ts](ui/src/api/schemas.ts).
- **O que:** preservar compatibilidade e versionar qualquer breaking change.
- **Como:** snapshots de contrato + testes de consumidor (frontend).

### P1.4 Refatoração estrutural obrigatória (sem rewrite total inicial)

- **Objetivo:** eliminar redundância, reduzir funções/módulos longos e melhorar organização sem quebrar o produto.
- **Onde (backend):** [app/main.py](app/main.py), [core/zone_ops.py](core/zone_ops.py), [core/listings_ops.py](core/listings_ops.py), [app/store.py](app/store.py).
- **Onde (frontend):** [ui/src/App.tsx](ui/src/App.tsx), [ui/src/api/client.ts](ui/src/api/client.ts), [ui/src/api/schemas.ts](ui/src/api/schemas.ts).
- **O que refatorar:**
  - funções com múltiplas responsabilidades (extração para serviços menores);
  - duplicações de parsing/IO/validação/log;
  - regras de negócio misturadas com camada HTTP/UI;
  - componentes grandes com estado excessivo.
- **Como refatorar (padrão):**
  1. congelar contrato atual (snapshot);
  2. extrair bloco interno sem mudar assinatura pública;
  3. cobrir com testes unitários e integração;
  4. validar E2E e invariantes;
  5. repetir em pequenos lotes.

### P1.5 Plano de modularização recomendado (alvo de arquitetura)

#### Backend (target)

- `app/main.py` mantém apenas roteamento/HTTP e delega para `app/services/*`.
- Criar serviços por domínio:
  - `app/services/runs_service.py`
  - `app/services/zones_service.py`
  - `app/services/listings_service.py`
  - `app/services/transport_service.py`
- Centralizar utilitários:
  - `app/utils/json_io.py`
  - `app/utils/error_map.py`
  - `app/utils/logging.py`

#### Frontend (target)

- `ui/src/App.tsx` vira orquestrador leve de layout/fluxo.
- Extrair por domínio:
  - `ui/src/features/reference/*`
  - `ui/src/features/zones/*`
  - `ui/src/features/listings/*`
  - `ui/src/features/map/*`
- Extrair estado e efeitos:
  - `ui/src/state/runState.ts`
  - `ui/src/hooks/useRunPolling.ts`
  - `ui/src/hooks/useZoneDetail.ts`

### P1.6 Critério objetivo: refatorar vs reescrever

Não reescrever frontend/backend inteiro de uma vez. Usar regra:

- **Refatorar incrementalmente** quando:
  - contratos atuais atendem o produto;
  - problema é organização, duplicação e legibilidade;
  - risco de regressão de rewrite total é maior que o benefício imediato.

- **Reescrever um módulo específico** quando:
  - módulo não é testável nem isolável após 2 ciclos de refatoração;
  - custo de manutenção segue alto com falhas recorrentes;
  - há evidência de regressão estrutural persistente.

- **Proibido neste plano:** rewrite completo de frontend+backend sem preservação de contratos e sem migração por etapas.

## P2 — Productização operacional

### P2.1 Observabilidade útil para incidentes

- **Onde:** [app/store.py](app/store.py), [app/runner.py](app/runner.py), [app/main.py](app/main.py).
- **O que:** correlação por request, latência por endpoint, taxa de falha por stage.
- **Como:** middleware + métricas mínimas com thresholds de alerta.

### P2.2 Runbook e rollback operacional

- **Onde:** [README.md](README.md), [TEST_RESULTS_2026-02-20.md](TEST_RESULTS_2026-02-20.md), `docs/runbook.md` (novo).
- **O que:** procedimentos para timeout, falha de scraping, artifact inválido e degradação de performance.
- **Como:** playbooks curtos com comandos, sintomas e ações de reversão.

## 5.9 Boas práticas adicionais ainda não explícitas (recomendadas)

Além do que já está no plano, incluir explicitamente:

1. Estratégia de migração de dados de artifacts
- Versionar schema dos arquivos em runs/ (ex.: campo schema_version).
- Garantir compatibilidade retroativa de leitura durante transição.

2. Política de depreciação de endpoint
- Definir janela de depreciação e aviso antes de remover campos.
- Publicar changelog de contrato para frontend.

3. Orçamento de erro e confiabilidade
- Definir SLO por endpoint crítico e budget mensal de erro.
- Se budget estourar, congelar novas features e priorizar estabilidade.

4. Feature flags para mudanças de risco
- Ativar refactors sensíveis por flag para rollback rápido sem revert total.

5. Determinismo de testes e fixtures
- Proibir testes dependentes de dados instáveis externos sem mock/fixture.
- Fixar seed/inputs para cenários de comparação baseline vs pós-mudança.

6. Política de observabilidade por evento crítico
- Toda falha crítica deve produzir evento estruturado com contexto mínimo padronizado.
- Padronizar taxonomia de erro para facilitar triagem.

7. ADRs para decisões estruturais
- Criar Architecture Decision Records para escolhas de modularização, contratos e rollout.

8. Limites de complexidade por módulo
- Definir thresholds para tamanho de arquivo/função e gatilho de refatoração obrigatória.

9. Revisão de segurança de cadeia de dependências
- Verificar origem/licença de novas dependências e risco de supply chain.

10. Checklist de release por lote
- Exigir checklist assinado (técnico + teste + operação) antes de promover lote.

## 6) Protocolo obrigatório de validação anti-regressão

Cada lote de mudança (P0/P1/P2) só pode avançar se cumprir **todos** os passos abaixo.

### 6.1 Etapa A — Verificação estática (rápida)

1. Lint e typecheck backend/frontend.
2. Secrets scan em código e docs.
3. SCA de dependências.

**Falha em qualquer item = bloqueia merge.**

### 6.2 Etapa B — Testes unitários e integração focada

Executar testes no escopo alterado:

- API/validação: `tests/test_api_contract.py` e `tests/test_api_validation.py` (novos).
- Runner: `tests/test_runner_async.py` (expandir) e `tests/test_runner_stages.py` (novo).
- Core: `tests/test_zone_ops.py` e `tests/test_listings_ops.py` (novos).
- UI contrato: `ui/src/App.test.tsx` com cenários de payload parcial/erro.

**Meta mínima:** 100% dos testes críticos da mudança aprovados.

### 6.3 Etapa C — Teste de contrato (compatibilidade)

Comparar respostas atuais com snapshots baseline:

- Campos obrigatórios não podem desaparecer.
- Tipos não podem mudar sem versionamento.
- Semântica de erro deve permanecer previsível para o frontend.

**Quebra de contrato sem versão = bloqueia merge.**

### 6.4 Etapa D — Regressão de pipeline com datasets fixos

Rodar smoke E2E em Docker (compose do projeto, `onde_morar_mvp`) em:

- Dataset A (smoke rápido);
- Dataset B (sobreposição/consolidação);
- Dataset C (estresse controlado com maior volume de zonas/listings).

**Critérios mínimos por execução:**

- pipeline conclui sem exceção não tratada;
- artifacts finais existem e são parseáveis;
- invariantes de dados preservadas (seção 8);
- tempo total não degrada além de limite da seção 9.

### 6.5 Etapa E — Aprovação de rollout

Somente após A+B+C+D verdes:

- liberar para branch principal;
- registrar evidências em relatório de lote;
- atualizar tracker do PRD.

## 7) Matriz de testes por tipo de alteração

| Tipo de alteração | Testes obrigatórios | Evidência de aprovação |
|---|---|---|
| Endpoints/API | unit + integração + contrato + E2E A | relatório com status code/payload e snapshot diff |
| Runner/stages | unit + integração + E2E A/B | ordem de stages, logs e artifacts por stage |
| Core geoespacial | unit determinístico + integração + E2E B | invariantes geométricos e outputs finais válidos |
| Scraping/listings | integração + E2E A/C | `listings_count`, taxa de sucesso por rua, qualidade de endereço |
| Dependências | estático + suíte completa A/B/C | lock atualizado + sem regressão funcional |
| UI contrato/fluxo | testes de UI + contrato + E2E A | fluxo 3 etapas sem quebra visual/funcional |

## 8) Invariantes obrigatórias de dados (não podem quebrar)

Após cada lote, validar obrigatoriamente:

1. `zones_consolidated.geojson` possui `features` não vazia quando baseline também possuir.
2. Toda feature de zona tem `zone_uid` único.
3. `listings_final.json` contém itens com `address` válido (logradouro aceito).
4. Itens com coordenadas inválidas não entram em `listings_final.geojson`.
5. `state` permanece preenchido para listings finais válidos.
6. Export CSV/JSON/GeoJSON é legível e consistente (mesma cardinalidade lógica esperada).

## 9) Limites de regressão aceitáveis (SLO de mudança)

Para declarar “continua funcionando normalmente”, aplicar estes limites:

- **Funcional:** taxa de sucesso do pipeline em smoke repetido ≥ 95%.
- **Qualidade de output:** queda de `listings_count` só é aceita com justificativa de regra nova; sem justificativa = regressão.
- **Performance:** degradação de tempo total > 20% no mesmo dataset exige investigação e aprovação explícita.
- **Contratos:** 0 breaking changes não versionadas.

## 10) Critérios objetivos de rollback

Rollback obrigatório se ocorrer qualquer item:

1. falha crítica em endpoint principal (`/runs`, `/status`, `/finalize`);
2. quebra de contrato que impede fluxo frontend;
3. artifacts finais ausentes/corrompidos;
4. regressão de performance acima do limite sem mitigação;
5. detecção de segredo exposto.

### Procedimento de rollback

1. reverter lote inteiro (não parcial);
2. restaurar baseline de dependências/lock;
3. rerodar smoke A/B para confirmação;
4. abrir relatório de causa-raiz antes de nova tentativa.

## 11) Ordem de execução recomendada (segura)

1. P0.3 Dependências/build (estabiliza ambiente).  
2. P0.1 Segredos/configuração (reduz risco operacional imediato).  
3. P0.2 Hardening API (protege a interface principal).  
4. P1.1 + P1.2 Refino interno (sem quebrar contratos).  
5. P1.3 Contratos API/UI (trava compatibilidade).  
6. P1.4 + P1.5 Refatoração estrutural e modularização incremental.  
7. P2 Observabilidade + runbook (operação e suporte).

Cada etapa só avança com protocolo da seção 6 totalmente aprovado.

## 12) Critério de pronto (DoD deste plano)

Este plano é considerado aplicado quando:

- baseline e snapshots de contrato estiverem instituídos;
- gates A/B/C/D estiverem automatizados e obrigatórios;
- invariantes de dados estiverem cobertas por testes;
- rollback estiver documentado e testado em simulação;
- os 3 últimos lotes de melhoria tiverem passado sem regressão funcional.

## 13) Evidências mínimas por lote de melhoria

Cada lote deve anexar:

1. escopo e arquivos alterados;
2. resultado dos gates A/B/C/D;
3. comparação baseline vs pós-mudança (funcional/performance/output);
4. decisão final: aprovado ou rollback;
5. atualização no tracker do [PRD.md](PRD.md).

## 14) Observação final

O projeto já é um MVP funcional forte. O que faltava era um protocolo de engenharia para provar, a cada melhoria, que segurança e qualidade avançam sem quebrar o fluxo principal (referência → zonas → imóveis → finalização). Este documento passa a ser esse protocolo.
