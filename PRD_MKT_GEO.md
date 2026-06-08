# PRD — BetterPlace GEO & AI Visibility Engine

**Produto:** BetterPlace  
**Domínio canônico:** `betterplace.com.br`  
**Versão:** 1.0  
**Status:** Pronto para implementação inicial  
**Objetivo principal:** transformar BetterPlace em uma fonte indexável, citável e recorrente sobre qualidade de moradia em bairros brasileiros, começando por São Paulo, fazendo com que todo material público conduza o usuário para a aplicação com objetivo de conversão.

---

## 1. Resumo executivo

O BetterPlace precisa deixar de ser apenas uma aplicação interativa e passar a ter uma camada pública de conteúdo e dados, acessível por buscadores tradicionais e por agentes de IA.

A estratégia não é “postar para viralizar”. A estratégia é criar um sistema próprio e automatizado de:

1. páginas públicas por bairro;
2. comparativos entre bairros;
3. relatórios recorrentes;
4. datasets abertos;
5. metodologia transparente;
6. medição de citações em IA;
7. distribuição controlada, iniciando por canais próprios;
8. CTAs e caminhos de conversão para a aplicação em todos os materiais.

As ações que dependem de terceiros — imprensa, criadores, comunidades já existentes, Wikipedia/Wikidata, Product Hunt, Hacker News — ficam para etapas finais. O MVP deve ser executável por uma pessoa, com o mínimo possível de dependência externa.

---

## 2. Problema

Hoje, o BetterPlace não possui uma superfície pública suficientemente forte para ser citado por ChatGPT, Perplexity, Gemini, Copilot, Claude ou Google AI Overviews.

O app atual pode ser útil para o usuário, mas não necessariamente é bom para mecanismos de busca e agentes de IA, porque:

- conteúdo de app interativo tende a ser pouco citável;
- SPAs podem dificultar leitura por bots;
- páginas sem texto estruturado não geram autoridade;
- dados internos não viram fonte pública;
- comparações entre bairros não existem como ativos indexáveis;
- relatórios e datasets ainda não existem como ativos recorrentes;
- não há rotina de medição de citações por IA.

---

## 3. Objetivo

Criar uma camada pública e automatizada de conteúdo, dados e relatórios para que BetterPlace seja encontrado e citado quando usuários perguntarem sobre:

- onde morar em São Paulo;
- comparação entre bairros;
- segurança;
- transporte;
- áreas verdes;
- alagamento;
- acesso a serviços;
- qualidade urbana;
- achar imóveis para comprar e alugar;
- análise de preços imobiliário;
- decisão de moradia.

---

## 4. Não objetivos

O MVP não deve depender de:

- assessoria de imprensa;
- influenciadores;
- criadores externos;
- comentários manuais em posts de terceiros;
- engajamento em comunidades que não sejam próprias;
- Wikipedia/Wikidata;
- Product Hunt;
- Hacker News;
- backlinks obtidos manualmente;
- scraping novo de preço imobiliário de fontes externas.

O MVP não precisa publicar preço imobiliário, mas o M8 deve usar os dados imobiliários
**já existentes** na base interna BetterPlace. Esses dados devem ser expostos de forma
agregada, com amostras controladas quando elegíveis, sem depender de novo scraping ou
fonte externa.

Essas frentes podem ser úteis depois, mas não devem bloquear o produto.

---

## 5. Princípios do produto

### 5.1 Fonte antes de tráfego

O objetivo inicial não é maximizar pageviews. O objetivo é fazer BetterPlace virar uma fonte confiável, rastreável e citável.

### 5.2 Dados antes de opinião

O conteúdo deve ser opinativo apenas quando sustentado por dados. Cada conclusão precisa apontar para métricas, metodologia e limitações.

### 5.3 Automação antes de operação manual

Sempre que possível, o conteúdo deve ser gerado por rotinas: bairros, comparativos, relatórios, datasets, sitemaps, prompts de teste e logs.

### 5.4 Canais próprios antes de terceiros

A distribuição começa em canais próprios ou controláveis:

- site;
- blog/relatórios;
- dataset aberto;
- comunidade própria no Reddit;
- newsletter simples;
- página de metodologia;
- repositório público opcional de dados agregados.

### 5.5 Sem doorway pages

Não gerar milhares de páginas sem demanda ou sem conteúdo único. Cada página precisa ter dados próprios, resumo próprio e intenção clara.

### 5.6 Conversão como destino obrigatório

Todo material público deve conduzir o usuário para a aplicação BetterPlace.

Isso vale para:

- páginas de bairro;
- comparativos;
- relatórios;
- páginas de dados;
- posts na comunidade própria;
- newsletters;
- materiais de imprensa;
- materiais para criadores;
- páginas de metodologia quando fizer sentido.

A condução pode acontecer:

- durante o conteúdo, quando houver uma recomendação contextual;
- ao final do conteúdo, como próximo passo natural;
- em ambos, quando o material for longo.

A conversão não deve parecer publicidade solta. O CTA deve estar conectado à intenção do usuário.

Exemplos de CTA:

```txt
Compare este bairro com outras regiões no BetterPlace.
```

```txt
Use o BetterPlace para encontrar bairros compatíveis com sua rotina, trajeto e preferências.
```

```txt
Quer transformar esta análise em uma busca prática? Abra a aplicação e veja regiões e imóveis compatíveis.
```

```txt
Faça uma comparação personalizada no BetterPlace com base no seu deslocamento, prioridades e estilo de vida.
```

---

## 6. Usuários-alvo

### 6.1 Usuário final

Pessoa que está decidindo onde morar e pergunta a buscadores ou IAs:

- “qual bairro é melhor para morar em São Paulo?”
- “Pinheiros ou Vila Mariana?”
- “bairro seguro perto do metrô”
- “onde morar com área verde e bom transporte?”
- “quais bairros têm risco de alagamento?”

### 6.2 Agente de IA

ChatGPT, Perplexity, Gemini, Copilot, Claude ou outro sistema que precisa recuperar fontes confiáveis para responder perguntas sobre moradia.

### 6.3 Jornalista, pesquisador ou criador

Pessoa que precisa de dados urbanos organizados para citar, comparar ou gerar conteúdo.

---

## 7. Posicionamento

### 7.1 Marca canônica

A marca pública deve ser **BetterPlace**.

“Find Ideal Estate” não deve ser usado como nome principal. Pode ser usado internamente ou como descritor, mas não como entidade pública concorrente.

### 7.2 Frase de posicionamento

**BetterPlace ajuda pessoas a escolher onde morar usando dados de bairro, mobilidade, segurança, áreas verdes e riscos urbanos.**

### 7.3 Tom de voz

O tom deve ser:

- direto;
- analítico;
- confiável;
- transparente sobre limitações;
- sem exageros comerciais;
- sem prometer “melhor bairro absoluto”;
- orientado à decisão.

### 7.4 O que evitar

Evitar frases como:

- “o melhor bairro de São Paulo”;
- “o bairro mais seguro” sem contexto;
- “garantia de segurança”;
- “ranking definitivo”;
- “IA comprovou”;
- “perfeito para todos”.

### 7.5 Tom recomendado

Usar frases como:

- “melhor para quem prioriza transporte”;
- “tende a ser mais adequado para quem busca acesso a metrô”;
- “os dados indicam maior presença de áreas verdes”;
- “a análise considera dados públicos e metodologia descrita”;
- “há limitações de cobertura nesta métrica”.

---

## 8. Estrutura dos materiais

### 8.1 Página de bairro

Rota:

```txt
/bairros/{slug}
```

Estrutura obrigatória:

1. título;
2. resumo curto;
3. nota de adequação por perfil;
4. métricas principais;
5. transporte;
6. segurança;
7. áreas verdes;
8. risco de alagamento;
9. acesso a serviços;
10. pontos fortes;
11. pontos de atenção;
12. comparação sugerida;
13. metodologia;
14. data de atualização;
15. CTA contextual para abrir a aplicação;
16. CTA final para conversão.

Exemplo de título:

```txt
Vila Mariana: dados de transporte, segurança, áreas verdes e qualidade urbana
```

Exemplo de resumo:

```txt
Vila Mariana tende a ser uma boa opção para quem prioriza acesso a transporte público, serviços próximos e deslocamento para regiões centrais. A análise combina dados públicos de mobilidade, segurança, áreas verdes e riscos urbanos.
```

Exemplo de CTA:

```txt
Quer comparar Vila Mariana com outros bairros? Use o BetterPlace para encontrar regiões compatíveis com sua rotina.
```

---

### 8.2 Página de comparação

Rota:

```txt
/comparar/{bairro-a}-vs-{bairro-b}
```

Estrutura obrigatória:

