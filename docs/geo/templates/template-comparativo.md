# Template — Página de comparação

**Rota:** `/comparar/{bairro-a}-vs-{bairro-b}`
**Base:** `PRD_MKT_GEO.md` §8.2, §13 · regras em `../content-guidelines.md`
**Consumido por:** gerador automatizado (M4)

> Gerar **apenas** para pares com demanda aprovada (`comparativos-prioritarios.md`).
> Geração cartesiana é proibida. Onde faltar dado, declarar a lacuna.

---

## Entrada esperada (pipeline)

```txt
bairro_a, bairro_b
slug                       # {bairro-a}-vs-{bairro-b}
metricas_a, metricas_b
diferencas_normalizadas
demanda_aprovada           # obrigatório = true
data_atualizacao
```

## Saída obrigatória (estrutura PRD §8.2 / §13.2)

1. **Título**
2. **Resposta direta**
3. **Tabela comparativa**
4. **Melhor para transporte**
5. **Melhor para áreas verdes**
6. **Melhor para acesso a serviços**
7. **Pontos de atenção**
8. **Recomendação por perfil**
9. **Metodologia** (link)
10. **CTA contextual** (após resposta direta)
11. **CTA final** (comparação personalizada na aplicação)
12. **FAQ comparativa**
13. **JSON-LD** `Article` + `FAQPage`

---

## Esqueleto de conteúdo

```md
# {{bairro_a}} vs {{bairro_b}}: qual bairro combina melhor com sua rotina?

> Atualizado em {{data_atualizacao}} · Metodologia: /metodologia

## Resposta direta
{{resposta_direta}}

<!-- CTA contextual (Bloco comparativo) -->
> A melhor escolha depende do seu trajeto, orçamento e prioridades. Use o BetterPlace para fazer uma comparação personalizada entre bairros.

## Tabela comparativa
| Métrica | {{bairro_a}} | {{bairro_b}} |
|---|---|---|
| Transporte | {{a.transport}} | {{b.transport}} |
| Segurança | {{a.safety}} | {{b.safety}} |
| Áreas verdes | {{a.green}} | {{b.green}} |
| Risco de alagamento | {{a.flood}} | {{b.flood}} |
| Acesso a serviços | {{a.poi}} | {{b.poi}} |

## Melhor para transporte
{{conclusao_transporte}}

## Melhor para áreas verdes
{{conclusao_verde}}

## Melhor para acesso a serviços
{{conclusao_servicos}}

## Pontos de atenção
{{pontos_atencao}}   <!-- incluir lacunas de cobertura quando houver -->

## Recomendação por perfil
{{recomendacao_por_perfil}}

## Perguntas frequentes
{{faq}}

## Metodologia e limitações
Detalhes em /metodologia.

<!-- CTA final -->
> Compare bairros com base no seu trajeto, rotina e preferências no BetterPlace.
```

---

## Regras de conformidade

- Publicar somente com `demanda_aprovada = true` e dados suficientes nos dois lados
  (`content-guidelines.md` §9.2).
- Conclusão própria obrigatória (sem texto duplicado de outra página).
- Aplicar thresholds de copy e proibir termos absolutos (`content-guidelines.md` §4).
- Eventos: `cta_compare_click`, `source_page_type=comparison`, `source_slug={{slug}}`,
  posições `mid` (contextual) e `end` (final).
</content>
