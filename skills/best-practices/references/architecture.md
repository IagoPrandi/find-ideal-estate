# Arquitetura de Sistemas Híbridos Web2 + Web3

## 1. Fronteiras de confiança

### 1.1 Front-end é não confiável
- Qualquer verificação feita apenas no front-end pode ser burlada.
- Validações críticas devem existir no **contrato** (on-chain) e/ou no **backend** (off-chain), conforme a ameaça.
- O front-end é responsável por UX — não por segurança ou integridade de dados.

### 1.2 Off-chain não substitui invariantes on-chain
- Regras que protegem fundos, distribuição de prêmios, limites e permissão **devem** estar on-chain.
- Off-chain pode otimizar UX e desempenho, mas não deve "decidir" valores finais críticos.
- Se o backend cair, o contrato deve continuar operando corretamente de forma autônoma.

### 1.3 Custo da imutabilidade
- Contratos mal deployados são caros, lentos e frequentemente irreversíveis de corrigir.
- Priorize revisão extensiva, testes e padrões consagrados antes de qualquer deploy em mainnet.
- "Podemos corrigir depois" não existe em contextos sem upgradeability explícita.

---

## 2. Componentes da arquitetura híbrida

| Componente | Responsabilidade | O que NÃO deve fazer |
|---|---|---|
| **dApp / Web UI** | Conecta carteira, assina, envia txs, exibe estado | Validar regras críticas de negócio |
| **Smart contracts** | Fonte de verdade de regras e estado financeiro | Depender de dados off-chain não verificados |
| **Indexer** (Ponder/The Graph/custom) | Projeções consultáveis: ranking, histórico, dashboards | Ser fonte de verdade de saldo ou resultado |
| **API Web2** | UX, cache, agregações, integrações, dados não críticos | Ser a única camada de autorização para ações on-chain |
| **Banco de dados** | Projeções (event sourcing / materialized views) | Armazenar "regras financeiras" como fonte de verdade |

### 2.1 Fluxo de dados seguro
```
Usuário → Frontend → Backend (authn/authz off-chain) → Contrato (authn/authz on-chain)
                                  ↑
                             Indexer (leitura de eventos)
```

---

## 3. Separação de responsabilidades

- **Contrato**: invariantes, regras financeiras, autorização, emissão de eventos ricos.
- **Indexer**: consistência, reprocessamento, reorg-awareness, normalização de eventos.
- **Backend**: autorização off-chain, rate limiting, cache, integrações de terceiros, dados auxiliares.
- **Frontend**: UX, estado derivado do indexer/backend, feedback de transação ao usuário.

**Regra de ouro**: se um dado é usado para decidir quanto alguém recebe ou pode fazer, ele pertence ao contrato.

---

## 4. Versionamento e compatibilidade

### 4.1 O que versionar obrigatoriamente
- **Esquemas de banco**: migrações com up/down, numeradas sequencialmente.
- **APIs**: versionamento por path (`/v1/`, `/v2/`) ou header — nunca quebrar silenciosamente.
- **ABIs e eventos**: mudanças de campo ou semântica exigem nova versão explícita.
- **Schemas de artifacts**: incluir `schema_version` para retrocompatibilidade de leitura.

### 4.2 Política de depreciação
- Anuncie depreciações com antecedência mínima de um ciclo de release.
- Mantenha backward compatibility até a remoção oficial.
- Documente no changelog: o que foi depreciado, quando será removido, qual alternativa usar.

---

## 5. Estrutura de diretórios recomendada

### 5.1 Backend (Python/Node)
```
app/
├── main.py           # Rotas e borda HTTP — sem lógica de negócio
├── schemas.py        # Contratos de request/response (tipagem, validação)
├── config.py         # Configuração tipada centralizada (lida de env vars)
├── services/         # Casos de uso por domínio — orquestra core + adapters
│   ├── auction.py
│   └── user.py
└── utils/            # Utilitários compartilhados: json, error, log, retry

core/                 # Regras de negócio puras — sem dependência de framework
├── auction.py        # Cálculos, validações de domínio
└── pricing.py

adapters/             # Integração com sistemas externos — sem regra final de negócio
├── rpc.py            # Comunicação com nós blockchain
├── subgraph.py       # Queries ao indexer
└── email.py          # Integração com serviço de e-mail

tests/
├── unit/             # Testa core/ isolado
├── integration/      # Testa services/ com DB/RPC reais ou mockados
├── contract/         # Testa compatibilidade de API (schema)
└── e2e/              # Fluxo completo com carteira simulada
```

### 5.2 Frontend (React/TypeScript)
```
ui/src/
├── App.tsx                  # Composição de layout e fluxo de navegação
├── features/                # Módulos por domínio — evitar "super componente"
│   ├── auction/
│   ├── listings/
│   └── map/
├── hooks/                   # Efeitos, polling, assinatura de eventos
├── state/                   # Estado global e derivado (Zustand, Redux, etc.)
├── api/                     # Cliente HTTP com validação de contrato de resposta
└── components/              # Componentes compartilhados sem regra de domínio
```

### 5.3 Web3 / Smart Contracts
```
contracts/
├── src/
│   ├── Auction.sol          # Contrato principal
│   ├── interfaces/          # Interfaces e tipos compartilhados
│   └── libraries/           # Lógica reutilizável (sem estado)
├── test/
│   ├── unit/
│   ├── integration/
│   └── invariant/           # Property-based / fuzz tests
├── script/
│   ├── Deploy.s.sol
│   └── Upgrade.s.sol
└── deployments/             # ABIs + endereços versionados por rede
    ├── mainnet/
    └── sepolia/
```

---

## 6. Governance de ownership

- Todo módulo deve ter um "owner" técnico explícito (pessoa ou equipe).
- Mudança cross-diretório exige validação de contrato entre as partes e testes de regressão.
- "Mover arquivo" sem justificar fronteira arquitetural é anti-padrão — toda reorganização exige ADR.
- Antes de criar um novo módulo, verifique se já existe um responsável por aquela responsabilidade.