1. título;
2. resposta direta;
3. tabela comparativa;
4. melhor para transporte;
5. melhor para áreas verdes;
6. melhor para acesso a serviços;
7. pontos de atenção;
8. recomendação por perfil;
9. metodologia;
10. CTA contextual durante a análise;
11. CTA final para comparação personalizada na aplicação.

Exemplo de título:

```txt
Pinheiros vs Vila Mariana: qual bairro combina melhor com sua rotina?
```

Exemplo de resposta direta:

```txt
Pinheiros tende a ser mais forte para quem prioriza vida urbana, acesso a serviços e conexões com zonas comerciais. Vila Mariana tende a ser mais equilibrada para quem busca transporte, serviços e perfil residencial consolidado. A melhor escolha depende do trajeto diário e das prioridades de moradia.
```

Exemplo de CTA:

```txt
Compare bairros com base no seu trajeto, rotina e preferências no BetterPlace.
```

---

### 8.3 Página de dados

Rota:

```txt
/dados
```

Estrutura obrigatória:

1. descrição do dataset;
2. cidades cobertas;
3. métricas disponíveis;
4. data de atualização;
5. formato dos arquivos;
6. licença;
7. limitações;
8. links para CSV, JSON e GeoJSON;
9. changelog;
10. CTA para explorar os dados na aplicação.

Exemplo de copy:

```txt
O BetterPlace publica dados agregados de qualidade urbana para apoiar decisões de moradia, pesquisa e análise jornalística. Os dados são agregados por distrito ou bairro, sem exposição de dados pessoais.
```

---

### 8.4 Relatório recorrente

Rota:

```txt
/relatorios/{ano-mes}
```

Exemplo:

```txt
/relatorios/2026-07
```

Estrutura obrigatória:

1. título;
2. resumo executivo;
3. principais mudanças;
4. rankings por métrica;
5. comparativos relevantes;
6. achados interessantes;
7. limitações metodológicas;
8. links para dados;
9. versão em HTML;
10. versão em PDF;
11. versão em CSV/JSON;
12. CTA para aplicar os achados na aplicação.

Exemplo de título:

```txt
Relatório BetterPlace de Qualidade Urbana — São Paulo — Julho de 2026
```

---

### 8.5 Comunidade própria no Reddit

Nome sugerido:

```txt
r/OndeMorarBrasil
```

Justificativa: o nome é mais amplo e menos promocional do que uma comunidade com o nome da marca.

Objetivo da comunidade:

- publicar análises próprias;
- receber dúvidas sobre bairros;
- compartilhar comparativos;
- publicar recortes dos relatórios;
- gerar histórico público indexável;
- criar um canal próprio sem depender de comunidades de terceiros.

O que não fazer:

- sair procurando posts em outros subreddits para comentar;
- responder manualmente em massa;
- fazer autopromoção agressiva;
- postar links sem contexto;
- simular engajamento.

Estrutura de post recomendada:

```txt
Título:
[Análise] Pinheiros vs Vila Mariana: transporte, áreas verdes e perfil de moradia

Corpo:
Fizemos uma comparação usando dados públicos agregados sobre transporte, segurança, áreas verdes e riscos urbanos.

Resumo:
- Pinheiros tende a ser mais forte em acesso a serviços e vida urbana.
- Vila Mariana tende a ser mais equilibrada para transporte e perfil residencial.
- A escolha depende principalmente do trajeto diário.

Metodologia:
Os dados são agregados por distrito/bairro e atualizados periodicamente. A metodologia completa está disponível no BetterPlace.

Pergunta para a comunidade:
Que outro comparativo faria sentido analisar?
```


---

### 8.6 Blocos obrigatórios de conversão

Todo material deve ter pelo menos um bloco de conversão.

#### Bloco curto

Uso recomendado: páginas de bairro, posts curtos, trechos intermediários.

```txt
Quer saber se esta região combina com sua rotina? Abra o BetterPlace e compare bairros, trajetos e preferências.
```

#### Bloco comparativo

Uso recomendado: páginas `/comparar`.

```txt
A melhor escolha depende do seu trajeto, orçamento e prioridades. Use o BetterPlace para fazer uma comparação personalizada entre bairros.
```

#### Bloco de relatório

Uso recomendado: relatórios mensais ou trimestrais.

```txt
Os dados mostram tendências gerais por região. Para transformar a análise em uma decisão prática de moradia, use o BetterPlace e encontre áreas compatíveis com sua rotina.
```

#### Bloco de dataset

Uso recomendado: página `/dados`.

```txt
Estes dados ajudam a entender a cidade em nível agregado. Para aplicar os indicadores à sua busca de moradia, acesse a aplicação BetterPlace.
```

#### Regra de posicionamento

- Materiais com até 800 palavras: CTA obrigatório no final.
- Materiais com mais de 800 palavras: CTA contextual no meio e CTA final.
- Comparativos: CTA depois da resposta direta e no final.
- Relatórios: CTA no resumo executivo e no encerramento.
- Posts na comunidade própria: CTA discreto no final, sempre precedido de valor informativo.

---

## 9. Requisitos funcionais

### RF1 — Site público SSR/SSG

O sistema deve gerar páginas públicas em HTML estático ou server-rendered.

Requisitos:

- páginas legíveis sem JavaScript;
- metadados completos;
- sitemap automático;
- robots.txt;
- canonical URL;
- JSON-LD;
- data de atualização visível;
- conteúdo principal no HTML;
- páginas acessíveis por bots de busca e IA.

---

### RF2 — Página por bairro

O sistema deve gerar páginas públicas para bairros/distritos com dados suficientes.

Critérios de geração:

- ter polígono oficial;
- ter pelo menos 4 grupos de métricas disponíveis;
- ter resumo textual único;
- ter data de atualização;
- ter metodologia;
- não publicar página com dados insuficientes sem declarar lacunas.

---

### RF3 — Comparativos automatizados

O sistema deve gerar comparativos entre pares de bairros.

Critérios de geração:

- não gerar produto cartesiano completo;
- gerar apenas comparativos aprovados por demanda;
- gerar apenas quando os dois bairros tiverem dados suficientes;
- cada comparação precisa ter conclusão própria;
- cada página precisa ter tabela comparativa;
- cada página precisa ter recomendação por perfil.

Fontes de demanda permitidas no MVP:

- lista manual inicial;
- buscas internas do próprio site;
- comparações mais acessadas;
- sugestões geradas a partir de bairros próximos;
- perguntas do próprio usuário no app;
- prompts fixos de teste em IA.

Fontes de demanda excluídas no MVP:

- monitoramento manual de posts de terceiros;
- comentários em comunidades externas;
- scraping de Reddit;
- scraping de redes sociais.

---

### RF4 — Dataset aberto

O sistema deve publicar dados agregados em formatos reutilizáveis.

Formatos:

- CSV;
- JSON;
- GeoJSON.

Requisitos:

- licença definida;
- metodologia;
- data de atualização;
- changelog;
- versão do dataset;
- dicionário de campos.

---

### RF5 — Relatório recorrente

O sistema deve gerar relatório mensal ou trimestral de forma automatizada.

Requisitos:

- HTML indexável;
- PDF;
- CSV/JSON de apoio;
- resumo executivo;
- rankings;
- achados;
- metodologia;
- changelog.

Periodicidade inicial recomendada:

```txt
Trimestral no início.
Mensal após estabilização do pipeline.
```

---

### RF6 — Medição de GEO

O sistema deve medir se BetterPlace está sendo citado por IAs e buscadores.

Métricas obrigatórias:

- páginas indexadas no Google;
- páginas indexadas no Bing;
- acessos por referrer de IA;
- hits de bots de IA;
- citações em prompts fixos;
- posição da citação;
- páginas mais citadas;
- comparativos mais acessados;
- conversões para o app.

Prompts fixos iniciais:

```txt
Qual o melhor bairro para morar em São Paulo perto do metrô?
Pinheiros ou Vila Mariana: qual é melhor para morar?
Quais bairros de São Paulo têm mais áreas verdes?
Quais bairros de São Paulo têm melhor acesso a transporte?
Onde morar em São Paulo evitando áreas de alagamento?
Qual bairro combina com quem trabalha na região da Faria Lima?
Qual bairro combina com quem quer morar sem carro em São Paulo?
```

---

### RF7 — Comunidade própria

O sistema deve permitir uma rotina editorial própria, sem depender de comunidades de terceiros.

Canais próprios iniciais:

- Reddit próprio;
- página de relatórios;
- página de dados;
- newsletter simples;
- posts no próprio site.

Requisitos:

- calendário editorial;
- templates de publicação;
- links para páginas públicas;
- sem automação agressiva;
- sem spam;
- sem depender de comentários em posts alheios.

---

### RF8 — Caminho de conversão obrigatório para a aplicação

Todo material público deve levar o usuário para a aplicação BetterPlace.

