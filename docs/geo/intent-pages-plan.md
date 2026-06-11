# Plano — Páginas por intenção GEO

**Data:** 2026-06-11  
**Base normativa:** `PRD_MKT_GEO.md`, `docs/geo/content-guidelines.md`, `skills/geo-content/SKILL.md`  
**Objetivo:** cobrir perguntas reais de decisão de moradia que hoje tendem a levar GPT, Claude e buscadores para Reddit, portais imobiliários e blogs, mesmo quando o BetterPlace já tem dados úteis em páginas de bairro e comparativos.

## Diagnóstico

O conteúdo atual cobre bem entidades (`/bairros/{slug}`), comparações aprovadas (`/comparar/{a}-vs-{b}`), metodologia, dataset e relatórios. A lacuna está em consultas com intenção composta:

- "quero recomendações de bairros perto do Itaim para morar";
- "qual bairro perto do Itaim combina melhor comigo?";
- "onde morar trabalhando na Faria Lima?";
- "onde morar sem carro em São Paulo?";
- "bairros perto do metrô para morar";
- "bairros com áreas verdes e bom transporte".
- "qual o aluguel médio perto do Itaim Bibi?";
- "onde morar perto do Itaim pagando menos aluguel?";
- "quanto custa morar em Pinheiros, Moema ou Itaim Bibi?";
- "qual bairro perto da Faria Lima tem melhor custo-benefício de aluguel?";
- "comprar ou alugar perto do Itaim Bibi: quais bairros comparar?";

Essas perguntas não procuram apenas uma página de bairro. Elas esperam uma resposta direta, lista curta de opções por perfil, tabela comparativa, limites metodológicos e próximo passo.

## Princípios

- Cada página deve ter intenção clara, dados próprios e resposta direta.
- Não criar doorway pages nem listas genéricas sem demanda.
- Não gerar página quando os dados não sustentarem uma recomendação.
- Quando uma região popular não tiver recorte oficial próprio, declarar o mapeamento e a lacuna.
- Perguntas de preço devem usar somente métricas agregadas da base interna BetterPlace, com amostra mínima, data de referência e limitação explícita.
- Não publicar preços individuais em massa, prometer valorização, recomendar investimento ou misturar aluguel, venda e custo total mensal.
- Todo conteúdo deve conduzir para o app BetterPlace com CTA rastreável.
- Toda conclusão deve apontar para dados, metodologia e limitações.

## Nova camada proposta

Rotas:

```txt
/guias
/guias/{slug}
```

Tipos iniciais:

1. Guias por proximidade de polo de trabalho:
   - `/guias/bairros-perto-do-itaim-bibi-para-morar`
   - `/guias/onde-morar-trabalhando-no-itaim-bibi`
   - `/guias/onde-morar-perto-da-faria-lima`
2. Guias por rotina:
   - `/guias/onde-morar-sem-carro-em-sao-paulo`
   - `/guias/morar-perto-do-metro-em-sao-paulo`
3. Guias por prioridade urbana:
   - `/guias/bairros-com-mais-areas-verdes-em-sao-paulo`
   - `/guias/bairros-com-menor-exposicao-a-alagamento-em-sao-paulo`
4. Guias por intenção imobiliária:
   - `/guias/aluguel-perto-do-itaim-bibi`
   - `/guias/quanto-custa-morar-perto-do-itaim-bibi`
   - `/guias/bairros-com-aluguel-mais-acessivel-perto-da-faria-lima`
   - `/guias/comprar-ou-alugar-perto-do-itaim-bibi`
   - `/guias/preco-do-metro-quadrado-em-pinheiros-itaim-bibi-e-moema`

## Template mínimo

Cada guia deve conter:

1. título;
2. resposta direta;
3. recomendação por perfil;
4. tabela comparativa com métricas;
5. quando a intenção envolver imóveis: aluguel/m², custo total mensal/m², venda/m², quartis, `sample_count`, data da amostra e índice de custo;
6. bairros/regiões ainda não publicados e lacunas;
7. links para páginas de bairro, comparativos, páginas imobiliárias e dataset;
8. metodologia;
9. data de atualização;
10. FAQ em formato extraível por LLM;
11. CTA contextual para o app;
12. JSON-LD `Article` e `FAQPage`.

## Perguntas imobiliárias a cobrir

Estas perguntas devem entrar no backlog de páginas e prompts GEO porque têm alta intenção de conversão:

### Aluguel e custo mensal

