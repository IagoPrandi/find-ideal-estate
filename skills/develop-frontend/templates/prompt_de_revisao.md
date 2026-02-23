# Template de prompt — Revisão de UI gerada por IA

Use este template para orientar uma IA (ou um revisor) a corrigir UI sem “gambiarra”.

## Prompt

Você é um revisor de frontend. Analise o layout e proponha correções seguindo estes critérios:

1) **Semântica e acessibilidade**: use `button/a`, foco visível, labels em forms, landmarks (`main/nav/header/footer`).
2) **Layout e espaçamento**: padronize spacing em múltiplos de 4/8; elimine `absolute` desnecessário; evite `overflow: hidden` como correção.
3) **Responsividade**: garanta bom comportamento em 320, 390, 768, 1024, 1440px; menus/modais devem caber na viewport.
4) **Consistência visual**: componentes com tokens (cores, radius, sombras, tipografia), estados (hover/focus/disabled).
5) **Estados de UI**: inclua loading/empty/error/success.

Entregue:
- Lista priorizada de problemas (com severidade)
- Mudanças recomendadas (o que e por quê)
- Trechos de código apenas quando necessário, evitando dependências novas

