const fs = require("fs");
const path = require("path");
const { chromium } = require("../apps/web/node_modules/playwright");

const APP_URL = process.env.M4_6_APP_URL || "http://127.0.0.1:3000";
const OUTPUT_DIR = path.join(process.cwd(), "runs", "m4_6_smoke");

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

/**
 * Sets the primary point by clicking on the map at a safe coordinate
 * (avoids the wizard panel area on the left at desktop widths).
 */
async function clickMapToSetPrimaryPoint(page) {
  // The map is rendered via MapLibre GL (WebGL canvas). Wait for the canvas to be visible.
  const canvas = page.locator('.maplibregl-canvas').first();
  await canvas.waitFor({ state: 'visible', timeout: 20000 }).catch(() => null);
  await page.waitForTimeout(800); // extra stabilisation after map tiles load

  // interactionMode defaults to "primary", so a map click sets the primary point.
  // Use page.mouse to fire a native pointer event on the canvas at a safe coordinate
  // (desktop panel occupies ~360px on the left, so x=800 is safely in the map area).
  await page.mouse.move(800, 420);
  await page.mouse.click(800, 420);
  await page.waitForTimeout(1200); // wait for React state update and re-render
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

/**
 * Waits for transport points list items to appear in Step 2.
 * Points now render as <li> elements inside the transport panel section.
 */
async function waitForTransportStage(page) {
  // Transport points are rendered as list items with rounded-[22px] styling
  const transportItems = page.locator('section').filter({ hasText: /Escolher o transporte elegível/i }).locator('li');
  const startedAt = Date.now();
  while (Date.now() - startedAt < 30000) {
    if ((await transportItems.count()) > 0) {
      return "cards";
    }
    // Check if transport loading message became static (no results)
    const loadingMsg = page.locator('p').filter({ hasText: /Carregando pontos de transporte/i });
    if ((await loadingMsg.count()) === 0) {
      const noResultsMsg = page.locator('p').filter({ hasText: /Gere zonas candidatas|Nenhum ponto/i });
      if ((await noResultsMsg.count()) > 0) return "empty";
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

  // --- Desktop pass (1440×1100) ---
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

  // --- Mobile position check (390×844, iPhone-style) ---
  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });

  try {
    await mobilePage.goto(APP_URL, { waitUntil: "networkidle", timeout: 30000 });
    // Capture mobile screenshot
    const mobileScreenshotPath = path.join(OUTPUT_DIR, "ui_mobile_step1.png");
    await mobilePage.screenshot({ path: mobileScreenshotPath });
    evidence.stages.mobile_screenshot = mobileScreenshotPath;

    // Probe shell BoundingClientRect to verify bottom-docking
    const shellRect = await mobilePage.locator(".wizard-shell").first().boundingBox();
    evidence.stages.mobile_shell_rect = shellRect;
    if (shellRect) {
      const viewportHeight = 844;
      // Bottom of shell should be near bottom of viewport (within 32px of bottom)
      const bottomEdge = shellRect.y + shellRect.height;
      evidence.stages.mobile_bottom_docked = bottomEdge >= viewportHeight - 32;
    } else {
      evidence.stages.mobile_bottom_docked = false;
    }
  } finally {
    await mobilePage.close();
  }

  try {
    // --- Step 1: navigate and set primary point ---
    await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 30000 });

    const desktopStep1Path = path.join(OUTPUT_DIR, "ui_desktop_step1.png");
    await page.screenshot({ path: desktopStep1Path });
    evidence.stages.desktop_step1_screenshot = desktopStep1Path;

    // Step 1 heading (eyebrow + h2)
    evidence.stages.initial_heading = await textOrNull(page.locator("h2").filter({ hasText: /Configurar jornada/i }));
    evidence.stages.step1_eyebrow_visible = await page.locator(".gem-eyebrow").first().isVisible().catch(() => false);

    // Set primary point by clicking on map (interactionMode defaults to "primary")
    await clickMapToSetPrimaryPoint(page);

    // Take screenshot after primary point set
    const desktopAfterClickPath = path.join(OUTPUT_DIR, "ui_desktop_step1_clicked.png");
    await page.screenshot({ path: desktopAfterClickPath });
    evidence.stages.desktop_step1_after_click_screenshot = desktopAfterClickPath;

    // Check primary point input is now populated (inputs use .inputValue(), not textContent)
    const primaryInputValue = await page.locator('input[readonly]').first().inputValue().catch(() => '');
    // When no point is selected the input shows hint text "Clique no mapa em..." – that is not a real point.
    const isRealPoint = primaryInputValue.length > 0 && !primaryInputValue.includes('Clique no mapa');
      console.error(`[DEBUG] primaryInputValue="${primaryInputValue}" isRealPoint=${isRealPoint}`);
    evidence.stages.primary_point_set = isRealPoint;
    evidence.stages.primary_point_value = primaryInputValue || null;

    // Click "Encontrar pontos de transporte"
    const createRunBtn = page.getByRole("button", { name: /Encontrar pontos de transporte/i });
    evidence.stages.create_run_button_found = (await createRunBtn.count()) > 0;

    if (evidence.stages.create_run_button_found) {
      if (evidence.stages.primary_point_set) {
        // Point was set — wait for button to become enabled, then click.
        await createRunBtn.waitFor({ state: 'visible' });
        await page.waitForTimeout(300);
        await createRunBtn.click().catch(async () => {
          // Button may still be disabled; attempt force click as last resort.
          await createRunBtn.click({ force: true }).catch(() => {
            evidence.stages.create_run_btn_click_failed = true;
          });
        });
      } else {
        evidence.stages.create_run_btn_click_failed = true;
        evidence.stages.skipped_click_reason = "primary_point_not_set";
      }
      await page.waitForTimeout(1200);
    }

    // Step 2: transport panel
    // Redesigned: h3 "Escolher o transporte elegível" inside a gem-panel-section
    const etapa2Heading = page.locator("h3").filter({ hasText: /Escolher o transporte elegível/i });
    const etapa3Heading = page.locator("h3").filter({ hasText: /Gerando zonas candidatas/i });
    const etapa4Heading = page.locator("h3").filter({ hasText: /Detalhe urbano da zona/i });

    await etapa2Heading.waitFor({ state: "visible", timeout: 15000 }).catch(() => null);

    evidence.stages.etapa2_visible = await etapa2Heading.isVisible().catch(() => false);
    evidence.stages.etapa3_visible = await etapa3Heading.isVisible().catch(() => false);
    evidence.stages.etapa4_visible = await etapa4Heading.isVisible().catch(() => false);

    if (evidence.stages.etapa2_visible) {
      // Screenshot at step 2
      await page.screenshot({ path: path.join(OUTPUT_DIR, "ui_desktop_step2.png") });
      evidence.stages.desktop_step2_screenshot = path.join(OUTPUT_DIR, "ui_desktop_step2.png");

      evidence.stages.transport_stage_resolution = await waitForTransportStage(page);

      // Count transport point list items
      const transportSection = page.locator("section").filter({ hasText: /Escolher o transporte elegível/i });
      evidence.stages.transport_cards = await transportSection.locator("li").count();

      // Status message text (gem-chip spans)
      evidence.stages.etapa2_chips = await textOrNull(page.locator(".gem-chip").first());
      evidence.stages.generate_button_text = await textOrNull(page.getByRole("button", { name: /Gerar zonas/i }));

      if (evidence.stages.transport_cards > 0) {
        // Select the first transport point
        await transportSection.locator("li").first().click();
        await maybeClick(page.getByRole("button", { name: /Gerar zonas/i }));
        await page.waitForTimeout(4000);

        evidence.stages.etapa3_visible_after_click = await etapa3Heading.isVisible().catch(() => false);
        evidence.stages.zone_generation_progress_bar = await page.locator(".gem-panel-section").filter({ hasText: /Gerando zonas candidatas/i }).locator("[class*='bg-pastel-violet']").count() > 0;
        evidence.stages.stage3_runtime_detected = Boolean(
          evidence.stages.etapa3_visible_after_click ||
            evidence.stages.zone_generation_progress_bar ||
            hasZoneGenerationRequest(evidence.requests) ||
            hasZoneFetch(evidence.requests),
        );

        if (evidence.stages.stage3_runtime_detected) {
          await page.waitForTimeout(5000);
          const continuarBtn = page.getByRole("button", { name: /Continuar para comparação de zonas/i });
          evidence.stages.continuar_btn_visible = await continuarBtn.isVisible().catch(() => false);
          evidence.stages.etapa4_visible_after_wait = await etapa4Heading.isVisible().catch(() => false);
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