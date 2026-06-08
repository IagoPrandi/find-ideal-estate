import { BAIRROS, type Bairro } from './bairros';

export interface RankingItem {
  slug: string;
  nome: string;
  score: number;
}

export interface RankingMetrica {
  metrica: string;
  label: string;
  nota: string;
  top: RankingItem[];
}

export interface Achado {
  titulo: string;
  descricao: string;
}

export interface PostResumo {
  titulo: string;
  corpo: string;
}

export interface Relatorio {
  slug: string;
  titulo: string;
  periodo: string;
  dataPublicacao: string;
  resumoExecutivo: string;
  rankingsPorMetrica: RankingMetrica[];
  principaisMudancas: string[];
  achados: Achado[];
  limitacoes: string[];
  totalDistritosAnalisados: number;
  csvPath: string;
  jsonPath: string;
  postResumo: PostResumo;
}

function topN(
  campo: keyof Pick<Bairro, 'transportScore' | 'greenScore' | 'floodRiskScore' | 'safetyScore' | 'poiScore'>,
  n = 5,
): RankingItem[] {
  return [...BAIRROS]
    .sort((a, b) => (b[campo] as number) - (a[campo] as number))
    .slice(0, n)
    .map((b) => ({ slug: b.slug, nome: b.nome, score: b[campo] as number }));
}

