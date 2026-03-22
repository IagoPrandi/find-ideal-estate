# Checklists Operacionais

## 1. Definition of Done (DoD)

Uma entrega só é considerada **pronta** quando todos os itens aplicáveis estão checados:

### Código e qualidade
- [ ] Compila/builda sem warnings em local e staging.
- [ ] Todos os testes relevantes passando (unit/integration/e2e conforme impacto da mudança).
- [ ] Sem regressão de cobertura abaixo do threshold definido.
- [ ] Linting e formatação aprovados no CI.
- [ ] Code review aprovado por pelo menos 1 pessoa além do autor.

### Segurança
- [ ] Nenhum segredo, chave ou credencial no código, logs, exemplos ou testes.
- [ ] Toda entrada pública validada e com limites definidos.
- [ ] Controle de acesso revisado (Web2 e Web3).
- [ ] Sem vulnerabilidades críticas no scan de dependências.

### Consistência híbrida (quando aplicável)
- [ ] Invariantes críticas estão on-chain, não apenas no backend.
- [ ] Indexer reorg-aware e idempotente para novos eventos.
- [ ] UX de transação cobre falhas e estados intermediários.
- [ ] ABI e eventos compatíveis com versão anterior (ou versão nova explícita).

### Migrações e dados
- [ ] Migrações de schema aplicadas e rollback documentado.
- [ ] Sem breaking change não planejada em API pública.
- [ ] Índices de banco atualizados conforme novas queries.

### Operação
- [ ] Logs e métricas essenciais presentes.
- [ ] Alertas atualizados se novo comportamento crítico foi adicionado.
- [ ] Runbook atualizado se fluxo operacional mudou.
- [ ] Deploy documentado e versionado (especialmente para contratos).

### Documentação
- [ ] README atualizado se comportamento externo mudou.
- [ ] ADR criado para decisões arquiteturais significativas.
- [ ] Changelog atualizado.

---

## 2. Anti-padrões — o agente deve ativamente evitar

### 2.1 Código e design
- ❌ "Refatorar tudo" para resolver um bug pequeno — scope creep disfarçado de boas práticas.
- ❌ Criar "contrato deus" ou módulo único com regras + integração + IO.
- ❌ Duplicar lógica de cálculo financeiro, parsing de eventos, comunicação com RPC.
- ❌ "Magic numbers" e endereços hardcoded espalhados sem constante nomeada.
- ❌ Swallow exceptions silenciosamente (`try { ... } catch { }`).
- ❌ `console.log` de dados sensíveis para debug — e esquecido em produção.

### 2.2 Segurança
- ❌ Segredos em `.env` commitado, mesmo que "temporariamente".
- ❌ Validação apenas no frontend — sempre contornável.
- ❌ Autorização por role global sem verificação de ownership do recurso.
- ❌ Aleatoriedade com `blockhash` ou `block.timestamp` para sorteio com valor real.
- ❌ Confiar em dado passado pelo caller sem verificação on-chain.
- ❌ EOA simples como owner de contrato de produção com valor em risco.

### 2.3 Web3 específico
- ❌ "Achar" que 1 confirmação é suficiente sem analisar o contexto e chain.
- ❌ Indexar eventos sem reorg-awareness e idempotência.
- ❌ Usar spot price de AMM como oráculo de preço (manipulável).
- ❌ Misturar lógica de negócio crítica off-chain com invariantes que deveriam ser on-chain.
- ❌ Deploy de upgrade sem verificação de storage layout.
- ❌ Função de upgrade protegida apenas por EOA sem multisig.

### 2.4 Processo e operação
- ❌ Deploy em produção sem staging equivalente testado primeiro.
- ❌ Mudanças de configuração em produção sem registro ou aprovação.
- ❌ Testes flaky ignorados ("às vezes falha, é normal").
- ❌ Não ter critério de rollback definido antes do deploy.
- ❌ Adicionar biblioteca externa para resolver problema que cabe em 20 linhas.

---

## 3. Checklist final antes de entregar

### Segurança
- [ ] Nenhum segredo exposto
- [ ] Toda entrada validada com limites
- [ ] Controle de acesso revisado em Web2 e Web3
- [ ] Dependências sem vulnerabilidades críticas

### Consistência híbrida
- [ ] Invariantes críticas on-chain
- [ ] Indexer reorg-aware e idempotente
- [ ] UX de transação cobre estados de falha

### Qualidade de código
- [ ] Funções/módulos coesos, sem duplicação
- [ ] Configuração centralizada, sem magic numbers
- [ ] Testes de regressão para bugs corrigidos

### Operação
- [ ] Logs e métricas essenciais presentes
- [ ] Runbook para incidentes críticos
- [ ] Deploy documentado e versionado
- [ ] Rollback possível e testado

---

## 4. Checklist de code review (revisor)

Use ao revisar PRs de outros:

- [ ] Entendi o que a mudança faz e por quê?
- [ ] Há algum caminho de erro não tratado?
- [ ] Há alguma condição de borda não coberta por testes?
- [ ] A mudança pode introduzir problemas de performance (N+1, lock, timeout)?
- [ ] Há algum dado sensível sendo logado ou exposto?
- [ ] A mudança é backward compatible? Se não, está documentada como breaking change?
- [ ] Para contratos: os padrões CEI, controle de acesso e eventos estão corretos?
- [ ] A descrição do PR é suficiente para entender o risco e o rollback?
