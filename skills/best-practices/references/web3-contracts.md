# Boas Práticas Web3 — Contratos, Segurança, Indexação

## 1. Design de contratos inteligentes

### 1.1 Princípios de design
- Contratos pequenos, com responsabilidades claras — prefira múltiplos contratos focados a um "contrato deus".
- Minimize funções públicas e estados mutáveis — cada variável pública é superfície de ataque.
- Emita eventos ricos e semanticamente estáveis — pense na indexação desde o design.
- Evite dependências externas desnecessárias — cada dependência é vetor de risco.
- Separe lógica em libraries sem estado quando possível (mais barato em gas, mais testável).

### 1.2 Eventos para indexação
- Eventos devem ser completos: inclua todos os dados necessários para reconstruir estado sem consultas adicionais.
- Use `indexed` para campos usados em filtros (`address`, `tokenId`, `status`).
- Nunca modifique a assinatura de um evento existente — crie uma versão nova se necessário.
- Documente a semântica de cada evento: o que ele significa, quando é emitido, quais invariantes valem após ele.

---

## 2. Segurança em contratos

### 2.1 Vulnerabilidades clássicas — proteções obrigatórias

**Reentrância**
- Use o padrão Checks-Effects-Interactions (CEI) rigorosamente.
- Para casos complexos, use `ReentrancyGuard` (OpenZeppelin).
- Nunca faça chamadas externas antes de atualizar o estado interno.

```solidity
// Errado
function withdraw(uint amount) external {
    (bool ok,) = msg.sender.call{value: amount}("");  // chamada antes de atualizar saldo
    balances[msg.sender] -= amount;
}

// Correto (CEI)
function withdraw(uint amount) external nonReentrant {
    require(balances[msg.sender] >= amount, "Insufficient");
    balances[msg.sender] -= amount;  // Effects primeiro
    (bool ok,) = msg.sender.call{value: amount}("");  // Interaction por último
    require(ok, "Transfer failed");
}
```

**Overflow/Underflow**
- Solidity 0.8+: proteção nativa — use `unchecked` apenas com justificativa explícita e testes.
- Para Solidity < 0.8: use SafeMath ou migre.

**Controle de acesso**
- Toda função que altera estado crítico deve ter controle de acesso explícito.
- Use `onlyOwner`, `onlyRole` (AccessControl) ou modifiers customizados — nunca assuma.
- Documente: quem pode chamar cada função, em quais condições.
- Prefira `AccessControl` multi-role a `Ownable` simples em contratos com múltiplos administradores.

**Validação de input**
- Valide todos os parâmetros no início da função (fail fast).
- Verifique: endereços não-zero, amounts > 0, limites de array, ranges válidos.
- Nunca confie em dados passados pelo caller sem verificação on-chain.

### 2.2 Aleatoriedade
- `blockhash` e `block.timestamp` são manipuláveis por miners/validators — **nunca** use para sorteios com valor real.
- Para randomness segura: use Chainlink VRF, commit-reveal schemes ou outros oráculos verificáveis.
- Documente explicitamente qual modelo de segurança de randomness é usado e suas limitações.

### 2.3 MEV e front-running
- Identifique operações sensíveis a front-running: swaps, leilões, reveals.
- Mitigações comuns:
  - **Commit-reveal**: submeta hash do valor, revele depois.
  - **Slippage protection**: defina tolerância máxima em swaps.
  - **Batch auctions**: acumule ordens e resolva em lote.
  - **Private mempools**: Flashbots Protect, MEV Blocker para transações sensíveis.
- MEV não é eliminável — avalie se o design do protocolo é robusto mesmo com front-running.

### 2.4 Oracle risks
- Oráculos on-chain (Chainlink, Pyth) podem ser manipulados em condições extremas.
- Nunca use spot price de AMM como oráculo de preço — use TWAP com janela adequada.
- Implemente circuit breakers: pause o protocolo se o preço divergir além de threshold.
- Valide dados do oráculo: timestamp recente, round completo, preço dentro de bounds razoáveis.

