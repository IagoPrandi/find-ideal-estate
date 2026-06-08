import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src")
    }
  },
  server: {
    host: true,
    port: 5173,
    proxy: (() => {
      // Em Docker: CONTENT_URL=http://content:4321 (nome do serviço no docker-compose)
      // Fora do Docker: usa localhost:4321 (Astro rodando localmente)
      const contentUrl = process.env.CONTENT_URL ?? 'http://localhost:4321';
      const routes = ['/bairros', '/comparar', '/dados', '/relatorios', '/metodologia', '/sitemap', '/robots.txt', '/llms.txt'];
      return Object.fromEntries(routes.map((r) => [r, contentUrl]));
    })()
  }
});
