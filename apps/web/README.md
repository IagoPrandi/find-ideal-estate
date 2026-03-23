# Find Ideal Estate — frontend (Vite)

Este é o frontend canônico do produto (substitui o diretório legado `ui/`).

- **Dev:** `npm install` e `npm run dev` (porta **5173**).
- **Variáveis:** `VITE_API_BASE`, `VITE_MAPTILER_API_KEY` (ver `.env.example` na raiz do repositório).
- **Docker:** serviço `ui` em `docker-compose.yml` monta este diretório em `/web`.

## Plano de reescrita — o que mudou na transferência

O plano original falava em substituir tudo dentro de `ui/`. O que foi acordado na prática:

| Plano original | Estado atual |
|----------------|--------------|
| Código só em `ui/` | **Canónico:** `apps/web/`. `ui/` fica como legado (ver `ui/README.md`). |
| `docker-compose` / Dockerfile apontando a `ui/` | **Atualizado** para `apps/web` e `WORKDIR /web`. |
| Estrutura em pastas + fim do monólito | **Parcial:** pastas `components/layout`, `map`, `features/steps`, `lib`, `state` existem; a lógica principal continua em `FindIdealApp.tsx`, com extrações incrementais (painéis por etapa; o passo 3 está fatiado em vários ficheiros — ver Estrutura). |
| REST + **SSE** granular (PRD) | **REST** + polling onde já existia; `src/lib/sse.ts` é ponto de extensão para EventSource/SSE. |
| Etapas 1–6 explícitas na UI | **UI com 3 passos** no tracker; listings/dashboard agrupados no passo 3 (alinhar com PRD é trabalho futuro). |

Próximos passos sugeridos: fatiar `FindIdealApp` em steps/results, ligar SSE real quando o backend expuser o stream, e alinhar nomenclatura de etapas ao PRD.

## Estrutura

- `src/features/app/FindIdealApp.tsx` — estado do fluxo, mapa MapLibre e painel (em desconstrução gradual). Metadados do assistente: `wizardSteps.ts`, `wizardExecution.ts`; imóveis/analytics: `listingAnalytics.ts`; métricas do passo 3: `step3DerivedMetrics.ts`; ordenação de lista: `features/steps/listingSort.ts`; formatação numérica: `lib/listingFormat.ts`; geo: `lib/geo.ts`.
- `src/components/layout` — `FloatingBrand`, `ProgressTracker`, `HelpModal`.
- `src/components/map` — `AddressSearchBar`, `InteractionModeBar`, `MapToolbarRight`, `MapLegend`, overlays de loading/erro.
- `src/features/steps` — etapas do assistente: `Step1ConfigurePanel`, `Step2TransportPanel`, `Step3ZonePanel` (compositor), `WizardSharedStatus`. **Passo 3 (zona / imóveis / dashboard):** tipos em `step3Types.ts`, helpers em `step3Helpers.ts`, e UI em `Step3ZoneDetailSection`, `Step3PanelTabBar`, `Step3SearchListingsSection`, `Step3FinalListingsSection`, `Step3DashboardSection`.
- `src/domain/mapLayers.ts` — chaves e labels das camadas do mapa (`MapLayerKey`, `MAP_LAYER_INFO`).
- `src/lib/*`, `src/api/*` — cliente HTTP e extensão SSE.
