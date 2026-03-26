import { test, expect } from "@playwright/test";

test("UI milestones: fluxo 1→6 pelo tracker + cancelamento (abort) na etapa 5", async ({ page }) => {
  // ----- Fixtures / IDs para mocks de API -----
  const apiBase = "http://localhost:8000";
  const runId = "run_e2e_smoke";
  const journeyId = "journey_e2e_smoke";
  const zoneUid = "zone_1";
  const jobId = "job_e2e_smoke";

  const step3Zone = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [] as unknown },
        properties: {
          zone_uid: zoneUid,
          centroid_lat: -23.55,
          centroid_lon: -46.63,
          time_agg: 41,
          score: 0.91,
          trace: {
            seed_bus_stop_id: "seed_1",
            downstream_stop_id: "down_1",
            stop_name: "Linha 1"
          }
        }
      }
    ]
  };

  const zoneDetail = {
    zone_uid: zoneUid,
    zone_name: "Zona 1",
    green_area_ratio: 0.3,
    flood_area_ratio: 0.1,
    poi_count_by_category: {
      parque: 12,
      farmacia: 11,
      mercado: 10,
      escola: 9,
      academia: 8,
      restaurante: 7,
      hospital: 6
    },
    bus_lines_count: 5,
    train_lines_count: 2,
    bus_stop_count: 10,
    train_station_count: 2,
    lines_used_for_generation: [
      { mode: "bus", route_id: "b1", line_name: "Linha 1" },
      { mode: "rail", route_id: "r1", line_name: "Linha 2" },
      { mode: "bus", route_id: "b3", line_name: "Linha 3" }
    ],
    reference_transport_point: { kind: "station", id: "ref_1", name: "Seed Ref", lon: -46.63, lat: -23.55 },
    seed_transport_point: { kind: "station", id: "seed_1", name: "Seed 1", lon: -46.633, lat: -23.551 },
    downstream_transport_point: { kind: "station", id: "down_1", name: "Down 1", lon: -46.629, lat: -23.553 },
    transport_points: [
      { kind: "station", id: "seed_1", name: "Seed 1", lon: -46.633, lat: -23.551 }
    ],
    poi_points: [{ id: "poi_1", name: "Escola 1", category: "escola", lon: -46.61, lat: -23.52 }],
    streets_count: 2,
    has_street_data: true,
    has_poi_data: true,
    has_transport_data: true,
    public_safety: {
      enabled: true,
      summary: {
        ocorrencias_no_raio_total: 12,
        delta_pct_vs_cidade: 0.02,
        top_delitos_no_raio: [
          { tipo_delito: "Furto", qtd: 4 },
          { tipo_delito: "Roubo", qtd: 3 },
          { tipo_delito: "Agressao", qtd: 2 }
        ],
        delegacias_mais_proximas: [{ nome: "DP 1", dist_km: 1.23 }]
      }
    }
  };

  const priceRollups = Array.from({ length: 30 }, (_, idx) => {
    const month = idx < 15 ? "02" : "03";
    const day = String((idx % 28) + 1).padStart(2, "0");
    return {
      id: `rollup_${idx}`,
      date: `2026-${month}-${day}`,
      zone_fingerprint: zoneUid,
      search_type: "rent",
      median_price: String(3000 + idx * 10),
      p25_price: String(2600 + idx * 8),
      p75_price: String(3600 + idx * 12),
      sample_count: 20 + idx,
      computed_at: "2026-03-22T10:00:00Z"
    };
  });

  let abortListingsOnce = true;

  // ----- Mocks de API (para o fluxo determinístico de 1→6) -----
  await page.route(`${apiBase}/runs`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        status: { state: "running", stage: "zones_raw" }
      })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/status`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        status: { state: "success", stage: "zones_enriched" }
      })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/zones`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(step3Zone)
    });
  });

  await page.route(`${apiBase}/journeys`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: journeyId,
        state: "running",
        created_at: "2026-03-22T10:00:00Z",
        updated_at: "2026-03-22T10:00:00Z",
        input_snapshot: { transport_search_radius_m: 250 }
      })
    });
  });

  await page.route(/\/journeys\/.+\/transport-points\/?(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "transport_1",
          journey_id: journeyId,
          source: "demo",
          name: "Ponto Transporte 1",
          lat: -23.55,
          lon: -46.63,
          walk_time_sec: 300,
          walk_distance_m: 250,
          route_ids: ["r1"],
          modal_types: ["train"],
          route_count: 1,
          created_at: "2026-03-22T10:00:00Z"
        }
      ])
    });
  });

  await page.route(`${apiBase}/jobs`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: jobId,
        job_type: "zone_generation",
        state: "queued",
        progress_percent: 0,
        created_at: "2026-03-22T10:00:00Z"
      })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/transport/routes`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        routes: { type: "FeatureCollection", features: [] },
        stops: { type: "FeatureCollection", features: [] }
      })
    });
  });

  await page.route(`${apiBase}/transport/stops*`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ type: "FeatureCollection", features: [] })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/zones/${zoneUid}/streets`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ zone_uid: zoneUid, streets: ["Rua A", "Rua B"] })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/zones/${zoneUid}/detail`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(zoneDetail)
    });
  });

  await page.route(`${apiBase}/runs/${runId}/zones/${zoneUid}/listings`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    if (abortListingsOnce) {
      abortListingsOnce = false;
      return route.abort();
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ zone_uid: zoneUid, listings_count: 0 })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/finalize`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        listings_final_json: "[]",
        listings_final_csv: "",
        listings_final_geojson: "[]",
        zones_final_geojson: "[]"
      })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/final/listings`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ type: "FeatureCollection", features: [] })
    });
  });

  await page.route(`${apiBase}/runs/${runId}/final/listings.json`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([])
    });
  });

  await page.route(
    new RegExp(`${apiBase}/journeys/${journeyId}/zones/${zoneUid}/price-rollups\\?search_type=rent&days=30$`),
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(priceRollups)
      });
    }
  );

  // ----- Fluxo UI -----
  await page.goto("/");

  // Smoke inicial do tracker (presença dos 6 passos).
  const expectedSteps = ["Configuração", "Origem", "Zonas", "Comparação", "Endereço", "Análise"];
  for (const stepTitle of expectedSteps) {
    await expect(page.getByRole("button", { name: new RegExp(`^${stepTitle}$`) })).toBeVisible();
  }

  await expect(page.getByRole("heading", { name: /Configurar Busca/i })).toBeVisible();

  // UX: o ProgressTracker não deve expandir ao minimizar e a busca deve ficar alinhada.
  const configStepButton = page.getByRole("button", { name: /^Configuração$/ });
  const trackerContainer = configStepButton.locator('xpath=ancestor::div[contains(@class,"rounded-2xl")][1]');
  await expect(trackerContainer).toBeVisible();

  const searchInput = page.locator("#map-search");
  await page.waitForTimeout(900);

  const trackerBoxExpanded = await trackerContainer.boundingBox();
  const searchBoxExpanded = await searchInput.boundingBox();

  expect(trackerBoxExpanded).not.toBeNull();
  expect(searchBoxExpanded).not.toBeNull();

  const deltaExpanded =
    (searchBoxExpanded!.x as number) - ((trackerBoxExpanded!.x as number) + (trackerBoxExpanded!.width as number));

  await page.getByRole("button", { name: /Minimizar painel/i }).click();

  const sidePanel = page.locator('aside[aria-label="Painel lateral"]');
  await expect(sidePanel).toBeHidden();

  await page.waitForTimeout(950);

  const trackerBoxCollapsed = await trackerContainer.boundingBox();
  const searchBoxCollapsed = await searchInput.boundingBox();

  expect(trackerBoxCollapsed).not.toBeNull();
  expect(searchBoxCollapsed).not.toBeNull();

  expect(trackerBoxCollapsed!.width).toBeLessThanOrEqual(trackerBoxExpanded!.width + 3);

  const deltaCollapsed =
    (searchBoxCollapsed!.x as number) -
    ((trackerBoxCollapsed!.x as number) + (trackerBoxCollapsed!.width as number));

  expect(Math.abs(deltaCollapsed - deltaExpanded)).toBeLessThanOrEqual(60);

  await page.getByRole("button", { name: /Expandir painel/i }).click();
  await expect(sidePanel).toBeVisible();
  await page.waitForTimeout(500);

  // Step 1: definir ponto principal no mapa.
  await page.getByRole("button", { name: /Definir no mapa/i }).click();

  const mapCanvas = page.locator("canvas").first();
  // Clica numa área do canvas que não fica coberta pelo painel lateral.
  const primaryInput = page.locator('input[readonly]').first();
  const clickPositions = [
    { x: 980, y: 340 },
    { x: 1060, y: 420 },
    { x: 1120, y: 520 },
    { x: 1180, y: 260 }
  ];

  for (const position of clickPositions) {
    await mapCanvas.click({ position });
    await page.waitForTimeout(450);
    const value = await primaryInput.inputValue();
    if (value.includes("Ponto principal")) break;
  }

  await expect(primaryInput).toHaveValue(/Ponto principal/i);
  await expect(page.getByRole("button", { name: /Achar pontos de transporte/i })).toBeEnabled();

  // Step 1 -> 2: iniciar run.
  await page.getByRole("button", { name: /Achar pontos de transporte/i }).click();
  await expect(page.getByRole("heading", { name: /Ponto de transporte/i })).toBeVisible();
  const transportRadio = page.locator('input[type="radio"][name="transport-selection"]').first();
  await expect(transportRadio).toBeVisible();

  const generateZonesButton = page.getByRole("button", { name: /Gerar zonas/i });
  await expect(generateZonesButton).toBeEnabled();

  // Step 2 -> 3: executar geração de zonas (job).
  await generateZonesButton.click();
  await expect(page.getByRole("heading", { name: /Geração de zonas/i })).toBeVisible();

  // Step 3 -> 4: CTA do Step3GenerationHint.
  const continueToCompareButton = page.getByRole("button", {
    name: /Continuar para comparação de zonas/i
  });
  await expect(continueToCompareButton).toBeVisible();
  await continueToCompareButton.click();
  await expect(page.getByRole("heading", { name: /Detalhe da zona/i })).toBeVisible();

  // Step 4 -> 5: carregar detalhamento.
  await page.getByRole("button", { name: /Carregar detalhamento/i }).click();
  await expect(page.getByRole("heading", { name: /Buscar imóveis/i })).toBeVisible();

  // Valida navegação via tracker para o Step 5.
  const enderecoStepBtn = page.getByRole("button", { name: /^Endereço$/ });
  await expect(enderecoStepBtn).toHaveAttribute("class", /bg-pastel-violet-500/);

  // Step 5: selecionar sugestão no autocomplete.
  const addressInput = page.getByPlaceholder("Digite bairro, rua ou referência");
  await addressInput.fill("Rua A");
  await expect(page.getByTestId("street-suggestions-ul")).toBeVisible();

  const suggestionButton = page
    .getByTestId("street-suggestions-ul")
    .getByRole("button", { name: /Rua A/i })
    .first();
  await suggestionButton.click();

  const searchListingsButton = page.getByRole("button", { name: /^Buscar imóveis$/ });
  await expect(searchListingsButton).toBeEnabled();

  // Cancelamento simulado: abortar a chamada de scrape na 1ª tentativa.
  await searchListingsButton.click();
  await expect(page.getByText(/Falha de comunicação/i).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Buscar imóveis/i })).toBeVisible();
  await expect(page.getByTestId("m6-dashboard-panel")).toBeHidden();

  // Tentativa 2: prosseguir até a etapa 6.
  await expect(searchListingsButton).toBeEnabled();
  await searchListingsButton.click();

  // Step 6 (via tracker) e então abrir aba Dashboard.
  const analiseStepBtn = page.getByRole("button", { name: /^Análise$/ });
  await expect(analiseStepBtn).toHaveAttribute("class", /bg-pastel-violet-500/);
  await analiseStepBtn.click();

  await page.getByRole("button", { name: /^Dashboard$/ }).click();
  await expect(page.getByTestId("m6-dashboard-panel")).toBeVisible();

  await page.screenshot({ path: "milestones-ui-full-flow.png", fullPage: true });
});