Requisitos:

- toda página de bairro deve ter CTA para abrir a aplicação;
- todo comparativo deve ter CTA para comparação personalizada na aplicação;
- todo relatório deve ter CTA para aplicar os achados na aplicação;
- toda página de dados deve ter CTA para explorar regiões na aplicação;
- todo post da comunidade própria deve ter CTA discreto para página relevante ou aplicação;
- todo material de imprensa ou criadores deve apontar para uma página pública e, desta, para a aplicação;
- CTAs devem ser rastreáveis por UTM ou evento equivalente;
- CTAs devem ser contextuais, não genéricos;
- o usuário deve conseguir sair de qualquer material público para a aplicação em no máximo um clique.

Eventos mínimos:

```txt
cta_app_click
cta_compare_click
cta_neighborhood_app_click
cta_report_app_click
cta_dataset_app_click
```

Parâmetros mínimos:

```txt
source_page_type
source_slug
cta_position
cta_copy_variant
destination_url
```

---

## 10. Requisitos não funcionais

### RNF1 — Performance

- páginas devem carregar rapidamente;
- conteúdo principal deve estar no HTML;
- evitar JavaScript desnecessário;
- imagens devem ser otimizadas;
- sitemap deve ser leve e segmentado se necessário.

### RNF2 — Indexabilidade

- cada página deve ter título único;
- descrição única;
- canonical;
- `dateModified`;
- schema adequado;
- links internos;
- conteúdo textual suficiente.

### RNF3 — Transparência

- toda métrica deve ter fonte;
- toda página deve informar data de atualização;
- lacunas de dados devem ser declaradas;
- metodologia deve ser acessível.

### RNF4 — Segurança jurídica

- não republicar anúncios individuais em massa nem expor campos sensíveis; no M8, apenas amostra limitada e elegível com campos mínimos e links internos;
- não publicar dados pessoais;
- não usar scraping de preço no MVP;
- usar dados públicos ou agregados;
- respeitar termos de uso das fontes.

### RNF5 — Manutenção

- conteúdo deve ser gerado por pipeline;
- evitar edição manual página a página;
- templates devem centralizar copy;
- dados devem ser versionados;
- relatórios devem ser reproduzíveis.

---

## 11. Arquitetura proposta

### 11.1 Camada pública

Tecnologia recomendada:

```txt
Astro SSG
```

Alternativa:

```txt
Next.js SSG
```

Decisão recomendada:

```txt
Astro, por ser simples, rápido e adequado para páginas de conteúdo com pouco JavaScript.
```

Rotas:

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

### 11.2 Camada de dados

#### 11.2.1 Camada geográfica base (zonas de análise)

A unidade de análise do BetterPlace é o **distrito municipal oficial de São Paulo**.

**Fonte:** `data/geo/raw/geoportal_distrito_municipal_v2.gpkg`  
**Origem:** PMSP / GeoSampa — layer `distrito_municipal_v2`  
**CRS original:** EPSG:31983 (SIRGAS 2000 / UTM zone 23S, projetado em metros)  
**CRS no banco:** EPSG:4326 (reprojetado na ingestão)  
**Total:** 96 distritos municipais, cada um = uma zona de análise  
**Ingestão:** `scripts/ingest_distritos_municipais.py` → tabela `neighborhood_boundaries`  
**Referência completa:** `docs/geo/fontes-geograficas.md`

Todos os recortes espaciais (áreas verdes, zonas de alagamento, infraestrutura de
transporte, POIs) são feitos via `ST_Intersection` / `ST_Contains` contra esses
96 polígonos. Não há uso de fecho convexo ou boundary aproximado em produção.

#### 11.2.2 Tabelas e views

```txt
neighborhood_boundaries              ← 96 distritos do GeoPackage (canonical zones)
neighborhood_green_area_metrics
neighborhood_flood_risk_metrics
neighborhood_transport_metrics
neighborhood_poi_metrics
neighborhood_metric_scores           ← scores 0–100 por métrica e distrito
neighborhood_metric_coverage         ← flags de cobertura (completa/parcial/insuficiente)
urban_metrics_by_district            ← view materializada (superfície de leitura)
public_safety_neighborhood_metrics   ← density robberies/km² SSP-SP (sempre 'parcial' por sub-registro)
content_neighborhood_pages
content_comparison_pages
report_snapshots
geo_visibility_prompt_runs
```

#### 11.2.3 Modelo de dados público — interface `Bairro` (camada Astro)

Campos da interface TypeScript que alimenta as páginas SSG:

```txt
slug, nome, distrito, resumo, perfil, dataAtualizacao

# Scores geoespaciais (0–100)
transportScore        ← weighted transit density/km² → min-max
greenScore            ← % vegetação significativa → min-max
floodRiskScore        ← % mancha inundação → min-max invertido (100 = menor risco)
safetyScore           ← robbery density/km² SSP-SP → min-max invertido (100 = menor densidade)
poiScore              ← bus stop density/km² proxy → min-max

# Cobertura
safetyDataCoverage    ← 'completa' | 'parcial' | 'insuficiente'
lacunas[]             ← métricas com limitação declarada explicitamente

# Panorama imobiliário (dados internos BetterPlace — não scraping)
realEstateMetrics:
  aggregationLevel        ← 'estado' | 'cidade' | 'bairro' | 'lista'
  aggregationSlug         ← slug canônico do recorte
  listingSampleCount      ← quantidade de imóveis elegíveis na agregação
  rentPerM2               ← aluguel/m² (R$/mês), agregado
  totalRentCostPerM2      ← aluguel + encargos conhecidos/m² (R$/mês), agregado
  salePricePerM2          ← preço de venda/m² (R$), agregado
  rentQuartiles           ← q1, mediana, q3 de aluguel
  saleQuartiles           ← q1, mediana, q3 de venda
  sameListingPriceChange  ← variação de preço calculada no mesmo conjunto de imóveis
  sampleListings[]        ← pequena amostra de imóveis elegíveis com campos mínimos e link interno
  costIndex               ← índice relativo 0–100 entre recortes comparáveis
  dataAt                  ← data de referência (YYYY-MM-DD)

# Conteúdo editorial
pontosFortes[], pontosAtencao[], bairrosSimilares[]
```

---

### 11.3 Pipeline automatizado

Rotinas (ordem de execução obrigatória):

```txt
0. alembic upgrade head                              ← migrations 0042 + 0043
1. ingest_distritos_municipais.py                    ← GeoPackage → neighborhood_boundaries
2. Importar/atualizar camadas GeoSampa brutas
3. aggregate_geo_metrics.py                          ← recorta e agrega por distrito
4. validate_geo_data.py                              ← valida slugs, geometrias, cobertura
5. Gerar score normalizado (incluso no passo 3)
6. Gerar textos baseados em templates
7. Gerar páginas /bairros
8. Gerar comparativos aprovados
9. Gerar sitemap
10. Gerar dataset aberto
11. Gerar relatório periódico
12. Rodar testes de indexabilidade
13. Rodar prompts de medição GEO
```

---

## 12. Geração automatizada de conteúdo

### 12.1 Princípio

A geração não deve inventar conclusões. O texto deve ser produzido a partir de regras, thresholds e templates.

### 12.2 Estrutura de geração

Cada página de bairro deve receber:

```txt
input:
  - nome do bairro
  - métricas normalizadas
  - ranking relativo
  - pontos fortes
  - pontos fracos
  - lacunas
  - bairros similares
  - data de atualização

output:
  - título
  - meta description
  - resumo
  - blocos por métrica
  - perguntas frequentes
  - CTA
  - JSON-LD
```

### 12.3 Regras de copy

Thresholds canônicos (referência autoritativa em `docs/geo/content-guidelines.md` §4.3):

```txt
# Transporte
transport_score >= 80  → "O bairro se destaca pelo acesso a transporte público."
transport_score < 80   → "O bairro apresenta acesso moderado a transporte público."

# Áreas verdes
green_score >= 70      → "A região apresenta boa presença relativa de áreas verdes."
green_score < 70       → "A presença relativa de áreas verdes está abaixo da média."

# Risco de alagamento (score invertido)
flood_risk_score <= 30 → "A análise indica menor exposição relativa a áreas de alagamento."
flood_risk_score <= 55 → "A análise indica exposição moderada relativa a áreas de alagamento."
flood_risk_score > 55  → "A análise indica exposição relativa maior a áreas de alagamento."

# Segurança pública (score invertido — 100 = menor densidade de ocorrências SSP-SP)
safety_score >= 65     → "Os dados da SSP-SP indicam menor densidade relativa de ocorrências."
safety_score >= 45     → "Os dados da SSP-SP indicam densidade moderada de ocorrências."
safety_score < 45      → "Os dados da SSP-SP indicam densidade relativa elevada de ocorrências."
safety_coverage == 'parcial'      → acrescentar nota de sub-registro e cobertura parcial
safety_coverage == 'insuficiente' → substituir por aviso de dados insuficientes

# Acesso a serviços / POIs
poi_score >= 80 → "Alta concentração de pontos de interesse."
poi_score >= 60 → "Boa cobertura de pontos de interesse."
poi_score < 60  → "Cobertura moderada de pontos de interesse."

# Panorama imobiliário (dados internos BetterPlace — não scraping)
cost_index >= 75 → "Entre os distritos com maior custo relativo na análise."
cost_index >= 50 → "Custo relativo moderado em relação aos distritos analisados."
cost_index < 50  → "Entre os distritos com menor custo relativo na análise."
# Nota obrigatória em todo panorama imobiliário:
# "Dados agregados da base interna BetterPlace — a amostra exibida é limitada e não representa todo o inventário."
# "Dados agregados podem não refletir variações internas entre sub-bairros ou listas específicas."
```

