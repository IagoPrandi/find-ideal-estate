import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import satori from 'satori';
import { Resvg } from '@resvg/resvg-js';

const require = createRequire(import.meta.url);

// Fontes lidas localmente do @fontsource (sem rede no build). Satori não suporta woff2.
const interRegular = readFileSync(
  require.resolve('@fontsource/inter/files/inter-latin-400-normal.woff'),
);
const interBold = readFileSync(
  require.resolve('@fontsource/inter/files/inter-latin-700-normal.woff'),
);

export interface OgStat {
  label: string;
  value: number;
}

export interface OgInput {
  eyebrow: string;
  title: string;
  subtitle?: string;
  stats?: OgStat[];
}

// Constrói a árvore de elementos no formato aceito pelo satori (sem JSX/React).
function buildTree({ eyebrow, title, subtitle, stats = [] }: OgInput) {
  const header = {
    type: 'div',
    props: {
      style: { display: 'flex', fontSize: 28, fontWeight: 400, color: '#9db8d8' },
      children: eyebrow,
    },
  };

  const titleBlock = {
    type: 'div',
    props: {
      style: { display: 'flex', flexDirection: 'column', gap: '14px' },
      children: [
        {
          type: 'div',
          props: {
            style: { display: 'flex', fontSize: title.length > 28 ? 60 : 76, fontWeight: 700, lineHeight: 1.1 },
            children: title,
          },
        },
        subtitle
          ? {
              type: 'div',
              props: {
                style: { display: 'flex', fontSize: 30, fontWeight: 400, color: '#cdddf0' },
                children: subtitle,
              },
            }
          : null,
      ].filter(Boolean),
    },
  };

  const statsRow = stats.length
    ? {
        type: 'div',
        props: {
          style: { display: 'flex', gap: '16px' },
          children: stats.map((s) => ({
            type: 'div',
            props: {
              style: {
                display: 'flex',
                flexDirection: 'column',
                backgroundColor: '#ffffff',
                color: '#1e3a5f',
                borderRadius: '14px',
                padding: '16px 22px',
              },
              children: [
                {
                  type: 'div',
                  props: { style: { display: 'flex', fontSize: 22, color: '#5f6b7a' }, children: s.label },
                },
                {
                  type: 'div',
                  props: {
                    style: { display: 'flex', fontSize: 42, fontWeight: 700 },
                    children: `${Math.round(s.value)}/100`,
                  },
                },
              ],
            },
          })),
        },
      }
    : null;

  return {
    type: 'div',
    props: {
      style: {
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        backgroundColor: '#1e3a5f',
        color: '#ffffff',
        padding: '64px',
        fontFamily: 'Inter',
      },
      children: [header, titleBlock, statsRow].filter(Boolean),
    },
  };
}

export async function renderOgPng(input: OgInput): Promise<Buffer> {
  const svg = await satori(buildTree(input) as Parameters<typeof satori>[0], {
    width: 1200,
    height: 630,
    fonts: [
      { name: 'Inter', data: interRegular, weight: 400, style: 'normal' },
      { name: 'Inter', data: interBold, weight: 700, style: 'normal' },
    ],
  });
  const png = new Resvg(svg, { fitTo: { mode: 'width', value: 1200 } }).render().asPng();
  return Buffer.from(png);
}
