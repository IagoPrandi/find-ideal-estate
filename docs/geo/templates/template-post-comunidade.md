# Template — Post de comunidade própria

**Canal:** comunidade própria no Reddit — `r/OndeMorarBrasil` (nome sugerido, PRD §8.5)
**Base:** `PRD_MKT_GEO.md` §8.5 · regras em `../content-guidelines.md`
**Uso:** publicação editorial própria (M8). Valor informativo primeiro; CTA discreto no final.

> O que **não** fazer: caçar posts de terceiros para comentar, responder em massa,
> autopromoção agressiva, postar links sem contexto, simular engajamento.

---

## Tipos de post

1. **Análise** (foco em um bairro)
2. **Comparativo** (par de bairros)
3. **Relatório** (recorte de relatório trimestral/mensal)

---

## Esqueleto — post de comparativo (modelo PRD §8.5)

```txt
Título:
[Análise] {{bairro_a}} vs {{bairro_b}}: transporte, áreas verdes e perfil de moradia

Corpo:
Fizemos uma comparação usando dados públicos agregados sobre transporte, segurança,
áreas verdes e riscos urbanos.

Resumo:
- {{ponto_a}}
- {{ponto_b}}
- A escolha depende principalmente do trajeto diário.

Metodologia:
Os dados são agregados por distrito/bairro e atualizados periodicamente. A metodologia
completa está disponível no BetterPlace.

Pergunta para a comunidade:
Que outro comparativo faria sentido analisar?

<!-- CTA discreto no final, sempre após valor informativo -->
Análise completa (transporte, segurança, verde e alagamento): {{url_publica}}
```

---

## Esqueleto — post de análise (bairro)

```txt
Título:
[Análise] {{bairro}}: o que os dados públicos dizem sobre transporte, verde e alagamento

Corpo:
Resumo dos indicadores agregados de {{bairro}}, com fontes e limitações declaradas.

Resumo:
- Transporte: {{resumo_transporte}}
- Áreas verdes: {{resumo_verde}}
- Risco de alagamento: {{resumo_alagamento}}
- Limitações: {{lacunas}}

Pergunta para a comunidade:
Mora em {{bairro}}? Os dados batem com sua experiência?

Página completa com metodologia: {{url_publica}}
```

---

## Regras de conformidade

- Tom informativo, não promocional (`content-guidelines.md` §3).
- CTA discreto **no final**, precedido de valor informativo (`content-guidelines.md` §6.2).
- Link para **página pública útil** (bairro/comparativo/relatório), nunca só a home.
- Proibir termos absolutos (`content-guidelines.md` §4.1).
- Links com tracking: `cta_app_click`, UTM `utm_medium=community`,
  `utm_content={{slug}}__end__comunidade-a`.
</content>
