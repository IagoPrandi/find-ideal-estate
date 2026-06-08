"""
Rotina mensal semiautomatizada de teste de visibilidade GEO do BetterPlace.

Abre cada prompt do geo-prompts.json sequencialmente no navegador padrão para
que o operador teste manualmente nas plataformas de IA. O operador registra
os resultados no CSV e o script atualiza o geo_visibility_log.ts.

Uso:
  # Mostra todos os prompts formatados (modo leitura)
  python scripts/test_geo_visibility.py --mes 2026-06 --list

  # Abre os prompts no navegador para teste manual
  python scripts/test_geo_visibility.py --mes 2026-06 --open

  # Registra um resultado diretamente via CLI
  python scripts/test_geo_visibility.py --mes 2026-06 --registrar \\
      --prompt geo-p01 --ai chatgpt --visibilidade citado \\
      --trecho "BetterPlace foi citado como..." --obs "link incluído"

  # Converte o CSV para o arquivo TS (regenera geo_visibility_log.ts)
  python scripts/test_geo_visibility.py --sincronizar

Requisitos:
  pip install (nenhum além de stdlib)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import webbrowser
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROMPTS_PATH = ROOT / "apps" / "content" / "public" / "geo-prompts.json"
CSV_PATH = ROOT / "data" / "geo" / "geo_visibility_log.csv"
TS_PATH = ROOT / "apps" / "content" / "src" / "data" / "geo_visibility_log.ts"

AI_PLATAFORMAS = {
    "chatgpt": "https://chatgpt.com",
    "perplexity": "https://www.perplexity.ai",
    "gemini": "https://gemini.google.com",
    "claude": "https://claude.ai",
    "bing_copilot": "https://www.bing.com/chat",
}

VISIBILIDADES = {"citado", "nao_citado", "citado_sem_link"}

CSV_FIELDNAMES = ["data", "prompt_id", "ai", "visibilidade", "trecho", "observacoes"]


def carregar_prompts() -> list[dict]:
    with PROMPTS_PATH.open(encoding="utf-8") as f:
        return json.load(f)["prompts"]


def listar_prompts(mes: str) -> None:
    prompts = carregar_prompts()
    print(f"\n=== Prompts GEO — {mes} ===\n")
    for p in prompts:
        print(f"[{p['id']}] ({p['categoria']})")
        print(f"  {p['prompt']}\n")
    print(f"Total: {len(prompts)} prompts | Plataformas: {', '.join(AI_PLATAFORMAS)}\n")


def abrir_no_navegador() -> None:
    prompts = carregar_prompts()
    print("Abrindo plataformas de IA no navegador padrão...")
    for nome, url in AI_PLATAFORMAS.items():
        print(f"  {nome}: {url}")
        webbrowser.open(url)
    print("\nPrompts para testar:")
    for p in prompts:
        print(f"  [{p['id']}] {p['prompt']}")
    print("\nRegistre os resultados via --registrar ou edite o CSV diretamente:")
    print(f"  {CSV_PATH}\n")


def ler_csv() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def escrever_csv(linhas: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(linhas)


def registrar(mes: str, prompt_id: str, ai: str, visibilidade: str, trecho: str, obs: str) -> None:
    if ai not in {*AI_PLATAFORMAS, "outro"}:
        print(f"Erro: plataforma '{ai}' inválida. Opções: {', '.join(AI_PLATAFORMAS)} ou 'outro'")
        sys.exit(1)
    if visibilidade not in VISIBILIDADES:
        print(f"Erro: visibilidade '{visibilidade}' inválida. Opções: {', '.join(VISIBILIDADES)}")
        sys.exit(1)

    linhas = ler_csv()
    nova = {
        "data": date.today().isoformat(),
        "prompt_id": prompt_id,
        "ai": ai,
        "visibilidade": visibilidade,
        "trecho": trecho.strip(),
        "observacoes": obs.strip(),
    }
    linhas.append(nova)
    escrever_csv(linhas)
    print(f"Registrado: {nova}")
    sincronizar_ts(linhas)


def sincronizar_ts(linhas: list[dict] | None = None) -> None:
    if linhas is None:
        linhas = ler_csv()

    entries_ts = []
    for r in linhas:
        trecho_escaped = r.get("trecho", "").replace("'", "\\'")
        obs_escaped = r.get("observacoes", "").replace("'", "\\'")
        entry = (
            "  {\n"
            f"    data: '{r['data']}',\n"
            f"    promptId: '{r['prompt_id']}',\n"
            f"    ai: '{r['ai']}',\n"
            f"    visibilidade: '{r['visibilidade']}',\n"
            f"    trecho: '{trecho_escaped}',\n"
            f"    observacoes: '{obs_escaped}',\n"
            "  }"
        )
        entries_ts.append(entry)

    log_content = ",\n".join(entries_ts)
    ts_content = (
        "export type GeoAi = 'chatgpt' | 'perplexity' | 'gemini' | 'claude' | 'bing_copilot' | 'outro';\n\n"
        "export type GeoVisibilidade = 'citado' | 'nao_citado' | 'citado_sem_link';\n\n"
        "export interface GeoVisibilityEntry {\n"
        "  data: string;\n"
        "  promptId: string;\n"
        "  ai: GeoAi;\n"
        "  visibilidade: GeoVisibilidade;\n"
        "  trecho: string;\n"
        "  observacoes: string;\n"
        "}\n\n"
        f"export const GEO_VISIBILITY_LOG: GeoVisibilityEntry[] = [\n{log_content}\n];\n"
    )
    TS_PATH.write_text(ts_content, encoding="utf-8")
    print(f"geo_visibility_log.ts sincronizado: {len(linhas)} entradas -> {TS_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Teste de visibilidade GEO — BetterPlace")
    parser.add_argument("--mes", help="Mês/período de teste, ex.: 2026-06", default=date.today().strftime("%Y-%m"))
    parser.add_argument("--list", action="store_true", help="Exibe todos os prompts formatados")
    parser.add_argument("--open", action="store_true", help="Abre as plataformas no navegador padrão")
    parser.add_argument("--registrar", action="store_true", help="Registra um resultado no CSV e atualiza o TS")
    parser.add_argument("--prompt", help="ID do prompt (ex.: geo-p01)")
    parser.add_argument("--ai", help="Plataforma: chatgpt|perplexity|gemini|claude|bing_copilot|outro")
    parser.add_argument("--visibilidade", help="citado|nao_citado|citado_sem_link")
    parser.add_argument("--trecho", default="", help="Trecho da resposta onde BetterPlace foi mencionado")
    parser.add_argument("--obs", default="", help="Observações adicionais")
    parser.add_argument("--sincronizar", action="store_true", help="Converte o CSV atual para geo_visibility_log.ts")

    args = parser.parse_args()

    if args.list:
        listar_prompts(args.mes)
    elif args.open:
        listar_prompts(args.mes)
        abrir_no_navegador()
    elif args.registrar:
        if not all([args.prompt, args.ai, args.visibilidade]):
            print("Erro: --registrar requer --prompt, --ai e --visibilidade.")
            sys.exit(1)
        registrar(args.mes, args.prompt, args.ai, args.visibilidade, args.trecho, args.obs)
    elif args.sincronizar:
        sincronizar_ts()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
