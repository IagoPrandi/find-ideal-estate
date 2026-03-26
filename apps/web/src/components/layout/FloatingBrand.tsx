import { MapPin } from "lucide-react";

/** Marca flutuante (referência FRONTEND_GEMINI). */
export function FloatingBrand() {
  return (
    <div className="pointer-events-none absolute right-4 top-4 z-20 flex items-center gap-3 rounded-full border border-white/70 bg-white/90 px-4 py-2.5 shadow-lg backdrop-blur-md">
      <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-pastel-violet-500 to-pastel-violet-600 text-white shadow-md shadow-pastel-violet-200">
        <MapPin className="h-3.5 w-3.5" aria-hidden />
      </div>
      <div>
        <p className="text-[10px] font-extrabold uppercase tracking-[0.22em] text-slate-400">Find Ideal Estate</p>
        <span className="text-sm font-bold tracking-tight text-slate-800">
          Decisão urbana guiada por mapa <span className="text-pastel-violet-500">2.0</span>
        </span>
      </div>
    </div>
  );
}
