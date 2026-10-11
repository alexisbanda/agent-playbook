#!/usr/bin/env python3
"""Checks a GitHub issue against the ticket contract, only when the repository
opts in with `tickets.contract: true` in .claude/agent-playbook.json.

Two levels, and agent-playbook needs neither Ticket Studio nor its code:
  - minimal (always available): `ready` label, acceptance criteria with a check
    type ([http] [test] [e2e] [manual]), risk and size labels;
  - full: if Ticket Studio is installed, its `ticket_core.lint` adds the score.

Usage (from the main clone):
  ticket_check.py <issue> [--repo owner/name] [--save .agent-playbook/runs/<ticket>/ticket_check.json]

Prints a JSON result. Always exits 0: the preflight warns and asks, it never blocks.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys

CONFIG_PATH = os.path.join(".claude", "agent-playbook.json")
CHECKS = ("http", "test", "e2e", "manual")
TYPED_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s*\[(\w+)\]\s*\S", re.MULTILINE)
CRITERIA_HEADING_RE = re.compile(r"^#{2,4}\s*(criterios de aceptaci[oó]n|acceptance criteria)\s*$", re.IGNORECASE | re.MULTILINE)


def load_config(path=CONFIG_PATH):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def contract_enabled(config):
    return bool((config.get("tickets") or {}).get("contract"))


def ready_label(config):
    return (config.get("tickets") or {}).get("ready_label", "ready")


def find_ticket_studio():
    """Path to Ticket Studio's ticket_core.py, if the plugin is installed (newest version)."""
    override = os.environ.get("TICKET_STUDIO_ROOT")
    candidates = [os.path.join(override, "scripts", "ticket_core.py")] if override else []
    pattern = os.path.expanduser("~/.claude/plugins/cache/*/ticket-studio/*/scripts/ticket_core.py")

    def version(path):
        name = os.path.basename(os.path.dirname(os.path.dirname(path)))
        return tuple(int(p) if p.isdigit() else 0 for p in name.split("."))

    candidates += sorted(glob.glob(pattern), key=version, reverse=True)
    return next((c for c in candidates if os.path.exists(c)), None)


def load_ticket_core(path):
    spec = importlib.util.spec_from_file_location("ticket_core", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def minimal_check(body, labels, ready_name="ready"):
    """The contract's minimum, with agent-playbook's own logic."""
    labels = [label if isinstance(label, str) else label.get("name", "") for label in labels or []]
    typed = [m.group(1).lower() for m in TYPED_RE.finditer(body or "")]
    valid = [t for t in typed if t in CHECKS]
    risk = [l[5:] for l in labels if l.startswith("risk:")]
    size = next((l[5:] for l in labels if l.startswith("size:")), None)
    kind = next((l[5:] for l in labels if l.startswith("type:")), None)
    missing = []
    if ready_name not in labels:
        missing.append(f"etiqueta `{ready_name}` (el tech lead no lo ha marcado como listo)")
    if kind != "epic":
        if not valid:
            if CRITERIA_HEADING_RE.search(body or ""):
                missing.append("tipo de prueba en los criterios de aceptación ([http], [test], [e2e] o [manual])")
            else:
                missing.append("criterios de aceptación")
        if not risk:
            missing.append("etiqueta de riesgo (`risk:*`)")
        if not size:
            missing.append("etiqueta de tamaño (`size:*`)")
    return {
        "type": kind,
        "ready": ready_name in labels,
        "typed_criteria": len(valid),
        "risk": risk,
        "size": size,
        "missing": missing,
        "contract_ok": not [m for m in missing if not m.startswith("etiqueta `")],
    }


def check(issue, ready_name="ready", studio_path=None):
    """issue = {"title", "body", "labels"} as `gh issue view --json` returns it."""
    result = {"source": "minimal", **minimal_check(issue.get("body"), issue.get("labels"), ready_name)}
    result["score"] = None
    if studio_path:
        try:
            core = load_ticket_core(studio_path)
            lint = core.lint(core.parse_github(issue.get("title"), issue.get("body"), issue.get("labels")))
            result.update(source="ticket-studio", score=lint["score"], errors=lint["errors"], warnings=lint["warnings"],
                          findings=lint["findings"])
        except Exception as exc:  # a broken or incompatible Ticket Studio never breaks the run
            result["studio_error"] = f"{type(exc).__name__}: {exc}"
    if result["type"] == "epic":
        result["epic"] = True
    return result


def fetch_issue(number, repo):
    args = ["gh", "issue", "view", str(number), "--json", "title,body,labels"] + (["-R", repo] if repo else [])
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0 and ("401" in out.stderr or "Bad credentials" in out.stderr):
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
        out = subprocess.run(args, capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise SystemExit(out.stderr.strip())
    return json.loads(out.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("issue")
    parser.add_argument("--repo")
    parser.add_argument("--save")
    args = parser.parse_args()

    config = load_config()
    if not contract_enabled(config):
        result = {"enabled": False, "note": "tickets.contract no está activado: no se comprueba el contrato."}
    else:
        result = {"enabled": True, **check(fetch_issue(args.issue, args.repo), ready_label(config), find_ticket_studio())}
    if args.save:
        os.makedirs(os.path.dirname(args.save), exist_ok=True)
        with open(args.save, "w") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
