#!/usr/bin/env python3
"""Closes a run: crosses the hook events with the transcripts and appends one
validated line to .agent-playbook/metrics.jsonl. Then removes the active-run marker.

Usage (from the main clone of the repo):
  close_run.py <run-id> [--e2e-first-pass yes|no|na] [--dry-run]

The metrics come from what the hooks measured, not from what the model reports.
The only declared field is e2e_first_pass, and it is labelled as such.
"""
import argparse
import collections
import datetime
import json
import os
import sys

STATE_DIR = ".agent-playbook"
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "metrics.schema.json")


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
    """Sums token usage by model from a Claude Code transcript (JSONL)."""
    totals = collections.defaultdict(lambda: collections.Counter())
    if not path or not os.path.exists(path):
        return totals
    seen = set()
    with open(path) as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") or {}
            usage = message.get("usage")
            if entry.get("type") != "assistant" or not usage:
                continue
            ts = parse_ts(entry.get("timestamp"))
            if (start and ts and ts < start) or (end and ts and ts > end):
                continue
            key = message.get("id") or entry.get("uuid")
            if key in seen:
                continue
            seen.add(key)
            counter = totals[message.get("model", "unknown")]
            for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                counter[field] += usage.get(field) or 0
    return totals


def merge_usage(target, source):
    for model, counter in source.items():
        target[model].update(counter)


def build_metrics(run, events, e2e_first_pass):
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
    transcripts = {
        e.get("transcript") for e in events
        if e["event"] == "session_start" and e.get("session_id") in sessions and e.get("transcript")
    }
    for path in transcripts:
        merge_usage(usage, usage_from_transcript(path, start, end))
    for path in {e.get("agent_transcript") for e in run_events if e.get("agent_transcript")}:
        merge_usage(usage, usage_from_transcript(path))

    return {
        "run": run,
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
        "prs_merged": counts["pr_merged"],
        "worktrees_created": counts["worktree_created"],
        "worktrees_removed": counts["worktree_removed"],
        "compactions": counts["compaction"],
        "gate_events": dict(gates),
        "overrides": overrides,
        "tokens_by_model": {model: dict(counter) for model, counter in usage.items()},
        "tokens_measured": bool(usage),
        "e2e_first_pass": e2e_first_pass,
        "e2e_first_pass_source": "declared",
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
    metrics = build_metrics(args.run, load_events(root), args.e2e_first_pass)
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