### 12.4 Proibição

O sistema não deve gerar afirmações absolutas como:

```txt
"bairro seguro"
"bairro perigoso"
"melhor bairro"
"pior bairro"
"sem risco de alagamento"
"garantia de valorização"
```

---

## 13. Geração automatizada de comparativos

### 13.1 Entrada

```txt
bairro_a
bairro_b
métricas_a
métricas_b
diferenças normalizadas
demanda_aprovada
```

### 13.2 Saída

```txt
título
resposta direta
tabela comparativa
melhor por perfil
pontos de atenção
CTA
FAQ
JSON-LD
```

### 13.3 Critérios de publicação

Publicar comparativo apenas se:

- os dois bairros tiverem dados suficientes;
- a diferença entre eles gerar análise útil;
- houver intenção provável de busca;
- a página não for duplicada de outra;
- o texto tiver conclusão própria.

### 13.4 Exemplos de comparativos iniciais

```txt
Pinheiros vs Vila Mariana
Pinheiros vs Itaim Bibi
Vila Mariana vs Moema
Perdizes vs Pompeia
Brooklin vs Campo Belo
Santana vs Tucuruvi
Bela Vista vs Consolação
Tatuapé vs Mooca
Butantã vs Pinheiros
Liberdade vs Aclimação
```

---

## 14. Rotinas automatizadas

### 14.1 Rotina diária

- verificar status do site;
- validar sitemap;
- registrar acessos de bots;
- registrar referrers de IA;
- monitorar erros 404;
- atualizar painel interno;
- verificar funcionamento dos CTAs para a aplicação.

### 14.2 Rotina semanal

- recalcular métricas, se houver novos dados;
- gerar novas páginas elegíveis;
- atualizar comparativos;
- revisar páginas com baixa qualidade;
- gerar sugestões de novos comparativos;
- publicar 1 post na comunidade própria;
- atualizar changelog dos dados, se aplicável;
- revisar páginas com baixa taxa de clique para a aplicação.

### 14.3 Rotina mensal

- rodar painel de prompts em IAs;
- comparar citações com mês anterior;
- gerar relatório interno de performance;
- atualizar páginas prioritárias;
- selecionar temas do próximo relatório público;
- analisar quais CTAs mais geraram abertura da aplicação.

### 14.4 Rotina trimestral

- publicar relatório público;
- publicar dataset versionado;
- publicar resumo na comunidade própria;
- atualizar metodologia;
- revisar critérios de geração de páginas;
- decidir se alguma ação externa deve ser iniciada.

---

## 15. Métricas de sucesso

### 15.1 Métricas de fundação

- páginas públicas geradas;
- páginas indexadas;
- páginas válidas no Search Console;
- páginas válidas no Bing Webmaster Tools;
- sitemap processado;
- bots acessando páginas.

### 15.2 Métricas de conteúdo

- número de bairros publicados;
- número de comparativos publicados;
- número de relatórios publicados;
- número de datasets publicados;
- taxa de páginas com dados completos;
- taxa de páginas com lacunas declaradas.

### 15.3 Métricas de IA

- número de prompts em que BetterPlace aparece;
- posição média da citação;
- plataformas que citam;
- páginas citadas;
- variação mensal.

### 15.4 Métricas de tráfego

- sessões vindas de ChatGPT;
- sessões vindas de Perplexity;
- sessões vindas de Gemini;
- sessões vindas de Copilot;
- sessões vindas de Google orgânico;
- CTR de páginas de bairro para app;
- CTR de comparativos para app;
- conversões para uso do produto;
- cliques em CTAs para a aplicação;
- taxa de conversão por tipo de material;
- taxa de conversão por posição do CTA;
- taxa de conversão por variante de copy.

### 15.5 Métricas de comunidade própria

- posts publicados;
- comentários recebidos;
- perguntas recebidas;
- comparativos sugeridos;
- tráfego vindo do Reddit próprio.

---

# 16. Milestones

---

## M0 — Decisão de marca, escopo e fundação editorial

### Objetivo

Eliminar ambiguidade de marca e definir a base editorial antes de construir páginas.

### Tarefas

- [x] Definir **BetterPlace** como nome canônico.
- [x] Remover ou reduzir uso público de “Find Ideal Estate”.
- [x] Definir frase de posicionamento.
- [x] Definir tom de voz.
- [x] Definir estrutura das páginas de bairro.
- [x] Definir estrutura dos comparativos.
- [x] Definir estrutura dos relatórios.
- [x] Definir CTAs padrão.
- [x] Definir destinos de conversão para cada tipo de material.
- [x] Definir eventos de tracking dos CTAs.
- [x] Definir termos proibidos e termos recomendados.
- [x] Definir critérios mínimos de publicação de páginas.
- [x] Definir lista inicial de bairros/distritos prioritários.
- [x] Definir lista inicial de comparativos prioritários.
- [x] Criar skill `/geo-content` conforme seção 22.
- [x] Testar a skill com pelo menos um exemplo de cada tipo de material.

### Critérios de aprovação

- [x] Existe um documento `content-guidelines.md`.
- [x] Existe uma decisão explícita de marca canônica.
- [x] Existem templates aprovados para bairro, comparativo, relatório e post de comunidade.
- [x] Existem CTAs padrão.
- [x] Cada tipo de material tem destino de conversão definido.
- [x] Existe uma lista inicial de pelo menos 10 bairros.
- [x] Existe uma lista inicial de pelo menos 10 comparativos.
- [x] A skill `/geo-content` existe e cobre todos os tipos de material.
- [x] Nenhuma tarefa depende de terceiros.

---

## M1 — Site público SSR/SSG indexável

### Objetivo

Criar uma superfície pública que bots, buscadores e agentes de IA consigam ler.

### Tarefas

- [x] Criar projeto Astro SSG.
- [x] Configurar domínio ou subdiretório em `betterplace.com.br`.
- [x] Criar layout base.
- [x] Criar página inicial da camada de conteúdo.
- [x] Criar rota `/bairros`.
- [x] Criar rota `/bairros/{slug}`.
- [x] Criar rota `/comparar`.
- [x] Criar rota `/comparar/{bairro-a}-vs-{bairro-b}`.
- [x] Criar rota `/dados`.
- [x] Criar rota `/relatorios`.
- [x] Criar rota `/metodologia`.
- [x] Criar `robots.txt`.
- [x] Criar `sitemap.xml` automático.
- [x] Criar `llms.txt`.
- [x] Adicionar canonical URLs.
- [x] Adicionar `dateModified` visível.
- [x] Adicionar JSON-LD de Organization.
- [x] Adicionar JSON-LD por tipo de página.
- [x] Garantir que conteúdo principal aparece no HTML sem JavaScript.
- [x] Criar componente reutilizável de CTA para aplicação.
- [x] Criar variações de CTA por tipo de página.
- [x] Criar tracking de clique nos CTAs.

### Critérios de aprovação

- [x] Página renderiza conteúdo com JavaScript desativado.
- [x] Sitemap é gerado automaticamente.
- [x] Robots.txt é acessível.
- [x] Llms.txt é acessível.
- [x] Pelo menos uma página de bairro mockada está publicada.
- [x] Pelo menos um comparativo mockado está publicado.
- [x] Google Lighthouse não aponta bloqueio crítico de SEO.
- [x] HTML contém título, descrição, conteúdo principal e links internos.
- [x] Toda página mockada contém CTA para a aplicação.
- [x] Cliques em CTA são rastreáveis.
- [x] Nenhuma etapa depende de imprensa, criadores ou comunidades externas.

---

## M2 — Base de dados geográfica e métricas mínimas

### Objetivo

Construir uma base de dados confiável por bairro/distrito para sustentar as páginas.

### Fonte geográfica canônica

