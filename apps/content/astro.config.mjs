// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { BAIRROS } from './src/data/bairros';
import { COMPARATIVOS } from './src/data/comparativos';
import { GUIAS } from './src/data/guias';

// lastmod por página derivado das datas reais dos dados (não inventado).
const lastmodByPath = new Map();
for (const b of BAIRROS) lastmodByPath.set(`/bairros/${b.slug}`, b.dataAtualizacao);
for (const c of COMPARATIVOS) lastmodByPath.set(`/comparar/${c.slug}`, c.dataAtualizacao);
for (const g of GUIAS) lastmodByPath.set(`/guias/${g.slug}`, g.dataAtualizacao);

export default defineConfig({
  site: 'https://www.betterplace.com.br',
  integrations: [
    sitemap({
      serialize(item) {
        const path = new URL(item.url).pathname.replace(/\/$/, '');
        const d = lastmodByPath.get(path);
        if (d) item.lastmod = new Date(`${d}T00:00:00Z`).toISOString();
        return item;
      },
    }),
  ],
  output: 'static',
});
