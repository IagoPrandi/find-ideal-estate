const fs = require("fs/promises");
const path = require("path");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    return require(path.join(process.cwd(), "apps", "web", "node_modules", "playwright"));
  }
}

const { chromium } = loadPlaywright();

const APP_URL = process.env.PW_APP_URL || "http://localhost:5173";
const API_URL = process.env.PW_API_URL || "http://localhost:8000";
const OUT_DIR = process.env.PW_OUT_DIR || path.join(process.cwd(), "output", "playwright");
const TARGET_COORD = { lat: -23.52149, lon: -46.72752 };
const PUBLIC_TRANSPORT_LABEL = process.env.PW_PUBLIC_TRANSPORT_LABEL || "Trem/Metrô";
const ADDRESS_QUERY = process.env.PW_ADDRESS_QUERY || "carlos";
const ADDRESS_REGEX = new RegExp(process.env.PW_ADDRESS_REGEX || "carlos", "i");
const RESULTS_TIMEOUT_MS = Number(process.env.PW_RESULTS_TIMEOUT_MS || 360000);
const EXPECTED_MIN_TOTAL = Number(process.env.PW_EXPECTED_MIN_TOTAL || 1);
const EXPECTED_PLATFORMS = (process.env.PW_EXPECTED_PLATFORMS || "quintoandar,vivareal,zapimoveis")
  .split(",")
  .map((item) => item.trim().toLowerCase())
  .filter(Boolean);

function normalizePlatformName(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function buildListingsSummary(listings) {
  const platformCounts = {};
  const platformSet = new Set();

  for (const listing of Array.isArray(listings) ? listings : []) {
    const primary = normalizePlatformName(listing?.platform);
    if (primary) {
      platformSet.add(primary);
      platformCounts[primary] = (platformCounts[primary] || 0) + 1;
    }

    for (const alternate of Array.isArray(listing?.platforms_available) ? listing.platforms_available : []) {
      const normalized = normalizePlatformName(alternate);
      if (!normalized) {
        continue;
      }
      platformSet.add(normalized);
      platformCounts[normalized] = platformCounts[normalized] || 0;
    }
  }

  return {
    total: Array.isArray(listings) ? listings.length : 0,
    platforms: Array.from(platformSet).sort(),
    platformCounts,
  };
}

function buildJobSnapshot(body, elapsedMs) {
  const diagnostics = body?.result_ref?.scrape_diagnostics || null;
  return {
    elapsedMs,
    state: body?.state || null,
    progressPercent: body?.progress_percent ?? null,
    currentStage: body?.current_stage || null,
    errorCode: body?.error_code || null,
    errorMessage: body?.error_message || null,
    scrapeDiagnostics: diagnostics,
  };
}

async function getStores(page) {
  return page.evaluate(async () => {
    const uiStore = await import("/src/state/ui-store.ts");
    const journeyStore = await import("/src/state/journey-store.ts");
    return {
      ui: uiStore.useUIStore.getState(),
      journey: journeyStore.useJourneyStore.getState(),
    };
  });
}

async function waitForStep(page, step, timeout = 120000) {
  await page.waitForFunction(
    async (targetStep) => {
      const uiStore = await import("/src/state/ui-store.ts");
      return uiStore.useUIStore.getState().step === targetStep;
    },
    step,
    { timeout },
  );
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function setPickedCoord(page) {
  await page.evaluate(async (coord) => {
    const journeyStore = await import("/src/state/journey-store.ts");
    journeyStore.useJourneyStore.getState().setPickedCoord({
      lat: coord.lat,
      lon: coord.lon,
      label: `PW ${coord.lat.toFixed(5)}, ${coord.lon.toFixed(5)}`,
    });
    journeyStore.useJourneyStore.getState().setPrimaryReferenceLabel("Playwright seed");
  }, TARGET_COORD);
}

async function clickFirstTransportPoint(page) {
  const cards = page.locator("div.panel-scroll div.space-y-3 > button");
  const confirmButton = page.getByRole("button", { name: /Confirmar ponto seed/i });
  await cards.first().waitFor({ timeout: 120000 });
  const firstTransportText = await cards.first().innerText();
  await cards.first().click();
  await page.waitForFunction(
    () => {
      const button = Array.from(document.querySelectorAll("button")).find((item) =>
        item.textContent?.includes("Confirmar ponto seed"),
      );
      return Boolean(button && !button.disabled);
    },
    { timeout: 30000 },
  );
  await confirmButton.click();
  return firstTransportText;
}

async function clickFirstZone(page) {
  const zoneCard = page.locator("div.cursor-pointer.rounded-xl").first();
  await zoneCard.waitFor({ timeout: 120000 });
  const firstZoneText = await zoneCard.innerText();
  await zoneCard.click();
  await page.getByRole("button", { name: /Procurar Imóveis nesta Zona/i }).click();
  return firstZoneText;
}

async function selectAddress(page) {
  const input = page.getByLabel("Endereço alvo na zona");
  await input.waitFor({ timeout: 120000 });
  await input.click();
  await input.fill("");
  await input.fill(ADDRESS_QUERY);
  const option = page.getByRole("option", { name: ADDRESS_REGEX }).first();
  await option.waitFor({ timeout: 120000 });
  const optionText = await option.innerText();
  await option.click();
  return optionText;
}

async function waitForListingsOrTimeout(page, captured) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < RESULTS_TIMEOUT_MS) {
    const latest = captured.zoneListings.at(-1);
    const total = Number(latest?.body?.total_count || 0);
    if (latest?.status === 200 && total > 0) {
      return { reachedListings: true, waitedMs: Date.now() - startedAt };
    }

    const cards = await page.locator("h3.text-xl.font-bold.text-slate-800").count();
    if (cards > 0) {
      return { reachedListings: true, waitedMs: Date.now() - startedAt };
    }

    await page.waitForTimeout(5000);
  }

  return { reachedListings: false, waitedMs: Date.now() - startedAt };
}

