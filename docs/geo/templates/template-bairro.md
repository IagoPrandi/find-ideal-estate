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
metricas_normalizadas      # transporte, segurança, áreas verdes, alagamento, POIs/serviços
ranking_relativo
pontos_fortes[]
pontos_atencao[]
lacunas[]                  # métricas com cobertura insuficiente
bairros_similares[]
data_atualizacao
```

## Saída obrigatória (estrutura PRD §8.1)

1. **Título** — `{{nome_bairro}}: dados de transporte, segurança, áreas verdes e qualidade urbana`
2. **Meta description** (única, ≤155 caracteres)
3. **Resumo curto** (citável, único)
4. **Nota de adequação por perfil**
5. **Métricas principais** (tabela)
6. **Transporte**
7. **Segurança**
8. **Áreas verdes**
9. **Risco de alagamento**
10. **Acesso a serviços / POIs**
11. **Pontos fortes**
12. **Pontos de atenção**
13. **Comparação sugerida** (link para `/comparar/...`)
14. **Metodologia** (link para `/metodologia`)
15. **Data de atualização** (`dateModified` visível)
16. **CTA contextual** para abrir a aplicação
17. **CTA final** para conversão
18. **FAQ** (perguntas frequentes)
19. **JSON-LD** `Place` + `FAQPage`

---

## Esqueleto de conteúdo

```md
# {{nome_bairro}}: dados de transporte, segurança, áreas verdes e qualidade urbana

> Atualizado em {{data_atualizacao}} · Metodologia: /metodologia

{{resumo_curto}}

## Para quem este bairro tende a ser adequado
{{nota_adequacao_por_perfil}}

## Métricas principais
| Métrica | Indicador | Cobertura |
|---|---|---|
| Transporte | {{transport_score}} | {{transport_coverage}} |
| Segurança | {{safety_score}} | {{safety_coverage}} |
| Áreas verdes | {{green_score}} | {{green_coverage}} |
| Risco de alagamento | {{flood_risk_score}} | {{flood_coverage}} |
| Acesso a serviços | {{poi_score}} | {{poi_coverage}} |

## Transporte
{{bloco_transporte}}

## Segurança
{{bloco_seguranca}}   <!-- se cobertura < mínimo: declarar limitação explicitamente -->

## Áreas verdes
{{bloco_verde}}

## Risco de alagamento
{{bloco_alagamento}}

## Acesso a serviços
{{bloco_servicos}}

## Pontos fortes
{{lista_pontos_fortes}}

## Pontos de atenção
{{lista_pontos_atencao}}

<!-- CTA contextual (Bloco curto) -->
> Quer saber se esta região combina com sua rotina? Abra o BetterPlace e compare bairros, trajetos e preferências.

## Comparações sugeridas
{{links_comparativos}}

## Bairros similares
{{links_bairros_similares}}

## Perguntas frequentes
{{faq}}

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
