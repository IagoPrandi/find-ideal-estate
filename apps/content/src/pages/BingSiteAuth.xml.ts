import type { APIRoute } from 'astro';

export const prerender = true;

const BING_VERIFICATION = process.env.PUBLIC_BING_VERIFICATION?.trim() ?? '';

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export const GET: APIRoute = () => {
  if (!BING_VERIFICATION || BING_VERIFICATION === 'BING_VERIFICATION_CODE_AQUI') {
    throw new Error('PUBLIC_BING_VERIFICATION precisa conter o codigo real do Bing Webmaster Tools.');
  }

  return new Response(
    `<?xml version="1.0"?>\n<users>\n  <user>${escapeXml(BING_VERIFICATION)}</user>\n</users>\n`,
    {
      headers: {
        'Content-Type': 'application/xml; charset=utf-8',
      },
    }
  );
};
