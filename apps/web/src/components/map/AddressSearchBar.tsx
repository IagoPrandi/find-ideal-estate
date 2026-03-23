import { FormEvent } from "react";
import { Search } from "lucide-react";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  containerStyle?: {
    left: string;
  };
};

export function AddressSearchBar({ value, onChange, onSubmit, containerStyle }: Props) {
  return (
    <div className="pointer-events-auto absolute top-6 z-40 w-80 max-w-[min(100%,calc(100vw-2rem))]" style={containerStyle}>
      <form
        onSubmit={onSubmit}
        className="flex items-center rounded-xl border border-slate-200 bg-white/95 px-4 py-3 shadow-md backdrop-blur-md"
      >
        <Search className="mr-3 h-5 w-5 shrink-0 text-slate-400" />
        <input
          id="map-search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Endereço ou bairro..."
          className="w-full border-none bg-transparent text-sm font-medium text-slate-700 outline-none placeholder:text-slate-400"
        />
        <button type="submit" className="ml-2 text-sm font-bold text-pastel-violet-600">
          Buscar
        </button>
      </form>
    </div>
  );
}
