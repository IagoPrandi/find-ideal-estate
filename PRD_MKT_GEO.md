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
- scraping novo de preço imobiliário.

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

- não republicar anúncios individuais de imóveis;
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

Tabelas/views sugeridas:

```txt
geo_districts
urban_metrics_by_district
safety_metrics_by_district
green_area_metrics_by_district
flood_risk_metrics_by_district
transport_access_metrics_by_district
poi_access_metrics_by_district
content_neighborhood_pages
content_comparison_pages
report_snapshots
geo_visibility_prompt_runs
```

---

### 11.3 Pipeline automatizado

Rotinas:

```txt
1. Importar/atualizar dados públicos
2. Validar geometria e cobertura
3. Agregar métricas por distrito/bairro
4. Gerar score normalizado
5. Gerar textos baseados em templates
6. Gerar páginas /bairros
7. Gerar comparativos aprovados
8. Gerar sitemap
9. Gerar dataset aberto
10. Gerar relatório periódico
11. Rodar testes de indexabilidade
12. Rodar prompts de medição GEO
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

Exemplo:

```txt
Se transport_score >= 80:
  "O bairro se destaca pelo acesso a transporte público."

Se green_score >= 80:
  "A região apresenta boa presença relativa de áreas verdes."

Se flood_risk_score <= 30:
  "A análise indica menor exposição relativa a áreas de alagamento."

Se safety_data_coverage < mínimo:
  "A métrica de segurança possui cobertura limitada para esta região."
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

### Tarefas

- [x] Importar polígonos oficiais.
- [x] Remover dependência de fecho convexo como boundary público.
- [x] Criar tabela de regiões canônicas.
- [x] Normalizar nomes e slugs.
- [x] Agregar dados de segurança por região oficial.
- [x] Agregar dados de áreas verdes.
- [x] Agregar dados de alagamento.
- [x] Agregar dados de POIs.
- [x] Agregar dados de transporte.
- [x] Criar score normalizado por métrica.
- [x] Criar campo de cobertura por métrica.
- [x] Criar flag de dados insuficientes.
- [x] Criar view materializada `urban_metrics_by_district`.
- [x] Criar script de validação.
- [x] Criar documentação da metodologia.

### Critérios de aprovação

- [x] Todas as regiões publicáveis usam boundary oficial.
- [x] Cada região tem slug único.
- [x] Cada métrica tem fonte documentada.
- [x] Cada métrica tem data de atualização.
- [x] Cada métrica tem score ou indicador comparável.
- [x] Regiões com dados insuficientes são bloqueadas ou marcadas.
- [x] Existe uma página `/metodologia` explicando os dados.
- [x] Nenhum dado de preço imobiliário é necessário no MVP.

---

## M3 — Geração automatizada de páginas de bairro

### Objetivo

Gerar páginas úteis, únicas e indexáveis para bairros/distritos com dados suficientes.

### Tarefas

- [ ] Criar template de página de bairro.
- [ ] Criar gerador de título.
- [ ] Criar gerador de meta description.
- [ ] Criar gerador de resumo.
- [ ] Criar blocos automáticos por métrica.
- [ ] Criar bloco de pontos fortes.
- [ ] Criar bloco de pontos de atenção.
- [ ] Criar bloco de bairros similares.
- [ ] Criar FAQ por bairro.
- [ ] Criar CTA contextual para app.
- [ ] Criar CTA final para app.
- [ ] Criar tracking de clique por página de bairro.
- [ ] Criar JSON-LD `Place`.
- [ ] Criar JSON-LD `FAQPage`.
- [ ] Criar validação de unicidade textual.
- [ ] Criar validação de lacunas.
- [ ] Publicar primeira leva de páginas.

### Escopo inicial

Publicar entre 10 e 20 páginas.

### Critérios de aprovação

- [ ] Pelo menos 10 páginas reais publicadas.
- [ ] Cada página tem dados próprios.
- [ ] Cada página tem resumo único.
- [ ] Cada página tem data de atualização.
- [ ] Cada página tem metodologia linkada.
- [ ] Cada página tem CTA contextual ou final para a aplicação.
- [ ] Cada CTA é rastreável.
- [ ] Nenhuma página usa afirmações absolutas indevidas.
- [ ] Nenhuma página é gerada sem dados suficientes.
- [ ] Todas as páginas aparecem no sitemap.

---

## M4 — Geração automatizada de comparativos

### Objetivo

Criar comparativos de alta intenção, sem gerar páginas doorway.

### Tarefas

