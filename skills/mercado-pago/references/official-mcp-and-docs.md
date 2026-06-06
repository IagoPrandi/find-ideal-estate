# Mercado Pago oficial: MCP e documentacao

## MCP oficial

O MCP oficial do Mercado Pago e remoto e usa o endpoint:

```txt
https://mcp.mercadopago.com/mcp
```

Exemplo oficial de configuracao em cliente compativel:

```json
{
  "mcpServers": {
    "mercadopago-mcp-server": {
      "url": "https://mcp.mercadopago.com/mcp"
    }
  }
}
```

Referencia oficial:

- Overview: https://www.mercadopago.com.br/developers/pt/docs/mcp-server/overview
- Connection: https://www.mercadopago.com.br/developers/en/docs/mcp-server/connection

O MCP oficial cobre onboarding e operacao assistida, incluindo:

- consulta de documentacao;
- gerenciamento de aplicacoes e credenciais;
- configuracao e monitoramento de webhooks;
- criacao de usuarios de teste;
- apoio a validacao da integracao.

## Quando usar MCP

Use MCP quando a tarefa for:

- conectar um cliente de IA ao ecossistema do Mercado Pago;
- navegar docs oficiais sem sair do ambiente do agente;
- descobrir tools oficiais;
- apoiar onboarding da conta/integracao;
- orientar operacoes de teste e validacao.

## Quando usar API direta do projeto

Use a API HTTP do proprio projeto quando a tarefa for:

- implementar checkout dentro da plataforma;
- tratar webhook do backend;
- persistir `external_reference` e reconciliar pagamentos locais;
- ajustar UI/UX da cobranca;
- escrever testes automatizados do repositorio.

MCP nao substitui o contrato interno do modulo de billing.

## Documentacao oficial util

### Pix via API de pagamentos

Doc oficial:

- https://www.mercadopago.com.br/developers/en/docs/checkout-api-payments/integration-configuration/integrate-pix

Pontos uteis:

- o pagamento Pix pode receber `date_of_expiration`;
- a expiracao configurada deve ficar entre 30 minutos e 30 dias a partir da emissao;
- o default documentado e 24 horas.

### Notificacoes e webhook

Doc oficial:

- https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/payment-notifications

Pontos uteis:

- o header de autenticidade e `x-signature`;
- o formato esperado inclui `ts` e `v1`;
- o manifesto de validacao usa `data.id`, `x-request-id` e `ts`;
- depois do webhook, o caminho correto e consultar o recurso oficial antes de decidir o
  estado local.

## Regra pratica para esta skill

Se o usuario disser "conecte ao MCP do Mercado Pago", trate isso como pedido de usar a
documentacao e o endpoint oficiais do MCP.

Se o usuario disser "implemente Mercado Pago na plataforma", trate isso como pedido de
editar a integracao do repositorio, usando o modulo interno de billing como base.
