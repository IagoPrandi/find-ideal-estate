import { BAIRROS, type Bairro } from './bairros';

export interface Comparativo {
  slug: string;
  bairroA: string;
  bairroB: string;
  slugA: string;
  slugB: string;
  titulo: string;
  respostaDireta: string;
  melhorTransporte: string;
  melhorAreas: string;
  melhorServicos: string;
  melhorFlood: string;
  recomendacaoPerfil: Array<{ perfil: string; recomendado: string }>;
  pontosAtencao: string[];
  dataAtualizacao: string;
}

// Pares aprovados explicitamente — anti-geração cartesiana.
// Nenhum comparativo pode ser publicado se seu slug não estiver neste set.
const PARES_APROVADOS = new Set([
  'pinheiros-vs-vila-mariana',
  'pinheiros-vs-itaim-bibi',
  'vila-mariana-vs-moema',
  'bela-vista-vs-consolacao',
  'tatuape-vs-mooca',
  'butanta-vs-pinheiros',
  'perdizes-vs-consolacao',
  'santana-vs-liberdade',
  'itaim-bibi-vs-moema',
  'liberdade-vs-vila-mariana',
]);

// Scores de referência (fonte: bairros.ts, pipeline 2026-06-06):
// pinheiros:    T:32,0 / G:68,1 / F:100,0 / S:81,9 / P:31,9
// vila-mariana: T:44,2 / G:25,4 / F:100,0 / S:89,9 / P:45,1
// itaim-bibi:   T:32,9 / G:34,5 / F:100,0 / S:84,9 / P:35,0
// moema:        T:21,5 / G:73,8 / F:100,0 / S:88,1 / P:22,5
// bela-vista:   T:28,9 / G:21,5 / F:100,0 / S:69,0 / P:28,6
// consolacao:   T:30,2 / G:82,5 / F:100,0 / S:60,2 / P:29,1
// liberdade:    T:38,9 / G:21,6 / F:99,7  / S:80,8 / P:42,0
// tatuape:      T:30,2 / G:15,4 / F:100,0 / S:89,3 / P:32,9
// mooca:        T:29,3 / G:12,4 / F:99,9  / S:90,6 / P:32,5
// santana:      T:31,4 / G:39,8 / F:100,0 / S:94,2 / P:34,2
// perdizes:     T:30,2 / G:54,7 / F:100,0 / S:78,6 / P:32,1
// butanta:      T:20,7 / G:77,7 / F:100,0 / S:89,3 / P:22,7

