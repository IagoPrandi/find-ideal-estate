# Skill: Revisão e Correção de Frontends Gerados por IA

Use este skill quando você precisar **avaliar, depurar e melhorar** a estética, estrutura e qualidade técnica de um frontend (web) que foi total ou parcialmente gerado por IA.

> IMPORTANTE: instruções do sistema e do usuário **sempre** têm precedência sobre este skill.

---

## Por que frontends gerados por IA falham (além do óbvio)
Você já citou problemas comuns (overflow, uso ruim de espaço, contraste, falta de coerência, design genérico). Abaixo estão **outros** problemas recorrentes que aparecem quando a IA “fecha” um layout sem uma regra de design explícita.

### 1) Problemas de hierarquia visual e leitura
- **Hierarquia de títulos confusa**: vários H1, títulos com tamanho parecido do corpo, ausência de “escada” (H1→H2→H3).
- **Densidade de informação irregular**: blocos muito “carregados” ao lado de áreas vazias sem intenção.
- **Ritmo de espaçamento incoerente**: paddings e margins variam sem padrão (ex.: 8px, 14px, 23px aleatórios).
- **Tipografia sem sistema**: tamanhos e line-height inconsistentes; falta de escalas (ex.: 12/14/16/20/24...).
- **Comprimento de linha ruim**: parágrafos muito largos em desktop (cansa) ou muito estreitos (quebra demais).

### 2) Responsividade quebrada e “mobile-first” inexistente
- **Breakpoints arbitrários**: muda o layout em larguras estranhas; não cobre 320–375–414–768–1024–1440.
- **Elementos “fixos”** (width/height hardcoded) que estouram em telas pequenas.
- **Conteúdo que depende de uma largura específica** (ex.: cards só “funcionam” em 3 colunas).
- **Menus e modais que não cabem** (altura > viewport; sem scroll interno controlado).

### 3) Acessibilidade (a11y) negligenciada
- **Sem navegação por teclado** (tab order quebrado, foco invisível, traps em modal).
- **Inputs sem label**, placeholders usados como label, ausência de `aria-describedby` para erros.
- **Contraste insuficiente** não só no texto, mas em bordas, ícones, estados de hover/focus.
- **Componentes “clicáveis” sem semântica** (div com onClick no lugar de button/link).
- **Headings e landmarks ausentes** (`main`, `nav`, `header`, `footer`) prejudicando leitores de tela.

### 4) Estados de UI esquecidos
- Falta de **loading**, **empty state**, **error state**, **disabled** e **success feedback**.
- Spinners que **mudam layout** (layout shift), ou carregamento sem esqueleto.
- **Validação de formulário** inconsistente: mensagem some ao digitar; erro em lugar diferente a cada campo.

### 5) Consistência de componentes e design system
- Botões com 5 estilos diferentes (radius, sombra, fonte, padding).
- Cards com bordas/sombras inconsistentes (parece “colcha de retalhos”).
- Ícones de bibliotecas diferentes misturados (traço, preenchimento, tamanhos).
- “Tokens” inexistentes: cores e espaçamentos hardcoded ao invés de variáveis (CSS vars / theme).

### 6) Layout e composição problemáticos (causas técnicas comuns)
- **Uso excessivo de posicionamento absoluto** para “encaixar” elementos.
- **Overflow escondido como gambiarra**: `overflow: hidden` para mascarar bug de layout.
- **Alturas travadas** (ex.: `height: 100vh`) quebrando em mobile por barras do navegador.
- **Grid/Flex mal aplicados**: `justify-between` criando vazios enormes; falta de `min-width: 0` (texto não quebra em flex); falta de `flex-wrap`.
- **Z-index caótico**: modais atrás de overlays; tooltips “cortados” por parents.

### 7) Performance e qualidade de entrega
- **Bundle inflado** por importações desnecessárias; bibliotecas usadas para coisas simples.
- Imagens sem otimização (sem `srcset`, sem dimensionamento, sem lazy-load).
- **Layout shift** (CLS alto) por carregar fontes sem estratégia ou imagens sem tamanho definido.
- Componentes re-renderizando demais por estado global sem necessidade.

### 8) SEO e semântica ignorados
- Páginas sem `title`, meta description, OG tags.
- Uso incorreto de headings afeta SEO e acessibilidade.
- Links sem texto descritivo ("clique aqui"), botões sem `type`.

### 9) Internacionalização e conteúdo real
- Layout “bonito” com **texto curto**, mas quebra com conteúdo real (nomes longos, descrições grandes).
- Strings hardcoded sem suporte a i18n; datas e moedas sem formatação local.

### 10) Manutenibilidade do código
- Nomes inconsistentes (`CardItem`, `itemCard`, `card_item`).
- Duplicação de CSS/estilos em 10 lugares.
- Componentes gigantes sem separação (500+ linhas), difícil testar.
- Dependência de libs inexistentes/hallucinação de imports.

---

## Processo recomendado (do diagnóstico à correção)

