#!/usr/bin/env python3
"""PreToolUse (Bash): stops irreversible or out-of-process actions.

Active in every repository that has the playbook configured, inside or outside a run.
Mode "block" denies, "warn" asks the human, "off" only records.
"""
import os
import re
import shlex
import subprocess

import common

# Deliberately broad (not anchored to command start): a false positive only asks
# or denies, a false negative lets the action through. Covers `git -C dir push`,
# and gh or git behind a variable ($GH, ${GIT}).
PUSH_RE = re.compile(r"(?:\bgit|\$\{?[A-Za-z_]\w*\}?)(?:\s+-[Cc]\s+\S+)*\s+push\b")
FORCE_RE = re.compile(r"(\s--force(-with-lease)?\b|\s-f\b|\s\+\S+)")
GH_RE = r"(?:\bgh|\$\{?[A-Za-z_]\w*\}?)(?:\s+(?:-R|--repo)(?:\s+|=)\S+)?\s+pr\s+"
MERGE_RE = re.compile(GH_RE + r"merge\b")
READY_RE = re.compile(GH_RE + r"ready\b(?![^;&|]*--undo)")
RM_RE = re.compile(r"\brm\s+([^;&|]*)")


def base_branches(root):
    names = {"main", "master"}
    try:
        head = subprocess.run(
            ["git", "-C", root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if head.returncode == 0:
            names.add(head.stdout.strip().split("/", 1)[-1])
    except (OSError, subprocess.SubprocessError):
        pass
    return names


def current_branch(cwd):
    out = subprocess.run(["git", "-C", cwd, "branch", "--show-current"], capture_output=True, text=True, timeout=5)
    return out.stdout.strip() if out.returncode == 0 else ""


def segments(command):
    return re.split(r"&&|\|\||;|\n", command)


def force_push(command):
    return any(PUSH_RE.search(s) and FORCE_RE.search(s) for s in segments(command))


def pushes_to_base(command, cwd, bases):
    for segment in segments(command):
        if not PUSH_RE.search(segment):
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if "push" not in words:
            continue
        at = words.index("push")
        where = cwd
        for i, word in enumerate(words[:at]):
            if word == "-C" and i + 1 < at:
                where = os.path.join(cwd, words[i + 1])
        args = [w for w in words[at + 1:] if not w.startswith("-")]
        targets = [ref.split(":")[-1].lstrip("+").replace("refs/heads/", "") for ref in args[1:]]
        if not targets and current_branch(where) in bases:
            return True
        if any(t in bases for t in targets):
            return True
    return False


def rm_outside(command, root, cwd):
    allowed = [os.path.realpath(root), os.path.realpath(root + ".worktrees")]
    for match in RM_RE.finditer(command):
        try:
            words = shlex.split(match.group(1))
        except ValueError:
            words = match.group(1).split()
        flags = "".join(w.lstrip("-") for w in words if w.startswith("-") and not w.startswith("--"))
        long_flags = {w for w in words if w.startswith("--")}
        recursive = "r" in flags.lower() or "--recursive" in long_flags
        force = "f" in flags or "--force" in long_flags
        if not (recursive and force):
            continue
        for path in (w for w in words if not w.startswith("-")):
            if path in ("/", "~", "*", ".", "..") or path.startswith("~"):
                return path
            full = os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path))
            # Strictly inside: deleting the repository or the worktrees folder itself is also outside.
            if not any(full.startswith(a + os.sep) for a in allowed):
                return path
    return None


def violations(command, payload, root, config):
    found = []
    cwd = payload.get("cwd") or root
    subagent = bool(payload.get("agent_id"))
    if force_push(command):
        found.append("push forzado")
    if pushes_to_base(command, cwd, base_branches(root)):
        found.append("push directo a la rama base (todo cambio entra por PR)")
    if MERGE_RE.search(command):
        if subagent:
            found.append("un subagente no puede mergear: solo el orquestador, con OK del usuario")
        elif "--match-head-commit" not in command:
            found.append("merge sin --match-head-commit (el merge debe atarse al commit revisado)")
    if READY_RE.search(command) and subagent:
        found.append("un subagente no puede promover un PR: lo hace el orquestador")
    path = rm_outside(command, root, cwd)
    if path:
        found.append(f"rm -rf fuera del repositorio y sus worktrees ({path})")
    for pattern in (config.get("hooks") or {}).get("production_patterns", []):
        if re.search(pattern, command):
            found.append(f"posible escritura en producción (patrón '{pattern}'): requiere confirmación explícita")
    return found


def main():
    payload = common.read_input()
    root, config = common.load_context(payload)
    if not root:
        common.emit(None)
    command = (payload.get("tool_input") or {}).get("command", "")
    found = violations(command, payload, root, config)
    if not found:
        common.emit(None)

    hook_mode = common.mode(config)
    common.log_event(root, payload, "safety_gate", mode=hook_mode, violations=found)
    reason = "Gate de seguridad del agent-playbook: " + "; ".join(found) + "."
    if hook_mode == "block":
        common.emit(common.pre_tool("deny", reason))
    if hook_mode == "warn":
        common.emit(common.pre_tool("ask", reason))
    common.emit(None)


if __name__ == "__main__":
    common.run_safely(main)
