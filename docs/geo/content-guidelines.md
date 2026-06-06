# Diretrizes Editoriais — BetterPlace GEO & AI Visibility

**Documento:** `content-guidelines.md`
**Milestone:** M0 — Decisão de marca, escopo e fundação editorial
**Versão:** 1.0
**Data:** 2026-06-05
**Status:** Proposta (aguarda confirmação do responsável para marcar o milestone)
**Base normativa:** `PRD_MKT_GEO.md` (PRD — BetterPlace GEO & AI Visibility Engine)
**Documentos abertos nesta execução:** `PRD_MKT_GEO.md`, `AGENTS.md`, `CLAUDE.md`, `PRD.md`, `WORK_LOG.md`, `SKILLS_README.md`, `docs/AI_VISIBILITY_GEO_PLAN.md`

> Este documento é a fonte única de verdade editorial para toda a camada pública de
> conteúdo (páginas de bairro, comparativos, relatórios, dataset e comunidade própria).
> Os geradores automatizados (M3, M4, M5, M6) devem consumir estas regras e os templates
> em `docs/geo/templates/`. Nenhuma tarefa aqui depende de terceiros.

---

## 1. Decisão de marca canônica

**Decisão:** a marca pública canônica é **BetterPlace**.

- **Nome canônico (entidade pública):** `BetterPlace`
- **Domínio canônico:** `betterplace.com.br`
- **Descritor interno permitido:** Somente BetterPlace, qualquer citação a "Find Ideal Estate" deve ser substituído por **BetterPlace**

### 1.1 Estado atual no código (verificado)

- `apps/web/index.html` → `<title>BetterPlace</title>` ✔ já canônico.
- `apps/web/src/features/auth/AuthAccessCard.tsx` → exibe "BetterPlace" na UI ✔.
- `apps/web/README.md` → ainda menciona "Find Ideal Estate" (uso interno/documental,
  aceitável; reduzir referência pública quando houver landing de conteúdo).
- Backend/produção já operam sob `api.betterplace.com.br` e `www.betterplace.com.br`.

### 1.2 Ação de redução de "Find Ideal Estate"

- Não criar nenhum novo material público com "Find Ideal Estate".
- Em qualquer superfície indexável (M1+), usar exclusivamente **BetterPlace**.
- Referências internas (README, código, logs) podem permanecer; não são entidade pública.

---

## 2. Posicionamento

### 2.1 Frase de posicionamento (canônica)

> **BetterPlace ajuda pessoas a escolher onde morar usando dados de bairro, mobilidade,
> segurança, áreas verdes e riscos urbanos.**

### 2.2 Variações curtas aprovadas

- "Dados de bairro para decidir onde morar em São Paulo."
- "Compare bairros por transporte, segurança, áreas verdes e riscos urbanos."
- "Decisão de moradia guiada por dados públicos e metodologia transparente."

---

## 3. Tom de voz

O tom deve ser **direto, analítico, confiável, transparente sobre limitações**, sem
exageros comerciais e orientado à decisão.

| Atributo | O que significa na prática |
|---|---|
| Direto | Resposta clara primeiro; contexto depois. |
| Analítico | Toda conclusão aponta para métrica, fonte e metodologia. |
| Confiável | Sem promessas absolutas; sempre declara limitações. |
| Transparente | Declara lacunas de dados em vez de preencher com proxy. |
| Orientado à decisão | Ajuda o usuário a escolher; não vende. |

---

## 4. Termos proibidos e termos recomendados

### 4.1 Termos e frases PROIBIDOS

Nenhum material público pode conter:

- "o melhor bairro de São Paulo" / "melhor bairro" / "pior bairro"
- "o bairro mais seguro" (sem contexto) / "bairro seguro" / "bairro perigoso"
- "garantia de segurança" / "garantia de valorização"
- "ranking definitivo" / "IA comprovou"
- "perfeito para todos"
- "sem risco de alagamento"

### 4.2 Termos e frases RECOMENDADOS

- "melhor para quem prioriza transporte"
- "tende a ser mais adequado para quem busca acesso a metrô"
- "os dados indicam maior presença de áreas verdes"
- "a análise considera dados públicos e metodologia descrita"
- "há limitações de cobertura nesta métrica"
- "a análise indica menor exposição relativa a áreas de alagamento"

