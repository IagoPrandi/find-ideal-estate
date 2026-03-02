# FE6 — Checklist de regressão visual (frontend)

Executar após smoke E2E do frontend (UI + API em Docker) e registrar evidência (screenshot/captura de tela).

## 1) Mapa e camadas
- [ ] Camada de ônibus aparece quando ativa e desaparece quando desativada.
- [ ] Camada de trilhos aparece quando ativa e desaparece quando desativada.
- [ ] Camada de alagamento respeita opacidade e não cobre controles principais.
- [ ] Camada de área verde respeita opacidade e não cobre controles principais.
- [ ] POIs aparecem com marcador circular e contraste suficiente.

## 2) Legenda
- [ ] Legenda mostra somente camadas ativas.
- [ ] Legenda não apresenta overflow horizontal em 360px, 768px e desktop.

## 3) Painel lateral
- [ ] Botão Minimizar/Abrir funciona sem quebrar layout.
- [ ] Com painel minimizado, controles do mapa permanecem clicáveis.
- [ ] Em telas menores, painel permanece no formato bottom sheet.

## 4) Estados e conteúdo
- [ ] Estado loading aparece durante criação/polling de run.
- [ ] Estado vazio (zonas sem features) exibe mensagem acionável.
- [ ] Estado de erro recuperável exibe ação de retentativa.
- [ ] Labels longos em interesses/cards não quebram o layout.

## 5) Acessibilidade rápida
- [ ] Ordem de tab alcança busca, camadas, zoom, ajuda e painel.
- [ ] Foco visível presente em elementos interativos principais.
- [ ] Modal de ajuda abre e fecha por botão; `Esc` fecha modal.
