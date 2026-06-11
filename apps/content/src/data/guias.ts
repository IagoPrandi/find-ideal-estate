import { BAIRROS, type Bairro } from './bairros';

export interface GuiaRecomendacao {
  slug: string;
  perfil: string;
  motivo: string;
}

export interface GuiaRegiaoLacuna {
  nome: string;
  status: string;
  observacao: string;
}

export interface GuiaFaq {
  pergunta: string;
  resposta: string;
}

export interface Guia {
  slug: string;
  titulo: string;
  descricao: string;
  tag: string;
  dataAtualizacao: string;
  respostaDireta: string;
  recomendacoes: GuiaRecomendacao[];
  regioesComLacuna: GuiaRegiaoLacuna[];
  comparativos: Array<{ slug: string; titulo: string }>;
  faq: GuiaFaq[];
}

export const GUIAS: Guia[] = [
  {
    slug: 'bairros-perto-do-itaim-bibi-para-morar',
    titulo: 'Bairros perto do Itaim Bibi para morar: comparação por perfil',
    descricao:
      'Compare Itaim Bibi, Pinheiros, Moema e Vila Mariana para morar perto do Itaim usando dados de transporte, áreas verdes, serviços, alagamento, segurança e custo imobiliário agregado.',
    tag: 'Guia de decisão · Itaim Bibi',
    dataAtualizacao: '2026-06-11',
    respostaDireta:
      'Para morar perto do Itaim Bibi, Itaim Bibi tende a ser mais adequado para quem prioriza proximidade direta da Faria Lima ou Berrini. Pinheiros tende a ser uma alternativa para quem quer vida urbana e melhor presença relativa de áreas verdes. Moema tende a funcionar melhor para quem prioriza áreas verdes e perfil residencial. Vila Mariana pode fazer sentido para quem aceita um deslocamento maior em troca de melhor score de transporte entre os distritos analisados.',
    recomendacoes: [
      {
        slug: 'itaim-bibi',
        perfil: 'Proximidade direta da Faria Lima ou Berrini',
        motivo:
          'O distrito concentra o polo de trabalho da busca e apresenta score de transporte próximo ao de Pinheiros, com maior score de acesso a serviços entre os dois.',
      },
      {
        slug: 'pinheiros',
        perfil: 'Vida urbana, restaurantes e maior presença relativa de áreas verdes',
        motivo:
          'Pinheiros tem score de áreas verdes superior ao Itaim Bibi entre os distritos publicados e mantém acesso moderado a transporte público.',
      },
      {
        slug: 'moema',
        perfil: 'Áreas verdes e perfil residencial',
        motivo:
          'Moema apresenta score de áreas verdes superior ao Itaim Bibi, mas tem score de transporte menor; a escolha depende do trajeto diário.',
      },
      {
        slug: 'vila-mariana',
        perfil: 'Transporte público com deslocamento maior até o Itaim',
        motivo:
          'Vila Mariana tem o melhor score de transporte entre os distritos desta lista, mas não é a opção mais próxima do Itaim Bibi.',
      },
    ],
    regioesComLacuna: [
      {
        nome: 'Vila Olímpia',
        status: 'Região de alta demanda ainda sem página própria publicada',
        observacao:
          'No MVP, parte da análise de Vila Olímpia é coberta pelo recorte oficial do distrito Itaim Bibi; a diferença bairro × distrito deve ser declarada antes de publicar página própria.',
      },
      {
        nome: 'Vila Nova Conceição',
        status: 'Região citada em buscas, sem recorte público próprio nesta camada',
        observacao:
          'Publicar somente após validar recorte geográfico, cobertura de métricas e demanda aprovada.',
      },
      {
        nome: 'Brooklin e Campo Belo',
        status: 'Candidatos a expansão',
        observacao:
          'Campo Belo possui recorte distrital oficial, mas ainda não está na lista publicada de páginas de bairro; Brooklin exige declaração de mapeamento por distrito.',
      },
      {
        nome: 'Jardim Europa/Jardins',
        status: 'Candidato a guia específico',
        observacao:
          'A região é frequente em respostas de mercado, mas precisa de mapeamento canônico antes de entrar como recomendação com score.',
      },
    ],
    comparativos: [
      { slug: 'pinheiros-vs-itaim-bibi', titulo: 'Pinheiros vs Itaim Bibi' },
      { slug: 'itaim-bibi-vs-moema', titulo: 'Itaim Bibi vs Moema' },
      { slug: 'pinheiros-vs-vila-mariana', titulo: 'Pinheiros vs Vila Mariana' },
      { slug: 'vila-mariana-vs-moema', titulo: 'Vila Mariana vs Moema' },
    ],
    faq: [
      {
        pergunta: 'Qual bairro perto do Itaim Bibi tende a ser melhor para quem trabalha na Faria Lima?',
        resposta:
          'Itaim Bibi tende a ser a opção mais direta para quem trabalha na Faria Lima ou Berrini. Pinheiros pode ser alternativa quando a prioridade inclui vida urbana e maior presença relativa de áreas verdes.',
      },
      {
        pergunta: 'Pinheiros ou Itaim Bibi: qual combina melhor para morar perto do Itaim?',
        resposta:
          'Itaim Bibi tende a favorecer menor deslocamento para Faria Lima/Berrini. Pinheiros tende a ser mais adequado para quem prioriza áreas verdes relativas e ambiente urbano diverso. A melhor escolha depende do trajeto diário.',
      },
      {
        pergunta: 'Moema é uma boa alternativa perto do Itaim Bibi?',
        resposta:
          'Moema pode ser alternativa para quem prioriza áreas verdes e perfil residencial, mas o score de transporte é menor que o do Itaim Bibi nos dados publicados. O trajeto diário deve ser comparado antes da decisão.',
      },
      {
        pergunta: 'Vila Olímpia aparece nos dados do BetterPlace?',
        resposta:
          'Vila Olímpia é uma região de alta demanda, mas ainda não tem página própria publicada nesta camada. No MVP, parte da região é tratada dentro do recorte oficial do distrito Itaim Bibi, com essa limitação declarada.',
      },
    ],
  },
];

export function getGuia(slug: string): Guia | undefined {
  return GUIAS.find((g) => g.slug === slug);
}

export function getBairrosDoGuia(guia: Guia): Bairro[] {
  return guia.recomendacoes
    .map((r) => BAIRROS.find((bairro) => bairro.slug === r.slug))
    .filter((bairro): bairro is Bairro => bairro != null);
}
