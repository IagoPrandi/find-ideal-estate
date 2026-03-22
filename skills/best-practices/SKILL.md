---
name: best-practices
description: >
  Orientações completas de boas práticas para desenvolvimento de projetos Web2 + Web3 híbridos.
  Use esta skill SEMPRE que a tarefa envolver: escrever, revisar ou refatorar código (backend, frontend, contratos); 
  projetar arquitetura de sistema; implementar segurança; escrever testes; configurar deploy/CI; 
  definir estratégias de observabilidade; trabalhar com smart contracts, indexadores ou APIs.
  Inclui anti-padrões, checklists de DoD e regras de atuação do agente.
  Ative também quando o usuário mencionar: "boas práticas", "code review", "segurança", "arquitetura", 
  "contrato inteligente", "Solidity", "indexer", "Ponder", "The Graph", "deploy", "testes", "auditoria".
---

# Best Practices — Web2 + Web3 Híbrido

Documento operacional para orientar agentes de IA durante análise, implementação, revisão e manutenção de sistemas híbridos (backend tradicional + blockchain).

## Como usar esta skill

Leia apenas os arquivos relevantes à tarefa atual. Não carregue todos de uma vez.

| Arquivo | Quando ler |
|---|---|
| `references/agent-principles.md` | Toda tarefa — leia primeiro. Regras de atuação e segredos. |
| `references/architecture.md` | Decisões de arquitetura, separação de responsabilidades, estrutura de diretórios |
| `references/code-quality.md` | Revisão de código geral, legibilidade, erros, dependências |
| `references/web2-backend.md` | APIs REST, banco de dados, autenticação, idempotência |
| `references/web3-contracts.md` | Smart contracts, segurança on-chain, upgradeability, indexação, reorgs |
| `references/testing.md` | Estratégia de testes, pirâmide, fuzzing, testes de contrato |
| `references/observability.md` | Logs, métricas, tracing, alertas on-chain |
| `references/deploy-release.md` | CI/CD, deploy de contratos, feature flags, rollback |
| `references/governance-compliance.md` | ADR, privacidade, licenças, papéis administrativos |
| `references/advanced-practices.md` | SLO, rollout incremental, determinismo de testes, maturidade de produto |
| `references/checklists.md` | Definition of Done, anti-padrões, checklist final antes de entregar |

## Regra de entrada obrigatória

**Antes de qualquer tarefa**, leia `references/agent-principles.md`.  
Ele define os limites inegociáveis de segurança e o comportamento esperado do agente.