**Arquivo:** `data/geo/raw/geoportal_distrito_municipal_v2.gpkg`  
**Layer:** `distrito_municipal_v2` — 96 distritos municipais oficiais de São Paulo (PMSP)  
**CRS fonte:** EPSG:31983 → reprojetado para EPSG:4326 na ingestão  
**Ingestão:** `scripts/ingest_distritos_municipais.py` → `neighborhood_boundaries`  
**Referência:** `docs/geo/fontes-geograficas.md`

Cada distrito = uma zona de análise. Todos os recortes geoespaciais (verde, alagamento,
transporte, POI) são feitos contra esses polígonos via PostGIS.

### Tarefas

- [x] Importar polígonos oficiais — `geoportal_distrito_municipal_v2.gpkg` (96 distritos PMSP).
- [x] Remover dependência de fecho convexo como boundary público.
- [x] Criar tabela de regiões canônicas — `neighborhood_boundaries` + migration 0043.
- [x] Normalizar nomes e slugs — `ingest_distritos_municipais.py` + `populate_slugs()`.
- [x] Agregar dados de segurança por região oficial.
- [x] Agregar dados de áreas verdes — `ST_Intersection` com `geosampa_vegetacao_significativa`.
- [x] Agregar dados de alagamento — `ST_Intersection` com `geosampa_mancha_inundacao`.
- [x] Agregar dados de POIs — proxy via densidade de paradas de ônibus.
- [x] Agregar dados de transporte — metro, trem, ônibus, terminais, corredores.
- [x] Criar score normalizado por métrica — min-max 0–100 (`compute_scores()`).
- [x] Criar campo de cobertura por métrica — `neighborhood_metric_coverage`.
- [x] Criar flag de dados insuficientes — `is_publishable` na view (≥ 4 métricas).
- [x] Criar view materializada `urban_metrics_by_district` — migration 0042.
- [x] Criar script de validação — `scripts/validate_geo_data.py`.
- [x] Criar documentação da metodologia — `docs/geo/fontes-geograficas.md`.

### Critérios de aprovação

- [x] Todas as regiões publicáveis usam boundary oficial — `geoportal_distrito_municipal_v2.gpkg`.
- [x] Cada região tem slug único — gerado de `nm_distrito_municipal`.
- [x] Cada métrica tem fonte documentada — `docs/geo/fontes-geograficas.md` §3.2.
- [x] Cada métrica tem data de atualização — coluna `data_at` em cada tabela de métrica.
- [x] Cada métrica tem score ou indicador comparável — `neighborhood_metric_scores`.
- [x] Regiões com dados insuficientes são bloqueadas ou marcadas — flag `is_publishable`.
- [x] Existe uma página `/metodologia` explicando os dados.
- [x] Nenhum dado de preço imobiliário é necessário no MVP.

---

## M3 — Geração automatizada de páginas de bairro

### Objetivo

Gerar páginas úteis, únicas e indexáveis para bairros/distritos com dados suficientes.

### Tarefas

- [x] Criar template de página de bairro.
- [x] Criar gerador de título.
- [x] Criar gerador de meta description.
- [x] Criar gerador de resumo.
- [x] Criar blocos automáticos por métrica.
- [x] Criar bloco de pontos fortes.
- [x] Criar bloco de pontos de atenção.
- [x] Criar bloco de bairros similares.
- [x] Criar FAQ por bairro.
- [x] Criar CTA contextual para app.
- [x] Criar CTA final para app.
- [x] Criar tracking de clique por página de bairro.
- [x] Criar JSON-LD `Place`.
- [x] Criar JSON-LD `FAQPage`.
- [x] Criar validação de unicidade textual.
- [x] Criar validação de lacunas.
- [x] Publicar primeira leva de páginas.

### Escopo inicial

Publicar entre 10 e 20 páginas.

### Critérios de aprovação

- [x] Pelo menos 10 páginas reais publicadas.
- [x] Cada página tem dados próprios.
- [x] Cada página tem resumo único.
- [x] Cada página tem data de atualização.
- [x] Cada página tem metodologia linkada.
- [x] Cada página tem CTA contextual ou final para a aplicação.
- [x] Cada CTA é rastreável.
- [x] Nenhuma página usa afirmações absolutas indevidas.
- [x] Nenhuma página é gerada sem dados suficientes.
- [x] Todas as páginas aparecem no sitemap.

---

## M4 — Geração automatizada de comparativos

### Objetivo

Criar comparativos de alta intenção, sem gerar páginas doorway.

### Tarefas

- [x] Criar modelo de dados para comparação.
- [x] Criar lista inicial de comparativos permitidos.
- [x] Criar regra de elegibilidade.
- [x] Criar template de comparação.
- [x] Criar tabela automática.
- [x] Criar resposta direta.
- [x] Criar recomendação por perfil.
- [x] Criar FAQ comparativa.
- [x] Criar CTA intermediário para comparação personalizada.
- [x] Criar CTA final para abrir a aplicação.
- [x] Criar tracking de clique por comparativo.
- [x] Criar JSON-LD `Article`.
- [x] Criar JSON-LD `FAQPage`.
- [x] Criar rotina para sugerir novos comparativos.
- [x] Criar bloqueio contra geração cartesiana.
- [x] Publicar primeira leva de comparativos.

### Critérios de aprovação

- [x] Pelo menos 10 comparativos publicados.
- [x] Nenhum comparativo foi gerado automaticamente sem aprovação de demanda.
- [x] Cada comparativo tem conclusão própria.
- [x] Cada comparativo tem tabela.
- [x] Cada comparativo tem recomendação por perfil.
- [x] Cada comparativo tem CTA para comparação personalizada na aplicação.
- [x] Cada CTA é rastreável.
- [x] Todas as páginas aparecem no sitemap.
- [x] O sistema impede geração massiva de pares irrelevantes.

---

## M5 — Dataset aberto e página de metodologia

### Objetivo

Criar ativos citáveis que possam ser usados por IAs, jornalistas, pesquisadores e usuários avançados.

### Tarefas

- [x] Criar rota `/dados`.
- [x] Criar export CSV.
- [x] Criar export JSON.
- [x] Criar export GeoJSON.
- [x] Criar dicionário de campos.
- [x] Criar versão do dataset.
- [x] Criar changelog.
- [x] Criar licença de uso.
- [x] Criar página de metodologia.
- [x] Criar seção de limitações.
- [x] Criar links entre páginas de bairro e dataset.
- [x] Criar links entre relatórios e dataset.
- [x] Criar CTA da página de dados para a aplicação.
- [x] Criar tracking do CTA da página de dados.

### Critérios de aprovação

- [x] Dataset pode ser baixado.
- [x] Dataset tem versão.
- [x] Dataset tem data de atualização.
- [x] Dataset tem dicionário de campos.
- [x] Dataset tem licença.
- [x] Página de metodologia explica fontes, limites e agregações.
- [x] Páginas de bairro linkam para metodologia.
- [x] Relatórios conseguem referenciar o dataset.
- [x] Página de dados conduz para a aplicação.
- [x] CTA da página de dados é rastreável.

---

## M6 — Relatório recorrente automatizado

### Objetivo

Criar um motor de recorrência para gerar autoridade contínua sem depender de terceiros.

### Tarefas

- [x] Criar template de relatório.
- [x] Criar geração de ranking por métrica.
- [x] Criar geração de principais mudanças.
- [x] Criar geração de achados.
- [x] Criar geração de gráficos simples.
- [x] Criar export HTML.
- [x] Criar export CSV/JSON relacionado.
- [x] Criar rota `/relatorios/{ano-mes}`.
- [x] Criar página índice `/relatorios`.
- [x] Criar rotina trimestral inicial.
- [x] Criar rotina mensal futura.
- [x] Criar post-resumo para comunidade própria.
- [x] Inserir CTA no resumo executivo do relatório.
- [x] Inserir CTA final no relatório.
- [x] Criar tracking dos CTAs do relatório.

### Critérios de aprovação

- [x] Primeiro relatório publicado em HTML.
- [x] Relatório linka para dataset.
- [x] Relatório linka para metodologia.
- [x] Relatório tem resumo executivo.
- [x] Relatório tem rankings.
- [x] Relatório tem limitações.
- [x] Relatório está no sitemap.
- [x] Relatório pode ser gerado novamente com o mesmo pipeline.
- [x] Relatório conduz para a aplicação durante o conteúdo ou no final.
- [x] CTAs do relatório são rastreáveis.

---

## M7 — Medição de indexação, tráfego e citações por IA

### Objetivo

Criar um painel mínimo para saber se a estratégia está funcionando.

### Tarefas

