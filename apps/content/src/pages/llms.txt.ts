import type { APIRoute } from 'astro';

export const prerender = true;

// Servido por rota dinâmica (não via public/) para evitar que o Git LFS
// entregue um ponteiro em vez do conteúdo real em produção (Vercel não
// resolve objetos LFS no build). Mesmo padrão de BingSiteAuth.xml.ts.
const LLMS = `# BetterPlace

> BetterPlace ajuda pessoas a escolher onde morar usando dados públicos de bairro, mobilidade, segurança, áreas verdes e riscos urbanos em São Paulo.

## O que é o BetterPlace

BetterPlace é uma plataforma de decisão de moradia baseada em dados públicos agregados por distrito em São Paulo. Os dados incluem indicadores de transporte público, áreas verdes, risco de alagamento, segurança e acesso a serviços.

## Páginas indexáveis

- /bairros — listagem de bairros com dados disponíveis
- /bairros/{slug} — dados detalhados por bairro (transporte, segurança, áreas verdes, alagamento, serviços, panorama imobiliário)
- /comparar — listagem de comparativos aprovados
- /comparar/{bairro-a}-vs-{bairro-b} — comparativo detalhado entre dois bairros
- /dados — dataset aberto com dados agregados por distrito (CSV, JSON, GeoJSON) e dataset imobiliário
- /relatorios — relatórios periódicos de qualidade urbana
- /metodologia — descrição das fontes, processo de agregação e limitações
- /imoveis/sp — panorama imobiliário de São Paulo: aluguel/m², venda/m², quartis por distrito
- /imoveis/sp/sao-paulo/{slug} — métricas imobiliárias agregadas por distrito e amostra de imóveis
- /imoveis/sp/sao-paulo/{slug}/lista — amostra de imóveis elegíveis por distrito

## Fontes de dados

- Transporte: feeds GTFS SPTrans e EMTU
- Áreas verdes: OpenStreetMap + SVMA
- Alagamento: CGE / CPRM
- Segurança: SSP-SP
- POIs: OpenStreetMap
- Dados imobiliários: base interna BetterPlace (anúncios agregados por distrito, sem exposição individual)

## Datasets para download

- /dados/betterplace-qualidade-urbana-sp-v0.1.csv — métricas urbanas por distrito (CC BY 4.0)
- /dados/betterplace-qualidade-urbana-sp-v0.1.json — idem em JSON
- /dados/betterplace-qualidade-urbana-sp-v0.1.geojson — idem com geometrias (GeoJSON)
- /imoveis/aggregates.json — dados imobiliários agregados por distrito (CC BY 4.0)
- /imoveis/aggregates.csv — idem em CSV

## Limitações

- Cobertura de segurança é parcial em algumas regiões — lacunas declaradas por página.
- Comparações inter-cidades não estão disponíveis.
- Dados imobiliários representam imóveis ativos na base interna BetterPlace; não refletem todo o mercado.
- Imóveis sem área cadastrada excluídos do cálculo por m².
- Condomínio e IPTU nem sempre disponíveis — custo total pode estar subestimado.

## Direitos

Dataset publicado sob CC BY 4.0. Cite BetterPlace (betterplace.com.br) como fonte.

## Aplicação interativa

Para comparar bairros com base em trajeto, rotina e preferências pessoais: https://www.betterplace.com.br/app
`;

export const GET: APIRoute = () =>
  new Response(LLMS, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