- [ ] Criar modelo de dados para comparação.
- [ ] Criar lista inicial de comparativos permitidos.
- [ ] Criar regra de elegibilidade.
- [ ] Criar template de comparação.
- [ ] Criar tabela automática.
- [ ] Criar resposta direta.
- [ ] Criar recomendação por perfil.
- [ ] Criar FAQ comparativa.
- [ ] Criar CTA intermediário para comparação personalizada.
- [ ] Criar CTA final para abrir a aplicação.
- [ ] Criar tracking de clique por comparativo.
- [ ] Criar JSON-LD `Article`.
- [ ] Criar JSON-LD `FAQPage`.
- [ ] Criar rotina para sugerir novos comparativos.
- [ ] Criar bloqueio contra geração cartesiana.
- [ ] Publicar primeira leva de comparativos.

### Critérios de aprovação

- [ ] Pelo menos 10 comparativos publicados.
- [ ] Nenhum comparativo foi gerado automaticamente sem aprovação de demanda.
- [ ] Cada comparativo tem conclusão própria.
- [ ] Cada comparativo tem tabela.
- [ ] Cada comparativo tem recomendação por perfil.
- [ ] Cada comparativo tem CTA para comparação personalizada na aplicação.
- [ ] Cada CTA é rastreável.
- [ ] Todas as páginas aparecem no sitemap.
- [ ] O sistema impede geração massiva de pares irrelevantes.

---

## M5 — Dataset aberto e página de metodologia

### Objetivo

Criar ativos citáveis que possam ser usados por IAs, jornalistas, pesquisadores e usuários avançados.

### Tarefas

- [ ] Criar rota `/dados`.
- [ ] Criar export CSV.
- [ ] Criar export JSON.
- [ ] Criar export GeoJSON.
- [ ] Criar dicionário de campos.
- [ ] Criar versão do dataset.
- [ ] Criar changelog.
- [ ] Criar licença de uso.
- [ ] Criar página de metodologia.
- [ ] Criar seção de limitações.
- [ ] Criar links entre páginas de bairro e dataset.
- [ ] Criar links entre relatórios e dataset.
- [ ] Criar CTA da página de dados para a aplicação.
- [ ] Criar tracking do CTA da página de dados.

### Critérios de aprovação

- [ ] Dataset pode ser baixado.
- [ ] Dataset tem versão.
- [ ] Dataset tem data de atualização.
- [ ] Dataset tem dicionário de campos.
- [ ] Dataset tem licença.
- [ ] Página de metodologia explica fontes, limites e agregações.
- [ ] Páginas de bairro linkam para metodologia.
- [ ] Relatórios conseguem referenciar o dataset.
- [ ] Página de dados conduz para a aplicação.
- [ ] CTA da página de dados é rastreável.

---

## M6 — Relatório recorrente automatizado

### Objetivo

Criar um motor de recorrência para gerar autoridade contínua sem depender de terceiros.

### Tarefas

- [ ] Criar template de relatório.
- [ ] Criar geração de ranking por métrica.
- [ ] Criar geração de principais mudanças.
- [ ] Criar geração de achados.
- [ ] Criar geração de gráficos simples.
- [ ] Criar export HTML.
- [ ] Criar export PDF.
- [ ] Criar export CSV/JSON relacionado.
- [ ] Criar rota `/relatorios/{ano-mes}`.
- [ ] Criar página índice `/relatorios`.
- [ ] Criar rotina trimestral inicial.
- [ ] Criar rotina mensal futura.
- [ ] Criar post-resumo para comunidade própria.
- [ ] Inserir CTA no resumo executivo do relatório.
- [ ] Inserir CTA final no relatório.
- [ ] Criar tracking dos CTAs do relatório.

### Critérios de aprovação

- [ ] Primeiro relatório publicado em HTML.
- [ ] Primeiro relatório publicado em PDF.
- [ ] Relatório linka para dataset.
- [ ] Relatório linka para metodologia.
- [ ] Relatório tem resumo executivo.
- [ ] Relatório tem rankings.
- [ ] Relatório tem limitações.
- [ ] Relatório está no sitemap.
- [ ] Relatório pode ser gerado novamente com o mesmo pipeline.
- [ ] Relatório conduz para a aplicação durante o conteúdo ou no final.
- [ ] CTAs do relatório são rastreáveis.

---

## M7 — Medição de indexação, tráfego e citações por IA

### Objetivo

Criar um painel mínimo para saber se a estratégia está funcionando.

### Tarefas

