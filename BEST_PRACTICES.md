# Boas práticas para agentes de IA em projetos Web2 + Web3
> Documento operacional para orientar agentes de IA (assistentes, copilots e automações) durante análise, implementação, revisão e manutenção de sistemas híbridos (backend tradicional + blockchain).

## Sumário
- [1. Princípios de atuação do agente](#1-princípios-de-atuação-do-agente)
- [2. Regras de ouro de segurança](#2-regras-de-ouro-de-segurança)
- [3. Fronteiras de confiança Web2 vs Web3](#3-fronteiras-de-confiança-web2-vs-web3)
- [4. Boas práticas de arquitetura (híbrida)](#4-boas-práticas-de-arquitetura-híbrida)
- [5. Boas práticas de código e design (geral)](#5-boas-práticas-de-código-e-design-geral)
- [6. Boas práticas Web2 (API, backend, dados)](#6-boas-práticas-web2-api-backend-dados)
- [7. Boas práticas Web3 (contratos, transações, segurança)](#7-boas-práticas-web3-contratos-transações-segurança)
- [8. Indexação, reorgs e consistência](#8-indexação-reorgs-e-consistência)
- [9. Testes e verificação](#9-testes-e-verificação)
- [10. Observabilidade e operação](#10-observabilidade-e-operação)
- [11. Deploy, release e mudanças](#11-deploy-release-e-mudanças)
- [12. Privacidade, compliance e governança](#12-privacidade-compliance-e-governança)
- [13. Definition of Done (DoD)](#13-definition-of-done-dod)
- [14. Anti-padrões que o agente deve evitar](#14-anti-padrões-que-o-agente-deve-evitar)
- [15. Checklist final](#15-checklist-final)

---

## 1. Princípios de atuação do agente
1. **Precisão acima de volume**  
   - Priorize mudanças pequenas, verificáveis e com rastreabilidade.
   - Evite “refactors” amplos quando o objetivo é uma correção pontual.

2. **Transparência de suposições**  
   - Declare claramente o que é fato, o que é inferência e o que é suposição.
   - Ao não ter contexto suficiente, proponha a opção mais segura (fail-closed) e registre as lacunas.

3. **Minimize diffs e risco de regressão**
   - Preserve APIs e contratos públicos sempre que possível.
   - Isolar mudanças por tema: segurança, bugfix, refactor, performance, documentação.

4. **Segurança por padrão**
   - “Se pode dar errado, vai dar errado” é regra em ambiente com dinheiro e incentivos adversariais.
   - Prefira designs simples, com invariantes explícitas e testáveis.

5. **Reprodutibilidade**
   - Toda mudança deve poder ser reproduzida localmente (scripts, comandos, seeds, fixtures).

---

## 2. Regras de ouro de segurança
- **Nunca**:
  - Inserir segredos (keys, mnemonics, tokens) no código, logs, exemplos, documentação ou testes.
  - Pedir ao usuário que compartilhe chave privada / seed.
  - Orientar bypass de mecanismos de segurança (2FA, KYC, etc.) ou práticas abusivas.

- **Sempre**:
  - Usar variáveis de ambiente e secret managers.
  - Redigir logs sem dados sensíveis (PII, segredos, payloads críticos).
  - Tratar entradas como hostis (validação + sanitização + limites).
  - Aplicar *least privilege* (permissões mínimas necessárias).

- **Fail-closed**:
  - Diante de inconsistências, o sistema deve negar a operação crítica, não permitir.

---

## 3. Fronteiras de confiança Web2 vs Web3
1. **Front-end é não confiável**  
   - O agente deve assumir que qualquer verificação feita apenas no front-end pode ser burlada.
   - Validações críticas devem existir no **contrato** (on-chain) e/ou no **backend** (off-chain), conforme a ameaça.

2. **Off-chain não pode “substituir” invariantes on-chain**
   - Regras que protegem fundos, distribuição de prêmios, limites e permissão devem estar on-chain.
   - Off-chain pode otimizar UX e desempenho, mas não deve “decidir” valores finais críticos.

3. **Imutabilidade e custo de erro**
   - Em contratos, “deploy errado” é caro, lento e frequentemente irreversível.
   - O agente deve priorizar revisão, testes, e padrões consagrados de segurança.

---

## 4. Boas práticas de arquitetura (híbrida)
### 4.1 Componentes recomendados
- **dApp / Web UI**
  - Conecta carteira, assina mensagens, envia transações, exibe estados.
- **Smart contracts**
  - Fonte de verdade de regras críticas e estado financeiro.
- **Indexer (Ponder/The Graph/Custom)**
  - Constrói projeções consultáveis (ranking, histórico, dashboards) a partir de eventos.
- **API Web2**
  - Serve UX, cache, agregações, integrações e dados não-críticos.
- **Banco de dados**
  - Armazena projeções (event sourcing / materialized views), não “regras” financeiras.

### 4.2 Diretrizes de separação de responsabilidades
- Contrato: invariantes, regras financeiras, autorização, emissão de eventos.
- Indexer: consistência, reprocessamento, reorg-awareness, normalização.
- Backend: autorização off-chain (quando aplicável), rate limiting, cache, integrações.
- Frontend: UX, estado derivado, feedback de transação.

### 4.3 Versionamento e compatibilidade
- Versione:
  - Esquemas de banco (migrações),
  - APIs (v1, v2),
  - Eventos/ABIs (semântica e campos).
- Evite breaking changes sem estratégia de migração.

---

## 5. Boas práticas de código e design (geral)
### 5.1 Legibilidade e manutenção
- Funções curtas, coesas, com nomes descritivos.
- Evitar “classes deus” ou módulos que “fazem tudo”.
- Preferir composição e interfaces claras.
- Remover duplicações: centralizar utilitários comuns (RPC, retries, parsing).

### 5.2 Configuração e “magic numbers”
- Centralize constantes e parâmetros em:
  - arquivos de config versionados,
  - variáveis de ambiente (para segredos e endpoints),
  - registries de parâmetros por rede (chainId, endereços, etc.).

### 5.3 Erros e exceções
- Mensagens de erro claras e acionáveis, sem vazar segredos.
- Use códigos de erro padronizados.
- Retry com backoff apenas onde é seguro (idempotência).

### 5.4 Segurança de dependências
- Fixar versões (lockfiles).
- Atualizações com changelog e testes.
- Scanner de vulnerabilidades (SCA).

---

## 6. Boas práticas Web2 (API, backend, dados)
### 6.1 APIs
- Autenticação robusta (tokens, sessões, expiração, revogação).
- Autorização por recurso (*object-level authorization*).
- Rate limiting e proteção contra abuso.
- Validação de payloads (schema validation).
- CORS e CSRF conforme tipo de app.
- Headers de segurança (CSP, HSTS quando aplicável).

### 6.2 Banco e migrações
- Migrações reversíveis quando possível.
- Índices alinhados às consultas reais (não “adivinhar”).
- Backups e política de retenção.
- Separar dados críticos (com acesso restrito) de dados de analytics.

### 6.3 Consistência e idempotência
- Operações que possam ser repetidas devem ser idempotentes (ex.: webhooks).
- Use chaves idempotentes (idempotency-key) em endpoints críticos.

### 6.4 Integrações (e-mails, etc.)
- Tratar falhas como normais: retries, dead-letter, reconciliação.
- Registrar auditoria: quem, quando, o quê (sem PII excessiva).

---

## 7. Boas práticas Web3 (contratos, transações, segurança)
### 7.1 Design de contratos
- Contratos pequenos, com responsabilidades claras.
- Minimizar funções públicas e estados mutáveis.
- Emitir eventos ricos e estáveis (pensados para indexação).
- Evitar dependências desnecessárias e “features” não usadas.

### 7.2 Segurança em contratos
- Seguir padrões consagrados (p. ex., OpenZeppelin quando aplicável).
- Proteções típicas (quando relevantes):
  - reentrancy guard,
  - checks-effects-interactions,
  - validação de input,
  - controle de acesso explícito,
  - pausas/timelocks com governança clara.
- Evitar “randomness” insegura (blockhash/timestamp) para sorteios com valor real.
- Considerar MEV/front-running e designs que reduzem exploração.

### 7.3 Upgradeability
- Só usar upgradeability se houver justificativa clara (governança, risco, necessidades).
- Se usar:
  - proteger upgrades com multisig,
  - auditar storage layout,
  - ter plano de rollback e runbook.
- Se não usar:
  - planejar “módulos” e migração de estado via novos contratos.

### 7.4 Transações e UX
- Estados de transação:
  - enviada → pendente → confirmada → (finalizada, quando aplicável).
- Evitar depender de 1 confirmação em fluxos de alto risco.
- Tratar falhas de RPC como normais (timeouts, forks, inconsistência entre providers).

### 7.5 Assinaturas e login via wallet
- Preferir padrões:
  - mensagens tipadas (EIP-712) quando apropriado,
  - login com nonce, domínio, expiração e anti-replay (padrão de “sign-in”).
- Nunca reutilizar nonce.
- Verificar chainId e domínio.

---

## 8. Indexação, reorgs e consistência
- Indexer deve ser **reorg-aware**:
  - detectar reorganizações,
  - reprocessar blocos afetados,
  - reverter projeções quando necessário.
- Banco de projeção deve ser **idempotente**:
  - chaves únicas por (txHash, logIndex) ou (blockNumber, logIndex).
- Separar:
  - estado “otimista” (rápido para UX) vs
  - estado “confirmado/final” (seguro para decisões críticas).
- Monitorar atrasos de indexação e divergências.

---

## 9. Testes e verificação
### 9.1 Pirâmide de testes (mínimo recomendado)
- **Unit tests**: regras isoladas (Web2 e Web3).
- **Integration tests**:
  - backend + DB,
  - indexer + eventos,
  - contratos em ambiente local.
- **E2E**: fluxo do usuário com carteira simulada.
- **Property-based / fuzz** (especialmente contratos):
  - invariantes (ex.: somatório de saldos, conservação de valor).

### 9.2 Testes específicos de Web3
- Fork tests (mainnet/testnet fork) para integrações reais.
- Testes de eventos (schema e compatibilidade).
- Simulações de adversário: reentrancy, front-running, inputs maliciosos.

### 9.3 Critérios de aceitação
- Cobertura não é objetivo único; priorize invariantes e casos de borda.
- Todo bug corrigido deve ganhar teste de regressão.

---

## 10. Observabilidade e operação
### 10.1 Logs, métricas, traces
- Logs estruturados (JSON) com correlação (request-id, trace-id, txHash).
- Métricas:
  - latência, erro, throughput,
  - backlog do indexer,
  - divergência entre providers,
  - taxas de falha de transação.
- Tracing distribuído quando houver múltiplos serviços.

### 10.2 Monitoramento on-chain
- Alertas para:
  - eventos críticos (upgrades, pausas, grandes transferências),
  - anomalias (picos de falhas, gas spikes),
  - mudanças de parâmetros e administração.

---

## 11. Deploy, release e mudanças
### 11.1 Estratégia de deploy
- Staging ≠ produção: ambientes separados, dados e chaves separados.
- Feature flags para mudanças off-chain.
- Canary releases para serviços Web2.

### 11.2 Deploy de contratos
- Checklist obrigatório:
  - parâmetros revisados (endereços, chainId, limites),
  - verificação em explorador (quando aplicável),
  - snapshots/artefatos versionados (ABI, bytecode, commit).
- Preferir multisig para ações administrativas.
- Plano de migração e comunicação aos usuários.

### 11.3 Gestão de mudanças
- PRs com:
  - descrição,
  - risco,
  - testes executados,
  - impacto em dados e compatibilidade.
- Changelog por release.
- Backward compatibility como padrão.

---

## 12. Privacidade, compliance e governança
- Licenças:
  - respeitar licenças de código e dependências.
- Governança:
  - documentar papéis administrativos (multisig, chaves, procedimentos).

---

## 13. Definition of Done (DoD)
Uma entrega só é considerada “pronta” quando:
- [ ] Compila/builda e roda em ambiente local e staging
- [ ] Testes relevantes passam (unit/integration/e2e conforme impacto)
- [ ] Sem segredos no repositório e logs
- [ ] Sem breaking change não planejada
- [ ] Eventos e ABIs compatíveis (ou versão nova explícita)
- [ ] Índices/migrações aplicadas e rollback/mitigação documentados
- [ ] Observabilidade mínima (logs + métricas essenciais)
- [ ] Documentação atualizada (README/Runbook/ADR quando necessário)

---

## 14. Anti-padrões que o agente deve evitar
- “Refatorar tudo” para resolver um bug pequeno.
- Criar “contrato deus” ou módulo único com regras + integração + IO.
- Duplicar lógica de:
  - cálculo financeiro,
  - parsing de eventos/logs,
  - comunicação com RPC/providers.
- “Magic numbers” e endereços hardcoded espalhados.
- Implementar aleatoriedade insegura para sorteio com valor real.
- Confiar em validação apenas no front-end.
- Indexar “na raça” sem reorg-awareness e idempotência.
- “Achar” que 1 confirmação é suficiente em qualquer contexto.
- Misturar segredos em exemplos, testes, `.env` commitado.

---

## 15. Checklist final
### Segurança
- [ ] Nenhum segredo exposto
- [ ] Entrada validada e limites definidos
- [ ] Controle de acesso revisado (Web2 e Web3)

### Consistência híbrida
- [ ] Invariantes críticas estão on-chain
- [ ] Indexer reorg-aware e idempotente
- [ ] UX de transação cobre falhas e estados intermediários

### Qualidade
- [ ] Funções/módulos coesos; duplicações removidas
- [ ] Config centralizada; sem magic numbers
- [ ] Testes de regressão adicionados

### Operação
- [ ] Logs/métricas essenciais presentes
- [ ] Runbook para incidentes críticos
- [ ] Deploy documentado e versionado

---

**Fim do documento.**