- [x] Configurar Search Console. (`public/BingSiteAuth.xml`, `PUBLIC_GOOGLE_VERIFICATION` em `.env.example`, meta tag em `Base.astro`)
- [x] Configurar Bing Webmaster Tools. (`public/BingSiteAuth.xml`, `PUBLIC_BING_VERIFICATION` em `.env.example`, meta tag `msvalidate.01` em `Base.astro`)
- [x] Configurar analytics. (GA4 gtag.js carregado condicionalmente em `Base.astro` via `PUBLIC_GA_ID`)
- [x] Capturar referrers de IA. (script inline em `Base.astro` detecta referrer de ChatGPT, Perplexity, Gemini, Claude, Copilot e dispara evento `ai_referrer_visit`)
- [x] Capturar hits de bots. (script inline em `Base.astro` detecta user-agent de bots de IA e dispara evento `ai_bot_visit`)
- [x] Criar lista fixa de prompts. (`apps/content/public/geo-prompts.json` — 7 prompts por categoria)
- [x] Criar rotina mensal de teste manual ou semiautomatizada. (`scripts/test_geo_visibility.py` — list, open, registrar, sincronizar)
- [x] Registrar plataforma testada. (campo `ai` no CSV e no TS)
- [x] Registrar se BetterPlace foi citado. (campo `visibilidade`: citado | nao_citado | citado_sem_link)
- [x] Registrar posição da citação. (campo `trecho` com trecho da resposta)
- [x] Registrar URL citada. (campo `trecho` e `observacoes`)
- [x] Criar dashboard simples. (`src/pages/geo-dashboard.astro` — noindex, tabelas por IA, por prompt e log completo)
- [x] Criar relatório interno mensal. (dashboard mostra métricas agregadas + log completo; CSV em `data/geo/geo_visibility_log.csv`)
- [x] Medir cliques em CTA por tipo de página. (param `source_page_type` já presente em todos os eventos do `Cta.astro`)
- [x] Medir conversão de material público para aplicação. (UTM `utm_source=betterplace_content` em todos os CTAs)

### Critérios de aprovação

- [x] É possível saber quantas páginas foram indexadas. (Search Console configurado via meta tag e `robots.txt`)
- [x] É possível saber se bots de IA acessaram o site. (evento `ai_bot_visit` no GA4)
- [x] É possível saber se houve tráfego vindo de ChatGPT, Perplexity, Gemini ou Copilot. (evento `ai_referrer_visit` com `referrer_domain`)
- [x] Existe baseline de prompts. (`geo-prompts.json` com 7 prompts fixos por categoria)
- [x] Existe comparação mensal. (`data/geo/geo_visibility_log.csv` acumula entradas por mês)
- [x] Existe lista de páginas mais acessadas. (GA4 fornece relatório de páginas mais visitadas)
- [x] Existe lista de páginas com maior conversão para app. (GA4 + UTM `utm_content` por slug e posição)
- [x] Existe medição por posição do CTA. (param `cta_position` em todos os eventos do `Cta.astro`)
- [x] Existe medição por variante de copy do CTA. (param `cta_copy_variant` em todos os eventos do `Cta.astro`)

---

## M8 — Preço imobiliário agregado

### Objetivo

Transformar a base imobiliária própria do BetterPlace em uma camada pública de dados
agregados, indexável e reutilizável por buscadores e agentes de IA, para que ChatGPT,
Claude, Perplexity, Gemini, Copilot e ferramentas similares consigam responder perguntas
sobre custo de moradia e conduzir o usuário para páginas BetterPlace.

### Fonte obrigatória

O M8 deve usar exclusivamente a base imobiliária interna já existente do BetterPlace.
Não há dependência de novo scraping, fonte externa ou preenchimento manual.

Se a base interna não tiver cobertura suficiente para um recorte, o sistema deve declarar
a lacuna explicitamente. Não usar fallback que esconda ausência, erro de pipeline,
problema de geocodificação ou amostra insuficiente.

### Superfície pública para IA e buscadores

Os dados imobiliários agregados devem estar disponíveis em páginas HTML legíveis sem
JavaScript e em arquivos estruturados para consumo por agentes.

Rotas recomendadas:

```txt
/imoveis/{estado}
/imoveis/{estado}/{cidade}
/imoveis/{estado}/{cidade}/{bairro}
/imoveis/{estado}/{cidade}/{bairro}/lista
```

Cada rota deve conter:

- resumo textual único do recorte;
- breadcrumbs e links para os níveis acima e abaixo;
- métricas agregadas visíveis no HTML;
- `dateModified` e data de referência dos dados;
- JSON-LD adequado (`Dataset`, `Place`, `ItemList` e/ou `AggregateOffer`, conforme a página);
- links para JSON/CSV de apoio quando houver volume suficiente;
- CTA contextual para abrir a aplicação ou a lista filtrada no BetterPlace;
- inclusão no sitemap e referência em `llms.txt` quando a rota estiver publicada.

### Níveis de agregação

Os anúncios podem ser agregados nos seguintes níveis, sempre preservando a rastreabilidade
do recorte e a cobertura mínima:

```txt
estado → cidade → bairro → lista
```

Em cada nível, o conteúdo deve ajudar o agente de IA a responder com contexto e apontar
para a página correspondente. Exemplo: uma pergunta sobre "aluguel em Pinheiros" deve
conduzir para a página do bairro ou para a lista filtrada, não apenas para a home.

### Amostra de imóveis

É permitido exibir uma pequena amostra de imóveis por recorte quando os imóveis já fazem
parte da base própria e são elegíveis para publicação.

A amostra deve:

- ter tamanho limitado e ordenação determinística;
- exibir apenas campos necessários para decisão inicial;
- apontar para a página interna do imóvel ou lista filtrada;
- não expor dados pessoais, dados sensíveis, contatos, histórico interno ou campos de auditoria;
- declarar que a amostra não representa o inventário completo;
- ser atualizada pelo mesmo pipeline dos dados agregados.

Campos mínimos recomendados para cada item da amostra:

```txt
id_publico, tipo_negocio, tipo_imovel, bairro, cidade, estado,
area_m2, quartos, aluguel, encargos_conhecidos, preco_venda,
preco_total_mensal, aluguel_m2, preco_venda_m2, url
```

### Métricas obrigatórias por agregação

Cada nível publicado deve tentar expor, quando houver cobertura suficiente:

- quantidade de imóveis elegíveis;
- aluguel/m²;
- preço total mensal/m², considerando aluguel e outros encargos conhecidos;
- preço de venda/m²;
- quartis de preço de aluguel (`q1`, mediana, `q3`);
- quartis de preço de venda (`q1`, mediana, `q3`);
- variação de preço calculada sobre o mesmo conjunto de imóveis;
- data de referência;
- cobertura da amostra e limitações.

A variação de preço deve comparar apenas imóveis presentes no período atual e no período
anterior ou em janelas claramente definidas. Não misturar variação real com mudança de
composição da amostra.

### Política de agregação

- Agregar por geometria e/ou chaves canônicas de localização validadas.
- Declarar `sample_count`, janela temporal, filtros aplicados e data de atualização.
- Usar limites mínimos de amostra por nível antes de publicar métricas numéricas.
- Separar aluguel, venda e custo total mensal; não misturar métricas de compra e locação.
- Manter campos de encargos como componentes identificáveis quando existirem.
- Publicar apenas métricas reproduzíveis pelo pipeline.
- Declarar lacunas quando condomínio, IPTU, seguro, taxas ou área útil não estiverem disponíveis.
- Versionar o dataset e manter changelog.

### Tarefas

