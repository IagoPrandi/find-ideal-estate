import type { APIRoute, GetStaticPaths } from 'astro';
import { BAIRROS } from '../../../data/bairros';
import { renderOgPng } from '../../../lib/og';

export const prerender = true;

export const getStaticPaths: GetStaticPaths = () =>
  BAIRROS.map((b) => ({ params: { slug: b.slug }, props: { bairro: b } }));

export const GET: APIRoute = async ({ props }) => {
  const b = props.bairro;
  const png = await renderOgPng({
    eyebrow: 'BetterPlace · Bairro · São Paulo',
    title: b.nome,
    stats: [
      { label: 'Transporte', value: b.transportScore },
      { label: 'Áreas verdes', value: b.greenScore },
      { label: 'Proteção alag.', value: b.floodRiskScore },
      { label: 'Segurança', value: b.safetyScore },
    ],
  });
  return new Response(new Uint8Array(png), {
    headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=31536000, immutable' },
  });
};
