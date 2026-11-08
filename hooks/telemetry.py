#!/usr/bin/env python3
"""Telemetry for every hook event the plugin registers. Measures, never intervenes.

Writes one line per event to <repo>/.agent-playbook/events.jsonl. Prompt and
command contents are not stored: only the facts needed for the metrics.
"""
import os
import re

import common
import route

# Anchored to where a command starts, so text that only mentions a command
# (a grep pattern, a heredoc, a brief) does not count.
PR_URL = re.compile(r"/pull/\d+")
BASH_FACTS = [
    ("pr_promoted", re.compile(common.gh_pr("ready").pattern + r"(?![^;&|\n]*--undo)", re.MULTILINE)),
    ("pr_merged", common.gh_pr("merge")),
    ("worktree_created", re.compile(common.CMD_START + common.GIT_BIN + r"\s+worktree\s+add\b", re.MULTILINE)),
    ("worktree_removed", re.compile(common.CMD_START + common.GIT_BIN + r"\s+worktree\s+remove\b", re.MULTILINE)),
]
PR_CREATE = common.gh_pr("create")


def bash_output(payload):
    response = payload.get("tool_response")
    if isinstance(response, dict):
        return f"{response.get('stdout', '')}\n{response.get('stderr', '')}\n{response.get('output', '')}"
    return str(response or "")


def facts(payload):
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    if event == "SessionStart":
        return [("session_start", {"source": payload.get("source"), "transcript": payload.get("transcript_path")})]
    if event == "SessionEnd":
        return [("session_end", {"reason": payload.get("reason")})]
    if event == "UserPromptSubmit":
        prompt = payload.get("prompt") or ""
        # A prompt that starts with a tag (<task-notification>, <system-reminder>...) is the
        # harness waking the session, not the human answering. Only the flag is stored.
        return [("user_prompt", {"chars": len(prompt), "automatic": prompt.lstrip().startswith("<") or None,
                                 "transcript": payload.get("transcript_path")})]
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
    if event == "PostToolUse" and tool in ("Bash", "run_command"):
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command") or tool_input.get("CommandLine") or ""
        found = [(name, {}) for name, pattern in BASH_FACTS if pattern.search(command)]
        # A PR counts as opened only if gh printed its URL.
        if PR_CREATE.search(command):
            url = PR_URL.search(bash_output(payload))
            if url:
                found.insert(0, ("pr_opened", {"pr": url.group(0).rsplit("/", 1)[-1]}))
        return found
    if event == "PostToolUse" and tool in ("Agent", "Task", "invoke_subagent"):
        tool_input = payload.get("tool_input") or {}
        if isinstance(tool_input.get("Subagents"), list):
            out = []
            for sub in tool_input["Subagents"]:
                role, klass, override = route.parse_header(sub.get("Prompt", ""))
                out.append(("subagent_launched", {"model": sub.get("Model"), "role": role, "klass": klass, "override": override}))
            return out
        role, klass, override = route.parse_header(tool_input.get("prompt", ""))
        # Agents run in the background: PostToolUse fires at launch, not at the end.
        return [("subagent_launched", {"model": tool_input.get("model"), "role": role, "klass": klass, "override": override})]
    if event == "PostToolUse" and tool in ("AskUserQuestion", "ask_question"):
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