### 4.3 Regra de geração automática (espelha PRD §12.3 e §12.4)

O gerador só pode afirmar com base em thresholds. Exemplos canônicos:

```txt
Se transport_score >= 80:  "O bairro se destaca pelo acesso a transporte público."
Se green_score >= 80:      "A região apresenta boa presença relativa de áreas verdes."
Se flood_risk_score <= 30: "A análise indica menor exposição relativa a áreas de alagamento."
Se safety_data_coverage < mínimo: "A métrica de segurança possui cobertura limitada para esta região."
```

Proibido gerar afirmações absolutas (lista §4.1) em qualquer circunstância.

---

## 5. Estrutura dos materiais

As estruturas obrigatórias abaixo resumem o PRD §8 e são detalhadas nos templates:

- Página de bairro → [`templates/template-bairro.md`](templates/template-bairro.md)
- Comparativo → [`templates/template-comparativo.md`](templates/template-comparativo.md)
- Relatório → [`templates/template-relatorio.md`](templates/template-relatorio.md)
- Post de comunidade própria → [`templates/template-post-comunidade.md`](templates/template-post-comunidade.md)

### 5.1 Rotas canônicas (camada pública)

```txt
/
/bairros
/bairros/{slug}
/comparar
/comparar/{bairro-a}-vs-{bairro-b}
/dados
/relatorios
/relatorios/{ano-mes}
/metodologia
/sobre
```

---

## 6. CTAs padrão

Todo material deve ter **pelo menos um** bloco de conversão para a aplicação.

### 6.1 Blocos canônicos

**Bloco curto** (páginas de bairro, posts curtos, trechos intermediários):

```txt
Quer saber se esta região combina com sua rotina? Abra o BetterPlace e compare bairros, trajetos e preferências.
```

**Bloco comparativo** (`/comparar`):

```txt
A melhor escolha depende do seu trajeto, orçamento e prioridades. Use o BetterPlace para fazer uma comparação personalizada entre bairros.
```

**Bloco de relatório** (relatórios mensais/trimestrais):

```txt
Os dados mostram tendências gerais por região. Para transformar a análise em uma decisão prática de moradia, use o BetterPlace e encontre áreas compatíveis com sua rotina.
```

**Bloco de dataset** (`/dados`):

```txt
Estes dados ajudam a entender a cidade em nível agregado. Para aplicar os indicadores à sua busca de moradia, acesse a aplicação BetterPlace.
```

### 6.2 Regra de posicionamento do CTA

- Materiais com até 800 palavras: CTA obrigatório no final.
- Materiais com mais de 800 palavras: CTA contextual no meio **e** CTA final.
- Comparativos: CTA depois da resposta direta **e** no final.
- Relatórios: CTA no resumo executivo **e** no encerramento.
- Posts da comunidade própria: CTA discreto no final, sempre após valor informativo.

### 6.3 Princípio

O CTA deve ser **contextual** (conectado à intenção do usuário), nunca publicidade solta.
O usuário deve sair de qualquer material público para a aplicação em **no máximo um clique**.

---

## 7. Destinos de conversão por tipo de material

Destino da aplicação: `https://www.betterplace.com.br/app` (rota da aplicação interativa).

| Tipo de material | Destino de conversão | Evento de tracking |
|---|---|---|
| Página de bairro (`/bairros/{slug}`) | App pré-filtrado pela região do bairro | `cta_neighborhood_app_click` |
| Comparativo (`/comparar/{a}-vs-{b}`) | App em modo comparação personalizada | `cta_compare_click` |
| Relatório (`/relatorios/{ano-mes}`) | App para aplicar os achados | `cta_report_app_click` |
| Página de dados (`/dados`) | App para explorar regiões | `cta_dataset_app_click` |
| Genérico / home / metodologia | App (entrada padrão) | `cta_app_click` |
| Post de comunidade própria | Página pública relevante → app | `cta_app_click` (com UTM de origem) |

Regra: cada destino deve preservar contexto (ex.: bairro pré-selecionado) sempre que possível.

---

