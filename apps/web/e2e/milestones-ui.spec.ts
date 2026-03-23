import { test, expect } from "@playwright/test";

test("UI milestones: tracker steps + address search alignment on minimize", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /Configurar busca/i })).toBeVisible();

  const createRunButton = page.getByRole("button", { name: /Achar pontos de transporte/i });
  await expect(createRunButton).toBeDisabled();

  const configStepButton = page.getByRole("button", { name: /^Configuração$/ });
  const trackerContainer = configStepButton.locator(
    'xpath=ancestor::div[contains(@class,"rounded-2xl")][1]'
  );
  await expect(trackerContainer).toBeVisible();

  // Não dependemos do count exato (o DOM pode ter nós extras com aria-label),
  // mas validamos que os 6 passos do PRD/Tracker estão presentes.
  const expectedSteps = ["Configuração", "Origem", "Zonas", "Comparação", "Endereço", "Análise"];
  for (const stepTitle of expectedSteps) {
    await expect(page.getByRole("button", { name: new RegExp(`^${stepTitle}$`) })).toBeVisible();
  }

  const searchInput = page.locator("#map-search");

  // Espera o layout estabilizar (o AddressSearchBar recalcula o left baseado no tracker).
  await page.waitForTimeout(900);

  const trackerBoxExpanded = await trackerContainer.boundingBox();
  const searchBoxExpanded = await searchInput.boundingBox();

  expect(trackerBoxExpanded).not.toBeNull();
  expect(searchBoxExpanded).not.toBeNull();

  const deltaExpanded =
    (searchBoxExpanded!.x as number) - ((trackerBoxExpanded!.x as number) + (trackerBoxExpanded!.width as number));
  expect(deltaExpanded).not.toBeNaN();

  // Minimiza o painel: o ProgressTracker não deve expandir.
  const minimizeBtn = page.getByRole("button", { name: /Minimizar painel/i });
  await minimizeBtn.click();

  const sidePanel = page.locator('aside[aria-label="Painel lateral"]');
  await expect(sidePanel).toBeHidden();

  // Espera o término da transição CSS + recalculo do left.
  await page.waitForTimeout(950);

  const trackerBoxCollapsed = await trackerContainer.boundingBox();
  const searchBoxCollapsed = await searchInput.boundingBox();

  expect(trackerBoxCollapsed).not.toBeNull();
  expect(searchBoxCollapsed).not.toBeNull();

  const deltaCollapsed =
    (searchBoxCollapsed!.x as number) - ((trackerBoxCollapsed!.x as number) + (trackerBoxCollapsed!.width as number));

  // 1) Tracker não pode expandir quando minimiza.
  expect(trackerBoxCollapsed!.width).toBeLessThanOrEqual(trackerBoxExpanded!.width + 3);

  // 2) Busca deve manter o alinhamento relativo ao lado externo do tracker.
  // Em headless, pequenas variações de layout são comuns; buscamos estabilidade relativa.
  expect(Math.abs(deltaCollapsed - deltaExpanded)).toBeLessThanOrEqual(60);

  await page.screenshot({ path: "milestones-ui.png", fullPage: true });
});

