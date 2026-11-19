#!/usr/bin/env python3
"""Summarises .agent-playbook/metrics.jsonl and checks the tripwires.

Usage: metrics_report.py [metrics.jsonl ...] [--window N] [--json]
With no files, reads ./.agent-playbook/metrics.jsonl. Several files (one per repo)
are combined. Prints a Markdown report; exit code 0 always (a tripped wire is a
signal for the tuning wave, not an error).
"""
import argparse
import json
import os
import statistics

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PRICES = os.path.join(ROOT, "metrics", "prices.json")
TRIPWIRES = os.path.join(ROOT, "metrics", "tripwires.json")
DEFAULT_METRICS = os.path.join(".agent-playbook", "metrics.jsonl")


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def load_runs(paths):
    runs = []
    for path in paths:
        with open(path) as fh:
            for line in fh:
                if line.strip():
                    run = json.loads(line)
                    run["_source"] = path
                    runs.append(run)
    return sorted(runs, key=lambda r: r.get("closed_at", ""))


def price_for(model, prices):
    """Prices by model id; dated ids (claude-haiku-4-5-20251001) match their base id."""
    best = None
    for model_id, price in prices.items():
        if model == model_id or model.startswith(model_id):
            if best is None or len(model_id) > len(best[0]):
                best = (model_id, price)
    return best[1] if best else None


def run_cost(run, prices):
    """Returns (estimated USD, models without a price)."""
    total, unpriced = 0.0, []
    for model, tokens in (run.get("tokens_by_model") or {}).items():
        price = price_for(model, prices)
        if not price:
            unpriced.append(model)
            continue
        total += (
            tokens.get("input_tokens", 0) * price["input"]
            + tokens.get("output_tokens", 0) * price["output"]
            + tokens.get("cache_read_input_tokens", 0) * price["cache_read"]
            + tokens.get("cache_creation_input_tokens", 0) * price["cache_write"]
        ) / 1_000_000
    return round(total, 2), unpriced


def wait_share(run):
    """Share of the run spent waiting for the human. Since 1.6.0, absences (stops longer
    than 30 minutes) are left out of both sides: they measure the human being away, not
    the process making them wait. Older lines only have the raw total."""
    wall = run.get("wall_minutes") or 0
    if "human_wait_active_minutes" in run:
        effective = wall - (run.get("human_absence_minutes") or 0)
        return (run["human_wait_active_minutes"] / effective) if effective > 0 else None
    return (run.get("human_wait_minutes", 0) / wall) if wall else None


def summarise(runs, prices):
    rows = []
    for run in runs:
        cost, unpriced = run_cost(run, prices)
        wall = run.get("wall_minutes") or 0
        rows.append({
            "run": run["run"],
            "closed_at": run.get("closed_at", "")[:16],
            "version": run.get("playbook_version", "?"),
            "wall": wall,
            "wait": run.get("human_wait_minutes", 0),
            "wait_share": wait_share(run),
            "stops": run.get("human_stops"),
            "subagents": run.get("subagents", 0),
            "prs_merged": run.get("prs_merged", 0),
            "compactions": run.get("compactions", 0),
            "e2e": run.get("e2e_first_pass", "na"),
            "cost": cost,
            "unpriced": unpriced,
            "ctx_start": run.get("orchestrator_ctx_start_k"),
            "orchestrator": run.get("orchestrator_model"),
            "coder_calls": run.get("coder_calls_max"),
            "coder_peak": run.get("coder_ctx_peak_k"),
            "overrides": len(run.get("overrides") or []),
            "model_blocks": (run.get("gate_events") or {}).get("model_block", 0),
            "tokens_measured": run.get("tokens_measured", False),
            "ticket": run.get("ticket_quality"),
            "gemini_readers": run.get("gemini_readers"),
        })
    return rows


