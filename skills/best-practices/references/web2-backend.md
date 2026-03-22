# Boas Práticas Web2 — API, Backend e Dados

## 1. APIs REST

### 1.1 Autenticação e autorização
- Use tokens com expiração curta (access token) + refresh token de longa duração.
- Implemente revogação de tokens (blocklist ou rotação de família em refresh).
- Autorização por recurso (*object-level authorization*): verifique sempre se o usuário tem acesso ao objeto específico, não apenas ao endpoint.
- Nunca confie em IDs passados pelo cliente sem verificar ownership no servidor.

### 1.2 Validação de entrada
- Valide schema de payloads na borda (ex.: `zod`, `pydantic`, `joi`).
- Defina limites explícitos: tamanho máximo de strings, arrays, uploads.
- Sanitize inputs antes de interpolação em queries, comandos ou templates.
- Retorne erros de validação detalhados para o cliente (campo, motivo) — mas nunca stack traces.

### 1.3 Proteção contra abuso
- Rate limiting por IP e por usuário autenticado — limites diferentes para cada.
- Throttling em endpoints de autenticação (login, reset de senha) — prevenção de brute force.
- CORS configurado explicitamente — nunca `Access-Control-Allow-Origin: *` em APIs com autenticação.
- CSRF protection em endpoints que alteram estado via formulários/cookies.
- Headers de segurança: `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`.

### 1.4 Design de endpoints
- Endpoints devem ser idempotentes sempre que possível (especialmente PUT, DELETE).
- Para operações não idempotentes críticas (pagamento, transferência), use `Idempotency-Key` no header.
- Evite expor IDs sequenciais — prefira UUIDs ou IDs opacos.
- Paginação obrigatória em endpoints que retornam listas — nunca retorne listas ilimitadas.

---

## 2. Banco de dados e migrações

### 2.1 Migrações
- Migrações reversíveis quando possível — inclua `up` e `down`.
- Numeradas sequencialmente e versionadas no repositório.
- Nunca execute migrações de schema em produção sem teste em staging primeiro.
- Migrações destrutivas (DROP, truncate) exigem aprovação explícita e backup prévio.
- Para tabelas grandes em produção: use migrações em múltiplos passos (adicionar coluna nullable → popular → adicionar constraint → remover coluna antiga).

### 2.2 Índices
- Crie índices alinhados às queries reais — analise `EXPLAIN ANALYZE` antes de criar.
- Índices em produção: use `CREATE INDEX CONCURRENTLY` para não bloquear leituras.
- Remova índices não utilizados — eles têm custo em writes.
- Índices compostos: a ordem dos campos importa — coloque campos de maior seletividade primeiro.

### 2.3 Dados críticos vs analytics
- Separe dados financeiros/críticos de dados de analytics em schemas ou databases distintos.
- Acesso a dados críticos: mínimo de usuários, auditoria de acesso, sem acesso direto de ferramentas de BI.
- Dados de analytics podem ser eventual consistent — dados críticos precisam de ACID.

### 2.4 Backups
- Backups automatizados com verificação de integridade periódica.
- Teste o processo de restore — backup não testado não existe.
- Política de retenção documentada e seguida.
- Point-in-time recovery (PITR) para bancos críticos.

---

## 3. Consistência e idempotência

### 3.1 Operações idempotentes
- Webhooks e callbacks externos: **sempre** idempotentes — podem ser entregues mais de uma vez.
- Use chaves de idempotência únicas (ex.: `txHash + eventIndex`, `webhookId`).
- Registre eventos processados para detectar e ignorar duplicatas.

### 3.2 Transações de banco
- Use transações de banco para operações que devem ser atômicas.
- Evite transações longas — liberem locks o quanto antes.
- Em sistemas distribuídos, prefira sagas ou outbox pattern a transações distribuídas.

### 3.3 Consistência eventual
- Documente explicitamente onde o sistema é eventual consistent e qual o lag esperado.
- Nunca deixe o usuário descobrir inconsistência sozinho — mostre estado de "processando" quando relevante.

---

## 4. Integrações externas

### 4.1 Resiliência
- Trate falhas de dependências externas como normais — elas vão acontecer.
- Implemente: retries com backoff, circuit breaker, timeouts explícitos.
- Dead-letter queue para mensagens que falharam após N tentativas — não perca eventos críticos.
- Reconciliação periódica para detectar divergências entre sistemas.

### 4.2 Auditoria
- Registre: quem fez, quando, o quê, resultado — sem PII excessiva.
- Logs de auditoria devem ser imutáveis (append-only) e separados de logs operacionais.
- Retenção de auditoria conforme requisitos legais (mínimo 1 ano para operações financeiras).

### 4.3 Contratos de integração
- Documente e versione o contrato de cada integração (schema de request/response).
- Testes de contrato (contract tests) para detectar breaking changes de fornecedores.
- Monitore saúde de dependências externas com health checks próprios.
