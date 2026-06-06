---
name: geo-content
description: >
  Gera e revisa materiais públicos da estratégia GEO e AI Visibility Engine do BetterPlace.
  Use esta skill SEMPRE que precisar criar ou revisar: página de bairro (/bairros/{slug}),
  comparativo (/comparar/{a}-vs-{b}), relatório recorrente (/relatorios/{ano-mes}),
  post de comunidade própria, bloco da página de dados (/dados), texto de metodologia,
  ou variante de CTA. Garante estrutura obrigatória, tom de voz, termos proibidos,
  blocos de CTA rastreáveis e critérios de indexabilidade — sem revisão manual caso a caso.
  Base normativa: PRD_MKT_GEO.md (seções 7, 8, 12, 13, 22) e docs/geo/content-guidelines.md.
---

# Skill: geo-content

Skill de geração padronizada de materiais GEO e AI Visibility para o BetterPlace.

---

## Regra de entrada obrigatória

**Antes de gerar qualquer material**, leia:

1. `docs/geo/content-guidelines.md` — fonte única de verdade editorial (marca, tom, CTAs, termos, critérios).
2. O template correspondente ao tipo solicitado (ver §Tipos e templates).
3. Os dados de entrada fornecidos pelo usuário (nome do bairro, métricas, período etc.).

Nunca gere conteúdo sem carregar o template do tipo correspondente.

---

## Tipos e templates

| Tipo | Rota | Template |
|---|---|---|
| `bairro` | `/bairros/{slug}` | `docs/geo/templates/template-bairro.md` |
| `comparativo` | `/comparar/{a}-vs-{b}` | `docs/geo/templates/template-comparativo.md` |
| `relatorio` | `/relatorios/{ano-mes}` | `docs/geo/templates/template-relatorio.md` |
| `post` | comunidade própria | `docs/geo/templates/template-post-comunidade.md` |
| `dados` | `/dados` | `docs/geo/content-guidelines.md` §6 bloco dataset |
| `metodologia` | `/metodologia` | `docs/geo/content-guidelines.md` §9 |
| `cta` | qualquer | `docs/geo/content-guidelines.md` §6 |

---

## Comportamentos obrigatórios

### 1. Carregar o template correto
Leia o arquivo de template antes de gerar. Não improvise estrutura.

### 2. Aplicar regras de copy (thresholds)

```txt
Se transport_score >= 80:  "O bairro se destaca pelo acesso a transporte público."
Se green_score >= 80:      "A região apresenta boa presença relativa de áreas verdes."
Se flood_risk_score <= 30: "A análise indica menor exposição relativa a áreas de alagamento."
Se safety_data_coverage < mínimo: "A métrica de segurança possui cobertura limitada para esta região."
```

Toda conclusão deve apontar para métrica, fonte e metodologia. Nenhuma afirmação sem dado.

### 3. Verificar e bloquear termos proibidos

Antes de finalizar, varrer o output por estes termos — se encontrar, substituir pela alternativa recomendada:

| Proibido | Substituir por |
|---|---|
| "o melhor bairro de São Paulo" / "melhor bairro" | "melhor para quem prioriza [critério]" |
| "pior bairro" | [remover ou reformular com dado] |
| "bairro seguro" / "bairro perigoso" | "tende a apresentar [indicador] relativo de segurança" |
| "o bairro mais seguro" (sem contexto) | "apresenta [métrica] acima da média" |
| "garantia de segurança" / "garantia de valorização" | [remover — nunca fazer promessas absolutas] |
| "ranking definitivo" | "análise comparativa com base em dados públicos" |
| "IA comprovou" | [remover — nunca] |
| "perfeito para todos" | [remover — nunca] |
| "sem risco de alagamento" | "a análise indica menor exposição relativa a áreas de alagamento" |
| "Find Ideal Estate" (em material público) | "BetterPlace" |

### 4. Aplicar tom de voz

- **Direto**: resposta clara primeiro; contexto depois.
- **Analítico**: toda conclusão aponta para dado, fonte, metodologia.
- **Confiável**: sem promessas absolutas; declara limitações.
- **Transparente**: declara lacunas de dados em vez de preencher com proxy.
- **Orientado à decisão**: ajuda o usuário a escolher; não vende.

### 5. Inserir CTA obrigatório

Regra de posicionamento:

- Material até 800 palavras → CTA no final.
- Material acima de 800 palavras → CTA contextual no meio **e** CTA final.
- Comparativo → CTA após resposta direta **e** no final.
- Relatório → CTA no resumo executivo **e** no encerramento.
- Post de comunidade → CTA discreto no final, após valor informativo.

Blocos canônicos (`docs/geo/content-guidelines.md` §6.1):

```txt
[BAIRRO / CURTO]
Quer saber se esta região combina com sua rotina? Abra o BetterPlace e compare bairros, trajetos e preferências.

[COMPARATIVO]
A melhor escolha depende do seu trajeto, orçamento e prioridades. Use o BetterPlace para fazer uma comparação personalizada entre bairros.

[RELATÓRIO]
Os dados mostram tendências gerais por região. Para transformar a análise em uma decisão prática de moradia, use o BetterPlace e encontre áreas compatíveis com sua rotina.

[DATASET / DADOS]
Estes dados ajudam a entender a cidade em nível agregado. Para aplicar os indicadores à sua busca de moradia, acesse a aplicação BetterPlace.
```

