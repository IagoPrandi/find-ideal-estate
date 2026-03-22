# Testes e Verificação

## 1. Pirâmide de testes

A pirâmide define a proporção ideal: muitos testes unitários, menos de integração, poucos E2E.

```
        /\
       /  \   E2E (poucos, lentos, alto valor)
      /----\
     /      \  Integration (moderado)
    /--------\
   /          \  Unit (muitos, rápidos, isolados)
  /____________\
```

### 1.1 Testes unitários
- Testam lógica isolada sem dependências externas (DB, RPC, filesystem).
- Use mocks/stubs para dependências — teste o comportamento, não a implementação.
- Devem ser rápidos (< 1ms por teste) e rodar sem configuração de ambiente.
- Cobertura: priorize branches de condição e casos de borda, não linhas.

### 1.2 Testes de integração
- Testam a interação entre componentes reais: backend + DB, indexer + eventos, contratos em ambiente local.
- Use containers (Docker) para isolar dependências reais.
- Cada teste deve limpar seu estado (setup/teardown explícito).
- Mais lentos que unitários — organize para rodar em paralelo quando possível.

### 1.3 Testes E2E
- Simulam o fluxo completo do usuário com carteira simulada (Anvil, Hardhat).
- Poucos e focados nos happy paths e critical paths mais importantes.
- Rodam no CI, mas podem ser separados em pipeline mais lento.
- Falhas em E2E são bloqueadoras de deploy — mantenha estável.

---

## 2. Testes específicos para Web3

### 2.1 Testes de contrato (Foundry/Hardhat)
```solidity
// Exemplo com Foundry
contract AuctionTest is Test {
    Auction auction;
    
    function setUp() public {
        auction = new Auction(/* params */);
    }
    
    function test_BidIncreasesHighestBid() public {
        auction.bid{value: 1 ether}();
        assertEq(auction.highestBid(), 1 ether);
    }
    
    function test_RevertIf_BidBelowMinimum() public {
        vm.expectRevert("BID_TOO_LOW");
        auction.bid{value: 0.001 ether}();
    }
    
    function test_RevertIf_AuctionEnded() public {
        vm.warp(block.timestamp + 7 days);  // avança tempo
        vm.expectRevert("AUCTION_ENDED");
        auction.bid{value: 1 ether}();
    }
}
```

### 2.2 Fork tests (mainnet/testnet fork)
- Use para testar integrações com contratos reais já deployados (Uniswap, Chainlink, etc.).
- `vm.createFork(rpcUrl, blockNumber)` — fixe o bloco para reprodutibilidade.
- Úteis para: simular condições reais de liquidez, testar oráculos, verificar integrações.
- Mais lentos — separe em suite específica no CI.

### 2.3 Property-based tests (Fuzz tests)
- Foundry tem fuzzing nativo — qualquer função com parâmetros é automaticamente fuzzed.
- Defina invariantes do protocolo e escreva testes que as verificam com inputs aleatórios.

```solidity
// Foundry fuzz test
function testFuzz_BalanceNeverExceedsDeposit(uint96 amount) public {
    vm.assume(amount > 0 && amount < 1000 ether);
    pool.deposit{value: amount}();
    assertLe(pool.balanceOf(address(this)), amount);
}
```

### 2.4 Invariant tests (stateful fuzzing)
- Testam invariantes globais após sequências aleatórias de chamadas.
- Exemplos de invariantes:
  - Somatório de saldos == total depositado.
  - Nenhum usuário pode sacar mais do que depositou.
  - Contrato pausado nunca processa transações.

```solidity
// Foundry invariant test
contract PoolInvariantTest is Test {
    function invariant_TotalBalanceEqualsDeposits() public {
        assertEq(pool.totalBalance(), pool.totalDeposits());
    }
}
```

### 2.5 Simulações de adversário
- Escreva testes que ativamente tentam quebrar o contrato:
  - Reentrancy attacks: contrato malicioso que chama de volta na função alvo.
  - Front-running: simule com `vm.prank` e `vm.roll` para orquestrar ordem de transações.
  - Flash loans: simule saldo infinito temporário para testar manipulação de oráculo.
  - Inputs maliciosos: zero address, overflow, array vazio, chamadas repetidas.

### 2.6 Testes de eventos
- Verifique que eventos são emitidos com os parâmetros corretos.
- Teste compatibilidade de schema: se o indexer depende de um campo, garanta que o contrato o emite.
- `vm.expectEmit()` no Foundry para verificar eventos com precisão.

---

## 3. Testes de regressão e qualidade

### 3.1 Regra de ouro
- **Todo bug corrigido deve ganhar um teste de regressão** que reproduz o bug antes da correção.
- Nomeie o teste com referência ao issue: `test_Fix_Issue123_WithdrawRevertsOnReentrancy`.

### 3.2 Critérios de aceitação
- Cobertura de linhas não é o objetivo — é consequência de testar invariantes e casos de borda.
- Priorize testar:
  - Invariantes de domínio (conservação de valor, consistência de estado).
  - Casos de borda (zero, máximo, vazio, expirado).
  - Caminhos de erro (reverts, falhas esperadas).
- Um teste que passa sempre sem verificar nada é pior que nenhum teste.

### 3.3 Determinismo e reprodutibilidade
- Testes não devem depender de: hora do sistema, rede externa, ordem de execução, dados de ambiente.
- Use seeds fixas para aleatoriedade, fixtures para dados, mocks para dependências externas.
- Se um teste flaky aparece: pause e corrija — não ignore.

---

## 4. Ferramentas recomendadas

| Contexto | Ferramenta |
|---|---|
| Contratos Solidity | Foundry (forge test, fuzz, invariant) |
| Contratos (alternativo) | Hardhat + Waffle/Chai |
| Backend Python | pytest + pytest-cov |
| Backend Node/TS | Jest ou Vitest |
| Property-based (Python) | Hypothesis |
| Contract tests de API | Pact |
| E2E Web | Playwright |
| Análise estática Solidity | Slither, Mythril |
| Cobertura de contratos | forge coverage |
