#!/usr/bin/env python3
"""Telemetry for every hook event the plugin registers. Measures, never intervenes.

Writes one line per event to <repo>/.agent-playbook/events.jsonl. Prompt and
command contents are not stored: only the facts needed for the metrics.
"""
import os
import re

import common
import route

BASH_FACTS = [
    ("pr_opened", re.compile(r"\bgh\s+pr\s+create\b")),
    ("pr_promoted", re.compile(r"\bgh\s+pr\s+ready\b(?![^;&|]*--undo)")),
    ("pr_merged", re.compile(r"\bgh\s+pr\s+merge\b")),
    ("worktree_created", re.compile(r"\bgit\s+worktree\s+add\b")),
    ("worktree_removed", re.compile(r"\bgit\s+worktree\s+remove\b")),
]


def facts(payload):
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    if event == "SessionStart":
        return [("session_start", {"source": payload.get("source"), "transcript": payload.get("transcript_path")})]
    if event == "SessionEnd":
        return [("session_end", {"reason": payload.get("reason")})]
    if event == "UserPromptSubmit":
        return [("user_prompt", {"chars": len(payload.get("prompt") or "")})]
    if event == "Stop":
        return [("turn_end", {})]
    if event == "PreCompact":
        return [("compaction", {"trigger": payload.get("trigger")})]
    if event == "SubagentStart":
        return [("subagent_start", {"agent_type": payload.get("agent_type"), "subagent": payload.get("agent_id")})]
    if event == "SubagentStop":
        return [("subagent_stop", {
            "agent_type": payload.get("agent_type"),
            "subagent": payload.get("agent_id"),
            "agent_transcript": payload.get("agent_transcript_path"),
        })]
    if event == "PostToolUse" and tool == "Bash":
        command = (payload.get("tool_input") or {}).get("command", "")
        return [(name, {}) for name, pattern in BASH_FACTS if pattern.search(command)]
    if event == "PostToolUse" and tool in ("Agent", "Task"):
        tool_input = payload.get("tool_input") or {}
        role, klass, override = route.parse_header(tool_input.get("prompt", ""))
        return [("subagent_done", {"model": tool_input.get("model"), "role": role, "klass": klass, "override": override})]
    if event == "PostToolUse" and tool == "AskUserQuestion":
        return [("asked_human", {})]
    return []


def main():
    payload = common.read_input()
    root, config = common.load_context(payload)
    if not root:
        common.emit(None)

    for name, fields in facts(payload):
        common.log_event(root, payload, name, **fields)

    if payload.get("hook_event_name") == "SessionStart" and common.mode(config) != "off":
        missing = route.missing_pins(route.load_routing())
        if missing:
            common.emit({"hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "agent-playbook: los alias de modelo no están fijados a una versión exacta. "
                    f"Faltan en el entorno: {', '.join(missing)}. Ver routing/ROUTING.md."
                ),
            }})
    common.emit(None)


if __name__ == "__main__":
    common.run_safely(main)
