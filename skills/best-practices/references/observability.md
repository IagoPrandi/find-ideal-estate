# Observabilidade e Operação

## 1. Os três pilares

### 1.1 Logs estruturados
- Use JSON como formato padrão — facilita parsing, busca e agregação.
- Inclua campos de correlação em todo log: `requestId`, `traceId`, `txHash`, `userId` (anonimizado).
- Níveis semânticos:
  - `ERROR`: requer ação humana imediata.
  - `WARN`: degradação ou condição inesperada, não crítica ainda.
  - `INFO`: eventos de negócio relevantes (operação iniciada, concluída, falhou).
  - `DEBUG`: detalhe técnico para diagnóstico — desabilitado em produção por padrão.
- **Nunca logue**: senhas, tokens, seed phrases, dados completos de cartão, PII não necessária.
- Sanitize antes de logar: mascare campos sensíveis, truncue payloads grandes.

```json
// Exemplo de log bem estruturado
{
  "level": "info",
  "timestamp": "2024-01-15T10:23:45.123Z",
  "requestId": "req_abc123",
  "traceId": "trace_xyz789",
  "event": "auction.bid.accepted",
  "auctionId": "auction_42",
  "bidder": "0x1234...abcd",
  "amount": "1500000000000000000",
  "durationMs": 45
}
```

### 1.2 Métricas
Métricas mínimas obrigatórias por categoria:

**API / Backend**
- Latência por endpoint (p50, p95, p99).
- Taxa de erros (4xx, 5xx) por endpoint.
- Throughput (requests/segundo).
- Tamanho de connection pool e uso.

**Indexer / Blockchain**
- Bloco atual indexado vs bloco atual da chain (lag).
- Taxa de eventos processados por segundo.
- Número de reorgs detectados e reprocessados.
- Divergência entre providers RPC (se usar múltiplos).
- Taxa de falhas de transação monitorada.

**Infraestrutura**
- CPU, memória, disco, I/O por serviço.
- Tamanho de filas (jobs pendentes, dead-letter).
- Uptime e disponibilidade.

### 1.3 Tracing distribuído
- Configure quando houver múltiplos serviços (API + indexer + workers).
- Propague `traceId` entre serviços via headers (`X-Trace-Id` ou padrão OpenTelemetry).
- Use para diagnosticar latência: identifique qual serviço está causando lentidão.
- Ferramentas: OpenTelemetry + Jaeger/Tempo/Datadog.

---

## 2. Monitoramento on-chain

### 2.1 Alertas obrigatórios para eventos críticos
- Upgrades de contrato (proxy).
- Ativação/desativação de Pause.
- Grandes transferências acima de threshold.
- Mudanças de ownership ou permissões administrativas.
- Ativação de funções de emergência.

### 2.2 Anomalias que merecem alerta
- Picos de falhas de transação acima da baseline.
- Gas price spike que possa travar operações.
- Volume de operações fora do range histórico (possível ataque ou bug).
- Indexer atrasado além do SLO definido.
- Provider RPC retornando dados divergentes entre si.

### 2.3 Ferramentas de monitoramento on-chain
- **Tenderly**: alertas de eventos, simulações de transação.
- **OpenZeppelin Defender**: monitoramento e automação.
- **Forta**: rede de bots de detecção de anomalias.
- **Dune Analytics**: dashboards públicos de métricas on-chain.
- **Alchemy / Quicknode Notify**: webhooks para eventos específicos.

---

## 3. Runbooks operacionais

### 3.1 O que todo runbook deve ter
- **Título**: nome do incidente/operação.
- **Trigger**: quando executar este runbook.
- **Impacto**: o que está afetado, severidade.
- **Diagnóstico**: passos para confirmar o problema e coletar evidências.
- **Mitigação**: ações imediatas para reduzir impacto.
- **Resolução**: solução definitiva.
- **Verificação**: como confirmar que o problema foi resolvido.
- **Post-mortem**: link para onde registrar o incidente.

### 3.2 Runbooks mínimos obrigatórios
- Indexer parado ou atrasado.
- Provider RPC principal indisponível.
- Contrato pausado (procedimento de ativação de emergência).
- Credencial comprometida.
- Deploy revertido em produção.

---

## 4. Alertas e on-call

- Alertas devem ser acionáveis — alerta sem ação possível gera fadiga e é ignorado.
- Cada alerta deve ter: severidade (P1/P2/P3), owner responsável, runbook associado.
- P1 (produção fora do ar, perda de fundos): resposta imediata, escala automática.
- P2 (degradação, componente não crítico): resposta em horas.
- P3 (aviso, tendência preocupante): resposta em dias.
- Revise alertas periodicamente: remova os que nunca disparam ou que sempre são ignorados.
