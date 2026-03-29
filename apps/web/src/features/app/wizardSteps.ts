import { BarChart3, Layers, MapPinned, MapPin, RefreshCw, Settings2, Train } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { TravelMode } from "../../state/journey-store";

/** Alinhado a PRD §9 (Etapas da jornada) e rótulos de `FRONTEND_GEMINI.html`. */
export const WIZARD_STEP_IDS = [1, 2, 3, 4, 5, 6] as const;
export type WizardStepId = (typeof WIZARD_STEP_IDS)[number];

export const WIZARD_STEPS: {
  id: WizardStepId;
  title: string;
  desc: string;
  Icon: LucideIcon;
}[] = [
  { id: 1, title: "Configuração", desc: "Parâmetros e ponto principal", Icon: Settings2 },
  { id: 2, title: "Origem", desc: "Ponto de transporte", Icon: Train },
  { id: 3, title: "Zonas", desc: "Geração e processamento", Icon: RefreshCw },
  { id: 4, title: "Comparação", desc: "Selecionar e detalhar zona", Icon: Layers },
  { id: 5, title: "Endereço", desc: "Buscar imóveis na zona", Icon: MapPinned },
  { id: 6, title: "Análise", desc: "Imóveis e dashboard", Icon: BarChart3 }
];

export function getVisibleWizardSteps(modal: TravelMode) {
  if (modal === "walk" || modal === "car") {
    return WIZARD_STEPS.filter((step) => step.id !== 2);
  }
  return WIZARD_STEPS;
}

/** Ícone do mapa na etapa 1 (ponto principal) — mantido para compat com usos que esperam MapPin na etapa inicial. */
export const WIZARD_PRIMARY_POINT_ICON = MapPin;