export const RELATORIOS: Relatorio[] = [
  {
    slug: '2026-06',
    titulo: 'Relatório BetterPlace de Qualidade Urbana — São Paulo — 2.º Trimestre de 2026',
    periodo: '2.º Trimestre de 2026 (abril–junho)',
    dataPublicacao: '2026-06-07',
    resumoExecutivo:
      'Esta é a primeira edição do relatório trimestral BetterPlace de qualidade urbana para São Paulo. ' +
      'A análise abrange 12 distritos municipais com dados reais do pipeline GeoSampa e SSP-SP. ' +
      'Os dados indicam que Consolação e Butantã lideram em cobertura de áreas verdes, ' +
      'Santana e Mooca apresentam menor densidade relativa de ocorrências registradas, ' +
      'e Vila Mariana concentra o maior acesso relativo a transporte público entre os distritos analisados. ' +
      'Por ser a edição inicial, não há variação mensal a reportar — o próximo relatório (Q3 2026) ' +
      'incluirá comparação com esta linha de base.',
    rankingsPorMetrica: [
      {
        metrica: 'transport_score',
        label: 'Acesso a transporte público',
        nota: 'Score ponderado de densidade de metrô, CPTM, ônibus e terminais. Fonte: GTFS GeoSampa.',
        top: topN('transportScore'),
      },
      {
        metrica: 'green_score',
        label: 'Áreas verdes',
        nota: '% vegetação significativa por área do distrito via ST_Intersection. Fonte: GeoSampa.',
        top: topN('greenScore'),
      },
      {
        metrica: 'flood_risk_score',
        label: 'Menor exposição a alagamento',
        nota: 'Score invertido — 100 = menor exposição relativa a manchas de inundação. Fonte: GeoSampa.',
        top: topN('floodRiskScore'),
      },
      {
        metrica: 'safety_score',
        label: 'Menor densidade de ocorrências SSP-SP',
        nota: 'Score invertido — 100 = menor densidade relativa de B.O. por km². Cobertura parcial — sub-registro estrutural SSP-SP.',
        top: topN('safetyScore'),
      },
      {
        metrica: 'poi_score',
        label: 'Acesso a pontos de interesse',
        nota: 'Proxy via densidade de paradas de ônibus por km². Fonte: GeoSampa.',
        top: topN('poiScore'),
      },
    ],
    principaisMudancas: [
      'Primeira edição — não há variação a reportar. Os dados desta edição constituem a linha de base para comparações futuras.',
      'Pipeline GeoSampa completamente operacional para 12 distritos municipais.',
      'Cobertura de segurança (SSP-SP) com status "parcial" em todos os distritos — limitação estrutural do sub-registro.',
      'Dados de preço imobiliário não incluídos nesta edição (previsto para M8).',
    ],
    achados: [
      {
        titulo: 'Consolação lidera em áreas verdes entre os distritos centrais',
        descricao:
          'Com green_score de 82,5/100, Consolação apresenta a maior cobertura relativa de vegetação significativa entre os distritos analisados. ' +
          'Destaque para a concentração de parques e corredores arborizados no eixo Paulista-Higienópolis.',
      },
      {
        titulo: 'Santana referência na zona norte com menor densidade de ocorrências',
        descricao:
          'Santana registra safety_score de 94,2/100, o maior entre os 12 distritos. ' +
          'Os dados indicam menor densidade relativa de boletins de ocorrência SSP-SP — mas cabe ressaltar o sub-registro estrutural em todos os distritos.',
      },
      {
        titulo: 'Vila Mariana com maior acesso relativo a transporte',
        descricao:
          'Transport_score de 44,2/100 coloca Vila Mariana à frente dos demais no conjunto analisado, ' +
          'reflexo da cobertura combinada das linhas 1 e 2 do metrô e dos corredores de ônibus na zona sul.',
      },
      {
        titulo: 'Distritos da zona leste com menor cobertura vegetal',
        descricao:
          'Mooca (12,4) e Tatuapé (15,4) apresentam os menores green_scores entre os 12 distritos. ' +
          'A urbanização densa nessas regiões reduz a proporção de vegetação significativa por km².',
      },
    ],
    limitacoes: [
      'Cobertura restrita a 12 dos 96 distritos municipais de São Paulo — expansão prevista para próximas edições.',
      'Dados de segurança (SSP-SP) com cobertura "parcial" para todos os distritos — sub-registro estrutural é uma limitação inerente.',
      'Dados de preço imobiliário não incluídos — previsto para M8.',
      'Sem variação histórica nesta edição — análise comparativa disponível a partir do relatório Q3 2026.',
      'Scores calculados apenas em relação aos distritos analisados — não representam ranking absoluto dos 96 distritos.',
      'Metodologia completa: betterplace.com.br/metodologia.',
    ],
    totalDistritosAnalisados: 12,
    csvPath: '/relatorios/betterplace-qualidade-urbana-sp-2026-06.csv',
    jsonPath: '/relatorios/betterplace-qualidade-urbana-sp-2026-06.json',
    postResumo: {
      titulo: '[Análise] Relatório BetterPlace Q2 2026 — rankings de qualidade urbana por distrito em SP',
      corpo: `Publicamos a primeira edição do nosso relatório trimestral de qualidade urbana para São Paulo. Analisamos 12 distritos com dados públicos de transporte, áreas verdes, alagamento, segurança e acesso a serviços.

Destaques desta edição:
- Consolação lidera em áreas verdes (green_score 82,5/100) entre os distritos analisados.
- Santana apresenta menor densidade relativa de ocorrências SSP-SP (safety_score 94,2/100) na zona norte.
- Vila Mariana tem o maior acesso relativo a transporte público (transport_score 44,2/100).
- Mooca e Tatuapé ficam com os menores scores de vegetação significativa — urbanização densa na zona leste.

Metodologia: dados do pipeline GeoSampa (PMSP) + SSP-SP, scores normalizados 0–100 entre os distritos analisados. Dados de segurança têm cobertura parcial — sub-registro estrutural declarado.

Relatório completo, dataset e metodologia: betterplace.com.br/relatorios/2026-06

Pergunta para a comunidade: qual comparativo de bairros faria sentido analisar na próxima edição?`,
    },
  },
];

export function getRelatorio(slug: string): Relatorio | undefined {
  return RELATORIOS.find((r) => r.slug === slug);
}

export function isPublishableBatch(): boolean {
  return RELATORIOS.length >= 1;
}
