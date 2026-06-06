# Template — Página de bairro

**Rota:** `/bairros/{slug}`
**Base:** `PRD_MKT_GEO.md` §8.1, §12 · regras em `../content-guidelines.md`
**Consumido por:** gerador automatizado (M3)

> Campos entre `{{ }}` são preenchidos pelo pipeline a partir de métricas normalizadas.
> Onde faltar dado, **declarar a lacuna** — nunca usar proxy ou fallback que esconda o problema.

---

## Entrada esperada (pipeline)

```txt
nome_bairro
slug
metricas_normalizadas:
  transport_score        # 0–100, maior = melhor
  green_score            # 0–100, maior = mais verde
  flood_risk_score       # 0–100, maior = menor risco (invertido)
  safety_score           # 0–100, maior = menor densidade de ocorrências SSP-SP (invertido)
  poi_score              # 0–100, maior = mais serviços
safety_data_coverage     # 'completa' | 'parcial' | 'insuficiente'
real_estate_metrics:
  pricePerM2Sale         # R$/m² — venda (agregado, não anúncio individual)
  pricePerM2Rent         # R$/m²·mês — aluguel (agregado)
  costIndex              # 0–100 (relativo entre distritos)
  trend                  # 'alta' | 'estavel' | 'queda'
  dataAt                 # YYYY-MM-DD
pontos_fortes[]
pontos_atencao[]
lacunas[]                # métricas com cobertura insuficiente
bairros_similares[]
data_atualizacao
```

## Saída obrigatória (estrutura PRD §8.1 + extensões M3)

1. **Título** — `{{nome_bairro}}: dados de transporte, segurança, áreas verdes e qualidade urbana`
2. **Meta description** (única, ≤155 caracteres)
3. **Resumo curto** (citável, único)
4. **Nota de adequação por perfil**
5. **Métricas principais** (barras visuais: transporte, áreas verdes, serviços, risco de alagamento, segurança pública)
6. **Transporte**
7. **Áreas verdes**
8. **Risco de alagamento**
9. **Segurança pública** (com score, fonte SSP-SP e ressalva de sub-registro)
10. **Acesso a serviços / POIs**
11. **Panorama imobiliário** (preço/m² venda, aluguel, índice de custo relativo, tendência — com nota obrigatória de dados agregados)
12. **Pontos fortes**
13. **Pontos de atenção**
14. **Lacunas declaradas** (bloco visual se houver dados ausentes/parciais)
15. **Comparação sugerida** (link para `/comparar/...`)
16. **Metodologia** (link para `/metodologia`)
17. **Data de atualização** (`dateModified` visível)
18. **CTA contextual** para abrir a aplicação (mid)
19. **CTA final** para conversão
20. **FAQ** (transporte, alagamento, segurança pública)
21. **JSON-LD** `Place` + `FAQPage` (inclui pergunta de segurança)

---

## Esqueleto de conteúdo

```md
# {{nome_bairro}}: dados de transporte, segurança, áreas verdes e qualidade urbana

> Atualizado em {{data_atualizacao}} · Metodologia: /metodologia

{{resumo_curto}}

## Para quem este bairro tende a ser adequado
{{nota_adequacao_por_perfil}}

## Indicadores principais
[barras visuais: transporte, áreas verdes, acesso a serviços, risco de alagamento, segurança pública]
| Métrica | Score | Cobertura |
|---|---|---|
| Transporte público | {{transport_score}}/100 | {{transport_coverage}} |
| Áreas verdes | {{green_score}}/100 | {{green_coverage}} |
| Acesso a serviços | {{poi_score}}/100 | {{poi_coverage}} |
| Risco de alagamento | {{flood_risk_score}}/100 ↓ | {{flood_coverage}} |
| Segurança pública | {{safety_score}}/100 | {{safety_coverage}} |

Score de risco e segurança: menor valor = maior exposição/ocorrência relativa.

<!-- CTA contextual (mid) -->
> Quer saber se esta região combina com sua rotina? Abra o BetterPlace e compare bairros, trajetos e preferências.

## Transporte
{{bloco_transporte}}

## Áreas verdes
{{bloco_verde}}

## Risco de alagamento
{{bloco_alagamento}}

## Segurança pública
{{bloco_seguranca}}
<!-- sempre incluir: fonte SSP-SP, ressalva de sub-registro e cobertura (completa/parcial/insuficiente) -->

## Acesso a serviços
{{bloco_servicos}}

## Panorama imobiliário
> Dados agregados por distrito — não representam anúncios individuais. Fonte: BetterPlace. Atualizado em {{real_estate_dataAt}}.

| Indicador | Valor |
|---|---|
| Preço médio/m² — venda | R$ {{pricePerM2Sale}} |
| Preço médio/m² — aluguel | R$ {{pricePerM2Rent}}/m²·mês |
| Custo relativo (0–100) | {{costIndex}}/100 |
| Tendência recente | {{trend}} |

{{bloco_custo_relativo}}
<!-- "Para análise detalhada de imóveis disponíveis neste distrito, acesse a aplicação." -->
<!-- Limitação obrigatória: dados agregados por distrito podem não refletir variações internas entre sub-bairros. -->

## Pontos fortes
{{lista_pontos_fortes}}

## Pontos de atenção
{{lista_pontos_atencao}}

{{#if lacunas}}
<!-- Bloco de lacunas (fundo amarelo) -->
**Lacunas de dados declaradas:**
{{lista_lacunas}}
{{/if}}

## Comparações sugeridas
{{links_comparativos}}

## Bairros similares
{{links_bairros_similares}}

## Perguntas frequentes

### {{nome_bairro}} tem bom transporte público?
{{faq_transporte}}

### {{nome_bairro}} tem risco de alagamento?
{{faq_alagamento}}

### Como é a segurança pública em {{nome_bairro}}?
{{faq_seguranca}}

## Metodologia e limitações
{{lacunas_declaradas}} — detalhes em /metodologia.

<!-- CTA final -->
> Quer transformar esta análise em uma busca prática? Abra a aplicação e veja regiões e imóveis compatíveis.
```

---

## Regras de conformidade

- Aplicar thresholds de copy (`content-guidelines.md` §4.3).
- Proibir termos absolutos (`content-guidelines.md` §4.1).
- CTA contextual no meio + CTA final (página costuma passar de 800 palavras).
- Eventos: `cta_neighborhood_app_click` (contextual e final), com `source_page_type=neighborhood`, `source_slug={{slug}}`.
- Não publicar se não atender os critérios mínimos (`content-guidelines.md` §9.1).
</content>