export const COMPARATIVOS: Comparativo[] = [
  {
    slug: 'pinheiros-vs-vila-mariana',
    bairroA: 'Pinheiros',
    bairroB: 'Vila Mariana',
    slugA: 'pinheiros',
    slugB: 'vila-mariana',
    titulo: 'Pinheiros vs Vila Mariana: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Pinheiros tende a ser mais adequado para quem prioriza áreas verdes e ambiente urbano próximo à Faria Lima. Vila Mariana tende a ser mais indicada para quem depende de transporte público, acesso a serviços e prefere perfil residencial consolidado. A melhor escolha depende principalmente do trajeto diário.',
    melhorTransporte: 'Vila Mariana (score 44,2 vs 32,0)',
    melhorAreas: 'Pinheiros (score 68,1 vs 25,4)',
    melhorServicos: 'Vila Mariana (score POI 45,1 vs 31,9)',
    melhorFlood: 'Ambos os distritos apresentam menor exposição relativa a áreas de alagamento (score 100,0 nos dois).',
    recomendacaoPerfil: [
      { perfil: 'Trabalha na Faria Lima ou zona oeste', recomendado: 'Pinheiros' },
      { perfil: 'Depende de transporte público diariamente', recomendado: 'Vila Mariana' },
      { perfil: 'Prioriza áreas verdes', recomendado: 'Pinheiros (score 68,1 vs 25,4)' },
      { perfil: 'Busca maior cobertura de serviços e comércio próximos', recomendado: 'Vila Mariana (score POI 45,1 vs 31,9)' },
    ],
    pontosAtencao: [
      'Ambos os distritos apresentam presença de áreas verdes abaixo da média geral — mas Pinheiros se destaca positivamente em relação a Vila Mariana nessa dimensão.',
      'Dados de segurança disponíveis com cobertura parcial (SSP-SP) — comparação relativa, não absoluta. Sub-registro é limitação estrutural dos dados de criminalidade.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão do dataset (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'pinheiros-vs-itaim-bibi',
    bairroA: 'Pinheiros',
    bairroB: 'Itaim Bibi',
    slugA: 'pinheiros',
    slugB: 'itaim-bibi',
    titulo: 'Pinheiros vs Itaim Bibi: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Pinheiros e Itaim Bibi são distritos próximos com perfis distintos. Pinheiros tende a ser mais adequado para quem prioriza áreas verdes e ambiente urbano diverso. Itaim Bibi tende a ser mais indicado para quem trabalha na Faria Lima ou Berrini e valoriza proximidade ao centro financeiro. O score de transporte é similar entre os dois.',
    melhorTransporte: 'Itaim Bibi (32,9 vs 32,0 — diferença marginal)',
    melhorAreas: 'Pinheiros (score 68,1 vs 34,5)',
    melhorServicos: 'Itaim Bibi (score POI 35,0 vs 31,9)',
    melhorFlood: 'Ambos os distritos apresentam menor exposição relativa a áreas de alagamento (score 100,0 nos dois).',
    recomendacaoPerfil: [
      { perfil: 'Trabalha na Faria Lima ou Berrini', recomendado: 'Itaim Bibi (menor deslocamento)' },
      { perfil: 'Prioriza áreas verdes', recomendado: 'Pinheiros (score 68,1 vs 34,5)' },
      { perfil: 'Busca maior cobertura de serviços', recomendado: 'Itaim Bibi (score POI 35,0 vs 31,9)' },
      { perfil: 'Acesso a transporte público', recomendado: 'Diferença marginal — Itaim Bibi (32,9 vs 32,0)' },
    ],
    pontosAtencao: [
      'A diferença de transporte entre os distritos é marginal (score 32,9 vs 32,0) — não deve ser fator determinante.',
      'Dados de segurança com cobertura parcial (SSP-SP) — interpretar com cautela. Sub-registro é limitação estrutural.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'vila-mariana-vs-moema',
    bairroA: 'Vila Mariana',
    bairroB: 'Moema',
    slugA: 'vila-mariana',
    slugB: 'moema',
    titulo: 'Vila Mariana vs Moema: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Vila Mariana tende a ser mais indicada para quem depende de transporte público e acesso a serviços próximos. Moema tende a ser mais adequada para quem valoriza áreas verdes, tranquilidade e proximidade ao Parque do Ibirapuera. A diferença de transporte é significativa (score 44,2 vs 21,5).',
    melhorTransporte: 'Vila Mariana (score 44,2 vs 21,5)',
    melhorAreas: 'Moema (score 73,8 vs 25,4 — Parque do Ibirapuera contribui para a cobertura vegetal do distrito)',
    melhorServicos: 'Vila Mariana (score POI 45,1 vs 22,5)',
    melhorFlood: 'Ambos os distritos apresentam menor exposição relativa a áreas de alagamento (score 100,0 nos dois).',
    recomendacaoPerfil: [
      { perfil: 'Depende de transporte público diariamente', recomendado: 'Vila Mariana (score 44,2 vs 21,5)' },
      { perfil: 'Prioriza áreas verdes e parques', recomendado: 'Moema (score 73,8 vs 25,4)' },
      { perfil: 'Busca maior cobertura de serviços e comércio', recomendado: 'Vila Mariana (score POI 45,1 vs 22,5)' },
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Vila Mariana (89,9 vs 88,1 — diferença pequena; ambos com cobertura parcial)' },
    ],
    pontosAtencao: [
      'A diferença de transporte é um dos fatores mais relevantes entre estes dois distritos — Moema depende mais de ônibus, com menor cobertura de metrô.',
      'Dados de segurança com cobertura parcial (SSP-SP) para ambos os distritos. Sub-registro é limitação estrutural.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'bela-vista-vs-consolacao',
    bairroA: 'Bela Vista',
    bairroB: 'Consolação',
    slugA: 'bela-vista',
    slugB: 'consolacao',
    titulo: 'Bela Vista vs Consolação: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Consolação tende a se destacar pela maior cobertura de áreas verdes (score 82,5 vs 21,5) — uma das maiores entre distritos centrais. Bela Vista apresenta indicadores de segurança ligeiramente melhores na análise SSP-SP. Os demais indicadores são similares entre os dois.',
    melhorTransporte: 'Consolação (30,2 vs 28,9 — diferença marginal)',
    melhorAreas: 'Consolação (score 82,5 vs 21,5 — diferença expressiva)',
    melhorServicos: 'Consolação (score POI 29,1 vs 28,6 — diferença marginal)',
    melhorFlood: 'Ambos os distritos apresentam menor exposição relativa a áreas de alagamento (score 100,0 nos dois).',
    recomendacaoPerfil: [
      { perfil: 'Prioriza áreas verdes no centro da cidade', recomendado: 'Consolação (score 82,5 vs 21,5)' },
      { perfil: 'Busca localização próxima ao centro histórico', recomendado: 'Bela Vista' },
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Bela Vista (69,0 vs 60,2 — ambos com cobertura parcial)' },
      { perfil: 'Acesso à Avenida Paulista', recomendado: 'Consolação (localização no eixo Paulista-Higienópolis)' },
    ],
    pontosAtencao: [
      'A diferença de transporte e serviços entre os distritos é marginal — áreas verdes são o principal diferencial.',
      'Ambos os distritos têm score de segurança (SSP-SP) abaixo da média dos distritos analisados — dado relativo com cobertura parcial.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'tatuape-vs-mooca',
    bairroA: 'Tatuapé',
    bairroB: 'Mooca',
    slugA: 'tatuape',
    slugB: 'mooca',
    titulo: 'Tatuapé vs Mooca: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Tatuapé e Mooca são distritos adjacentes da zona leste com perfis muito similares em quase todas as dimensões. Mooca apresenta score de segurança ligeiramente superior (90,6 vs 89,3). A escolha entre eles tende a depender de fatores específicos de localização interna ou custo imobiliário, não de diferença expressiva nos indicadores.',
    melhorTransporte: 'Tatuapé (30,2 vs 29,3 — diferença marginal)',
    melhorAreas: 'Tatuapé (score 15,4 vs 12,4 — ambos significativamente abaixo da média)',
    melhorServicos: 'Tatuapé (score POI 32,9 vs 32,5 — diferença marginal)',
    melhorFlood: 'Tatuapé (100,0) e Mooca (99,9) — praticamente equivalentes; ambos com menor exposição relativa.',
    recomendacaoPerfil: [
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Mooca (90,6 vs 89,3 — diferença pequena; ambos com cobertura parcial)' },
      { perfil: 'Acesso a transporte público na zona leste', recomendado: 'Diferença marginal — ambos têm metrô linha 3' },
      { perfil: 'Busca maior presença de comércio e serviços', recomendado: 'Diferença marginal (32,9 vs 32,5)' },
      { perfil: 'Menor risco de alagamento', recomendado: 'Ambos equivalentes — scores próximos de 100,0' },
    ],
    pontosAtencao: [
      'Ambos os distritos têm presença de áreas verdes expressivamente abaixo da média — não é um diferencial relevante na comparação.',
      'Dados de segurança com cobertura parcial (SSP-SP) para ambos os distritos. Sub-registro é limitação estrutural.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8) — podem ser um fator decisivo entre estes dois distritos similares.',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'butanta-vs-pinheiros',
    bairroA: 'Butantã',
    bairroB: 'Pinheiros',
    slugA: 'butanta',
    slugB: 'pinheiros',
    titulo: 'Butantã vs Pinheiros: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Butantã tende a ser mais adequado para quem prioriza áreas verdes, proximidade à USP e ambiente residencial mais tranquilo na zona oeste. Pinheiros tende a ser mais indicado para quem depende de transporte público e quer maior acesso a serviços, vida urbana e opções gastronômicas. A diferença de transporte é o fator mais relevante (score 32,0 vs 20,7).',
    melhorTransporte: 'Pinheiros (score 32,0 vs 20,7)',
    melhorAreas: 'Butantã (score 77,7 vs 68,1 — campus da USP contribui para a cobertura vegetal)',
    melhorServicos: 'Pinheiros (score POI 31,9 vs 22,7)',
    melhorFlood: 'Ambos os distritos apresentam menor exposição relativa a áreas de alagamento (score 100,0 nos dois).',
    recomendacaoPerfil: [
      { perfil: 'Prioriza áreas verdes e ambiente universitário', recomendado: 'Butantã (score 77,7 vs 68,1)' },
      { perfil: 'Depende de transporte público', recomendado: 'Pinheiros (score 32,0 vs 20,7)' },
      { perfil: 'Busca maior cobertura de serviços e comércio', recomendado: 'Pinheiros (score POI 31,9 vs 22,7)' },
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Butantã (89,3 vs 81,9 — ambos com cobertura parcial)' },
    ],
    pontosAtencao: [
      'Butantã tem score de transporte abaixo da média — dependência maior de ônibus e acesso menos direto ao metrô.',
      'Dados de segurança com cobertura parcial (SSP-SP) para ambos os distritos. Sub-registro é limitação estrutural.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'perdizes-vs-consolacao',
    bairroA: 'Perdizes',
    bairroB: 'Consolação',
    slugA: 'perdizes',
    slugB: 'consolacao',
    titulo: 'Perdizes vs Consolação: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Consolação tende a se destacar pela maior cobertura de áreas verdes (score 82,5 vs 54,7). Perdizes apresenta melhor cobertura de serviços e menor densidade relativa de ocorrências (SSP-SP). O score de transporte é idêntico. A escolha depende da prioridade entre áreas verdes e acesso a comércio e serviços.',
    melhorTransporte: 'Empate (score 30,2 nos dois distritos)',
    melhorAreas: 'Consolação (score 82,5 vs 54,7 — ambos acima da média entre distritos analisados)',
    melhorServicos: 'Perdizes (score POI 32,1 vs 29,1)',
    melhorFlood: 'Ambos os distritos apresentam menor exposição relativa a áreas de alagamento (score 100,0 nos dois).',
    recomendacaoPerfil: [
      { perfil: 'Prioriza áreas verdes', recomendado: 'Consolação (score 82,5 vs 54,7)' },
      { perfil: 'Busca maior cobertura de serviços e comércio', recomendado: 'Perdizes (score POI 32,1 vs 29,1)' },
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Perdizes (78,6 vs 60,2 — ambos com cobertura parcial)' },
      { perfil: 'Acesso a transporte público', recomendado: 'Ambos equivalentes (score 30,2 nos dois)' },
    ],
    pontosAtencao: [
      'Ambos os distritos são vizinhos e têm bom acesso ao eixo Paulista-Higienópolis.',
      'Consolação tem score de segurança (SSP-SP) abaixo de Perdizes — dado relativo com cobertura parcial; interpretar com cautela.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'santana-vs-liberdade',
    bairroA: 'Santana',
    bairroB: 'Liberdade',
    slugA: 'santana',
    slugB: 'liberdade',
    titulo: 'Santana vs Liberdade: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'São dois distritos em zonas opostas da cidade — Santana na zona norte, Liberdade na zona central sul. Santana tende a ser mais adequada para quem prioriza menor densidade relativa de ocorrências e ambiente residencial consolidado. Liberdade tende a ser mais indicada para quem depende de transporte público e acesso a maior variedade de serviços.',
    melhorTransporte: 'Liberdade (score 38,9 vs 31,4)',
    melhorAreas: 'Santana (score 39,8 vs 21,6)',
    melhorServicos: 'Liberdade (score POI 42,0 vs 34,2)',
    melhorFlood: 'Santana (100,0) e Liberdade (99,7) — praticamente equivalentes; ambos com menor exposição relativa.',
    recomendacaoPerfil: [
      { perfil: 'Depende de transporte público e acesso ao centro', recomendado: 'Liberdade (score 38,9 vs 31,4)' },
      { perfil: 'Prioriza áreas verdes na zona norte', recomendado: 'Santana (score 39,8 vs 21,6)' },
      { perfil: 'Busca maior cobertura de serviços', recomendado: 'Liberdade (score POI 42,0 vs 34,2)' },
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Santana (94,2 vs 80,8 — ambos com cobertura parcial)' },
    ],
    pontosAtencao: [
      'Estes distritos estão em zonas distintas da cidade — a comparação é mais relevante para quem não tem restrição de zona.',
      'Dados de segurança com cobertura parcial (SSP-SP) para ambos. Sub-registro é limitação estrutural dos dados de criminalidade.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'itaim-bibi-vs-moema',
    bairroA: 'Itaim Bibi',
    bairroB: 'Moema',
    slugA: 'itaim-bibi',
    slugB: 'moema',
    titulo: 'Itaim Bibi vs Moema: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Itaim Bibi tende a ser mais indicado para quem trabalha na Faria Lima ou Berrini e depende de transporte público. Moema tende a ser mais adequada para quem prioriza áreas verdes, tranquilidade e menor densidade relativa de ocorrências. A diferença de áreas verdes (score 73,8 vs 34,5) e transporte (32,9 vs 21,5) são os fatores mais relevantes.',
    melhorTransporte: 'Itaim Bibi (score 32,9 vs 21,5)',
    melhorAreas: 'Moema (score 73,8 vs 34,5)',
    melhorServicos: 'Itaim Bibi (score POI 35,0 vs 22,5)',
    melhorFlood: 'Ambos os distritos apresentam menor exposição relativa a áreas de alagamento (score 100,0 nos dois).',
    recomendacaoPerfil: [
      { perfil: 'Trabalha na Faria Lima ou Berrini', recomendado: 'Itaim Bibi (menor deslocamento)' },
      { perfil: 'Prioriza áreas verdes e ambiente mais tranquilo', recomendado: 'Moema (score 73,8 vs 34,5)' },
      { perfil: 'Depende de transporte público', recomendado: 'Itaim Bibi (score 32,9 vs 21,5)' },
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Moema (88,1 vs 84,9 — ambos com cobertura parcial)' },
    ],
    pontosAtencao: [
      'Moema tem score de transporte abaixo da média — dependência maior de ônibus com menor cobertura de metrô.',
      'Dados de segurança com cobertura parcial (SSP-SP) para ambos. Sub-registro é limitação estrutural.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8).',
    ],
    dataAtualizacao: '2026-06-06',
  },
  {
    slug: 'liberdade-vs-vila-mariana',
    bairroA: 'Liberdade',
    bairroB: 'Vila Mariana',
    slugA: 'liberdade',
    slugB: 'vila-mariana',
    titulo: 'Liberdade vs Vila Mariana: qual bairro combina melhor com sua rotina?',
    respostaDireta:
      'Vila Mariana tende a apresentar scores ligeiramente superiores em transporte e acesso a serviços. Liberdade apresenta perfil similar em transporte (38,9 vs 44,2) e se destaca pela diversidade cultural e localização central. A diferença entre os distritos é menor do que em outros pares — a escolha pode depender mais da localização do trabalho ou do custo imobiliário.',
    melhorTransporte: 'Vila Mariana (score 44,2 vs 38,9)',
    melhorAreas: 'Vila Mariana (score 25,4 vs 21,6 — ambos abaixo da média, diferença pequena)',
    melhorServicos: 'Vila Mariana (score POI 45,1 vs 42,0)',
    melhorFlood: 'Vila Mariana (100,0 vs 99,7) — praticamente equivalentes; ambos com menor exposição relativa.',
    recomendacaoPerfil: [
      { perfil: 'Depende de transporte público', recomendado: 'Vila Mariana (score 44,2 vs 38,9 — diferença moderada)' },
      { perfil: 'Prioriza localização central e diversidade cultural', recomendado: 'Liberdade (eixo central sul da cidade)' },
      { perfil: 'Busca maior cobertura de serviços e comércio', recomendado: 'Vila Mariana (score POI 45,1 vs 42,0)' },
      { perfil: 'Menor densidade relativa de ocorrências (SSP-SP)', recomendado: 'Vila Mariana (89,9 vs 80,8 — ambos com cobertura parcial)' },
    ],
    pontosAtencao: [
      'A diferença geral entre estes dois distritos é menor do que em outros pares analisados — indicadores de transporte e serviços são próximos.',
      'Dados de segurança com cobertura parcial (SSP-SP) para ambos. Sub-registro é limitação estrutural.',
      'Dados imobiliários agregados por distrito não disponíveis nesta versão (previstos em M8) — podem ser fator decisivo entre distritos com indicadores similares.',
    ],
    dataAtualizacao: '2026-06-06',
  },
];

export function getComparativo(slug: string): Comparativo | undefined {
  return COMPARATIVOS.find((c) => c.slug === slug);
}

/**
 * Verifica se um par de slugs está na lista aprovada.
 * Impede geração cartesiana — nenhum comparativo pode existir fora desta lista.
 */
export function isParAprovado(slug: string): boolean {
  return PARES_APROVADOS.has(slug);
}

/**
 * Verifica se um par de bairros tem dados suficientes para ser publicado.
 * Ambos precisam existir em BAIRROS e ter safetyDataCoverage !== 'insuficiente'.
 */
export function isElegivel(slugA: string, slugB: string): boolean {
  const a = BAIRROS.find((b) => b.slug === slugA);
  const b = BAIRROS.find((b) => b.slug === slugB);
  if (!a || !b) return false;
  if (a.safetyDataCoverage === 'insuficiente' || b.safetyDataCoverage === 'insuficiente') return false;
  return true;
}

/**
 * Sugere novos pares de comparação baseados nos bairrosSimilares de cada bairro.
 * Retorna apenas sugestões que ainda não existem em COMPARATIVOS.
 * NÃO gera comparativos automaticamente — apenas lista candidatos para aprovação manual.
 */
export function sugerirNovasComparacoes(): Array<{ slugA: string; slugB: string; motivo: string }> {
  const existentes = new Set(COMPARATIVOS.map((c) => c.slug));
  const sugestoes: Array<{ slugA: string; slugB: string; motivo: string }> = [];
  const vistos = new Set<string>();

  for (const bairro of BAIRROS) {
    for (const similar of bairro.bairrosSimilares) {
      const existe = BAIRROS.find((b) => b.slug === similar);
      if (!existe) continue;

      // Ordem canônica alfabética para evitar duplicatas
      const [a, b] = [bairro.slug, similar].sort();
      const slugComparativo = `${a}-vs-${b}`;

      if (vistos.has(slugComparativo)) continue;
      vistos.add(slugComparativo);

      if (existentes.has(slugComparativo)) continue;
      if (PARES_APROVADOS.has(slugComparativo)) continue;

      if (!isElegivel(a, b)) continue;

      sugestoes.push({
        slugA: a,
        slugB: b,
        motivo: `${bairro.nome} lista ${existe.nome} como bairro similar`,
      });
    }
  }

  return sugestoes;
}

/**
 * Verifica se todos os comparativos publicados estão na lista aprovada.
 * Deve retornar true em produção — protege contra geração cartesiana acidental.
 */
export function validarBloqueioCartesiano(): boolean {
  return COMPARATIVOS.every((c) => PARES_APROVADOS.has(c.slug));
}

/**
 * Verifica se o lote atende o critério mínimo de publicação do M4 (≥ 10 comparativos).
 */
export function isPublishableBatch(): boolean {
  return COMPARATIVOS.length >= 10;
}
