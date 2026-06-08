# Template — Relatório recorrente

**Rota:** `/relatorios/{ano-mes}` (ex.: `/relatorios/2026-07`)
**Base:** `PRD_MKT_GEO.md` §8.4, RF5 · regras em `../content-guidelines.md`
**Consumido por:** gerador automatizado (M6)
**Periodicidade:** trimestral no início; mensal após estabilização do pipeline.

---

## Entrada esperada (pipeline)

```txt
periodo                    # {ano-mes}
rankings_por_metrica
principais_mudancas
comparativos_relevantes
achados
limitacoes_metodologicas
links_dataset
data_atualizacao
```

## Saída obrigatória (estrutura PRD §8.4 / RF5)

1. **Título**
2. **Resumo executivo** (com CTA)
3. **Principais mudanças**
4. **Rankings por métrica**
5. **Comparativos relevantes**
6. **Achados interessantes**
7. **Limitações metodológicas**
8. **Links para dados** (`/dados`)
9. **Versão HTML** (indexável)
10. **Versão PDF**
11. **Versão CSV/JSON**
12. **CTA final** para aplicar os achados na aplicação

---

## Esqueleto de conteúdo

```md
# Relatório BetterPlace de Qualidade Urbana — São Paulo — {{periodo_extenso}}

> Atualizado em {{data_atualizacao}} · Dados: /dados · Metodologia: /metodologia

## Resumo executivo
{{resumo_executivo}}

<!-- CTA no resumo executivo (Bloco de relatório) -->
> Os dados mostram tendências gerais por região. Para transformar a análise em uma decisão prática de moradia, use o BetterPlace e encontre áreas compatíveis com sua rotina.

## Principais mudanças no período
{{principais_mudancas}}

## Rankings por métrica
{{rankings_por_metrica}}   <!-- evitar "melhor/pior bairro"; usar "melhor para X" -->

## Comparativos relevantes
{{comparativos_relevantes}}

## Achados interessantes
{{achados}}

## Limitações metodológicas
{{limitacoes_metodologicas}}

## Dados de apoio
- CSV/JSON: {{links_dataset}}
- Metodologia: /metodologia

<!-- CTA final -->
> Para aplicar estes achados à sua busca de moradia, abra o BetterPlace e encontre regiões compatíveis com sua rotina.
```

---

## Regras de conformidade

- CTA no resumo executivo **e** no encerramento (`content-guidelines.md` §6.2).
- Relatório deve linkar dataset (`/dados`) e metodologia (`/metodologia`).
- Reprodutível pelo mesmo pipeline (mesma entrada → mesma saída).
- Proibir termos absolutos; usar "melhor para <perfil>" nos rankings.
- Eventos: `cta_report_app_click`, `source_page_type=report`, `source_slug={{periodo}}`,
  posições `hero`/`mid` (resumo executivo) e `end` (encerramento).
</content>
