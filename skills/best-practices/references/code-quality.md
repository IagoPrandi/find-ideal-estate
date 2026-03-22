# Boas Práticas de Código e Design Geral

## 1. Legibilidade e manutenção

### 1.1 Funções e módulos
- Funções curtas, coesas, com nomes que descrevem **o que fazem**, não **como fazem**.
- Regra prática: se uma função precisa de mais de um parágrafo de comentário para explicar o que faz, ela provavelmente deveria ser dividida.
- Evite "classes deus" ou módulos que acumulam responsabilidades não relacionadas.
- Prefira composição sobre herança — interfaces claras e explícitas.

### 1.2 Nomeação
- Variáveis booleanas: prefixe com `is`, `has`, `can`, `should` (`isActive`, `hasPermission`).
- Funções: verbos no imperativo (`calculateFee`, `validateInput`, `emitTransfer`).
- Evite abreviações obscuras — `pricePerUnit` é melhor que `ppu`.
- Constantes: UPPER_SNAKE_CASE com contexto (`MAX_BID_DURATION_SECONDS`, não apenas `MAX_DURATION`).

### 1.3 Comentários
- Comente o **porquê**, não o **o quê** — o código já diz o quê.
- Bons candidatos a comentário: decisões não óbvias, workarounds temporários (com `// TODO: #issue`), invariantes que o compilador não pode verificar.
- Comentários desatualizados são piores que nenhum comentário — remova ou atualize junto com o código.

### 1.4 Remoção de duplicação
- Centralize utilitários comuns: comunicação com RPC, retries, parsing de eventos, formatação de erros.
- Regra dos três: ao copiar código pela terceira vez, abstraia.
- Cuidado com abstrações prematuras — duplicação temporária é melhor que abstração errada.

---

## 2. Configuração e "magic numbers"

### 2.1 Centralize parâmetros
- Centralize em arquivos de config versionados (ex.: `config/networks.ts`, `config/params.py`).
- Use variáveis de ambiente para segredos e endpoints — nunca hardcode.
- Crie registries de parâmetros por rede: chainId, endereços de contrato, thresholds específicos.

### 2.2 Exemplos do que nunca hardcodar
```python
# Ruim
if confirmations >= 12:  # O que é 12? Por quê?

# Bom
FINALITY_CONFIRMATIONS = int(os.getenv("FINALITY_CONFIRMATIONS", "12"))
if confirmations >= FINALITY_CONFIRMATIONS:
```

### 2.3 Feature flags
- Use feature flags para comportamentos que precisam ser alterados sem redeploy.
- Flags devem ter owner, data de criação e critério de remoção documentados.
- Flags não removidas acumulam débito técnico — revise periodicamente.

---

## 3. Tratamento de erros e exceções

### 3.1 Mensagens de erro
- Claras, acionáveis e sem vazar segredos ou stack traces internos para o cliente.
- Inclua contexto suficiente para diagnóstico: qual operação falhou, com quais parâmetros (sanitizados).
- Use códigos de erro padronizados e documentados (ex.: `INSUFFICIENT_BALANCE`, `AUCTION_ENDED`).

### 3.2 Retry e backoff
- Retry **apenas** onde a operação é idempotente ou explicitamente projetada para ser retentada.
- Use exponential backoff com jitter para evitar thundering herd.
- Defina `max_retries` e `max_delay` — retries infinitos mascaram problemas reais.
- Registre cada tentativa com contexto (tentativa N de M, delay, motivo).

### 3.3 Erros esperados vs inesperados
- Erros de negócio (input inválido, recurso não encontrado) → retorne ao cliente com código semântico.
- Erros de infraestrutura (DB indisponível, RPC timeout) → log detalhado internamente, resposta genérica ao cliente, alerta operacional.
- Nunca swallow exceptions silenciosamente — pelo menos logue.

---

## 4. Segurança de dependências

### 4.1 Gestão de versões
- Fixe versões exatas em lockfiles (`package-lock.json`, `poetry.lock`, `Cargo.lock`).
- Nunca use `*` ou ranges abertos (`^`, `~`) em dependências de produção sem entender o impacto.
- Atualizações de dependências: leia o changelog, rode a suíte completa de testes, faça em PR separado.

### 4.2 Avaliação de novas dependências
- Antes de adicionar uma biblioteca, pergunte: posso implementar isso em 20 linhas sem dependência externa?
- Verifique: data do último commit, número de mantenedores, histórico de vulnerabilidades, licença.
- Evite dependências transitivas de alto risco — um `npm install` pode trazer dezenas de pacotes.

### 4.3 Scanning contínuo
- Configure scanner de vulnerabilidades (SCA) no CI: `npm audit`, `safety` (Python), `cargo audit`, Snyk, Dependabot.
- Trate vulnerabilidades críticas como bugs bloqueadores de deploy.
- Revise alerts de segurança semanalmente — não deixe acumular.

---

## 5. TypeScript / tipos estáticos

- Ative `strict: true` — nunca desative para "facilitar".
- Evite `any` — se precisar, use `unknown` e faça narrowing explícito.
- Tipos de domínio devem ser distintos de tipos de infraestrutura: crie types/interfaces próprios, não reutilize DTOs da API como objetos de domínio.
- Use `zod` ou equivalente para validação de entrada em runtime além dos tipos estáticos.

---

## 6. Performance responsável

- Otimize apenas o que está medido como gargalo — não antecipe.
- Prefira legibilidade sobre micro-otimização em código de negócio.
- Cache deve ser explícito, com TTL definido e estratégia de invalidação documentada.
- N+1 queries são bugs, não "otimizações futuras" — detecte com query logging em desenvolvimento.