### Etapa 0 — Defina regras antes de mexer
- **Design tokens mínimos**: cores (primária/secundária/neutros), escala de espaçamento (ex.: 4–8–12–16–24–32), radius, sombras, tipografia.
- **Grid base**: largura máxima de conteúdo (ex.: 1200–1280px), gutters, breakpoints.
- **Componentes-chave**: botão, input, card, modal, toast/alert, navbar.

### Etapa 1 — Auditoria visual rápida (5–15 min)
- Varra a UI procurando: desalinhamentos, padding irregular, contraste, excesso de estilos.
- Cheque se há “vazios” sem intenção (principalmente em desktop).
- Encontre onde a IA usou “tapa-buraco”: absolute, fixed widths, overflow hidden.

### Etapa 2 — Corrija layout com princípios (não com gambiarras)
- Prefira **flex/grid com regras claras**.
- Evite altura fixa; use `min-height`, `clamp()`, e comportamento fluido.
- Garanta que textos em flex tenham `min-width: 0` e que haja quebra (`overflow-wrap`).

### Etapa 3 — Responsividade por cenários
Testar pelo menos:
- 320–360px (celular pequeno)
- 390–430px (celular grande)
- 768px (tablet)
- 1024px (desktop pequeno)
- 1440px (desktop grande)

### Etapa 4 — Acessibilidade mínima (não-negociável)
- Tudo clicável deve ser `button`/`a`.
- Foco visível e ordem de tab lógica.
- Formulários com label, mensagens de erro associadas.
- Contraste aceitável (texto, ícones, bordas e estados).

### Etapa 5 — Estados e UX
- Defina e implemente: loading, empty, error, success.
- Padronize feedback (toast, inline error, banner).

### Etapa 6 — Performance e “acabamento”
- Imagens com dimensionamento e lazy-load.
- Evite dependências pesadas quando não necessário.
- Revise fontes (pré-carregamento quando fizer sentido) e evite CLS.

---

## Checklist prática de revisão (copiar/colar)

### Layout e espaçamento
- [ ] Não há overflow horizontal (exceto carrosséis intencionais)
- [ ] Escala de espaçamento consistente (ex.: múltiplos de 4/8)
- [ ] Alinhamentos coerentes (grid, baseline, bordas)
- [ ] Componentes respeitam container e max-width

### Tipografia e hierarquia
- [ ] Escala de títulos clara (H1/H2/H3)
- [ ] Line-height e comprimento de linha confortáveis
- [ ] Texto não estoura em flex/grid (min-width: 0 / wrap)

### Cores e estados
- [ ] Contraste legível em texto, ícones, bordas
- [ ] Hover/focus/active/disabled padronizados
- [ ] Não depende só de cor para indicar estado (ex.: erro)

### Responsividade
- [ ] Funciona em 320px e 1440px sem “quebrar”
- [ ] Menus/modais cabem na viewport
- [ ] Tabelas têm estratégia (scroll, colunas adaptativas, cards)

### Acessibilidade
- [ ] Tudo clicável é `button`/`a` com nome acessível
- [ ] Foco visível e tab order correto
- [ ] Form inputs têm label e erro associado

### UX e produto
- [ ] Existem estados: loading / vazio / erro / sucesso
- [ ] Mensagens claras e consistentes
- [ ] Fluxo principal pode ser concluído sem “becos sem saída”

### Performance e qualidade
- [ ] Imagens otimizadas e com dimensões definidas
- [ ] Evita dependências pesadas desnecessárias
- [ ] Sem re-render excessivo em listas/grids

---

## Sinais de “código de IA” que merecem refatoração imediata
- Muitos `div` com `onClick`.
- Classes utilitárias longas e contraditórias (ex.: `p-6 p-4` no mesmo elemento).
- Regras duplicadas e “ajustes finos” repetidos (ex.: `mt-[13px]`, `top-[7px]`).
- Componentes sem limites claros (página inteira dentro de um componente).
- Dependência de bibliotecas que não existem ou APIs inventadas.

---

## Estrutura de pasta de skill no padrão usado internamente (OpenAI)
Uma pasta de skill costuma ser **autoexplicativa** e conter um arquivo principal `skill.md` como ponto de entrada.

Estrutura recomendada:

```
skill_frontend_ai_quality/
  skill.md                    # Guia principal (este arquivo)
  checklists/
    checklist_pronto.md       # Checklists reutilizáveis (opcional)
  templates/
    prompt_de_revisao.md      # Templates de prompt / padrões (opcional)
  examples/
    exemplo_antes_depois.md   # Exemplos curtos e reproduzíveis (opcional)
```

Regras práticas:
- **`skill.md` é obrigatório** e deve funcionar sozinho.
- Arquivos extras são **opcionais**, mas ajudam na adoção (checklists, templates, exemplos).
- Prefira exemplos pequenos e copiáveis.
- Não misture múltiplos “skills” na mesma pasta.

---

## Como usar este skill em um PRD ou revisão de pull request
- Adicione a checklist como **Definition of Done** do frontend.
- Exija evidência: screenshots em breakpoints + auditoria rápida de a11y + verificação de overflow.
- Mantenha “tokens” e componentes base como fonte de verdade (botão/input/card/modal).

