# Find Ideal Estate (BetterPlace)

O BetterPlace ajuda quem procura imóvel em São Paulo a escolher primeiro onde morar. Você informa os lugares que frequenta, como trabalho ou faculdade, e os tempos máximos de deslocamento. A aplicação sugere regiões compatíveis com a rotina, compara indicadores urbanos e reúne anúncios para alugar ou comprar.

## Explore online

- [Explore os bairros de São Paulo](https://betterplace.com.br/bairros) para ver mapas e indicadores por distrito.
- [Compare Pinheiros e Vila Mariana](https://betterplace.com.br/comparar/pinheiros-vs-vila-mariana) para ver um exemplo com dados publicados.
- [Abra a aplicação](https://app.betterplace.com.br) para iniciar uma busca por área ou tempo de deslocamento.

## Como funciona uma busca

1. Informe um endereço importante para sua rotina, selecione o meio de transporte e defina quanto tempo você aceita gastar no trajeto.
2. A aplicação calcula isócronas, que são áreas alcançáveis dentro do tempo informado. Você também pode delimitar uma área no mapa.
3. Compare as zonas por transporte, segurança, áreas verdes, alagamento e pontos de interesse. A cobertura de cada indicador depende da fonte e da região.
4. Consulte os anúncios reunidos de QuintoAndar, ZAP Imóveis e Viva Real, filtre por preço e tipo de imóvel e salve os resultados de interesse. A aplicação deduplica anúncios e usa os preços coletados para compor painéis por região.

As páginas públicas reúnem comparativos e indicadores de São Paulo. A [metodologia](https://betterplace.com.br/metodologia) explica as fontes e suas limitações.

## Rodar localmente

Instale Git, Git LFS e Docker com Compose. O Git LFS baixa o `requirements.txt` e as bases geográficas e de transporte. Na raiz do repositório, copie o arquivo de ambiente e suba a API e a interface.

```bash
git lfs install
git clone https://github.com/IagoPrandi/find-ideal-estate.git
cd find-ideal-estate
git lfs pull
cp .env.example .env
docker compose up -d --build api ui
```

Se o GitHub pedir autenticação para baixar os arquivos LFS, autentique o Git na sua conta do GitHub e repita `git lfs pull`. No PowerShell, use `Copy-Item .env.example .env` para criar o arquivo de ambiente. O Compose também inicia PostgreSQL/PostGIS, Redis e o site público em Astro. A API aplica as migrações do Alembic ao iniciar.

| Serviço | Endereço |
| --- | --- |
| Aplicação | [localhost:5173](http://localhost:5173) |
| Site público | [localhost:4321](http://localhost:4321) |
| API | [Health check](http://localhost:8000/health) |

### Habilitar a jornada com dados reais

A primeira subida disponibiliza a interface e cria o banco. Para fazer buscas completas, configure as fontes que a sua instalação vai usar.

| Funcionalidade | Dependência |
| --- | --- |
| Mapa interativo | Preencha `VITE_MAPTILER_API_KEY` no `.env` com uma chave do MapTiler. |
| Zonas por tempo de viagem | Configure `VALHALLA_URL` para uma instância do Valhalla com dados da região, acessível pelo contêiner da API. Para transporte público, prepare o roteador com GTFS e preencha as tabelas de transporte no PostGIS. |
| Camadas e indicadores urbanos | Use os conjuntos de dados e os scripts de ingestão descritos na [documentação técnica](DOCUMENTATION.md) e nas [fontes geográficas](docs/geo/fontes-geograficas.md). |
| Coleta de anúncios | Configure o coletor em [`.env.example`](.env.example). Se usar Firecrawl, informe `FIRECRAWL_API_KEY`. Para tarefas de coleta que usam um navegador, inicie o worker com `docker compose up -d worker-scrape-browser`. |

Após editar o `.env`, execute `docker compose up -d api ui` para aplicar as alterações. Os dados carregados em instalações anteriores e as credenciais de serviços externos devem ser fornecidos pela própria instalação.

### Carregar dados básicos de transporte

Com a API em execução, copie os scripts e as bases de transporte incluídas no repositório para o contêiner. Os comandos abaixo importam GTFS e a rede de transporte do GeoSampa no banco local.

```bash
docker compose cp scripts api:/app/scripts
docker compose cp data_cache api:/app/data_cache
docker compose exec api python scripts/ingest_gtfs_postgis.py
docker compose exec api python scripts/ingest_geosampa_postgis.py
```

Para parar os serviços, use `docker compose down`.

## Estrutura do repositório

| Caminho | Responsabilidade |
| --- | --- |
| [`apps/web`](apps/web) | Jornada de busca e mapas com React, Vite e MapLibre |
| [`apps/api`](apps/api) | API FastAPI, consultas espaciais e tarefas em segundo plano com Dramatiq e Redis |
| [`apps/content`](apps/content) | Páginas públicas em Astro, com indicadores, comparativos e relatórios |
| [`infra/migrations`](infra/migrations) | Esquema PostgreSQL/PostGIS e migrações Alembic |
| [`scripts`](scripts) | Ingestão de dados, geração de relatórios e verificações da aplicação |

Leia a [documentação técnica](DOCUMENTATION.md) para aprofundar cada etapa da jornada, a [documentação GEO](docs/geo/README.md) para entender os indicadores e o [guia de deploy](DEPLOY.md) para publicar uma instalação.
