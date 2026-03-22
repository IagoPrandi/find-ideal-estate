# Práticas Avançadas — Maturidade de Produto

## 1. Confiabilidade orientada por SLO

### 1.1 Definindo SLOs
- SLO (Service Level Objective): meta mensurável de confiabilidade para um serviço.
- Defina por endpoint/fluxo crítico, não globalmente.
- Exemplos práticos:
  - "99.9% das requisições de consulta de saldo respondem em < 500ms"
  - "99.5% das transações submetidas são confirmadas em < 30s"
  - "Indexer nunca mais de 10 blocos atrasado em relação à chain"

### 1.2 Error budget
- Error budget = 100% - SLO. Ex: SLO 99.9% → 0.1% de budget (~43 minutos/mês).
- Se o budget estourar: congele features e priorize estabilidade — sem exceções.
- Monitore o consumo do budget em tempo real.
- Use o budget restante para calibrar agressividade de deploys e experimentos.

### 1.3 Limites de degradação aceitável
- Defina explicitamente o que é "degradação aceitável" vs "indisponibilidade":
  - Leitura lenta (p95 > 2s) = degradação.
  - Leitura retornando dados incorretos = indisponibilidade.
  - Escrita com retry automático = degradação.
  - Escrita silenciosamente perdida = indisponibilidade crítica.

---

## 2. Rollout e rollback seguros

### 2.1 Feature flags para controle de risco
- Use feature flags para qualquer mudança com risco não trivial.
- Tipos de rollout:
  - **Percentual**: ative para X% dos usuários, monitore, expanda.
  - **Por segmento**: ative para usuários internos ou beta testers primeiro.
  - **Por região/rede**: ative em testnet, depois mainnet.
- Flags devem ter: owner, critério de ativação/desativação, data de criação, prazo de remoção.

### 2.2 Critérios objetivos de rollback
- Defina **antes** do deploy quais métricas indicam rollback automático:
  - "Taxa de erro acima de X% por Y minutos consecutivos → rollback."
  - "Latência p99 acima de Z ms → rollback."
- Rollback não deve exigir aprovação em emergência — deve ser possível em 1 comando por qualquer engenheiro de plantão.
- Teste o processo de rollback em staging periodicamente.

### 2.3 Rollout incremental por etapas
```
1. Deploy em staging → validação manual + smoke tests
2. Canary: 1% de produção → monitorar por 30 min
3. Expand: 10% → monitorar por 1h
4. Expand: 50% → monitorar por 2h
5. Full: 100% → monitorar por 24h
6. Remover feature flag
```

---

## 3. Determinismo de testes e evidência de qualidade

### 3.1 Eliminando flakiness
- Testes que falham intermitentemente são bugs — trate como P2, não ignore.
- Causas comuns de flakiness:
  - Dependência de serviço externo sem mock.
  - Race condition ou timing dependency (`sleep` no teste é sinal de alerta).
  - Ordem de execução dos testes importando.
  - Dados compartilhados entre testes sem isolamento.
- Use datasets fixos para testes de baseline vs pós-mudança.

### 3.2 Evidência por entrega
Cada entrega significativa deve ter evidência documentada:
- [ ] Testes passando (link para CI run).
- [ ] Diffs de contrato de API (se houve mudança).
- [ ] Métricas antes/depois (se mudança de performance).
- [ ] Screenshot ou log de smoke test em staging.
- [ ] Decisão de aprovação registrada (quem aprovou, quando).

### 3.3 Baseline comparativo
- Mantenha dataset de referência fixo para comparações de regressão de performance.
- Antes de refactor de performance: meça o baseline; depois: compare com o mesmo dataset.
- Nunca declare "melhorou performance" sem dado comparativo.

---

## 4. Segurança de cadeia de dependências

### 4.1 Auditoria de novas dependências
Antes de adicionar qualquer biblioteca, responda:
1. Posso implementar isso sem dependência externa em < 50 linhas? Se sim, faça.
2. Quem mantém? Quando foi o último commit? Quantos mantenedores ativos?
3. Qual a licença? É compatível com nosso projeto?
4. Tem histórico de vulnerabilidades críticas? Como foram tratadas?
5. Quantas dependências transitivas traz?

### 4.2 Rotina periódica de atualização
- Revise dependências com vulnerabilidades semanalmente.
- Atualizações não urgentes: agrupe em PR mensal dedicado.
- Processo: leia changelog → atualize → rode suíte completa → deploy em staging → promova.
- Nunca atualize múltiplas dependências em um único commit quando houver mudança comportamental.

---

## 5. Limites de complexidade e saúde do código

### 5.1 Métricas de complexidade como gatilho
- Defina limites que, quando ultrapassados, trigam refatoração obrigatória:
  - Função com > 50 linhas → candidata a divisão.
  - Função com ciclomaticidade > 10 → refatorar.
  - Módulo com > 500 linhas → considerar separação.
  - Mais de 3 níveis de indentação em lógica de negócio → refatorar.

### 5.2 Débito técnico gerenciado
- Registre débito técnico com tickets explícitos — não apenas comentários `// TODO`.
- Priorize débito que afeta segurança ou confiabilidade acima de débito de legibilidade.
- Reescritas totais: somente com dados claros de inviabilidade do incremental.
  - Evidências necessárias: custo de manutenção medido, limitações arquiteturais concretas, estimativa comparativa de custo.
  - Reescrita total sem dados é aposta, não engenharia.

### 5.3 Evolução do schema de dados
- Versione schemas de artifacts/eventos com `schema_version` para retrocompatibilidade.
- Consumidores de schema devem tolerar campos novos (ignore o que não conhece).
- Nunca remova campo em uso sem período de depreciação com versão explícita.
- Para mudanças breaking: mantenha parser das versões antigas por tempo suficiente para migração.