async function waitForListingsJobId(captured, timeoutMs = 30000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const listingsSearchJobId = captured.listingsSearch.at(-1)?.body?.job_id || null;
    const zoneListingsJobId = captured.zoneListings.at(-1)?.body?.job_id || null;
    if (listingsSearchJobId || zoneListingsJobId) {
      return listingsSearchJobId || zoneListingsJobId;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return null;
}

async function pollJobSnapshots(jobId) {
  const startedAt = Date.now();
  const snapshots = [];
  while (Date.now() - startedAt < RESULTS_TIMEOUT_MS) {
    let status = null;
    let body = null;
    try {
      const response = await fetch(`${API_URL}/jobs/${jobId}`);
      status = response.status;
      body = await response.json();
    } catch (error) {
      snapshots.push({
        elapsedMs: Date.now() - startedAt,
        state: null,
        progressPercent: null,
        currentStage: null,
        errorCode: "poll_failed",
        errorMessage: String(error),
        scrapeDiagnostics: null,
      });
      break;
    }

    snapshots.push({
      httpStatus: status,
      ...buildJobSnapshot(body, Date.now() - startedAt),
    });

    if (["completed", "failed", "cancelled", "cancelled_partial"].includes(String(body?.state || ""))) {
      break;
    }

    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  return snapshots;
}

async function main() {
  await ensureDir(OUT_DIR);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const captured = {
    journeyCreate: [],
    jobs: [],
    transportPoints: [],
    zoneList: [],
    addressSuggest: [],
    listingsSearch: [],
    zoneListings: [],
    console: [],
    pageErrors: [],
  };

  page.on("console", (message) => {
    captured.console.push({
      type: message.type(),
      text: message.text(),
    });
  });

  page.on("pageerror", (error) => {
    captured.pageErrors.push(String(error));
  });

  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("localhost:8000")) {
      return;
    }
    try {
      if (url.endsWith("/journeys") && response.request().method() === "POST") {
        captured.journeyCreate.push({
          url,
          status: response.status(),
          body: await response.json(),
        });
      }
      if (url.includes("/jobs")) {
        captured.jobs.push({
          url,
          status: response.status(),
          method: response.request().method(),
          body: response.headers()["content-type"]?.includes("application/json") ? await response.json() : null,
        });
      }
      if (url.includes("/transport-points") && response.request().method() === "GET") {
        captured.transportPoints.push({
          url,
          status: response.status(),
          body: await response.json(),
        });
      }
      if (url.includes("/zones") && !url.includes("/listings") && response.request().method() === "GET") {
        captured.zoneList.push({
          url,
          status: response.status(),
          body: await response.json(),
        });
      }
      if (url.includes("/listings/address-suggest") && response.request().method() === "GET") {
        captured.addressSuggest.push({
          url,
          status: response.status(),
          body: await response.json(),
        });
      }
      if (url.includes("/listings/search") && response.request().method() === "POST") {
        captured.listingsSearch.push({
          url,
          status: response.status(),
          body: await response.json(),
        });
      }
      if (url.includes("/zones/") && url.includes("/listings") && response.request().method() === "GET") {
        captured.zoneListings.push({
          url,
          status: response.status(),
          body: await response.json(),
        });
      }
    } catch (error) {
      captured.zoneListings.push({ url, status: response.status(), error: String(error) });
    }
  });

  try {
    await page.goto(APP_URL, { waitUntil: "networkidle" });
    await setPickedCoord(page);

    await page.getByRole("button", { name: PUBLIC_TRANSPORT_LABEL, exact: true }).click();

    for (const label of ["Segurança", "Áreas verdes", "Alagamento", "Serviços"]) {
      const checkbox = page.getByLabel(label);
      if (await checkbox.isChecked()) {
        await checkbox.uncheck();
      }
    }

    await page.getByRole("button", { name: /Encontrar pontos seed/i }).click();
    await waitForStep(page, 2, 120000);
    await page.getByRole("heading", { name: /Transporte/i }).waitFor({ timeout: 120000 });

    const firstTransportText = await clickFirstTransportPoint(page);
    await waitForStep(page, 3, 120000);
    await page.getByRole("heading", { name: /Gerar zonas/i }).waitFor({ timeout: 120000 });
    await page.getByRole("button", { name: /Gerar zonas|Retomar geração/i }).click();

    await waitForStep(page, 4, 360000);
    await page.getByRole("heading", { name: /Zonas Encontradas/i, exact: false }).waitFor({ timeout: 360000 });
    const firstZoneText = await clickFirstZone(page);

    await waitForStep(page, 5, 120000);
    await page.getByRole("heading", { name: /Refinar Busca/i }).waitFor({ timeout: 120000 });
    const selectedOptionText = await selectAddress(page);

    await waitForStep(page, 6, 120000);
    await page.getByRole("heading", { name: /Resultados/i }).waitFor({ timeout: 120000 });
    const listingsJobId = await waitForListingsJobId(captured);
    const jobPollsPromise = listingsJobId ? pollJobSnapshots(listingsJobId) : Promise.resolve([]);
    const waitSummary = await waitForListingsOrTimeout(page, captured);
    const jobPolls = await jobPollsPromise;

    const cardPlatforms = await page.locator("text=/plataformas?|Zapimoveis|Vivareal|Quintoandar/i").allTextContents();
    const cardPrices = await page.locator("h3.text-xl.font-bold.text-slate-800").allTextContents();
    const scrapePlanText = await page.locator("text=/Paginação prevista do webscraping/i").allTextContents();
    const suggestionTexts = await page.getByRole("option").allTextContents().catch(() => []);
    const stores = await getStores(page);
    const latestZoneListings = captured.zoneListings.at(-1) || null;
    const latestListingsSearch = captured.listingsSearch.at(-1) || null;
    const finalJobSnapshot = jobPolls.at(-1) || null;
    const listingsSummary = buildListingsSummary(latestZoneListings?.body?.listings || []);
    const missingPlatforms = EXPECTED_PLATFORMS.filter((platform) => !listingsSummary.platforms.includes(platform));
    const acceptance = {
      expectedMinTotal: EXPECTED_MIN_TOTAL,
      expectedPlatforms: EXPECTED_PLATFORMS,
      actualTotalCount: Number(latestZoneListings?.body?.total_count || 0),
      actualPlatforms: listingsSummary.platforms,
      platformCounts: listingsSummary.platformCounts,
      minimumTotalMet: Number(latestZoneListings?.body?.total_count || 0) > EXPECTED_MIN_TOTAL,
      allPlatformsMet: missingPlatforms.length === 0,
      missingPlatforms,
    };
    acceptance.status = acceptance.minimumTotalMet && acceptance.allPlatformsMet ? "pass" : "fail";

    const result = {
      appUrl: APP_URL,
      targetCoord: TARGET_COORD,
      publicTransportLabel: PUBLIC_TRANSPORT_LABEL,
      addressQuery: ADDRESS_QUERY,
      firstTransportText,
      firstZoneText,
      selectedOptionText,
      listingsJobId,
      waitSummary,
      scrapePlanText,
      suggestionTexts,
      cardPlatforms,
      cardPrices,
      stores,
      latestJourneyCreate: captured.journeyCreate.at(-1) || null,
      latestTransportPoints: captured.transportPoints.at(-1) || null,
      latestZoneList: captured.zoneList.at(-1) || null,
      latestAddressSuggest: captured.addressSuggest.at(-1) || null,
      latestJob: captured.jobs.at(-1) || null,
      totalListingsResponses: captured.zoneListings.length,
      latestListingsSearch,
      jobPolls,
      finalJobSnapshot,
      latestZoneListings,
      listingsSummary,
      acceptance,
      allZoneListings: captured.zoneListings,
      pageErrors: captured.pageErrors,
      consoleTail: captured.console.slice(-20),
    };

    await page.screenshot({ path: path.join(OUT_DIR, "step6-platforms.png"), fullPage: true });
    await fs.writeFile(
      path.join(OUT_DIR, "step6-platforms.json"),
      JSON.stringify(result, null, 2),
      "utf-8",
    );

    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    const failureText = await page.locator("body").innerText().catch(() => "");
    await page.screenshot({ path: path.join(OUT_DIR, "step6-platforms-failure.png"), fullPage: true }).catch(() => {});
    await fs.writeFile(
      path.join(OUT_DIR, "step6-platforms-failure.txt"),
      failureText,
      "utf-8",
    ).catch(() => {});
    throw error;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