def check_tripwires(rows, config):
    window = rows[-config["window"]:]
    wires = config["tripwires"]
    results = []

    def add(name, observed, tripped, detail):
        results.append({"name": name, "threshold": wires[name]["value"], "observed": observed,
                        "tripped": tripped, "why": wires[name]["why"], "detail": detail})

    if len(window) < config["min_runs"]:
        return results, f"solo {len(window)} corridas (mínimo {config['min_runs']}): tripwires sin evaluar"

    judged = [r for r in window if r["e2e"] in ("yes", "no")]
    if judged:
        rate = sum(r["e2e"] == "yes" for r in judged) / len(judged)
        add("e2e_first_pass_rate_min", round(rate, 2), rate < wires["e2e_first_pass_rate_min"]["value"], f"{len(judged)} corridas con pruebas en vivo")

    shares = [r["wait_share"] for r in window if r["wait_share"] is not None]
    if shares:
        median = statistics.median(shares)
        add("human_wait_share_max", round(median, 2), median > wires["human_wait_share_max"]["value"],
            "mediana de minutos esperando / minutos totales, sin ausencias de más de 30 min desde la 1.6.0")

    stops = [r["stops"] for r in window if r["stops"] is not None]
    if stops:
        median = statistics.median(stops)
        add("human_stops_per_run_max", median, median > wires["human_stops_per_run_max"]["value"],
            f"mediana de paradas en las que respondió el humano ({len(stops)} corridas medidas)")

    share = sum(r["compactions"] > 0 for r in window) / len(window)
    add("compaction_runs_share_max", round(share, 2), share > wires["compaction_runs_share_max"]["value"], "corridas con al menos una compactación")

    costs = [r["cost"] for r in window if r["tokens_measured"]]
    if costs:
        median = statistics.median(costs)
        add("cost_per_run_usd_max", round(median, 2), median > wires["cost_per_run_usd_max"]["value"], "mediana del coste estimado")

    starts = [r["ctx_start"] for r in window if r["ctx_start"] is not None]
    if starts:
        median = statistics.median(starts)
        add("orchestrator_ctx_start_k_max", median, median > wires["orchestrator_ctx_start_k_max"]["value"],
            f"mediana de miles de tokens en la primera llamada del orquestador ({len(starts)} corridas medidas)")

    calls = [r["coder_calls"] for r in window if r["coder_calls"] is not None]
    if calls:
        median = statistics.median(calls)
        add("coder_calls_max", median, median > wires["coder_calls_max"]["value"],
            f"mediana de llamadas del coder más largo de cada corrida ({len(calls)} corridas medidas)")

    peaks = [r["coder_peak"] for r in window if r["coder_peak"] is not None]
    if peaks:
        median = statistics.median(peaks)
        add("coder_ctx_peak_k_max", median, median > wires["coder_ctx_peak_k_max"]["value"],
            f"mediana del contexto máximo de un coder, en miles de tokens ({len(peaks)} corridas medidas)")

    overrides = statistics.mean(r["overrides"] for r in window)
    add("overrides_per_run_max", round(overrides, 2), overrides > wires["overrides_per_run_max"]["value"], "media por corrida")

    blocks = statistics.mean(r["model_blocks"] for r in window)
    add("model_blocks_per_run_max", round(blocks, 2), blocks > wires["model_blocks_per_run_max"]["value"], "media por corrida")

    if "gemini_readers_degraded_share_max" in wires:
        readers = [r["gemini_readers"] for r in window
                   if isinstance(r.get("gemini_readers"), dict) and (r["gemini_readers"].get("calls") or 0) > 0]
        reader_calls = sum(int(g.get("calls") or 0) for g in readers)
        degraded = sum(int(g.get("degraded") or 0) for g in readers)
        if reader_calls > 0:
            share = degraded / reader_calls
            add("gemini_readers_degraded_share_max", round(share, 2),
                share > wires["gemini_readers_degraded_share_max"]["value"],
                f"lectores degradados / llamadas ({reader_calls} lectores en {len(readers)} corridas)")

    untracked = sum(not r["tokens_measured"] for r in window)
    add("untracked_runs_max", untracked, untracked > wires["untracked_runs_max"]["value"], "corridas sin tokens medidos")
    return results, None