- [ ] Configurar Search Console.
- [ ] Configurar Bing Webmaster Tools.
- [ ] Configurar analytics.
- [ ] Capturar referrers de IA.
- [ ] Capturar hits de bots.
- [ ] Criar lista fixa de prompts.
- [ ] Criar rotina mensal de teste manual ou semiautomatizada.
- [ ] Registrar plataforma testada.
- [ ] Registrar se BetterPlace foi citado.
- [ ] Registrar posição da citação.
- [ ] Registrar URL citada.
- [ ] Criar dashboard simples.
- [ ] Criar relatório interno mensal.
- [ ] Medir cliques em CTA por tipo de página.
- [ ] Medir conversão de material público para aplicação.

### Critérios de aprovação

- [ ] É possível saber quantas páginas foram indexadas.
- [ ] É possível saber se bots de IA acessaram o site.
- [ ] É possível saber se houve tráfego vindo de ChatGPT, Perplexity, Gemini ou Copilot.
- [ ] Existe baseline de prompts.
- [ ] Existe comparação mensal.
- [ ] Existe lista de páginas mais acessadas.
- [ ] Existe lista de páginas com maior conversão para app.
- [ ] Existe medição por posição do CTA.
- [ ] Existe medição por variante de copy do CTA.

---

## M8 — Comunidade própria e distribuição controlada

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

## M9 — Expansão de autoridade dependente de terceiros

### Objetivo

Iniciar ações externas somente depois que o BetterPlace já tiver ativos públicos sólidos.

### Pré-requisito

Só iniciar este milestone após M1 a M8 estarem aprovados.

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

## M10 — Preço imobiliário agregado

### Objetivo

Adicionar preço como métrica apenas depois da base GEO estar consolidada.

### Observação

Preço fica fora do MVP porque envolve maior complexidade operacional e risco jurídico.

### Tarefas

- [ ] Avaliar fontes permitidas.
- [ ] Avaliar termos de uso.
- [ ] Definir política de agregação.
- [ ] Garantir que nenhum anúncio individual será republicado.
- [ ] Criar métrica agregada por região.
- [ ] Criar cobertura mínima.
- [ ] Adicionar preço às páginas de bairro.
- [ ] Adicionar preço aos comparativos.
- [ ] Atualizar metodologia.
- [ ] Atualizar dataset.
- [ ] Atualizar relatórios.

### Critérios de aprovação

- [ ] Existe avaliação jurídica ou de risco documentada.
- [ ] Apenas dados agregados são publicados.
- [ ] Nenhum anúncio individual é exposto.
- [ ] A metodologia explica fonte e cobertura.
- [ ] Páginas indicam limitações da métrica.
- [ ] O sistema funciona mesmo sem preço.

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
9. M8 — Comunidade própria
10. M9 — Autoridade externa dependente de terceiros
11. M10 — Preço imobiliário agregado
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

A comunidade própria entra logo depois, em M8, porque é útil, mas não deve atrasar a base técnica.

---

## 19. Definição de pronto do MVP

O MVP estará pronto quando:

- [ ] BetterPlace tiver uma camada pública SSR/SSG.
- [ ] O conteúdo principal for legível sem JavaScript.
- [ ] Houver páginas reais de bairro.
- [ ] Houver comparativos reais.
- [ ] Houver metodologia pública.
- [ ] Houver dataset aberto.
- [ ] Houver pelo menos um relatório publicado.
- [ ] Houver sitemap e robots.txt.
- [ ] Houver medição de indexação.
- [ ] Houver medição de bots de IA.
- [ ] Houver medição de referrers de IA.
- [ ] Houver baseline de prompts.
- [ ] Todo material público tiver caminho de conversão para a aplicação.
- [ ] Cliques para a aplicação forem rastreáveis por tipo de material.
- [ ] O sistema puder gerar novas páginas sem edição manual página a página.

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

- deixar ações externas para M9;
- priorizar canais próprios;
- automatizar conteúdo;
- não depender de comentários manuais em comunidades externas.

---

## 21. Decisões finais

- Marca canônica: **BetterPlace**.
- Estratégia inicial: **site público de dados e conteúdo, não campanha de mídia**.
- Tecnologia recomendada: **Astro SSG**.
- MVP: **até M7**.
- Comunidade própria: **M8**.
- Imprensa, criadores e comunidades externas: **M9**.
- Preço imobiliário: **M10**, fora do MVP.
- Geração massiva de comparativos: **proibida**.
- Comentários manuais em posts de terceiros: **fora de escopo**.
- Relatórios e datasets: **ativos centrais da estratégia**.
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
— checklist de critérios de aprovação do milestone correspondente (M3 para bairros, M4 para comparativos, M6 para relatórios, M8 para posts).
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
