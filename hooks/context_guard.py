#!/usr/bin/env python3
# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
"""PostToolUse inside a coder (or patriot): warns when its context grows too large.

Every call of an agent re-reads its whole context, so a coder that reaches
300-400k tokens pays that on each of its last hundred calls. Past the limit
(`hooks.coder_ctx_handback_k`, 150k by default) or past `CALLS_LIMIT` calls,
the hook tells the agent to commit, leave HANDBACK.md and end its turn, so that
a fresh coder resumes from the handback. It warns again every further
`STEP_K` thousand tokens. It never blocks a tool call.

Only active during a run, in Claude Code, for subagents whose prompt starts
with ROLE: coder or ROLE: patriot.
"""
import json
import os

import common
import route

DEFAULT_LIMIT_K = 150
CALLS_LIMIT = 80
STEP_K = 50
WRITER_ROLES = ("coder", "patriot")


def agent_transcript(payload):
    """The subagent's own transcript: given by the payload or next to the session's
    (<dir>/<session>.jsonl -> <dir>/<session>/subagents/agent-<id>.jsonl)."""
    path = payload.get("agent_transcript_path")
    if path:
        return path
    session = payload.get("transcript_path")
    agent = payload.get("agent_id")
    if not session or not agent:
        return None
    base = session[:-len(".jsonl")] if session.endswith(".jsonl") else session
    return os.path.join(base, "subagents", f"agent-{agent}.jsonl")


def read_agent(path):
    """(role, context tokens of the last call, number of calls) of a subagent transcript."""
    role, last_ctx, calls = None, 0, set()
    with open(path) as fh:
        for line in fh:
            if role is None and '"user"' in line:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") == "user":
                    content = (entry.get("message") or {}).get("content")
                    if isinstance(content, list):
                        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    role = route.parse_header(content or "")[0] or ""
                continue
            if '"assistant"' not in line or '"usage"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") or {}
            usage = message.get("usage")
            if entry.get("type") != "assistant" or not usage:
                continue
            calls.add(message.get("id") or entry.get("uuid"))
            last_ctx = sum(usage.get(f) or 0 for f in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return role, last_ctx, len(calls)


def level(ctx_k, calls, limit_k):
    """0 below the limits; then 1, 2, 3... one more per STEP_K thousand tokens past the limit."""
    if ctx_k < limit_k and calls < CALLS_LIMIT:
        return 0
    return 1 + max(0, int((ctx_k - limit_k) // STEP_K))


def main():
    payload = common.read_input()
    if payload.get("_runtime") != "claude" or not payload.get("agent_id"):
        common.emit(None)
    root, config = common.load_context(payload)
    if not root or common.mode(config) == "off" or not common.active_run(root, payload.get("session_id")):
        common.emit(None)

    path = agent_transcript(payload)
    if not path or not os.path.exists(path):
        common.emit(None)
    role, ctx, calls = read_agent(path)
    if role not in WRITER_ROLES:
        common.emit(None)

    limit_k = (config.get("hooks") or {}).get("coder_ctx_handback_k", DEFAULT_LIMIT_K)
    ctx_k = round(ctx / 1000)
    current = level(ctx_k, calls, limit_k)
    if not current:
        common.emit(None)

    state_dir = os.path.join(root, common.STATE_DIR, "cache")
    state = os.path.join(state_dir, f"context-guard-{payload['agent_id']}")
    try:
        with open(state) as fh:
            warned = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        warned = 0
    if current <= warned:
        common.emit(None)
    os.makedirs(state_dir, exist_ok=True)
    with open(state, "w") as fh:
        fh.write(str(current))

    common.log_event(root, payload, "context_guard", role=role, ctx_k=ctx_k, calls=calls, limit_k=limit_k)
    common.emit({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            f"agent-playbook: llevas {ctx_k}k tokens de contexto y {calls} llamadas "
            f"(límite {limit_k}k o {CALLS_LIMIT} llamadas). Cada llamada relee todo tu contexto. "
            "Termina el paso en curso, commitea lo que esté en verde, deja HANDBACK.md en el worktree "
            "(hecho, falta, comando de tests, archivos y líneas clave, fallas vistas) y termina tu turno: "
            "un coder nuevo seguirá desde ahí. No abras el PR si aún faltan criterios."
        ),
    }})


if __name__ == "__main__":
    common.run_safely(main)
