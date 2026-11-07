#!/usr/bin/env python3
"""Closes a run: crosses the hook events with the transcripts and appends one
validated line to .agent-playbook/metrics.jsonl. Then removes the active-run marker.

Usage (from the main clone of the repo):
  close_run.py <run-id> [--e2e-first-pass yes|no|na] [--dry-run]

The metrics come from what the hooks measured, not from what the model reports.
The only declared field is e2e_first_pass, and it is labelled as such.

A PR the user merges by hand (for example because auto mode blocked
`gh pr merge`) leaves no hook event, so the PRs opened in the run are also
looked up on GitHub: prs_merged counts both, and prs_merged_outside says how
many were merged outside the session. Without gh or network, only the events count.
"""
import argparse
import collections
import datetime
import json
import os
import subprocess
import sys

import route

STATE_DIR = ".agent-playbook"
PLUGIN_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCHEMA = os.path.join(PLUGIN_ROOT, "config", "metrics.schema.json")


def playbook_version():
    try:
        with open(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")) as fh:
            return json.load(fh)["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_events(root):
    path = os.path.join(root, STATE_DIR, "events.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def minutes(delta):
    return round(delta.total_seconds() / 60, 1)


def usage_from_transcript(path, start=None, end=None):
    """Sums token usage by model from a Claude Code or Google Antigravity (agy) transcript (JSONL).

    In Claude Code, a response is written as several records with the same message id
    (one per content block while it streams); only the last one carries the final
    output_tokens, so the last record of each message wins.
    In agy, steps of type PLANNER_RESPONSE carry usage in `usage` or `metadata.usage`."""
    totals = collections.defaultdict(lambda: collections.Counter())
    if not path or not os.path.exists(path):
        return totals
    last = {}
    with open(path) as fh:
        for idx, line in enumerate(fh):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "PLANNER_RESPONSE":
                meta = entry.get("metadata") or {}
                usage = entry.get("usage") or meta.get("usage")
                if not usage:
                    continue
                ts = parse_ts(entry.get("created_at") or entry.get("timestamp"))
                if (start and ts and ts < start) or (end and ts and ts > end):
                    continue
                key = entry.get("step_index", f"agy-{idx}")
                model = entry.get("model") or meta.get("model") or "unknown"
                last[key] = (model, usage)
                continue
            message = entry.get("message") or {}
            usage = message.get("usage")
            if entry.get("type") != "assistant" or not usage:
                continue
            ts = parse_ts(entry.get("timestamp"))
            if (start and ts and ts < start) or (end and ts and ts > end):
                continue
            last[message.get("id") or entry.get("uuid") or f"cc-{idx}"] = (message.get("model", "unknown"), usage)
    for model, usage in last.values():
        counter = totals[model]
        for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            counter[field] += usage.get(field) or 0
    return totals


def context_tokens(usage):
    """Tokens the model had in its context for one call: fresh input plus cache read and write."""
    return sum(usage.get(f) or 0 for f in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def context_samples(path, start=None, end=None, with_model=False):
    """(timestamp, context tokens) of each main-thread call in a transcript, inside the window.
    With with_model, (timestamp, context tokens, model)."""
    samples = []
    if not path or not os.path.exists(path):
        return samples
    with open(path) as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "PLANNER_RESPONSE":
                meta = entry.get("metadata") or {}
                usage = entry.get("usage") or meta.get("usage")
                ts = parse_ts(entry.get("created_at") or entry.get("timestamp"))
                model = entry.get("model") or meta.get("model")
            elif entry.get("type") == "assistant":
                usage = (entry.get("message") or {}).get("usage")
                ts = parse_ts(entry.get("timestamp"))
                model = (entry.get("message") or {}).get("model")
            else:
                continue
            if not usage or not ts or (start and ts < start) or (end and ts > end):
                continue
            samples.append((ts, context_tokens(usage), model) if with_model else (ts, context_tokens(usage)))
    return samples


def agent_profile(path):
    """(role from the ROLE header of its prompt, model calls, peak context tokens) of a subagent transcript."""
    role, ids, peak = None, set(), 0
    if not path or not os.path.exists(path):
        return role, 0, 0
    with open(path) as fh:
        for idx, line in enumerate(fh):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") or {}
            if role is None and entry.get("type") == "user":
                content = message.get("content")
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                role = route.parse_header(content or "")[0] or ""
            elif entry.get("type") == "assistant" and message.get("usage"):
                ids.add(message.get("id") or entry.get("uuid") or idx)
                peak = max(peak, context_tokens(message["usage"]))
    return role, len(ids), peak


def session_transcripts(events, sessions):
    """Main-thread transcripts of the run's sessions: the one each event recorded
    (session_start, user_prompt) or, if the session started before the hooks
    could see it, the one next to its subagents' transcripts
    (<dir>/<session>/subagents/agent-*.jsonl -> <dir>/<session>.jsonl)."""
    paths = {e.get("transcript") for e in events if e.get("session_id") in sessions and e.get("transcript")}
    for e in events:
        agent = e.get("agent_transcript")
        if e.get("session_id") in sessions and agent:
            session_dir = os.path.dirname(os.path.dirname(agent))
            candidate = session_dir + ".jsonl"
            if os.path.basename(session_dir) == e["session_id"] and os.path.exists(candidate):
                paths.add(candidate)
    return {p for p in paths if p}


def merge_usage(target, source):
    for model, counter in source.items():
        target[model].update(counter)


def gh(args, cwd):
    """Runs gh; retries without a stale GITHUB_TOKEN/GH_TOKEN from the environment."""
    run = lambda env=None: subprocess.run(["gh", *args], capture_output=True, text=True, cwd=cwd, env=env)
    out = run()
    if out.returncode != 0 and ("401" in out.stderr or "Bad credentials" in out.stderr):
        out = run({k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")})
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return out.stdout


def merged_on_github(prs, root):
    """How many of these PRs are merged on GitHub, or None if gh cannot tell."""
    try:
        states = [json.loads(gh(["pr", "view", pr, "--json", "state"], root))["state"] for pr in prs]
    except (OSError, RuntimeError, ValueError, KeyError):
        return None
    return sum(state == "MERGED" for state in states)


def ticket_quality(root, run):
    """Result of scripts/ticket_check.py for this run, if the repository checks the ticket contract."""
    try:
        with open(os.path.join(root, STATE_DIR, "runs", run, "ticket_check.json")) as fh:
            check = json.load(fh)
    except (OSError, ValueError):
        return None
    if not check.get("enabled"):
        return None
    return {
        "source": check.get("source", "minimal"),
        "score": check.get("score"),
        "contract_ok": bool(check.get("contract_ok")),
        "ready": bool(check.get("ready")),
    }


def build_metrics(run, events, e2e_first_pass, root=None):
    run_events = [e for e in events if e.get("run") == run]
    if not run_events:
        raise SystemExit(f"no hay eventos de la corrida '{run}' en {STATE_DIR}/events.jsonl")
    start = parse_ts(run_events[0]["ts"])
    end = parse_ts(run_events[-1]["ts"])
    sessions = {e["session_id"] for e in run_events if e.get("session_id")}
    counts = collections.Counter(e["event"] for e in run_events)

    # Waiting for the human: from the end of a main-thread turn to the next prompt.
    waiting = datetime.timedelta()
    waits = 0
    pending = None
    for event in run_events:
        if event["event"] == "turn_end" and not event.get("agent_id"):
            pending = parse_ts(event["ts"])
        elif event["event"] == "user_prompt" and pending:
            waiting += parse_ts(event["ts"]) - pending
            waits += 1
            pending = None

    gates = collections.Counter()
    overrides = []
    for event in run_events:
        if event["event"] == "model_gate":
            gates[f"model_{event.get('decision')}"] += 1
            if event.get("override"):
                overrides.append(event["override"])
        elif event["event"] == "safety_gate":
            gates["safety"] += 1

    subagents = collections.Counter(
        # subagent_done: name used by 0.4.0 for the same event.
        e.get("model") or "default" for e in run_events if e["event"] in ("subagent_launched", "subagent_done")
    )

    usage = collections.defaultdict(collections.Counter)
    # The orchestrator's own tokens, only inside the run's window.
    for path in session_transcripts(events, sessions):
        merge_usage(usage, usage_from_transcript(path, start, end))
    for path in {e.get("agent_transcript") for e in run_events if e.get("agent_transcript")}:
        merge_usage(usage, usage_from_transcript(path))

    # Context the orchestrator already carried on its first call: a run that inherits
    # a previous ticket's session starts high and pays for it on every later call.
    samples = [s for path in session_transcripts(events, sessions) for s in context_samples(path, start, end, with_model=True)]
    ctx_start = round(min(samples)[1] / 1000, 1) if samples else None
    # The model that made most of the orchestrator's calls (the session can switch with /model mid-run).
    models = collections.Counter(m for _, _, m in samples if m and m != "<synthetic>")
    orchestrator_model = models.most_common(1)[0][0] if models else None

    # The coders' own loops: how many calls the longest one made and how far its context grew.
    coders = [agent_profile(p) for p in {e.get("agent_transcript") for e in run_events if e.get("agent_transcript")}]
    coders = [(calls, peak) for role, calls, peak in coders if role in ("coder", "patriot") and calls]

    merged = counts["pr_merged"]
    opened = sorted({str(e["pr"]) for e in run_events if e["event"] == "pr_opened" and e.get("pr")})
    on_github = merged_on_github(opened, root) if opened and root else None
    merged_outside = max(0, on_github - merged) if on_github is not None else 0

    return {
        "run": run,
        "playbook_version": playbook_version(),
        "closed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "started_at": run_events[0]["ts"],
        "ended_at": run_events[-1]["ts"],
        "wall_minutes": minutes(end - start),
        "human_wait_minutes": minutes(waiting),
        "human_waits": waits,
        "sessions": len(sessions),
        "subagents": sum(subagents.values()),
        "subagents_by_model": dict(subagents),
        "prs_opened": counts["pr_opened"],
        "prs_promoted": counts["pr_promoted"],
        "prs_merged": merged + merged_outside,
        "prs_merged_outside": merged_outside,
        "worktrees_created": counts["worktree_created"],
        "worktrees_removed": counts["worktree_removed"],
        "compactions": counts["compaction"],
        "gate_events": dict(gates),
        "overrides": overrides,
        "tokens_by_model": {model: dict(counter) for model, counter in usage.items()},
        "tokens_measured": bool(usage),
        "orchestrator_ctx_start_k": ctx_start,
        "orchestrator_model": orchestrator_model,
        "coder_calls_max": max(c for c, _ in coders) if coders else None,
        "coder_ctx_peak_k": round(max(p for _, p in coders) / 1000, 1) if coders else None,
        "context_guard_warnings": counts["context_guard"],
        "e2e_first_pass": e2e_first_pass,
        "e2e_first_pass_source": "declared",
        "ticket_quality": ticket_quality(root, run) if root else None,
    }


def validate(metrics):
    try:
        import jsonschema
    except ImportError:
        return "jsonschema no instalado: línea sin validar contra el esquema"
    with open(SCHEMA) as fh:
        jsonschema.validate(metrics, json.load(fh))
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--e2e-first-pass", choices=["yes", "no", "na"], default="na")
    parser.add_argument("--root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    metrics = build_metrics(args.run, load_events(root), args.e2e_first_pass, root)
    warning = validate(metrics)
    line = json.dumps(metrics, ensure_ascii=False)
    print(line)
    if warning:
        print(warning, file=sys.stderr)
    if args.dry_run:
        return

    with open(os.path.join(root, STATE_DIR, "metrics.jsonl"), "a") as fh:
        fh.write(line + "\n")
    marker = os.path.join(root, STATE_DIR, "active-run")
    try:
        with open(marker) as fh:
            parts = fh.read().split()
        if parts and parts[0] == args.run:
            os.remove(marker)
    except OSError:
        pass


if __name__ == "__main__":
    main()