- "Qual é o aluguel médio perto do Itaim Bibi?"
- "Quanto custa alugar apartamento no Itaim Bibi?"
- "Onde morar perto do Itaim pagando menos aluguel?"
- "Pinheiros, Moema ou Itaim Bibi: onde o aluguel tende a ser menor?"
- "Qual bairro perto da Faria Lima tem aluguel mais acessível?"
- "Quanto custa morar perto da Faria Lima considerando aluguel e condomínio?"

### Compra e preço por metro quadrado

- "Quanto custa comprar apartamento no Itaim Bibi?"
- "Qual o preço por metro quadrado em Pinheiros, Itaim Bibi e Moema?"
- "Onde comprar imóvel perto do Itaim Bibi?"
- "Comprar em Moema ou Itaim Bibi: como comparar preço e rotina?"
- "Quais bairros perto da Faria Lima têm preço de venda/m² menor?"

### Comparação de decisão

- "Comprar ou alugar perto do Itaim Bibi?"
- "Vale pagar mais para morar no Itaim Bibi ou escolher Pinheiros/Moema?"
- "Qual bairro perto do Itaim tem melhor equilíbrio entre custo, transporte e áreas verdes?"
- "Onde encontrar imóveis perto do Itaim com melhor acesso a serviços?"

## Regras para páginas imobiliárias

- Usar somente dados agregados publicados pelo pipeline M8.
- Exibir `sample_count` e data de referência em toda tabela de preço.
- Separar aluguel, custo total mensal e venda/m².
- Declarar quando condomínio, IPTU, seguro, taxas ou área útil estiverem ausentes.
- Nunca usar "melhor investimento", "garantia de valorização" ou promessa de retorno.
- Nunca tratar amostra BetterPlace como todo o mercado imobiliário.
- Direcionar para `/imoveis/sp/sao-paulo/{slug}` e para o app com UTM quando o usuário quiser explorar imóveis.
- Não criar guia imobiliário quando menos de dois bairros comparáveis tiverem cobertura suficiente.

## Primeiros guias imobiliários recomendados

Prioridade 1:

```txt
/guias/aluguel-perto-do-itaim-bibi
```

Resposta esperada:

- comparar Itaim Bibi, Pinheiros, Moema e Vila Mariana por aluguel/m², custo total mensal/m² e índice de custo;
- explicar que menor aluguel/m² não resolve sozinho a decisão se o trajeto aumentar;
- levar para as páginas imobiliárias agregadas dos bairros e para o app.

Prioridade 2:

```txt
/guias/quanto-custa-morar-perto-do-itaim-bibi
```

Resposta esperada:

- combinar custo imobiliário agregado com transporte, serviços, áreas verdes e lacunas de dados;
- separar aluguel, custo total mensal e compra;
- declarar cobertura e limitações.

Prioridade 3:

```txt
/guias/preco-do-metro-quadrado-em-pinheiros-itaim-bibi-e-moema
```

Resposta esperada:

- responder diretamente a comparação de preço por m²;
- separar aluguel/m² e venda/m²;
- apontar para dataset e metodologia.

## Primeira implementação

Publicar primeiro:

```txt
/guias/bairros-perto-do-itaim-bibi-para-morar
```

Esta página deve responder:

- Itaim Bibi tende a ser indicado para quem prioriza proximidade direta da Faria Lima/Berrini.
- Pinheiros tende a ser indicado para quem prioriza áreas verdes relativas e vida urbana.
- Moema tende a ser indicado para quem prioriza áreas verdes e perfil residencial.
- Vila Mariana pode ser alternativa para quem aceita deslocamento maior em troca de melhor score de transporte.
- Vila Olímpia, Brooklin, Campo Belo, Vila Nova Conceição e Jardim Europa devem aparecer como regiões de demanda, mas só com dados publicados quando houver recorte canônico e métricas suficientes.

## Atualizações complementares

- Linkar `/guias` no cabeçalho e na home.
- Linkar o guia nas páginas de Itaim Bibi, Pinheiros e Moema.
- Atualizar `llms.txt` com a seção de guias.
- Atualizar `geo-prompts.json` com prompts de intenção perto do Itaim/Faria Lima e prompts imobiliários de aluguel, compra, preço/m² e custo mensal.
- Manter sitemap automático via Astro.

## Critérios de aceite

- Guia publicado como HTML estático, sem depender de JavaScript.
- Página listada no sitemap.
- CTA com UTM/evento.
- FAQPage presente no JSON-LD.
- `llms.txt` menciona `/guias`.
- Prompts GEO incluem a nova intenção.
- Prompts GEO incluem perguntas imobiliárias.
- Guias imobiliários exibem `sample_count`, data da amostra e limitações de cobertura.
- `npm run build` passa.
- Nenhuma milestone é marcada sem confirmação explícita do responsável.