def fmt(value, pct=False):
    if value is None:
        return "—"
    return f"{value:.0%}" if pct else str(value)


def short_model(model):
    """claude-opus-5-5 -> opus; unknown or missing -> as is or a dash."""
    if not model:
        return "—"
    parts = model.split("-")
    return parts[1] if len(parts) > 1 and parts[0] == "claude" else model


def coder_cell(row):
    if row["coder_calls"] is None:
        return "—"
    return f"{row['coder_calls']} / {fmt(row['coder_peak'])}"


def ticket_cell(quality):
    if not quality:
        return "—"
    score = f"{quality['score']}/100" if quality.get("score") is not None else ("ok" if quality.get("contract_ok") else "incompleto")
    return score + ("" if quality.get("ready") else " (sin ready)")


def markdown(rows, wires, note, window):
    out = ["## Corridas", "",
           "| Corrida | Cerrada | Versión | Orquestador | Min. totales | Min. esperando | Paradas | Subagentes | PRs mergeados | Compactaciones | Contexto inicial (k) | Coder: llamadas / pico (k) | E2E a la primera | Calidad del ticket | Coste estimado |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        cost = f"${r['cost']}" + (" (*)" if r["unpriced"] else "")
        out.append(f"| {r['run']} | {r['closed_at']} | {r['version']} | {short_model(r['orchestrator'])} | {r['wall']} | {r['wait']} | {fmt(r['stops'])} | {r['subagents']} | "
                   f"{r['prs_merged']} | {r['compactions']} | {fmt(r['ctx_start'])} | {coder_cell(r)} | {r['e2e']} | {ticket_cell(r['ticket'])} | {cost} |")
    if any(r["unpriced"] for r in rows):
        out += ["", "(*) Modelos sin precio en `metrics/prices.json`: " + ", ".join(sorted({m for r in rows for m in r["unpriced"]}))]
    out += ["", f"## Tripwires (últimas {window} corridas)", ""]
    if note:
        out.append(note)
    else:
        out += ["| Tripwire | Umbral | Observado | Estado | Detalle |", "| --- | --- | --- | --- | --- |"]
        for w in wires:
            out.append(f"| `{w['name']}` | {w['threshold']} | {w['observed']} | {'🔴 salta' if w['tripped'] else '🟢 ok'} | {w['detail']} |")
        tripped = [w for w in wires if w["tripped"]]
        if tripped:
            out += ["", "### Por qué importa"] + [f"- `{w['name']}`: {w['why']}" for w in tripped]
    return "\n".join(out)


def sanitize_runs(runs):
    """Returns a client-safe copy of runs without private ticket IDs, paths, or free-text override reasons."""
    sanitized = []
    for idx, r in enumerate(runs, 1):
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        clean["run"] = f"run-{idx}"
        if clean.get("overrides"):
            clean["overrides"] = ["redacted" for _ in clean["overrides"]]
        sanitized.append(clean)
    return sanitized


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--window", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--export-sanitized", help="Exporta un archivo metrics.jsonl sanitizado (sin IDs ni textos de cliente)")
    args = parser.parse_args()

    files = args.files or [DEFAULT_METRICS]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        raise SystemExit("no existe: " + ", ".join(missing))
    raw_runs = load_runs(files)
    if args.export_sanitized:
        clean = sanitize_runs(raw_runs)
        with open(args.export_sanitized, "w") as fh:
            for item in clean:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(json.dumps({"ok": True, "exported": len(clean), "output": args.export_sanitized}, ensure_ascii=False))
        return
    config = load_json(TRIPWIRES)
    if args.window:
        config["window"] = args.window
    rows = summarise(raw_runs, load_json(PRICES)["models"])
    wires, note = check_tripwires(rows, config)
    if args.json:
        print(json.dumps({"runs": rows, "tripwires": wires, "note": note}, ensure_ascii=False, indent=2))
    else:
        print(markdown(rows, wires, note, config["window"]))


if __name__ == "__main__":
    main()
