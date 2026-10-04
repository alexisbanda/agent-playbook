#!/usr/bin/env python3
"""Runs the regression journeys of .claude/agent-playbook.json and prints the
evidence table. Logs go to .agent-playbook/runs/<ticket>/journeys/.

Usage (from the main clone): run_journeys.py <ticket> [--timeout 600]
Exit code 0 when every journey passed (or there are none), 1 when one failed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

CONFIG_PATH = os.path.join(".claude", "agent-playbook.json")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "journey"


def run_journeys(journeys, log_dir, timeout):
    os.makedirs(log_dir, exist_ok=True)
    results = []
    for journey in journeys:
        log_path = os.path.join(log_dir, slug(journey["name"]) + ".log")
        start = time.time()
        try:
            out = subprocess.run(journey["command"], shell=True, capture_output=True, text=True, timeout=timeout)
            code, output = out.returncode, out.stdout + out.stderr
        except subprocess.TimeoutExpired as exc:
            code, output = None, f"{exc.stdout or ''}{exc.stderr or ''}\nTIMEOUT tras {timeout} s"
        with open(log_path, "w") as fh:
            fh.write(output if isinstance(output, str) else output.decode(errors="replace"))
        results.append({
            "name": journey["name"],
            "ok": code == 0,
            "exit": code,
            "seconds": round(time.time() - start, 1),
            "log": log_path,
        })
    return results


def table(results):
    lines = ["| Journey | Resultado | Duración | Log |", "| --- | --- | --- | --- |"]
    for r in results:
        status = "✅ pasa" if r["ok"] else ("⏱️ timeout" if r["exit"] is None else f"❌ falla (exit {r['exit']})")
        lines.append(f"| {r['name']} | {status} | {r['seconds']} s | `{r['log']}` |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    try:
        with open(CONFIG_PATH) as fh:
            journeys = json.load(fh).get("journeys") or []
    except (OSError, ValueError):
        sys.exit(f"no se pudo leer {CONFIG_PATH}")

    if not journeys:
        print("No hay journeys configurados: decláralo en LÍMITES y sugiere 2 o 3 recorridos para `journeys`.")
        return
    results = run_journeys(journeys, os.path.join(".agent-playbook", "runs", args.ticket, "journeys"), args.timeout)
    print(table(results))
    sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
