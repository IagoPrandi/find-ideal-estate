const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const APP_URL = process.env.M4_6_APP_URL || "http://127.0.0.1:3000";
const OUTPUT_DIR = path.join(process.cwd(), "runs", "m4_6_smoke");

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

async function fillPrimaryPoint(page) {
  await page.locator('input[placeholder="-23.550520"]').first().fill("-23.550520");
  await page.locator('input[placeholder="-46.633308"]').first().fill("-46.633308");
}

async function maybeClick(buttonLocator) {
  if ((await buttonLocator.count()) > 0) {
    await buttonLocator.click();
    return true;
  }
  return false;
}

async function textOrNull(locator) {
  if ((await locator.count()) === 0) {
    return null;
  }
  return (await locator.first().textContent())?.trim() || null;
}

async function waitForTransportStage(page) {
  const cards = page.locator(".transport-point-card");
  const error = page.locator(".error-message");
  const empty = page.locator(".empty-state");

  const startedAt = Date.now();
  while (Date.now() - startedAt < 30000) {
    if ((await cards.count()) > 0) {
      return "cards";
    }
    if ((await error.count()) > 0) {
      return "error";
    }
    if ((await empty.count()) > 0 && (await page.locator(".progress-card").count()) === 0) {
      return "empty";
    }
    await page.waitForTimeout(500);
  }

  return "timeout";
}

function hasZoneGenerationRequest(requests) {
  return requests.some(
    (entry) =>
      entry.method === "POST" &&
      entry.url.includes("/api/jobs") &&
      typeof entry.post_data === "string" &&
      entry.post_data.includes('"job_type":"zone_generation"'),
  );
}

function hasZoneFetch(requests) {
  return requests.some((entry) => entry.method === "GET" && entry.url.includes("/api/journeys/") && entry.url.includes("/zones"));
}

async function main() {
  ensureDir(OUTPUT_DIR);

  const evidence = {
    app_url: APP_URL,
    started_at: new Date().toISOString(),
    requests: [],
    responses: [],
    stages: {},
    outcome: "unknown",
  };

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });

  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/api/journeys") || url.includes("/api/jobs")) {
      evidence.requests.push({
        method: request.method(),
        url,
        post_data: request.postData() || null,
      });
    }
  });

  page.on("response", async (response) => {
    const url = response.url();
    if (url.includes("/api/journeys") || url.includes("/api/jobs")) {
      let body = null;
      try {
        body = await response.text();
      } catch {
        body = null;
      }
      evidence.responses.push({
        status: response.status(),
        url,
        body,
      });
    }
  });

  try {
    await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 30000 });
    evidence.stages.initial_heading = await textOrNull(page.getByRole("heading", { name: /Etapa 1/i }));

    await fillPrimaryPoint(page);
    await page.getByRole("button", { name: "Criar jornada e continuar" }).click();

    await page.waitForTimeout(1000);

    const etapa2Heading = page.getByRole("heading", { name: /Etapa 2: Seleção de transporte/i });
    const etapa3Heading = page.getByRole("heading", { name: /Etapa 3: Geracao de zonas/i });
    const etapa4Heading = page.getByRole("heading", { name: /Etapa 4: Comparação de zonas/i });

    await etapa2Heading.waitFor({ state: "visible", timeout: 15000 }).catch(() => null);

    evidence.stages.etapa2_visible = await etapa2Heading.isVisible().catch(() => false);
    evidence.stages.etapa3_visible = await etapa3Heading.isVisible().catch(() => false);
    evidence.stages.etapa4_visible = await etapa4Heading.isVisible().catch(() => false);

    if (evidence.stages.etapa2_visible) {
      evidence.stages.transport_stage_resolution = await waitForTransportStage(page);
      evidence.stages.progress_message = await textOrNull(page.locator(".progress-copy strong"));
      evidence.stages.progress_percent_text = await textOrNull(page.locator(".progress-copy span"));
      evidence.stages.etapa2_message = await textOrNull(page.locator(".empty-state, .error-message, .panel-intro, p"));
      evidence.stages.transport_cards = await page.locator(".transport-point-card").count();
      evidence.stages.generate_button_text = await textOrNull(page.getByRole("button", { name: /Gerar zonas/i }));

      if (evidence.stages.transport_cards > 0) {
        await page.locator(".transport-point-card").first().click();
        await maybeClick(page.getByRole("button", { name: /Gerar zonas/i }));
        await page.waitForTimeout(4000);

        evidence.stages.etapa3_visible_after_click = await etapa3Heading.isVisible().catch(() => false);
        evidence.stages.progress_text = await textOrNull(page.locator(".progress-percent"));
        evidence.stages.zone_items = await page.locator(".zone-item").count();
        evidence.stages.stage3_runtime_detected = Boolean(
          evidence.stages.etapa3_visible_after_click ||
            evidence.stages.progress_text ||
            evidence.stages.zone_items > 0 ||
            hasZoneGenerationRequest(evidence.requests) ||
            hasZoneFetch(evidence.requests),
        );

        if (evidence.stages.stage3_runtime_detected) {
          await page.waitForTimeout(5000);
          evidence.stages.progress_text_after_wait = await textOrNull(page.locator(".progress-percent"));
          evidence.stages.zone_items_after_wait = await page.locator(".zone-item, .zone-list-item").count();
          evidence.stages.cancel_visible = await page.getByRole("button", { name: /Cancelar geracao|Cancelando/i }).isVisible().catch(() => false);
          evidence.stages.etapa4_visible_after_wait = await etapa4Heading.isVisible().catch(() => false);
          evidence.stages.search_cta_visible = await page.getByRole("button", { name: /Buscar imóveis nesta zona/i }).isVisible().catch(() => false);
          evidence.stages.badges_provisional_visible = await page.getByText(/Badges calculados com dados parciais/i).isVisible().catch(() => false);
        }
      }
    }

    const screenshotPath = path.join(OUTPUT_DIR, "m4_6_smoke.png");
    await page.screenshot({ path: screenshotPath, fullPage: true });
    evidence.screenshot = screenshotPath;

    if (evidence.stages.etapa4_visible_after_wait) {
      evidence.outcome = "passed_to_stage_4";
    } else if (evidence.stages.stage3_runtime_detected) {
      evidence.outcome = "reached_stage_3_only";
    } else if (evidence.stages.etapa2_visible) {
      evidence.outcome = "blocked_at_stage_2";
    } else {
      evidence.outcome = "blocked_before_stage_2";
    }
  } finally {
    evidence.finished_at = new Date().toISOString();
    fs.writeFileSync(
      path.join(OUTPUT_DIR, "m4_6_smoke_evidence.json"),
      JSON.stringify(evidence, null, 2),
      "utf8",
    );
    await browser.close();
  }
}

main().catch((error) => {
  const outputPath = path.join(process.cwd(), "runs", "m4_6_smoke", "m4_6_smoke_error.txt");
  ensureDir(path.dirname(outputPath));
  fs.writeFileSync(outputPath, `${error.stack || error.message}\n`, "utf8");
  console.error(error.stack || error.message);
  process.exit(1);
});