## 8. Tracking de CTA (eventos e parâmetros)

### 8.1 Eventos mínimos (espelha PRD §9 RF8)

```txt
cta_app_click
cta_compare_click
cta_neighborhood_app_click
cta_report_app_click
cta_dataset_app_click
```

### 8.2 Parâmetros mínimos por evento

```txt
source_page_type     # neighborhood | comparison | report | dataset | home | methodology | community
source_slug          # ex.: vila-mariana | pinheiros-vs-vila-mariana | 2026-07
cta_position         # inline | mid | end | hero
cta_copy_variant     # identificador da variante de copy (ex.: curto-a, comparativo-b)
destination_url      # URL final com UTM
```

### 8.3 Convenção de UTM (canônica)

```txt
utm_source   = betterplace_content
utm_medium   = <source_page_type>           # neighborhood | comparison | report | dataset | community
utm_campaign = geo_mvp
utm_content  = <source_slug>__<cta_position>__<cta_copy_variant>
```

Todo CTA deve ser rastreável por evento **e** por UTM (redundância proposital para medir
mesmo quando o analytics de eventos não estiver disponível).

---

## 9. Critérios mínimos de publicação

### 9.1 Página de bairro (espelha PRD §9 RF2)

Publicar `/bairros/{slug}` somente se a região:

- tiver **polígono oficial** — boundary proveniente de
  `data/geo/raw/geoportal_distrito_municipal_v2.gpkg` (96 distritos municipais PMSP),
  ingerido em `neighborhood_boundaries` via `scripts/ingest_distritos_municipais.py`.
  Boundary aproximado ou fecho convexo é proibido em qualquer material público;
- tiver pelo menos **4 grupos de métricas** disponíveis (`is_publishable = TRUE` na view
  `urban_metrics_by_district`);
- tiver **resumo textual único** (passar no piso de unicidade);
- tiver **data de atualização**;
- tiver **metodologia** linkada (`docs/geo/fontes-geograficas.md`);
- **não** for publicada com dados insuficientes sem declarar as lacunas.

### 9.2 Comparativo (espelha PRD §13.3)

Publicar `/comparar/{a}-vs-{b}` somente se:

- os dois bairros tiverem dados suficientes;
- a diferença entre eles gerar análise útil;
- houver intenção provável de busca (demanda aprovada);
- a página tiver conclusão própria;
- a página tiver tabela comparativa e recomendação por perfil;
- **não** for produto cartesiano (geração massiva é proibida).

### 9.3 Regra anti-doorway

Cada página precisa ter dados próprios, resumo próprio e intenção clara. Onde faltar dado,
**declarar a lacuna** — nunca preencher com proxy ou fallback que esconda o problema.

---

## 10. Listas iniciais

- Bairros/distritos prioritários (≥10): [`bairros-prioritarios.md`](bairros-prioritarios.md)
- Comparativos prioritários (≥10): [`comparativos-prioritarios.md`](comparativos-prioritarios.md)

---

## 11. Dependências de terceiros

**Nenhuma.** Todo o M0 é executável por uma pessoa, com artefatos documentais. As frentes
que dependem de terceiros (imprensa, criadores, Wikipedia/Wikidata, Product Hunt, Hacker
News, comunidades externas) ficam para M9, conforme PRD §4 e §16.

---

## 12. Checklist de aprovação do M0 (rastreio)

| Critério (PRD §16 · M0) | Status |
|---|---|
| Existe `content-guidelines.md` | ✔ este documento |
| Decisão explícita de marca canônica | ✔ §1 |
| Templates de bairro, comparativo, relatório e post de comunidade | ✔ `docs/geo/templates/` |
| CTAs padrão | ✔ §6 |
| Destino de conversão por tipo de material | ✔ §7 |
| Lista inicial de ≥10 bairros | ✔ `bairros-prioritarios.md` |
| Lista inicial de ≥10 comparativos | ✔ `comparativos-prioritarios.md` |
| Nenhuma tarefa depende de terceiros | ✔ §11 |

> O tick oficial do milestone no `PRD_MKT_GEO.md` só ocorre **após confirmação explícita
> do responsável** (regra `AGENTS.md`).
</content>
</invoke>
