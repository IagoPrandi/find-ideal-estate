export interface RealEstateMetrics {
  aggregationLevel: 'estado' | 'cidade' | 'bairro' | 'lista';
  aggregationSlug: string;
  /** Quantidade de imóveis elegíveis na agregação. */
  listingSampleCount: number;
  /** Aluguel/m² agregado (R$/mês). */
  rentPerM2?: number;
  /** Aluguel + encargos conhecidos/m² (R$/mês). */
  totalRentCostPerM2?: number;
  /** Preço de venda/m² agregado (R$). */
  salePricePerM2?: number;
  rentQuartiles?: { q1: number; median: number; q3: number };
  saleQuartiles?: { q1: number; median: number; q3: number };
  /** Variação de preço calculada sobre o mesmo conjunto de imóveis. */
  sameListingPriceChange?: number;
  /** Índice de custo relativo entre recortes comparáveis: 0 = mais acessível, 100 = maior custo. */
  costIndex: number;
  sampleListings?: Array<{
    idPublico: string;
    tipoNegocio: 'aluguel' | 'venda';
    tipoImovel: string;
    bairro: string;
    cidade: string;
    estado: string;
    areaM2?: number;
    quartos?: number;
    aluguel?: number;
    encargosConhecidos?: number;
    precoVenda?: number;
    precoTotalMensal?: number;
    aluguelM2?: number;
    precoVendaM2?: number;
    url: string;
  }>;
  dataAt: string;
}
export interface Bairro {
  slug: string;
  nome: string;
  distrito: string;
  resumo: string;
  perfil: string;
  /** Fonte: neighborhood_metric_scores (metric_name='transport'), min-max normalizado 0–100. */
  transportScore: number;
  /** Fonte: neighborhood_metric_scores (metric_name='green_area'), min-max normalizado 0–100. */
  greenScore: number;
  /** Fonte: neighborhood_metric_scores (metric_name='flood_risk'), invertido — 100 = menor risco. */
  floodRiskScore: number;
  /** Fonte: neighborhood_metric_scores (metric_name='safety'), invertido — 100 = menor densidade SSP-SP. Dado relativo, não absoluto. */
  safetyScore: number;
  safetyDataCoverage: 'completa' | 'parcial' | 'insuficiente';
  /** Fonte: neighborhood_metric_scores (metric_name='poi_access'), proxy = densidade de paradas de ônibus. */
  poiScore: number;
  /** Dados imobiliários agregados da base interna, com amostra limitada quando elegível. */
  realEstateMetrics?: RealEstateMetrics;
  pontosFortes: string[];
  pontosAtencao: string[];
  bairrosSimilares: string[];
  dataAtualizacao: string;
  lacunas?: string[];
}

