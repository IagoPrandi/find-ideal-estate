---
name: mercado-pago
description: >
  Integra e opera pagamentos Mercado Pago neste projeto. Use esta skill quando a tarefa
  envolver MCP oficial do Mercado Pago, Checkout Pro, Pix, webhook, validacao de
  x-signature, credenciais MERCADO_PAGO_*, reconciliacao por external_reference,
  confirmacao de pagamento, expiracao, cancelamento ou troubleshooting de pagamentos
  pendentes/expirados/nao reconciliados.
---

# Skill: mercado-pago

Skill para trabalhar com Mercado Pago neste repositorio sem perder o contrato interno
de billing ja existente.

## Regra de entrada obrigatoria

Antes de executar qualquer tarefa com Mercado Pago:

1. Leia `references/repo-integration.md`.
2. Se a tarefa envolver MCP oficial, conexao de cliente, documentacao oficial ou escolha
   entre MCP e API direta, leia `references/official-mcp-and-docs.md`.
3. Se houver mudanca de codigo, confira os arquivos-chave citados na secao
   "Arquivos-chave do projeto".

Nunca trate "pagamento criado", "checkout aberto" ou "usuario voltou para a UI" como
sinonimo de "pagamento aprovado".

## Fluxo de decisao

### 1. Tarefa de documentacao, onboarding ou uso do MCP

Use esta rota quando o usuario pedir:

- conectar o MCP oficial do Mercado Pago;
- descobrir tools oficiais;
- consultar docs do Mercado Pago sem sair do cliente MCP;
- configurar `.mcp.json` ou `.cursor/mcp.json`;
- comparar quando usar MCP vs API HTTP direta.

Acao:

1. Ler `references/official-mcp-and-docs.md`.
2. Verificar se o cliente MCP alvo esta claramente definido.
3. Se a tarefa for neste repositorio, alinhar a configuracao local com a documentacao
   oficial sem inventar endpoints.

### 2. Tarefa de implementacao no repositorio

Use esta rota quando o usuario pedir:

- checkout Pix ou Checkout Pro;
- webhook;
- polling/reconciliacao;
- ajustes em planos, ativacao ou billing;
- correcoes de `external_reference`, `external_payment_id` ou expiracao;
- ajustes em `.env.example`, `config.py`, testes e UI de pagamento.

Acao:

1. Ler `references/repo-integration.md`.
2. Preservar a arquitetura interna de `billing`.
3. Aplicar a mudanca no backend primeiro, depois alinhar frontend/testes.

### 3. Tarefa de troubleshooting

Use esta rota quando houver:

- pagamento `pending` que nao ativa plano;
- pagamento aprovado fora de sincronia com a base local;
- webhook chegando sem validacao;
- expiracao divergente;
- comprador de teste falhando no sandbox;
- erro por credencial `test` vs `live`.

Acao:

1. Verificar ambiente efetivo (`MERCADO_PAGO_ENVIRONMENT`).
2. Verificar `external_reference`, `external_payment_id` e status salvo localmente.
3. Verificar se o webhook foi validado antes do processamento.
4. Confirmar se a ativacao do plano continua idempotente.

## Guardrails obrigatorios

1. Nunca expor `access token`, `webhook secret` ou credencial em log, teste ou resposta.
2. Nunca marcar um pagamento como aprovado apenas por retorno do frontend.
3. Sempre validar `x-signature` e `x-request-id` antes de processar o payload do webhook.
4. Sempre manter a ativacao de plano idempotente.
5. Sempre persistir o `external_reference` local antes de redirecionar o usuario ao checkout.
6. Nunca trocar o contrato interno do billing sem alinhar `routes`, `service` e testes.
7. Em sandbox, respeitar a regra do projeto para comprador de teste e `payer` prefill.
8. Nunca usar fallback que esconda falha de webhook, reconciliacao ou credencial.

## Checklist de implementacao

### Checkout

- Confirmar qual fluxo esta em uso: MCP, Checkout Pro/preference ou API de pagamentos.
- Persistir pagamento local antes de chamar Mercado Pago.
- Definir `external_reference` igual ao identificador local quando o projeto depender disso.
- Salvar URL do checkout, QR, payload ou metadados retornados pelo provedor.
- Garantir expiracao coerente com configuracao local.

### Webhook

- Receber corpo bruto antes de parsear JSON.
- Validar `x-signature`.
- Extrair `data.id` e `x-request-id`.
- Reconsultar o recurso oficial antes de atualizar estado local.
- Fazer processamento idempotente.

### Reconciliacao

- Primeiro reconciliar por `external_payment_id` quando ele ja existir.
- Se ainda nao existir, buscar por `external_reference`.
- Atualizar status local com base no status real do Mercado Pago.
- So ativar plano em status terminal elegivel.

### Testes

- Cobrir validacao de assinatura.
- Cobrir callback HTTP.
- Cobrir criacao de checkout com usuario autenticado.
- Cobrir reconciliacao por `external_reference`.
- Cobrir regras de sandbox/test user quando aplicavel.

## Arquivos-chave do projeto

- `apps/api/src/modules/billing/mercado_pago.py`
- `apps/api/src/modules/billing/pix.py`
- `apps/api/src/api/routes/billing.py`
- `apps/api/src/core/config.py`
- `apps/api/tests/test_phase8_mercado_pago.py`
- `.env.example`

## Saida esperada

Ao usar esta skill, a resposta final deve deixar claro:

1. qual fluxo foi tratado (`MCP`, `checkout`, `webhook`, `reconciliacao` ou `troubleshooting`);
2. quais arquivos do repositorio foram alterados;
3. quais testes ou verificacoes foram executados;
4. quais variaveis de ambiente ou credenciais ainda faltam;
5. se a pendencia restante e de codigo, ambiente, webhook publico ou operacao manual.

## Referencias

- `references/repo-integration.md`
- `references/official-mcp-and-docs.md`
