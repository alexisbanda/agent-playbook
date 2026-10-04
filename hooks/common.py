"""Shared helpers for the agent-playbook hooks.

Every hook is a no-op outside a repository that has .claude/agent-playbook.json,
because the plugin is installed per user and fires in every project.
Hooks fail open: an internal error is logged and never breaks the session.
"""
import datetime
import json
import os
import subprocess
import sys
import traceback

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))

CONFIG_REL = os.path.join(".claude", "agent-playbook.json")
STATE_DIR = ".agent-playbook"


def read_input():
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def project_root(cwd):
    """Main clone root: worktrees resolve to the repository that owns them."""
    try:
        common = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if common.returncode == 0:
            return os.path.dirname(common.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def load_context(payload):
    """Returns (root, config) or (None, None) when the playbook is not set up here."""
    cwd = payload.get("cwd") or os.getcwd()
    root = project_root(cwd)
    if not root:
        return None, None
    try:
        with open(os.path.join(root, CONFIG_REL)) as fh:
            return root, json.load(fh)
    except (OSError, ValueError):
        return None, None


def mode(config):
    return (config.get("hooks") or {}).get("mode", "warn")


def active_run(root):
    try:
        with open(os.path.join(root, STATE_DIR, "active-run")) as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log_event(root, payload, event, **fields):
    record = {
        "ts": now(),
        "event": event,
        "session_id": payload.get("session_id"),
        "agent_id": payload.get("agent_id"),
        "run": active_run(root),
    }
    record.update({k: v for k, v in fields.items() if v is not None})
    os.makedirs(os.path.join(root, STATE_DIR), exist_ok=True)
    with open(os.path.join(root, STATE_DIR, "events.jsonl"), "a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def emit(output):
    if output:
        print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


def pre_tool(decision=None, reason=None, updated_input=None, context=None):
    out = {"hookEventName": "PreToolUse"}
    if decision:
        out["permissionDecision"] = decision
    if reason:
        out["permissionDecisionReason"] = reason
    if updated_input is not None:
        out["updatedInput"] = updated_input
    if context:
        out["additionalContext"] = context
    return {"hookSpecificOutput": out}


def run_safely(main):
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        try:
            payload_root = project_root(os.getcwd()) or os.getcwd()
            os.makedirs(os.path.join(payload_root, STATE_DIR), exist_ok=True)
            with open(os.path.join(payload_root, STATE_DIR, "hook-errors.log"), "a") as fh:
                fh.write(f"{now()} {os.path.basename(sys.argv[0])}\n{traceback.format_exc()}\n")
        except OSError:
            pass
        sys.exit(0)