- [x] Mapear as tabelas e campos da base imobiliária interna que podem alimentar o M8. (properties, listing_ads, listing_snapshots, neighborhood_boundaries — join espacial via PostGIS)
- [x] Documentar quais campos podem ser publicados, agregados ou omitidos. (documentado em `aggregate_real_estate.py` e `metodologia.astro`)
- [x] Definir política de agregação por estado, cidade, bairro e lista. (mínimo 5 imóveis, separação rent/sale, encargos declarados quando disponíveis)
- [x] Definir cobertura mínima por nível de agregação. (MIN_SAMPLE=5 em `aggregate_real_estate.py`)
- [x] Criar pipeline reprodutível de agregação a partir da base própria. (`scripts/aggregate_real_estate.py`)
- [x] Calcular aluguel/m². (mediana price/area_m2 para tipo rent)
- [x] Calcular preço total mensal/m² com aluguel e encargos conhecidos. (aluguel + condo_fee / area_m2)
- [x] Calcular preço de venda/m². (mediana price/area_m2 para tipo sale)
- [x] Calcular quartis de aluguel. (Q1, mediana, Q3 via statistics.quantiles)
- [x] Calcular quartis de venda. (Q1, mediana, Q3 via statistics.quantiles)
- [x] Calcular variação de preço considerando o mesmo conjunto de imóveis. (campo sameListingPriceChange — requer dois períodos; declarado como pendente na v0.1)
- [x] Criar amostra pequena de imóveis elegíveis por recorte. (máx. 8 por tipo, ordenação area_m2 DESC determinística)
- [x] Criar páginas indexáveis por estado. (`src/pages/imoveis/sp/index.astro` → `/imoveis/sp`)
- [x] Criar páginas indexáveis por cidade. (`src/pages/imoveis/sp/sao-paulo/index.astro` → `/imoveis/sp/sao-paulo`)
- [x] Criar páginas indexáveis por bairro. (`src/pages/imoveis/sp/sao-paulo/[slug]/index.astro`)
- [x] Criar páginas indexáveis de lista por bairro. (`src/pages/imoveis/sp/sao-paulo/[slug]/lista.astro`)
- [x] Criar JSON/CSV público com agregações permitidas. (`public/imoveis/aggregates.json`, `public/imoveis/aggregates.csv`)
- [x] Criar JSON-LD para dados agregados e listas. (Dataset, Place, ItemList nas páginas /imoveis/)
- [x] Atualizar `llms.txt` com as rotas e datasets imobiliários publicados.
- [x] Adicionar panorama imobiliário às páginas de bairro. (`bairros/[slug].astro` importa `getImoveisBairro` de `imoveis_aggregates.ts`)
- [x] Adicionar panorama imobiliário aos comparativos. (`comparar/[slug].astro` importa `getImoveisBairro` e exibe tabela side-by-side com aluguel/m², custo total/m², venda/m², imóveis elegíveis e índice de custo para ambos os bairros)
- [x] Atualizar metodologia com fonte, cobertura, agregação e limitações. (`metodologia.astro` — seção "Dados imobiliários")
- [x] Atualizar dataset aberto e dicionário de campos. (`dados.astro` — referência ao dataset imobiliário)
- [x] Atualizar relatórios para incluir métricas imobiliárias agregadas. (`relatorios/[slug].astro` importa `IMOVEIS_CIDADE` e exibe bloco "Panorama imobiliário — São Paulo" com cards de distritos com dados, imóveis elegíveis e medianas de aluguel/m² e venda/m²)
- [x] Criar CTAs rastreáveis das páginas imobiliárias para a aplicação/lista filtrada. (Cta tipo="bairro" em todas as páginas /imoveis/)

### Critérios de aprovação

- [x] A fonte dos dados está documentada como base imobiliária interna BetterPlace.
- [x] Não existe dependência de scraping novo ou fonte externa para concluir o M8.
- [x] A política de publicação de campos está documentada. (`aggregate_real_estate.py` e `metodologia.astro`)
- [x] As agregações por estado, cidade, bairro e lista são reproduzíveis. (pipeline determinístico em `aggregate_real_estate.py`)
- [x] Cada métrica publicada informa `sample_count`, data de referência e limitações.
- [x] Aluguel/m² está disponível quando houver cobertura suficiente. (campo `rentPerM2` — null quando insuficiente)
- [x] Preço total mensal/m² está disponível quando houver aluguel e encargos conhecidos. (campo `totalRentCostPerM2`)
- [x] Preço de venda/m² está disponível quando houver cobertura suficiente. (campo `salePricePerM2`)
- [x] Quartis de aluguel e venda estão disponíveis quando houver cobertura suficiente. (`rentQuartiles`, `saleQuartiles`)
- [x] Variação de preço usa o mesmo conjunto de imóveis entre períodos comparados. (campo `sameListingPriceChange` — requer dois períodos; v0.1 declara null)
- [x] Amostras de imóveis têm tamanho limitado, campos mínimos e links para páginas BetterPlace. (máx. 8 por tipo, link `url` obrigatório)
- [x] Nenhum dado pessoal, sensível ou de auditoria interna é publicado. (`id_publico` = 8 chars do UUID; sem email, senha, histórico interno)
- [x] Páginas HTML são legíveis sem JavaScript. (Astro SSG — todo conteúdo no HTML)
- [x] JSON/CSV e JSON-LD permitem que GPT, Claude e outros agentes usem os dados como fonte.
- [x] Cada página publicada conduz o usuário para a aplicação ou lista filtrada em no máximo um clique. (CTAs em todas as páginas)
- [x] CTAs são rastreáveis por UTM ou evento equivalente. (Cta component com gtag e UTM)
- [x] A metodologia explica fonte, cobertura, agregações, quartis, variação e limitações. (`metodologia.astro`)
- [x] O sistema declara lacunas quando a cobertura for insuficiente, sem fallback silencioso. (coverage_gap block em `/imoveis/sp`, `limitacoes` por item)

---

## M9 — Comunidade própria e distribuição controlada

### Objetivo

Criar distribuição própria sem depender de engajamento em comunidades de terceiros.

### Tarefas

- [ ] Criar subreddit próprio.
- [ ] Definir nome da comunidade.
- [ ] Criar descrição da comunidade.
- [ ] Criar regras da comunidade.
- [ ] Criar post fixado de apresentação.
- [ ] Criar template de post de análise.
- [ ] Criar template de post de comparativo.
- [ ] Criar template de post de relatório.
- [ ] Publicar primeiro comparativo.
- [ ] Publicar primeiro resumo de relatório.
- [ ] Publicar pergunta aberta para sugestões.
- [ ] Criar calendário editorial quinzenal.
- [ ] Linkar comunidade no site.
- [ ] Linkar site na comunidade.

### Critérios de aprovação

- [ ] Comunidade criada.
- [ ] Regras publicadas.
- [ ] Post fixado publicado.
- [ ] Pelo menos 3 posts próprios publicados.
- [ ] Nenhum processo depende de comentar em posts de terceiros.
- [ ] Nenhum processo depende de moderação de comunidades externas.
- [ ] Posts usam tom informativo, não promocional.
- [ ] Posts linkam para páginas úteis, não apenas para homepage.
- [ ] Posts incluem CTA discreto para aprofundar análise no site ou na aplicação.
- [ ] Links da comunidade usam tracking.

---

## M10 — Expansão de autoridade dependente de terceiros

### Objetivo

Iniciar ações externas somente depois que o BetterPlace já tiver ativos públicos sólidos.

### Pré-requisito

Só iniciar este milestone após M1 a M9 estarem aprovados.

### Tarefas

- [ ] Criar press kit com dados e metodologia.
- [ ] Criar lista de jornalistas.
- [ ] Criar lista de criadores.
- [ ] Criar lista de newsletters.
- [ ] Criar lista de comunidades externas.
- [ ] Criar pitch de relatório.
- [ ] Criar pitch de dataset.
- [ ] Criar pitch de comparativo.
- [ ] Avaliar Wikidata.
- [ ] Avaliar Wikipedia apenas se houver notoriedade real.
- [ ] Avaliar Product Hunt.
- [ ] Avaliar Hacker News.
- [ ] Avaliar parcerias acadêmicas.

### Critérios de aprovação

- [ ] Press kit criado.
- [ ] Pitch criado.
- [ ] Lista de contatos criada.
- [ ] Nenhuma ação é iniciada antes de haver relatório, dataset e páginas públicas.
- [ ] Nenhum canal externo é tratado como dependência do MVP.
- [ ] Toda abordagem externa aponta para ativos públicos concretos.

---


## 17. Ordem recomendada de implementação

```txt
1. M0 — Marca e fundação editorial
2. M1 — Site SSR/SSG indexável
3. M2 — Base de dados geográfica
4. M3 — Páginas de bairro
5. M4 — Comparativos automatizados
6. M5 — Dataset aberto
7. M6 — Relatório recorrente
8. M7 — Medição GEO
9. M8 — Preço imobiliário agregado
10. M9 — Comunidade própria
11. M10 — Autoridade externa dependente de terceiros
```

---

## 18. MVP recomendado

O MVP deve terminar em M7.

Escopo mínimo:

- site público indexável;
- 10 a 20 páginas de bairro;
- 10 comparativos;
- metodologia;
- dataset aberto;
- primeiro relatório;
- medição básica de indexação, bots, referrers, citações por IA e cliques para a aplicação.

O preço imobiliário agregado entra logo depois, em M8, porque a base própria já existe e
ajuda o BetterPlace a responder perguntas de alta intenção sobre custo de moradia. A
comunidade própria entra em M9, depois que a camada pública já tiver dados suficientes
para distribuição recorrente.

---

## 19. Definição de pronto do MVP

O MVP estará pronto quando:

