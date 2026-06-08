# Mercado Pago no repositorio

## Visao geral

Este projeto ja possui integracao Mercado Pago no modulo de billing do backend. A skill
deve preservar esse desenho em vez de criar um fluxo paralelo.

Arquitetura atual:

- `apps/api/src/modules/billing/mercado_pago.py`: cliente HTTP do Mercado Pago e validacao
  de assinatura do webhook.
- `apps/api/src/modules/billing/pix.py`: orquestracao do pagamento interno, reconciliacao,
  ativacao de plano e processamento do webhook.
- `apps/api/src/api/routes/billing.py`: rotas HTTP do billing.
- `apps/api/tests/test_phase8_mercado_pago.py`: suite focal da integracao.

## Fluxo implementado no projeto

### 1. Criacao do pagamento local

O projeto cria primeiro o registro interno de pagamento e depois usa o identificador local
como `external_reference`.

Regra pratica:

- persistir o pagamento interno;
- gerar `external_reference = str(payment_id)`;
- so entao chamar o Mercado Pago.

### 2. Checkout

O fluxo principal atual usa checkout hospedado por preferencia do Mercado Pago, e nao um
Pix puro via `/v1/payments` como caminho primario da plataforma.

O retorno relevante do provedor deve ser salvo no pagamento local, incluindo quando
disponivel:

- `external_payment_id`
- URL do checkout
- QR/base64 ou metadados de exibicao
- `ticket_url`
- status inicial

### 3. Reconciliacao

Ordem esperada:

1. Se `external_payment_id` existir, consultar por ele.
2. Se ainda nao existir, buscar por `external_reference`.
3. Atualizar o estado local.
4. Ativar plano apenas quando o status real permitir.

O boundary de ativacao deve continuar idempotente.

### 4. Webhook

O callback atual recebe corpo bruto, valida assinatura e so depois interpreta o payload.

Pontos obrigatorios:

- validar `x-signature`;
- usar `x-request-id`;
- extrair `data.id`;
- remontar o manifesto no formato:

```txt
id:{data_id};request-id:{x_request_id};ts:{ts};
```

- reconsultar o pagamento no Mercado Pago antes de alterar estado local.

## Regras de ambiente e credenciais

Configuracoes atuais em `apps/api/src/core/config.py`:

- `PIX_PROVIDER`
- `PIX_PAYMENT_EXPIRATION_MINUTES`
- `MERCADO_PAGO_ENVIRONMENT`
- `MERCADO_PAGO_PUBLIC_KEY_TEST`
- `MERCADO_PAGO_PUBLIC_KEY_LIVE`
- `MERCADO_PAGO_ACCESS_TOKEN_TEST`
- `MERCADO_PAGO_ACCESS_TOKEN_LIVE`
- `MERCADO_PAGO_WEBHOOK_SECRET`
- `MERCADO_PAGO_WEBHOOK_URL`
- `MERCADO_PAGO_CHECKOUT_BACK_URL`
- `MERCADO_PAGO_TIMEOUT_SECONDS`

Observacao:

- `.env.example` precisa continuar refletindo o contrato de configuracao real.
- Se `config.py` introduzir nova variavel, alinhar `.env.example`.

## Regra de sandbox deste projeto

Em ambiente `test`, o projeto evita prefill de `payer` quando o email nao termina em
`@testuser.com`, para reduzir conflito com compradores sandbox do Mercado Pago.

Implicacao:

- nao remova essa regra sem ajustar testes e fluxo de sandbox;
- quando o email terminar em `@testuser.com`, o prefill pode ser usado conforme a logica
  existente.

## Rotas do billing

Rotas ja existentes:

- `GET /billing/plans`
- `POST /billing/pix/checkout`
- `GET /billing/payments/{payment_id}`
- `POST /billing/payments/{payment_id}/cancel`
- `POST /billing/pix/callback`

Ao evoluir a integracao, prefira manter esse contrato e adaptar a implementacao interna.

## Testes existentes

A suite focal cobre pelo menos:

- validacao da assinatura do webhook;
- callback HTTP;
- checkout autenticado;
- regra de `payer` em sandbox;
- busca por `external_reference`;
- reconciliacao por referencia externa.

Arquivo:

- `apps/api/tests/test_phase8_mercado_pago.py`

## Erros comuns a evitar

1. Marcar pagamento como pago sem reconsulta oficial.
2. Processar webhook sem validar assinatura.
3. Perder `external_reference` e inviabilizar reconciliacao.
4. Misturar credenciais `test` e `live`.
5. Mudar fluxo de checkout sem alinhar rotas, UI e testes.
