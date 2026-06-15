import type { APIRoute, GetStaticPaths } from 'astro';
import { COMPARATIVOS } from '../../../data/comparativos';
import { renderOgPng } from '../../../lib/og';

export const prerender = true;

export const getStaticPaths: GetStaticPaths = () =>
  COMPARATIVOS.map((c) => ({ params: { slug: c.slug }, props: { comp: c } }));

export const GET: APIRoute = async ({ props }) => {
  const c = props.comp;
  const png = await renderOgPng({
    eyebrow: 'BetterPlace · Comparativo · São Paulo',
    title: `${c.bairroA} vs ${c.bairroB}`,
    subtitle: 'Transporte, áreas verdes, serviços e riscos urbanos lado a lado.',
  });
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=31536000, immutable' },
  });
};
