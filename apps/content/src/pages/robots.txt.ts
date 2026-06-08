import type { APIRoute } from 'astro';

export const prerender = true;

// Servido por rota dinâmica (não via public/) para evitar que o Git LFS
// entregue um ponteiro em vez do conteúdo real em produção (Vercel não
// resolve objetos LFS no build). Mesmo padrão de BingSiteAuth.xml.ts.
const ROBOTS = `User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Googlebot
Allow: /

Sitemap: https://www.betterplace.com.br/sitemap-index.xml
`;

export const GET: APIRoute = () =>
  new Response(ROBOTS, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