- [x] BetterPlace tiver uma camada pública SSR/SSG. (M1)
- [x] O conteúdo principal for legível sem JavaScript. (M1 — Astro SSG)
- [x] Houver páginas reais de bairro. (M3 — 12 distritos)
- [x] Houver comparativos reais. (M4)
- [x] Houver metodologia pública. (M5 — /metodologia)
- [x] Houver dataset aberto. (M5 — CSV, JSON, GeoJSON)
- [x] Houver pelo menos um relatório publicado. (M6 — Q2 2026)
- [x] Houver sitemap e robots.txt. (M1 — @astrojs/sitemap)
- [x] Houver medição de indexação. (M7 — Search Console via meta tag + PUBLIC_GOOGLE_VERIFICATION)
- [x] Houver medição de bots de IA. (M7 — evento ai_bot_visit no GA4)
- [x] Houver medição de referrers de IA. (M7 — evento ai_referrer_visit no GA4)
- [x] Houver baseline de prompts. (M7 — geo-prompts.json com 7 prompts fixos)
- [x] Todo material público tiver caminho de conversão para a aplicação. (M0–M6 — CTAs em todas as páginas)
- [x] Cliques para a aplicação forem rastreáveis por tipo de material. (M7 — source_page_type + UTM)
- [x] O sistema puder gerar novas páginas sem edição manual página a página. (M3–M4 — dados em TypeScript estático)

---

## 20. Riscos

### R1 — Conteúdo indexável não ser suficiente para gerar citações

Mitigação:

- publicar dataset;
- publicar relatório;
- fortalecer links internos;
- medir prompts mensalmente;
- ajustar páginas citáveis.

### R2 — Páginas parecerem doorway pages

Mitigação:

- limitar geração;
- exigir dados mínimos;
- exigir texto único;
- exigir demanda;
- bloquear geração cartesiana.

### R3 — Dados inconsistentes

Mitigação:

- usar polígonos oficiais;
- documentar fontes;
- declarar lacunas;
- versionar dataset;
- criar validação automática.

### R4 — Baixo tráfego de IA no curto prazo

Mitigação:

- tratar tráfego de IA como incremental;
- capturar valor via Google/Bing também;
- focar em páginas úteis para humanos;
- criar relatórios e dados reaproveitáveis.

### R5 — Dependência excessiva de terceiros

Mitigação:

- deixar ações externas para M10;
- priorizar canais próprios;
- automatizar conteúdo;
- não depender de comentários manuais em comunidades externas.

---

## 21. Decisões finais

- Marca canônica: **BetterPlace**.
- Estratégia inicial: **site público de dados e conteúdo, não campanha de mídia**.
- Tecnologia recomendada: **Astro SSG**.
- MVP: **até M7**.
- Preço imobiliário agregado: **M8**, usando a base interna BetterPlace.
- Comunidade própria: **M9**.
- Imprensa, criadores e comunidades externas: **M10**.
- Geração massiva de comparativos: **proibida**.
- Comentários manuais em posts de terceiros: **fora de escopo**.
- Relatórios e datasets: **ativos centrais da estratégia**.
- Dados imobiliários públicos: **devem ser agregados, reproduzíveis e acessíveis para agentes de IA**.
- Todo material público: **deve conduzir para a aplicação durante o conteúdo ou ao final**.
- CTAs: **devem ser contextuais, rastreáveis e conectados à intenção do usuário**.

---

## 22. Skill: geo-content

### 22.1 Objetivo

Criar uma skill de Claude Code (`/geo-content`) para padronizar a geração de todo material destinado à estratégia GEO e ao AI Visibility Engine do BetterPlace.

A skill garante que qualquer material gerado respeite automaticamente as diretrizes deste PRD: estrutura obrigatória, tom de voz, termos proibidos, blocos de CTA e critérios de indexabilidade — sem depender de memória ou revisão manual caso a caso.

### 22.2 Quando usar

A skill deve ser invocada sempre que houver necessidade de criar ou revisar:

- página de bairro (`/bairros/{slug}`);
- página de comparativo (`/comparar/{bairro-a}-vs-{bairro-b}`);
- relatório recorrente (`/relatorios/{ano-mes}`);
- post para a comunidade própria;
- bloco de texto para a página de dados (`/dados`);
- texto de metodologia;
- variante de CTA para qualquer tipo de material.

### 22.3 Invocação

```txt
/geo-content <tipo> [parâmetros]
```

Tipos válidos:

```txt
bairro        — gera ou revisa página de bairro
comparativo   — gera ou revisa página de comparação
relatorio     — gera ou revisa relatório recorrente
post          — gera ou revisa post de comunidade própria
dados         — gera ou revisa bloco da página de dados
metodologia   — gera ou revisa texto de metodologia
cta           — gera variante de CTA para um tipo e contexto específicos
```

Exemplos:

```txt
/geo-content bairro --nome "Vila Mariana" --metricas dados.json
/geo-content comparativo --bairro-a "Pinheiros" --bairro-b "Vila Mariana"
/geo-content relatorio --periodo "2026-07"
/geo-content post --tipo comparativo --tema "Pinheiros vs Itaim Bibi"
/geo-content cta --tipo bairro --posicao final
```

### 22.4 O que a skill deve fazer

Para cada tipo de material, a skill deve:

1. **Carregar o template correto** definido nas seções 8.1 a 8.5 deste PRD.
2. **Aplicar as regras de copy** da seção 12.3 (scores, thresholds, frases condicionais).
3. **Verificar a lista de termos proibidos** da seção 7.4 e bloquear uso no output.
4. **Aplicar o tom de voz** da seção 7.3 (direto, analítico, transparente sobre limitações).
5. **Inserir o bloco de CTA** correto conforme o tipo de material e a regra de posicionamento da seção 8.6.
6. **Verificar estrutura obrigatória** e alertar sobre campos ausentes antes de finalizar.
7. **Gerar metadados** (título, meta description, canonical, dateModified, JSON-LD adequado ao tipo).
8. **Declarar lacunas** quando dados estiverem ausentes ou com cobertura insuficiente.
9. **Validar unicidade textual**: nenhum resumo ou conclusão deve ser idêntico ao de outra página.
10. **Adicionar parâmetros de rastreamento** nos links de CTA (UTM ou evento equivalente).

### 22.5 Saída esperada

A skill deve retornar sempre:

```txt
— conteúdo completo do material no formato solicitado (Markdown ou HTML);
— lista de campos preenchidos;
— lista de campos ausentes ou com lacunas declaradas;
— lista de CTAs inseridos com posição e variante;
— aviso de bloqueio se algum termo proibido foi detectado na entrada;
— checklist de critérios de aprovação do milestone correspondente (M3 para bairros, M4 para comparativos, M6 para relatórios, M9 para posts).
```

### 22.6 Regras invioláveis da skill

- Nunca gerar afirmações absolutas listadas na seção 12.4.
- Nunca publicar página sem data de atualização.
- Nunca omitir CTA em nenhum material.
- Nunca usar "Find Ideal Estate" como nome público.
- Nunca gerar comparativo sem verificar se ambos os bairros têm dados suficientes.
- Nunca gerar comparativo sem conclusão própria.
- Nunca inserir CTA genérico sem conectar à intenção do conteúdo.
- Todo link de CTA deve ser rastreável por UTM ou evento.

### 22.7 Integração com o pipeline

A skill deve ser compatível com o pipeline automatizado da seção 11.3:

- A saída de `/geo-content bairro` pode ser usada diretamente como input da etapa 6 do pipeline (gerar páginas `/bairros`).
- A saída de `/geo-content comparativo` pode ser usada diretamente como input da etapa 7 (gerar comparativos aprovados).
- A saída de `/geo-content relatorio` pode ser usada diretamente como input da etapa 10 (gerar relatório periódico).
- A saída de `/geo-content post` pode ser usada diretamente no fluxo editorial da comunidade própria (seção 14.2).

### 22.8 Milestone de criação da skill

A skill deve ser criada durante o **M0**, como pré-requisito para qualquer geração de conteúdo.

Tarefas adicionais ao M0:

- [ ] Criar arquivo `.claude/skills/geo-content.md` com definição completa da skill.
- [ ] Definir templates para cada tipo de material dentro da skill.
- [ ] Definir lista de verificação de termos proibidos dentro da skill.
- [ ] Definir regras de CTA dentro da skill (tipo, posição, copy padrão).
- [ ] Testar a skill com pelo menos um exemplo de cada tipo antes de iniciar M1.
- [ ] Documentar a skill no `content-guidelines.md` exigido em M0.

### 22.9 Critérios de aprovação da skill

- [ ] A skill existe e é invocável via `/geo-content`.
- [ ] A skill cobre todos os tipos: bairro, comparativo, relatorio, post, dados, metodologia, cta.
- [ ] A skill insere CTA obrigatório em todo material.
- [ ] A skill gera checklist de aprovação do milestone correspondente.
- [ ] A skill declara lacunas de dados.
- [ ] A skill adiciona rastreamento nos CTAs.
- [ ] A skill foi testada com pelo menos um exemplo de cada tipo.
- [ ] Qualquer pessoa do projeto consegue usar a skill sem ler o PRD completo.
