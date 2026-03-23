import { MapPin } from "lucide-react";

/** Marca flutuante (referência FRONTEND_GEMINI). */
export function FloatingBrand() {
  return (
    <div className="pointer-events-none absolute right-4 top-4 z-20 flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-4 py-2 shadow-sm backdrop-blur-md">
      <div className="flex h-6 w-6 items-center justify-center rounded-md bg-pastel-violet-500 text-white">
        <MapPin className="h-3.5 w-3.5" aria-hidden />
      </div>
      <span className="text-sm font-bold tracking-tight text-slate-800">
        Find Ideal Estate <span className="text-pastel-violet-500">2.0</span>
      </span>
    </div>
  );
}
