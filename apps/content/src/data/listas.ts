import type { Bairro } from './bairros';

/** Métricas elegíveis para ranking — todas orientadas a "maior = melhor". */
export type MetricaScore = 'transportScore' | 'greenScore' | 'floodRiskScore' | 'poiScore';

export interface Lista {
  slug: string;
  /** Título SEO sem ano — o ano é anexado no template a partir de dataAtualizacao. */
  titulo: string;
  h1: string;
  descricao: string;
  tag: string;
  metrica: MetricaScore;
  /** Rótulo da dimensão usado no texto e nos itens. */
  unidade: string;
  /** Ressalva metodológica exibida abaixo do ranking. */
  notaMetrica: string;
  topN: number;
  faq: Array<{ pergunta: string; resposta: string }>;
  dataAtualizacao: string;
}

// Rótulo legível por métrica (para "vs média" e itens).
export const METRICA_LABEL: Record<MetricaScore, string> = {
  transportScore: 'transporte público',
  greenScore: 'áreas verdes',
  floodRiskScore: 'proteção contra alagamento',
  poiScore: 'acesso a serviços',
};

export function rankBairros(bairros: Bairro[], metrica: MetricaScore, topN: number): Bairro[] {
  return [...bairros].sort((a, b) => b[metrica] - a[metrica]).slice(0, topN);
}

export const LISTAS: Lista[] = [
  {
    slug: 'bairros-com-melhor-transporte-publico-em-sao-paulo',
    titulo: 'Bairros com melhor transporte público em São Paulo',
    h1: 'Bairros com melhor transporte público em São Paulo',
    descricao:
      'Ranking dos distritos de São Paulo com melhor acesso a transporte público (metrô, CPTM, ônibus e terminais), entre os distritos analisados pelo BetterPlace. Dados públicos com metodologia transparente.',
    tag: 'Ranking · Transporte',
    metrica: 'transportScore',
    unidade: 'transporte público',
    notaMetrica:
      'O score de transporte combina densidade ponderada de metrô, CPTM, ônibus (SPTrans/EMTU) e terminais por km² do distrito, normalizada (0–100) entre os distritos analisados.',
    topN: 5,
    faq: [
      {
        pergunta: 'Como é calculado o score de transporte público?',
        resposta:
          'O score combina a densidade ponderada de metrô, CPTM, linhas de ônibus e terminais por km² do distrito, normalizada de 0 a 100 entre os distritos analisados. Maior score indica maior cobertura relativa de transporte público.',
      },
      {
        pergunta: 'Este ranking cobre todos os bairros de São Paulo?',
        resposta:
          'Não. O ranking considera apenas os distritos já publicados pelo BetterPlace, com dados suficientes e recorte oficial. A cobertura é ampliada a cada atualização.',
      },
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'bairros-com-mais-areas-verdes-em-sao-paulo',
    titulo: 'Bairros de São Paulo com mais áreas verdes',
    h1: 'Bairros de São Paulo com mais áreas verdes',
    descricao:
      'Ranking dos distritos de São Paulo com maior presença relativa de áreas verdes, entre os distritos analisados pelo BetterPlace. Baseado em vegetação significativa por área do distrito.',
    tag: 'Ranking · Áreas verdes',
    metrica: 'greenScore',
    unidade: 'áreas verdes',
    notaMetrica:
      'O score de áreas verdes usa o percentual de vegetação significativa por área do distrito (interseção com a camada GeoSampa de vegetação), normalizado (0–100) entre os distritos analisados.',
    topN: 5,
    faq: [
      {
        pergunta: 'O que conta como área verde neste ranking?',
        resposta:
          'A métrica usa a camada de vegetação significativa do GeoSampa, recortada por interseção espacial contra o polígono oficial de cada distrito. O resultado é o percentual de cobertura vegetal relativo, normalizado entre os distritos analisados.',
      },
      {
        pergunta: 'Áreas verdes significam mais qualidade de vida?',
        resposta:
          'Maior presença de áreas verdes é um indicador associado a conforto térmico e lazer, mas a decisão de moradia depende de outros fatores como transporte, serviços e custo. Compare as dimensões na página de cada bairro.',
      },
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'bairros-com-menor-risco-de-alagamento-em-sao-paulo',
    titulo: 'Bairros de São Paulo com menor risco de alagamento',
    h1: 'Bairros de São Paulo com menor risco de alagamento',
    descricao:
      'Ranking dos distritos de São Paulo com menor exposição relativa a manchas de inundação, entre os distritos analisados pelo BetterPlace. Score invertido: maior = menor risco.',
    tag: 'Ranking · Alagamento',
    metrica: 'floodRiskScore',
    unidade: 'proteção contra alagamento',
    notaMetrica:
      'O índice usa o percentual da área do distrito coberto por mancha de inundação (GeoSampa), invertido e normalizado (0–100). Maior índice indica menor exposição relativa — não significa ausência de risco.',
    topN: 5,
    faq: [
      {
        pergunta: 'Um índice alto significa que o bairro não alaga?',
        resposta:
          'Não. O índice é relativo entre os distritos analisados: maior valor indica menor exposição relativa a manchas de inundação mapeadas, não ausência de risco. Eventos extremos podem causar alagamentos pontuais em qualquer região.',
      },
      {
        pergunta: 'Qual a fonte dos dados de alagamento?',
        resposta:
          'A mancha de inundação vem do GeoSampa (PMSP), recortada por interseção espacial contra o polígono oficial de cada distrito. Veja a metodologia para detalhes e limitações.',
      },
    ],
    dataAtualizacao: '2026-06-06',
  },
];