// Scores gerados pelo pipeline aggregate_geo_metrics.py a partir do banco PostGIS local.
// Fonte primária: GeoSampa (green, flood, transport, poi) e SSP-SP via join espacial (safety).
// Última execução do pipeline: 2026-06-06.
// NÃO alterar manualmente — atualizar via pipeline.
export const BAIRROS: Bairro[] = [
  {
    slug: 'vila-mariana',
    nome: 'Vila Mariana',
    distrito: 'Vila Mariana',
    resumo:
      'Vila Mariana tende a ser uma opção para quem prioriza acesso moderado a transporte público, menor exposição relativa a alagamentos e bom acesso a serviços. A análise combina dados públicos de mobilidade, segurança, áreas verdes e riscos urbanos.',
    perfil: 'Adequado para quem busca equilíbrio entre transporte, serviços e perfil residencial consolidado na zona sul.',
    transportScore: 44.2,
    greenScore: 25.4,
    floodRiskScore: 100.0,
    safetyScore: 89.9,
    safetyDataCoverage: 'parcial',
    poiScore: 45.1,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — metrô linhas 1 e 2 e corredores de ônibus.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'A presença relativa de áreas verdes está abaixo da média dos distritos analisados.',
      'Cobertura moderada de pontos de interesse em relação a distritos de maior centralidade.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['moema', 'bela-vista', 'liberdade'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'pinheiros',
    nome: 'Pinheiros',
    distrito: 'Pinheiros',
    resumo:
      'Pinheiros tende a combinar boa presença de áreas verdes com acesso moderado a transporte público e menor exposição relativa a alagamentos. A análise combina dados públicos de mobilidade, segurança, áreas verdes e riscos urbanos.',
    perfil: 'Adequado para quem valoriza centralidade, opções gastronômicas e acesso à Faria Lima e região Oeste.',
    transportScore: 32.0,
    greenScore: 68.1,
    floodRiskScore: 100.0,
    safetyScore: 81.9,
    safetyDataCoverage: 'parcial',
    poiScore: 31.9,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — metrô linha 2 e CPTM.',
      'A presença de áreas verdes está próxima à média dos distritos analisados.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
    ],
    pontosAtencao: [
      'Cobertura moderada de pontos de interesse em relação a distritos de maior centralidade.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências — sempre interpretar com ressalva de sub-registro.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['itaim-bibi', 'vila-mariana', 'consolacao'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'itaim-bibi',
    nome: 'Itaim Bibi',
    distrito: 'Itaim Bibi',
    resumo:
      'Itaim Bibi tende a ser uma opção para quem trabalha na região da Faria Lima ou Berrini e valoriza acesso moderado a transporte e menor exposição relativa a alagamentos. A análise combina dados públicos de mobilidade, acesso a POIs, áreas verdes e riscos urbanos.',
    perfil: 'Adequado para quem prioriza proximidade ao centro financeiro e mobilidade com perfil residencial consolidado.',
    transportScore: 32.9,
    greenScore: 34.5,
    floodRiskScore: 100.0,
    safetyScore: 84.9,
    safetyDataCoverage: 'parcial',
    poiScore: 35.0,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — linhas de ônibus e acesso ao metrô.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'A presença relativa de áreas verdes está abaixo da média dos distritos analisados.',
      'Cobertura moderada de pontos de interesse — score de POI abaixo de distritos mais centrais.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['pinheiros', 'moema', 'vila-mariana'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'moema',
    nome: 'Moema',
    distrito: 'Moema',
    resumo:
      'Moema tende a se destacar entre os distritos que combinam boa presença relativa de áreas verdes com menor exposição a alagamentos e menor densidade relativa de ocorrências. A análise combina dados públicos de mobilidade, vegetação, riscos urbanos e pontos de interesse.',
    perfil: 'Adequado para quem busca equilíbrio entre áreas verdes, transporte e perfil residencial de média-alta densidade.',
    transportScore: 21.5,
    greenScore: 73.8,
    floodRiskScore: 100.0,
    safetyScore: 88.1,
    safetyDataCoverage: 'parcial',
    poiScore: 22.5,
    pontosFortes: [
      'A região apresenta boa presença relativa de áreas verdes — Parque do Ibirapuera e corredores arborizados.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'O bairro apresenta acesso moderado a transporte público — dependência maior de ônibus em relação ao metrô.',
      'Cobertura moderada de pontos de interesse — score de POI abaixo da média.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['vila-mariana', 'itaim-bibi', 'campo-belo'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'bela-vista',
    nome: 'Bela Vista',
    distrito: 'Bela Vista',
    resumo:
      'Bela Vista tende a se destacar pela centralidade geográfica e acesso moderado a transporte público no eixo central de São Paulo. A análise combina dados públicos de mobilidade, serviços, áreas verdes e riscos urbanos.',
    perfil: 'Adequado para quem prioriza acesso ao centro histórico, transporte público e diversidade de serviços urbanos.',
    transportScore: 28.9,
    greenScore: 21.5,
    floodRiskScore: 100.0,
    safetyScore: 69.0,
    safetyDataCoverage: 'parcial',
    poiScore: 28.6,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — múltiplas linhas de metrô e ônibus na região central.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
      'Localização central com fácil deslocamento para diferentes zonas da cidade.',
    ],
    pontosAtencao: [
      'A presença relativa de áreas verdes está abaixo da média dos distritos analisados.',
      'Os dados da SSP-SP indicam densidade moderada de ocorrências registradas — sub-registro estrutural conhecido.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['consolacao', 'liberdade', 'vila-mariana'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'consolacao',
    nome: 'Consolação',
    distrito: 'Consolação',
    resumo:
      'Consolação tende a se destacar pela alta cobertura de áreas verdes e localização no eixo Paulista-Higienópolis com acesso moderado a transporte público. A análise combina dados públicos de mobilidade, áreas verdes, riscos urbanos e pontos de interesse.',
    perfil: 'Adequado para quem prioriza centralidade, acesso à Avenida Paulista e presença de áreas verdes.',
    transportScore: 30.2,
    greenScore: 82.5,
    floodRiskScore: 100.0,
    safetyScore: 60.2,
    safetyDataCoverage: 'parcial',
    poiScore: 29.1,
    pontosFortes: [
      'A região apresenta boa presença relativa de áreas verdes — destaque entre os distritos centrais.',
      'O bairro apresenta acesso moderado a transporte público — metrô linha 2 e corredores de ônibus.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
    ],
    pontosAtencao: [
      'Os dados da SSP-SP indicam densidade moderada de ocorrências registradas — sub-registro estrutural conhecido.',
      'Cobertura moderada de pontos de interesse em relação ao score de transporte.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['bela-vista', 'pinheiros', 'perdizes'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'liberdade',
    nome: 'Liberdade',
    distrito: 'Liberdade',
    resumo:
      'Liberdade tende a se destacar pela localização privilegiada no eixo central sul de São Paulo e menor exposição relativa a alagamentos. A análise combina dados públicos de mobilidade, serviços, áreas verdes e riscos urbanos.',
    perfil: 'Adequado para quem prioriza acesso ao centro histórico, diversidade cultural e mobilidade por transporte público.',
    transportScore: 38.9,
    greenScore: 21.6,
    floodRiskScore: 99.7,
    safetyScore: 80.8,
    safetyDataCoverage: 'parcial',
    poiScore: 42.0,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — metrô linhas 1 e 3 e ônibus expressos.',
      'A análise indica menor exposição relativa a áreas de alagamento entre os distritos centrais.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'A presença relativa de áreas verdes está abaixo da média — distritos centrais tendem a menor cobertura vegetal.',
      'Cobertura moderada de pontos de interesse em relação a distritos de maior centralidade.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['bela-vista', 'vila-mariana', 'cambuci'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'tatuape',
    nome: 'Tatuapé',
    distrito: 'Tatuapé',
    resumo:
      'Tatuapé tende a ser uma opção relevante na zona leste para quem busca acesso moderado a transporte, menor exposição a alagamentos e menor densidade relativa de ocorrências. A análise combina dados públicos de mobilidade, vegetação, riscos urbanos e pontos de interesse.',
    perfil: 'Adequado para quem busca infraestrutura consolidada na zona leste com acesso ao metrô e CPTM.',
    transportScore: 30.2,
    greenScore: 15.4,
    floodRiskScore: 100.0,
    safetyScore: 89.3,
    safetyDataCoverage: 'parcial',
    poiScore: 32.9,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — metrô linha 3 e CPTM.',
      'A análise indica menor exposição relativa a áreas de alagamento para a zona leste.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'A presença relativa de áreas verdes está abaixo da média dos distritos analisados.',
      'Cobertura moderada de pontos de interesse — score de POI abaixo de distritos centrais.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['mooca', 'vila-prudente', 'penha'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'mooca',
    nome: 'Mooca',
    distrito: 'Mooca',
    resumo:
      'Mooca tende a apresentar acesso moderado a transporte público e menor densidade relativa de ocorrências na zona leste consolidada. A análise combina dados públicos de mobilidade, vegetação, riscos urbanos e pontos de interesse.',
    perfil: 'Adequado para quem busca distrito com infraestrutura consolidada na zona leste e bom acesso ao centro.',
    transportScore: 29.3,
    greenScore: 12.4,
    floodRiskScore: 99.9,
    safetyScore: 90.6,
    safetyDataCoverage: 'parcial',
    poiScore: 32.5,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — metrô linha 3 e opções de ônibus.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'A presença relativa de áreas verdes está abaixo da média dos distritos analisados.',
      'Cobertura moderada de pontos de interesse — score de POI abaixo de distritos centrais.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['tatuape', 'belem', 'bras'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'santana',
    nome: 'Santana',
    distrito: 'Santana',
    resumo:
      'Santana tende a ser uma das referências de infraestrutura na zona norte, com acesso moderado a transporte público e menor densidade relativa de ocorrências. A análise combina dados públicos de mobilidade, áreas verdes, riscos urbanos e pontos de interesse.',
    perfil: 'Adequado para quem busca distrito estruturado na zona norte com acesso ao metrô e perfil residencial consolidado.',
    transportScore: 31.4,
    greenScore: 39.8,
    floodRiskScore: 100.0,
    safetyScore: 94.2,
    safetyDataCoverage: 'parcial',
    poiScore: 34.2,
    pontosFortes: [
      'O bairro apresenta acesso moderado a transporte público — metrô linha 1 e corredores de ônibus.',
      'A análise indica menor exposição relativa a áreas de alagamento na zona norte.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'A presença relativa de áreas verdes está abaixo da média dos distritos analisados.',
      'Cobertura moderada de pontos de interesse — score de POI abaixo de distritos centrais.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['tucuruvi', 'casa-verde', 'mandaqui'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'perdizes',
    nome: 'Perdizes',
    distrito: 'Perdizes',
    resumo:
      'Perdizes tende a combinar boa presença de áreas verdes com acesso moderado a transporte público na zona oeste. A análise combina dados públicos de mobilidade, vegetação, riscos urbanos e pontos de interesse.',
    perfil: 'Adequado para quem busca perfil residencial tranquilo com boa arborização e acesso ao eixo Paulista-Higienópolis.',
    transportScore: 30.2,
    greenScore: 54.7,
    floodRiskScore: 100.0,
    safetyScore: 78.6,
    safetyDataCoverage: 'parcial',
    poiScore: 32.1,
    pontosFortes: [
      'A região apresenta presença relativa de áreas verdes acima da média na zona oeste.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'O bairro apresenta acesso moderado a transporte público — menor cobertura de metrô em relação a distritos centrais.',
      'Cobertura moderada de pontos de interesse — dependência maior de comércio local.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['pompeia', 'lapa', 'consolacao'],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'butanta',
    nome: 'Butantã',
    distrito: 'Butantã',
    resumo:
      'Butantã tende a apresentar boa presença de áreas verdes e menor exposição relativa a alagamentos na zona oeste. A análise combina dados públicos de mobilidade, vegetação, riscos urbanos e pontos de interesse.',
    perfil: 'Adequado para quem busca proximidade à USP, áreas verdes e ambiente de perfil universitário e residencial.',
    transportScore: 20.7,
    greenScore: 77.7,
    floodRiskScore: 100.0,
    safetyScore: 89.3,
    safetyDataCoverage: 'parcial',
    poiScore: 22.7,
    pontosFortes: [
      'A região apresenta boa presença relativa de áreas verdes — campus da USP contribui para cobertura vegetal.',
      'A análise indica menor exposição relativa a áreas de alagamento.',
      'Os dados da SSP-SP indicam menor densidade relativa de ocorrências registradas nesta região.',
    ],
    pontosAtencao: [
      'O bairro apresenta acesso moderado a transporte público — menor cobertura de metrô na zona oeste.',
      'Cobertura moderada de pontos de interesse — score de POI abaixo da média dos distritos analisados.',
    ],
    lacunas: [
      'Dados imobiliários agregados vêm da base interna BetterPlace e não representam todo o mercado.',
      'Dados de segurança com sub-registro estrutural conhecido (SSP-SP) — interpretar com cautela.',
    ],
    bairrosSimilares: ['perdizes', 'pinheiros', 'lapa'],
    dataAtualizacao: '2026-06-06',
  },
];

export function getBairro(slug: string): Bairro | undefined {
  return BAIRROS.find((b) => b.slug === slug);
}

/**
 * Verifica se há resumos duplicados entre bairros — viola o requisito M3 de unicidade textual.
 * Retorna lista de slugs com conflito (deve ser vazia em produção).
 */
export function validateUniqueness(): string[] {
  const seen = new Map<string, string>();
  const conflicts: string[] = [];
  for (const b of BAIRROS) {
    const key = b.resumo.trim().toLowerCase();
    if (seen.has(key)) {
      conflicts.push(`${b.slug} duplica resumo de ${seen.get(key)}`);
    } else {
      seen.set(key, b.slug);
    }
  }
  return conflicts;
}

/**
 * Retorna bairros com lacunas de dados declaradas.
 */
export function getBairrosComLacunas(): Bairro[] {
  return BAIRROS.filter(
    (b) => b.safetyDataCoverage === 'insuficiente' || (b.lacunas && b.lacunas.length > 0),
  );
}

/**
 * Verifica se o conjunto atende o critério mínimo de publicação do M3 (≥ 10 páginas).
 */
export function isPublishableBatch(): boolean {
  return BAIRROS.length >= 10;
}
