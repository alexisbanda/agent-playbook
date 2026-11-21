# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
"""Shared helpers for the agent-playbook hooks.

Every hook is a no-op outside a repository that has .claude/agent-playbook.json,
because the plugin is installed per user and fires in every project.
Hooks fail open: an internal error is logged and never breaks the session.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import traceback

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))

CONFIG_RELS = (
    ".agent-playbook.json",
    os.path.join(".claude", "agent-playbook.json"),
)
STATE_DIR = ".agent-playbook"

# Where a command starts: line start, after ; & | ( or $(, optionally behind
# `env -u X ...`, VAR=value assignments or `command`. Matching only here keeps
# text that merely mentions a command (grep patterns, heredocs) from counting.
CMD_START = (
    r"(?:^|[;&|(\n]|\$\()\s*"
    r"(?:env\b(?:\s+(?:-u\s+\S+|-i|[A-Za-z_]\w*=\S*))*\s+)?"
    r"(?:[A-Za-z_]\w*=\S*\s+)*(?:command\s+)?"
)
# gh itself, a path to it, or a variable holding it ($GH, ${GH}).
GH_BIN = r"(?:\S*/)?(?:gh|\$\{?[A-Za-z_]\w*\}?)(?:\s+(?:-R|--repo)(?:\s+|=)\S+)?"
GIT_BIN = r"(?:\S*/)?(?:git|\$\{?[A-Za-z_]\w*\}?)(?:\s+-[Cc]\s+\S+)*"


def gh_pr(verb):
    return re.compile(CMD_START + GH_BIN + r"\s+pr\s+" + verb + r"\b", re.MULTILINE)


GIT_PUSH = re.compile(CMD_START + GIT_BIN + r"\s+push\b", re.MULTILINE)


def normalize_payload(data):
    """Protocol sniffing: normalizes Claude Code (snake_case) and Google Antigravity agy
    (camelCase) hook payloads into a single canonical dictionary."""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    is_agy = any(k in data for k in ("hookEventName", "toolName", "toolInput", "trajectoryId")) or (
        data.get("tool_name") in ("run_command", "invoke_subagent", "ask_question")
        or data.get("toolName") in ("run_command", "invoke_subagent", "ask_question")
    )
    out["_runtime"] = "agy" if is_agy else "claude"
    out.setdefault("session_id", data.get("sessionId") or data.get("trajectoryId") or data.get("conversationId"))
    out.setdefault("agent_id", data.get("agentId") or data.get("subagentId"))
    out.setdefault("hook_event_name", data.get("hookEventName"))
    out.setdefault("tool_name", data.get("toolName"))
    out.setdefault("tool_input", data.get("toolInput"))
    out.setdefault("tool_response", data.get("toolResponse"))
    out.setdefault("transcript_path", data.get("transcriptPath"))
    out.setdefault("agent_transcript_path", data.get("agentTranscriptPath"))
    out.setdefault("agent_type", data.get("agentType"))
    return out


def read_input():
    raw = sys.stdin.read()
    return normalize_payload(json.loads(raw)) if raw.strip() else {}


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
    for rel in CONFIG_RELS:
        try:
            with open(os.path.join(root, rel)) as fh:
                return root, json.load(fh)
        except (OSError, ValueError):
            continue
    return None, None


def mode(config):
    return (config.get("hooks") or {}).get("mode", "warn")


def read_marker(root):
    """Returns (run, owner_session) from .agent-playbook/active-run, or (None, None).

    The marker is "<run> <session id>"; the session part is optional.
    """
    try:
        with open(os.path.join(root, STATE_DIR, "active-run")) as fh:
            parts = fh.read().split()
    except OSError:
        return None, None
    if not parts:
        return None, None
    return parts[0], (parts[1] if len(parts) > 1 else None)


def active_run(root, session_id=None):
    """The open run, but only for the session that opened it (and its subagents).

    Other sessions working in the same repo are not part of the run.
    """
    run, owner = read_marker(root)
    if run and owner and session_id and owner != session_id:
        return None
    return run


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log_event(root, payload, event, **fields):
    record = {
        "ts": now(),
        "event": event,
        "session_id": payload.get("session_id"),
        "agent_id": payload.get("agent_id"),
        "run": active_run(root, payload.get("session_id")),
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
