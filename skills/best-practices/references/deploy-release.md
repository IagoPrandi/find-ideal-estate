# Deploy, Release e Gestão de Mudanças

## 1. Estratégia de ambientes

### 1.1 Separação obrigatória
- **local**: desenvolvimento individual, mocks liberados.
- **staging**: espelho de produção com dados sintéticos — nunca dados reais de usuários.
- **produção**: dados reais, acesso restrito, auditado.

Regras:
- Chaves, endpoints e databases **completamente separados** entre ambientes.
- Acesso a produção: mínimo de pessoas, MFA obrigatório, auditado.
- Staging deve ser capaz de reproduzir bugs de produção — mantenha paridade de configuração.

### 1.2 Feature flags para off-chain
- Use feature flags para mudanças que precisam de rollout gradual ou podem ser revertidas rapidamente.
- Flags devem ter: owner, data de criação, critério de ativação/remoção.
- Não acumule flags obsoletas — cleanup após remoção completa.

### 1.3 Canary releases
- Para mudanças de alto risco em serviços Web2: rollout gradual (1% → 10% → 50% → 100%).
- Monitore métricas de erro durante o rollout — rollback automático se threshold for ultrapassado.
- Documente o critério de promoção antes de iniciar.

---

## 2. CI/CD

### 2.1 Pipeline mínimo
```
Push → Lint → Build → Unit Tests → Integration Tests → Security Scan → Deploy Staging → Smoke Tests → (manual approval) → Deploy Produção
```

### 2.2 Gates obrigatórios antes de merge
- [ ] Todos os testes passando.
- [ ] Sem vulnerabilidades críticas no scan de dependências.
- [ ] Linting e formatação aprovados.
- [ ] Cobertura não regrediu abaixo do threshold definido.
- [ ] Code review aprovado por pelo menos 1 pessoa além do autor.

### 2.3 Artefatos de build
- Builds devem ser reproduzíveis: mesmos inputs → mesmo output.
- Versione artefatos com: tag semântica + hash do commit.
- Nunca sobrescreva artefatos publicados — crie nova versão.

---

## 3. Deploy de contratos inteligentes

### 3.1 Checklist pré-deploy (obrigatório)
- [ ] Parâmetros revisados: endereços, chainId, limites, configurações.
- [ ] Testes completos passando (unit + integration + fuzz + invariant).
- [ ] Análise estática executada (Slither, Mythril) sem findings críticos.
- [ ] Auditoria externa realizada para contratos com valor significativo em risco.
- [ ] ABI e bytecode versionados no repositório.
- [ ] Staging deploy realizado e verificado antes do mainnet.
- [ ] Script de deploy revisado por segunda pessoa.
- [ ] Endereços de configuração verificados (multisig, treasury, oráculos).

### 3.2 Durante o deploy
- Use scripts de deploy versionados — nunca deploy manual ad-hoc.
- Verifique o contrato no explorador (Etherscan/Blockscout) após deploy.
- Salve: endereço deployado, txHash, bloco, ABI, bytecode, commit — no repositório de deployments.
- Para upgrades: verifique storage layout antes e depois.

### 3.3 Pós-deploy
- Smoke tests em produção: chamadas de leitura, simulação de operação básica.
- Verifique que o indexer detectou e começou a processar eventos do novo contrato.
- Atualize documentação: README, changelog, anúncio para usuários se necessário.
- Configure alertas específicos para o novo contrato.

### 3.4 Gestão de chaves para deploy
- Nunca use EOA pessoal para deploy de contratos de produção.
- Use: hardware wallet, multisig, ou pipeline CI com chave dedicada e auditada.
- Ownership de contratos deve ser transferido para multisig após deploy inicial.
- Documente: quem controla as chaves administrativas, qual o processo de uso.

---

## 4. Gestão de mudanças

### 4.1 Pull Requests
Todo PR deve incluir:
- **Descrição**: o que foi feito e por quê.
- **Risco**: qual o impacto potencial se algo der errado.
- **Testes executados**: quais testes cobrem a mudança.
- **Impacto em dados**: há migração de schema? Breaking change de API?
- **Rollback**: como reverter se necessário.

### 4.2 Changelog
- Mantenha changelog por release no padrão [Keep a Changelog](https://keepachangelog.com).
- Categorias: Added, Changed, Deprecated, Removed, Fixed, Security.
- Versão semântica (SemVer): MAJOR.MINOR.PATCH.
  - MAJOR: breaking change.
  - MINOR: nova feature, backward compatible.
  - PATCH: bugfix, backward compatible.

### 4.3 Backward compatibility como padrão
- APIs: nunca remova ou renomeie campos sem período de depreciação.
- Eventos de contrato: nunca modifique assinatura — crie versão nova.
- Banco: adicione colunas novas como nullable antes de torná-las obrigatórias.
- Se precisar fazer breaking change: versione, comunique com antecedência, mantenha versão antiga por tempo acordado.
