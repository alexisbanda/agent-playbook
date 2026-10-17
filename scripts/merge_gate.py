#!/usr/bin/env python3
"""Merge gate: checks the four conditions before merging a PR and prints the exact
merge command, tied to the reviewed commit.

  1. Fresh, anchored verdict: the review bot check (when review_bot.enabled) is
     green on the PR's current HEAD and finished after the promotion.
  2. Checks green: nothing failing or pending on the HEAD.
  3. Mergeable: no conflicts, not behind.
  4. Deploy spacing: no deploy of the base branch in progress.

Usage (from the main clone):
  merge_gate.py <pr> [--promoted-at ISO] [--repo owner/name] [--watch [--interval 30] [--timeout 3600]]

Exit code 0 when ready to merge, 1 when not, 2 when a condition can never pass
without a change (closed PR, changes requested, failed check): the run must stop.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

CONFIG_PATH = os.path.join(".claude", "agent-playbook.json")
CONFIG_PATHS = (".agent-playbook.json", CONFIG_PATH)
OK, WAIT, FAIL = "ok", "wait", "fail"
GOOD_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def gh(args):
    """Runs gh; retries without a stale GITHUB_TOKEN/GH_TOKEN from the environment."""
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0 and ("401" in out.stderr or "Bad credentials" in out.stderr):
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
        out = subprocess.run(["gh", *args], capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"gh {' '.join(args)} falló")
    return out.stdout


def parse_ts(value):
    if not value:
        return None
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_config(path=None):
    paths = (path,) if path else CONFIG_PATHS
    for candidate in paths:
        try:
            with open(candidate) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            continue
    return {}


def check_verdict(review_enabled, review_run, head, promoted_at):
    if not review_enabled:
        return OK, "review bot desactivado: el veredicto es la revisión interna sobre este HEAD (anótala en RUN_STATE.md)"
    if not review_run:
        return WAIT, "el review bot todavía no corrió sobre el HEAD actual"
    if review_run.get("head_sha") != head:
        return WAIT, f"el veredicto es de {review_run.get('head_sha', '?')[:7]}, no del HEAD {head[:7]}"
    if review_run.get("status") != "completed":
        return WAIT, "el review bot está revisando"
    conclusion = (review_run.get("conclusion") or "").upper()
    if conclusion == "SKIPPED":
        return WAIT, "el review bot se saltó (¿el PR seguía en borrador?): haz un ciclo borrador → listo"
    if conclusion != "SUCCESS":
        return FAIL, f"el review bot pidió cambios ({conclusion.lower()}): ver su comentario en el PR"
    completed = parse_ts(review_run.get("completed_at"))
    if promoted_at and completed and completed < promoted_at:
        return WAIT, "el veredicto es anterior a la última promoción: espera la nueva review"
    return OK, f"APPROVE sobre {head[:7]}" + (f", posterior a la promoción" if promoted_at else "")


def check_runs(rollup, review_name):
    pending, failed = [], []
    for item in rollup or []:
        name = item.get("name") or item.get("context") or "?"
        if name == review_name:
            continue
        if item.get("__typename") == "StatusContext":
            state = (item.get("state") or "").upper()
            if state in ("PENDING", "EXPECTED"):
                pending.append(name)
            elif state not in ("SUCCESS",):
                failed.append(name)
            continue
        if (item.get("status") or "").upper() != "COMPLETED":
            pending.append(name)
        elif (item.get("conclusion") or "").upper() not in GOOD_CONCLUSIONS:
            failed.append(name)
    if failed:
        return FAIL, "fallan: " + ", ".join(sorted(failed))
    if pending:
        return WAIT, "pendientes: " + ", ".join(sorted(pending))
    if not [i for i in rollup or [] if (i.get("name") or i.get("context")) != review_name]:
        return OK, "sin checks configurados (decláralo en LÍMITES)"
    return OK, "todos en verde"


def check_mergeable(pr):
    if pr.get("state") != "OPEN":
        return FAIL, f"el PR está {pr.get('state', '?').lower()}"
    if pr.get("isDraft"):
        return WAIT, "el PR sigue en borrador: promuévelo"
    mergeable, status = pr.get("mergeable"), pr.get("mergeStateStatus")
    if mergeable == "CONFLICTING" or status == "DIRTY":
        return FAIL, "tiene conflictos con la base"
    if mergeable == "UNKNOWN":
        return WAIT, "GitHub todavía está calculando si se puede mergear"
    if status == "BEHIND":
        return WAIT, "la rama va por detrás de la base: actualízala (y la review vuelve a correr)"
    return OK, f"{mergeable} / {status}"


def check_deploy(deploy_ok, active_runs):
    if deploy_ok is not None:
        return (OK, "deploy_check en verde") if deploy_ok else (WAIT, "deploy_check: hay un deploy en curso o el último falló")
    if active_runs:
        return WAIT, "workflows en curso en la rama base: " + ", ".join(sorted(set(active_runs)))
    return OK, "sin workflows en curso en la rama base"


def evaluate(pr, review_run, promoted_at, review_enabled, review_name, deploy_ok, active_runs):
    head = pr["headRefOid"]
    rows = [
        ("1. Veredicto fresco y anclado", *check_verdict(review_enabled, review_run, head, promoted_at)),
        ("2. Checks en verde", *check_runs(pr.get("statusCheckRollup"), review_name)),
        ("3. Mergeable", *check_mergeable(pr)),
        ("4. Espaciado de deploys", *check_deploy(deploy_ok, active_runs)),
    ]
    states = {row[1] for row in rows}
    overall = FAIL if FAIL in states else WAIT if WAIT in states else OK
    return overall, rows


def gather(args, config):
    repo_args = ["-R", args.repo] if args.repo else []
    fields = "number,state,isDraft,headRefOid,baseRefName,mergeable,mergeStateStatus,statusCheckRollup,url"
    pr = json.loads(gh(["pr", "view", str(args.pr), *repo_args, "--json", fields]))
    repo = args.repo or pr["url"].split("github.com/")[1].split("/pull/")[0]

    review = config.get("review_bot") or {}
    review_enabled = bool(review.get("enabled"))
    review_name = review.get("check_name", "claude-review")
    review_run = None
    if review_enabled:
        runs = json.loads(gh(["api", f"repos/{repo}/commits/{pr['headRefOid']}/check-runs?check_name={review_name}"]))
        runs = sorted(runs.get("check_runs", []), key=lambda r: r.get("started_at") or "", reverse=True)
        review_run = runs[0] if runs else None

    deploy_ok = None
    deploy_check = (config.get("environment") or {}).get("deploy_check")
    if deploy_check:
        deploy_ok = subprocess.run(deploy_check, shell=True, capture_output=True).returncode == 0
        active_runs = []
    else:
        runs = json.loads(gh(["run", "list", "-R", repo, "--branch", pr["baseRefName"], "--limit", "20",
                              "--json", "status,workflowName"]))
        active_runs = [r["workflowName"] for r in runs if r["status"] in ("in_progress", "queued", "waiting", "pending")]

    return pr, repo, review_run, review_enabled, review_name, deploy_ok, active_runs


def report(pr, repo, overall, rows):
    print(f"PR #{pr['number']} · HEAD {pr['headRefOid'][:7]} · {repo}")
    print("| Condición | Estado | Detalle |")
    print("| --- | --- | --- |")
    for name, state, detail in rows:
        print(f"| {name} | {state.upper()} | {detail} |")
    if overall == OK:
        print("\nLISTO. Comando de merge (pide OK al usuario antes de ejecutarlo):")
        print(f"gh pr merge {pr['number']} -R {repo} --squash --delete-branch --match-head-commit {pr['headRefOid']}")
    elif overall == FAIL:
        print("\nNO SE PUEDE MERGEAR sin un cambio: detén la corrida y muestra este estado.")
    else:
        print("\nTODAVÍA NO: espera y vuelve a comprobar.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pr")
    parser.add_argument("--repo")
    parser.add_argument("--promoted-at", help="Hora de la última promoción (ISO 8601, UTC)")
    parser.add_argument("--watch", action="store_true", help="Repite hasta que esté listo, falle o venza --timeout")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    config = load_config()
    promoted_at = parse_ts(args.promoted_at) if args.promoted_at else None
    deadline = time.time() + args.timeout
    while True:
        pr, repo, review_run, enabled, name, deploy_ok, active = gather(args, config)
        overall, rows = evaluate(pr, review_run, promoted_at, enabled, name, deploy_ok, active)
        if overall != WAIT or not args.watch or time.time() >= deadline:
            report(pr, repo, overall, rows)
            if overall == WAIT and args.watch:
                print("Venció el tiempo del vigilante: detén la corrida y muestra este estado.")
            sys.exit({OK: 0, WAIT: 1, FAIL: 2}[overall])
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
