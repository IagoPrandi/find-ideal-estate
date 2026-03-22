const { chromium } = require("playwright");

function parsePulse(debugText) {
  const match = /pulse=(\d)/.exec(debugText || "");
  return match ? match[1] : "?";
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto("http://127.0.0.1:5173", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: "Usar centro atual" }).click();
    await page.getByRole("button", { name: "Gerar Zonas Candidatas" }).click();

    await page.getByRole("heading", { name: "Etapa 2: seleção de transporte" }).waitFor({ timeout: 15000 });

    const firstPoint = page.locator("ul li").first();
    await firstPoint.hover();

    const debug = page.locator('[data-testid="m3-8-hover-debug"]');
    await debug.waitFor({ state: "attached", timeout: 5000 });

    const sampleA = (await debug.textContent()) || "";
    await page.waitForTimeout(420);
    const sampleB = (await debug.textContent()) || "";
    await page.waitForTimeout(420);
    const sampleC = (await debug.textContent()) || "";

    const pulseA = parsePulse(sampleA);
    const pulseB = parsePulse(sampleB);
    const pulseC = parsePulse(sampleC);
    const hoverBlinkObserved = new Set([pulseA, pulseB, pulseC]).size > 1;

    await page.getByRole("button", { name: "Gerar zonas" }).click();
    await page.getByRole("heading", { name: "Detalhamento da zona" }).waitFor({ timeout: 10000 });

    const apiResponse = await page.request.get("http://127.0.0.1:18080/__e2e__/last-job");
    const apiJson = await apiResponse.json();
    const payload = apiJson.last_job_payload || {};

    const proof = {
      hover_marker_blinks: hoverBlinkObserved,
      hover_debug_samples: [sampleA.trim(), sampleB.trim(), sampleC.trim()],
      jobs_payload: payload,
      jobs_payload_has_zone_generation: payload.job_type === "zone_generation",
    };

    console.log(JSON.stringify(proof, null, 2));

    if (!hoverBlinkObserved) {
      throw new Error("Hover blink evidence not observed in debug samples.");
    }
    if (payload.job_type !== "zone_generation") {
      throw new Error(`Expected job_type=zone_generation, got ${payload.job_type}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(`[m3.8-e2e] ${error.message}`);
  process.exit(1);
});