### 2.5 Padrões consagrados — use, não reinvente
- OpenZeppelin: ERC20, ERC721, ERC1155, AccessControl, Pausable, ReentrancyGuard.
- Antes de implementar algo do zero, verifique se existe implementação auditada.
- Ao usar dependências auditadas: fixe a versão exata, leia o changelog de segurança.

---

## 3. Upgradeability

### 3.1 Quando usar
- Upgradeability adiciona complexidade e superfície de ataque — use somente com justificativa clara.
- Justificativas válidas: protocolo em fase inicial, possibilidade de bugs críticos, necessidade de governança evolutiva.
- Justificativas inválidas: "para facilitar mudanças futuras" sem risco concreto identificado.

### 3.2 Se usar upgradeability (proxy patterns)
- Proteja upgrades com multisig (Gnosis Safe) + timelock — nunca EOA simples.
- **Storage layout**: colisões de storage são bugs silenciosos e catastróficos.
  - Use `@openzeppelin/upgrades-core` para verificação automática.
  - Nunca reordene variáveis de storage em upgrades.
  - Use storage gaps (`uint256[50] private __gap`) em contratos base.
- Documente: quem pode fazer upgrade, qual o processo de aprovação, qual o delay do timelock.
- Tenha plano de rollback e runbook testado antes de qualquer upgrade em produção.
- Audite cada upgrade como se fosse um contrato novo.

### 3.3 Se não usar upgradeability
- Planeje "módulos" e migração de estado via novos contratos desde o início.
- Documente o processo de migração: como usuários migram saldo, como indexers acompanham.
- Use padrões como factory + registry para facilitar adição de novos contratos sem upgrade.

---

## 4. Transações e UX on-chain

### 4.1 Estados de transação
- Toda transação passa por: `pending → confirmado (N blocos) → finalizado`.
- Mostre ao usuário o estado atual — nunca deixe em "aguardando" sem feedback.
- Trate explicitamente: timeout de pending, transação dropada, reorg que desfaz confirmação.

### 4.2 Confirmações
- Nunca assuma que 1 confirmação é suficiente — depende da chain e do valor em risco.
- Recomendações conservadoras:
  - Ethereum mainnet: 12 confirmações para operações de alto valor.
  - L2s (Arbitrum, Optimism): seguir recomendação oficial de finalidade da chain.
  - Testnets: 1-3 confirmações geralmente suficientes para desenvolvimento.
- Documente a política de confirmações do seu protocolo.

### 4.3 Estimativa de gas
- Sempre estime gas antes de submeter — evite falhas por out-of-gas.
- Adicione margem de segurança (10-20%) sobre a estimativa.
- Monitore variações de gas price — transações travadas em mempool são UX ruim.

---

## 5. Indexação, reorgs e consistência

### 5.1 Reorg-awareness obrigatório
- Reorganizações de blockchain **acontecem** — seu indexer deve tratar como caso normal, não exceção.
- Implemente:
  - Detecção de reorg (comparar `parentHash` do bloco atual com o armazenado).
  - Rollback de projeções para blocos afetados.
  - Reprocessamento automático dos blocos corretos.

### 5.2 Idempotência do banco de projeção
- Chaves únicas por `(txHash, logIndex)` ou `(blockNumber, logIndex)` — nunca processe o mesmo evento duas vezes.
- Operações de upsert ao invés de insert simples para lidar com reprocessamento.
- Teste explicitamente: processar o mesmo bloco duas vezes não deve alterar o estado final.

### 5.3 Estado otimista vs confirmado
- Separe claramente:
  - **Estado otimista**: rápido para UX, baseado em confirmações baixas.
  - **Estado confirmado/final**: seguro para decisões críticas (pagamentos, rankings finais).
- Nunca use estado otimista como base para cálculos financeiros irreversíveis.

### 5.4 Monitoramento do indexer
- Alerte para: atraso de indexação acima do threshold, divergência entre providers RPC, falhas de conexão.
- Dashboards: bloco atual indexado vs bloco atual da chain, taxa de eventos processados, erros por tipo.
- Teste o processo de resync completo — deve ser reproduzível e documentado.