### 6. Verificar estrutura obrigatória

Antes de entregar, conferir que todos os campos do template estão preenchidos. Para campos ausentes por falta de dados: **declarar a lacuna explicitamente** — nunca omitir em silêncio.

Exemplo de lacuna:
```txt
Métrica de segurança: cobertura insuficiente para esta região na data de atualização atual.
```

### 7. Gerar metadados

Para `bairro` e `comparativo`, gerar obrigatoriamente:

```txt
título único
meta description única (até 160 caracteres)
canonical URL
dateModified
JSON-LD adequado ao tipo (Place / Article / FAQPage)
```

### 8. Validar unicidade textual

Resumo e conclusão não podem ser idênticos aos de outra página. Se o input for igual ao de outro bairro/comparativo, sinalizar: "Resumo potencialmente duplicado — revisar diferenciação."

### 9. Adicionar rastreamento nos CTAs

Todo link de CTA deve incluir UTM canônico:

```txt
utm_source   = betterplace_content
utm_medium   = <source_page_type>
utm_campaign = geo_mvp
utm_content  = <source_slug>__<cta_position>__<cta_copy_variant>
```

Eventos de tracking correspondentes:

```txt
cta_neighborhood_app_click  → páginas de bairro
cta_compare_click           → comparativos
cta_report_app_click        → relatórios
cta_dataset_app_click       → dados
cta_app_click               → genérico / metodologia / post de comunidade
```

### 10. Declarar lacunas de dados

Se qualquer métrica estiver ausente ou com cobertura abaixo do mínimo, declarar explicitamente no campo correspondente. Nunca preencher com valor aproximado sem indicar que é estimado.

---

## Regras invioláveis

1. **Nunca** gerar afirmações absolutas (lista §3 acima).
2. **Nunca** publicar página sem data de atualização.
3. **Nunca** omitir CTA em nenhum material.
4. **Nunca** usar "Find Ideal Estate" como nome público.
5. **Nunca** gerar comparativo sem verificar se ambos os bairros têm dados suficientes.
6. **Nunca** gerar comparativo sem conclusão própria.
7. **Nunca** inserir CTA genérico sem conectar à intenção do conteúdo.
8. **Todo** link de CTA deve ser rastreável por UTM **e** evento.
9. **Nunca** gerar conteúdo sem carregar o template correspondente.
10. **Nunca** usar fallback que esconda lacunas — sempre declarar o problema.

---

## Saída esperada

Para cada material gerado, entregar:

```txt
1. Conteúdo completo (Markdown ou HTML conforme o tipo)
2. Lista de campos preenchidos
3. Lista de campos ausentes / lacunas declaradas
4. Lista de CTAs inseridos (posição + variante + UTM)
5. Aviso de bloqueio se termo proibido foi detectado na entrada
6. Checklist de critérios de aprovação do milestone correspondente:
   — bairro      → M3
   — comparativo → M4
   — relatorio   → M6
   — post        → M8
   — dados       → M5
```

---

## Critérios de elegibilidade por tipo

### Bairro (`/bairros/{slug}`)
Publicar somente se:
- tiver polígono oficial (não fecho convexo);
- tiver ≥4 grupos de métricas disponíveis;
- tiver resumo textual único;
- tiver data de atualização;
- tiver metodologia linkada;
- lacunas declaradas onde existirem.

### Comparativo (`/comparar/{a}-vs-{b}`)
Publicar somente se:
- ambos os bairros tiverem dados suficientes;
- a diferença gerar análise útil;
- houver intenção aprovada de busca (par na lista `comparativos-prioritarios.md` ou demanda real);
- tiver conclusão própria, tabela comparativa, recomendação por perfil;
- não for geração cartesiana não aprovada.

---

## Exemplo de invocação

```txt
/geo-content bairro --nome "Vila Mariana" --metricas dados.json
/geo-content comparativo --bairro-a "Pinheiros" --bairro-b "Vila Mariana"
/geo-content relatorio --periodo "2026-07"
/geo-content post --tipo comparativo --tema "Pinheiros vs Itaim Bibi"
/geo-content cta --tipo bairro --posicao final
```

---

## Integração com o pipeline automatizado (PRD §11.3)

| Saída da skill | Etapa do pipeline |
|---|---|
| `/geo-content bairro` | Etapa 6 — gerar páginas `/bairros` |
| `/geo-content comparativo` | Etapa 7 — gerar comparativos aprovados |
| `/geo-content relatorio` | Etapa 10 — gerar relatório periódico |
| `/geo-content post` | Fluxo editorial da comunidade própria (M8) |
| `/geo-content dados` | Etapa 9 — gerar dataset e página `/dados` |

---

## Referências normativas

- `PRD_MKT_GEO.md` — seções 7 (posicionamento/tom), 8 (estrutura), 12 (copy rules), 13 (comparativos), 22 (spec da skill)
- `docs/geo/content-guidelines.md` — fonte única de verdade editorial
- `docs/geo/bairros-prioritarios.md` — lista canônica de bairros
- `docs/geo/comparativos-prioritarios.md` — lista canônica de comparativos aprovados
- `docs/geo/templates/template-bairro.md`
- `docs/geo/templates/template-comparativo.md`
- `docs/geo/templates/template-relatorio.md`
- `docs/geo/templates/template-post-comunidade.md`
