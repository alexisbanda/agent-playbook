#!/usr/bin/env python3
"""Consolidated preflight checker for agent-playbook runs.

Replaces 7-9 separate bash invocations at the start of `resolve-issue` with a
single deterministic command:
  1. Session model check (via route.py) + missing model pin check
  2. Playbook version check (cached for 24h in .agent-playbook/cache/version-check.json)
  3. Repo configuration (.claude/agent-playbook.json or .agent-playbook.json)
  4. Tools & permissions (`git remote`, `gh auth status` with stale token fallback)
  5. Main clone git state (`git fetch origin`, `git status --porcelain`, ahead/behind base)
  6. Hooks & active run (`.agent-playbook/hook-errors.log`, `.agent-playbook/active-run`,
     and optional `--open-run <ticket>` to start the run atomically)
  7. Session context: warns when the session already carries more context than
     the `orchestrator_ctx_start_k_max` tripwire (a previous ticket left in it)

Usage:
  preflight.py --session-model <model> [--override-model "<reason>"]
               [--open-run <ticket>] [--session-id <id>] [--keep-session]
               [--no-fetch] [--no-remote-version]

Prints a JSON object with `ok`, `checks`, `markdown` (ready for RUN_STATE.md),
and detected metadata (`profile`, `tracker_type`, `base_branch`, `origin_sha`,
`gh_env_prefix`). Exits 0 when no check failed, 1 when any check is `fail`.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, SCRIPT_DIR)
import close_run  # noqa: E402
import route  # noqa: E402

CONFIG_CANDIDATES = (
    ".agent-playbook.json",
    os.path.join(".claude", "agent-playbook.json"),
)
ALLOWED_SETUP_DIRTY = {
    ".agent-playbook.json",
    ".claude/agent-playbook.json",
    ".gitignore",
}
SUPPORTED_TRACKERS = ("github", "notion", "jira")
VERSION_CACHE_TTL_SECONDS = 86400  # 24 hours


def _ver_tuple(version_str):
    return tuple(int(p) if p.isdigit() else 0 for p in (version_str or "0").split("."))


def find_config_path(cwd="."):
    for rel in CONFIG_CANDIDATES:
        full = os.path.join(cwd, rel)
        if os.path.exists(full):
            return rel
    return os.path.join(".claude", "agent-playbook.json")


def check_session_model(session_model, profile="reduced", override_reason=None, routing=None, env=os.environ):
    routing = routing or route.load_routing()
    res = route.check_session(session_model or "", routing)
    pins = route.missing_pins(routing, env=env)
    notes = []
    status = "ok"
    if res["decision"] == "block":
        if override_reason:
            status = "warn"
            notes.append(f"override de modelo aplicado ({session_model}): {override_reason}")
        else:
            return {
                "id": "session_model",
                "status": "fail",
                "detail": f"{res['reason']}. Cambia el modelo de la sesión o pasa --override-model.",
                "tier": res["tier"],
                "missing_pins": pins,
            }
    else:
        notes.append(f"{session_model} ({res['tier']})")
    if profile == "full" and res["tier"] != "fable":
        status = "warn"
        notes.append("el perfil full recomienda fable para el orquestador")
    if pins:
        status = "warn"
        notes.append(f"alias sin fijar: {', '.join(pins)}")
    return {
        "id": "session_model",
        "status": status,
        "detail": " · ".join(notes),
        "tier": res["tier"],
        "missing_pins": pins,
    }


def check_version(cwd=".", plugin_root=PLUGIN_ROOT, remote_check=True, now=None, gh_prefix=()):
    now = time.time() if now is None else now
    manifest = os.path.join(plugin_root, ".claude-plugin", "plugin.json")
    try:
        with open(manifest) as fh:
            installed = json.load(fh).get("version", "0.0.0")
    except (OSError, ValueError):
        installed = "0.0.0"

    if not remote_check:
        return {"id": "version", "status": "ok", "installed": installed, "latest": installed,
                "detail": f"instalada {installed} (consulta remota omitida)"}

    cache_path = os.path.join(cwd, ".agent-playbook", "cache", "version-check.json")
    latest = None
    cached = False
    try:
        with open(cache_path) as fh:
            data = json.load(fh)
        if now - float(data.get("checked_at", 0)) < VERSION_CACHE_TTL_SECONDS and data.get("latest"):
            latest = data["latest"]
            cached = True
    except (OSError, ValueError, TypeError):
        pass

    if not latest:
        cmd = [*gh_prefix, "gh", "api", "repos/alexisbanda/agent-playbook/contents/.claude-plugin/plugin.json", "--jq", ".content"]
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if out.returncode == 0 and out.stdout.strip():
            try:
                raw = base64.b64decode(out.stdout.strip()).decode("utf-8")
                latest = json.loads(raw).get("version")
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w") as fh:
                    json.dump({"latest": latest, "checked_at": now}, fh)
            except Exception:
                latest = None

    if not latest:
        return {
            "id": "version",
            "status": "warn",
            "installed": installed,
            "latest": None,
            "detail": f"instalada {installed} (no se pudo consultar la versión remota; continúa)",
        }

    if _ver_tuple(installed) < _ver_tuple(latest):
        return {
            "id": "version",
            "status": "warn",
            "installed": installed,
            "latest": latest,
            "cached": cached,
            "detail": f"instalada {installed} < última {latest} (actualiza el plugin en Marketplaces)",
        }
    return {
        "id": "version",
        "status": "ok",
        "installed": installed,
        "latest": latest,
        "cached": cached,
        "detail": f"al día ({installed})",
    }


def check_config(cwd="."):
    rel_path = find_config_path(cwd)
    full_path = os.path.join(cwd, rel_path)
    if not os.path.exists(full_path):
        return {
            "id": "config",
            "status": "fail",
            "path": rel_path,
            "detail": f"No existe {rel_path}. Ejecuta primero el skill setup-project.",
            "config": {},
        }
    try:
        with open(full_path) as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        return {
            "id": "config",
            "status": "fail",
            "path": rel_path,
            "detail": f"{rel_path} no es un JSON válido: {exc}",
            "config": {},
        }

    version = cfg.get("version")
    profile = cfg.get("profile", "reduced")
    tracker_type = (cfg.get("tracker") or {}).get("type")
    if version != 1:
        return {"id": "config", "status": "fail", "path": rel_path, "config": cfg,
                "detail": f"{rel_path}: version debe ser 1 (encontrado: {version!r})."}
    if profile not in ("reduced", "full"):
        return {"id": "config", "status": "fail", "path": rel_path, "config": cfg,
                "detail": f"{rel_path}: profile inválido ({profile!r})."}
    if tracker_type not in SUPPORTED_TRACKERS:
        return {
            "id": "config",
            "status": "fail",
            "path": rel_path,
            "config": cfg,
            "detail": f"{rel_path}: tracker.type={tracker_type!r} no soportado (soportados: {', '.join(SUPPORTED_TRACKERS)}).",
        }
    return {
        "id": "config",
        "status": "ok",
        "path": rel_path,
        "config": cfg,
        "detail": f"{rel_path} válido (profile={profile}, tracker={tracker_type})",
    }


def check_tools(cwd=".", tracker_type="github"):
    remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=cwd)
    if remote.returncode != 0 or not remote.stdout.strip():
        return {"id": "tools", "status": "fail", "gh_env_prefix": "",
                "detail": "git remote 'origin' no está configurado."}

    gh = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, cwd=cwd)
    if gh.returncode == 0:
        return {"id": "tools", "status": "ok", "gh_env_prefix": "",
                "detail": f"gh auth OK · origin={remote.stdout.strip()}"}

    clean_env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
    gh_retry = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, cwd=cwd, env=clean_env)
    if gh_retry.returncode == 0:
        prefix = "env -u GITHUB_TOKEN -u GH_TOKEN"
        return {
            "id": "tools",
            "status": "warn",
            "gh_env_prefix": prefix,
            "detail": f"GITHUB_TOKEN/GH_TOKEN inválido en el entorno; antepón `{prefix}` a cada comando gh",
        }

    return {
        "id": "tools",
        "status": "fail",
        "gh_env_prefix": "",
        "detail": f"gh auth status falló: {(gh.stderr or gh.stdout).strip()}",
    }


def _detect_base_branch(cwd="."):
    sym = subprocess.run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], capture_output=True, text=True, cwd=cwd)
    if sym.returncode == 0 and sym.stdout.strip():
        return sym.stdout.strip().rsplit("/", 1)[-1]
    for candidate in ("main", "master"):
        chk = subprocess.run(["git", "rev-parse", "--verify", f"origin/{candidate}"], capture_output=True, text=True, cwd=cwd)
        if chk.returncode == 0:
            return candidate
    cur = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, cwd=cwd)
    return cur.stdout.strip() or "main"


def check_git_state(cwd=".", do_fetch=True):
    if do_fetch:
        fetch = subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True, cwd=cwd)
        if fetch.returncode != 0:
            return {
                "id": "git_state",
                "status": "fail",
                "base_branch": None,
                "origin_sha": None,
                "detail": f"git fetch origin falló: {(fetch.stderr or fetch.stdout).strip()}",
            }

    base = _detect_base_branch(cwd)
    sha_proc = subprocess.run(["git", "rev-parse", f"origin/{base}"], capture_output=True, text=True, cwd=cwd)
    origin_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None

    status_proc = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=cwd)
    dirty_lines = [line for line in status_proc.stdout.splitlines() if line.strip()]
    dirty_files = [line[3:].strip() for line in dirty_lines]

    warnings = []
    if dirty_files:
        if set(dirty_files).issubset(ALLOWED_SETUP_DIRTY):
            warnings.append(f"archivos de configuración sin versionar ({', '.join(dirty_files)})")
        else:
            warnings.append(f"clon principal con cambios sin commitear ({', '.join(dirty_files[:5])}); pregunta antes de tocar nada")

    ahead = subprocess.run(["git", "log", "--oneline", f"origin/{base}..{base}"], capture_output=True, text=True, cwd=cwd)
    behind = subprocess.run(["git", "log", "--oneline", f"{base}..origin/{base}"], capture_output=True, text=True, cwd=cwd)
    ahead_commits = [line for line in ahead.stdout.splitlines() if line.strip()] if ahead.returncode == 0 else []
    behind_commits = [line for line in behind.stdout.splitlines() if line.strip()] if behind.returncode == 0 else []

    if ahead_commits:
        warnings.append(f"{len(ahead_commits)} commit(s) locales en {base} sin push (no entrarán al worktree si no haces push)")
    if behind_commits:
        warnings.append(f"{base} local va {len(behind_commits)} commit(s) por detrás de origin/{base} (el worktree parte de origin/{base})")

    return {
        "id": "git_state",
        "status": "warn" if warnings else "ok",
        "base_branch": base,
        "origin_sha": origin_sha,
        "dirty_files": dirty_files,
        "ahead_commits": ahead_commits,
        "behind_commits": behind_commits,
        "detail": " · ".join(warnings) if warnings else f"clon limpio · base origin/{base} ({(origin_sha or '')[:7]})",
    }


def check_hooks_and_active_run(cwd=".", open_ticket=None, session_id=None, can_open=True):
    warnings = []
    hook_log = os.path.join(cwd, ".agent-playbook", "hook-errors.log")
    last_hook_error = None
    if os.path.exists(hook_log):
        try:
            with open(hook_log) as fh:
                lines = [line.strip() for line in fh if line.strip()]
            if lines:
                last_hook_error = lines[-1]
                warnings.append(f"hook-errors.log tiene entradas (última: {last_hook_error})")
        except OSError:
            pass

    active_path = os.path.join(cwd, ".agent-playbook", "active-run")
    existing_active = None
    if os.path.exists(active_path):
        try:
            with open(active_path) as fh:
                existing_active = fh.read().strip()
        except OSError:
            pass

    if existing_active:
        active_ticket = existing_active.split()[0]
        if not open_ticket or str(active_ticket) != str(open_ticket):
            warnings.append(f"active-run existente de otro ticket ({existing_active})")

    opened = False
    if open_ticket and can_open and (not existing_active or existing_active.split()[0] == str(open_ticket)):
        os.makedirs(os.path.dirname(active_path), exist_ok=True)
        sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("AGY_SESSION_ID") or "local"
        with open(active_path, "w") as fh:
            fh.write(f"{open_ticket} {sid}\n")
        opened = True

    detail_parts = warnings[:]
    if opened:
        detail_parts.append(f"active-run abierto para {open_ticket}")
    elif not detail_parts:
        detail_parts.append("hooks en orden · sin corrida previa abierta")

    return {
        "id": "hooks",
        "status": "warn" if warnings else "ok",
        "last_hook_error": last_hook_error,
        "existing_active_run": existing_active,
        "opened_run": str(open_ticket) if opened else None,
        "detail": " · ".join(detail_parts),
    }


def session_transcript(cwd=".", session_id=None):
    """Transcript of this session as the hooks recorded it; without an id, the most recent one."""
    path = os.path.join(cwd, ".agent-playbook", "events.jsonl")
    found = None
    try:
        with open(path) as fh:
            for line in fh:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("transcript") and (not session_id or event.get("session_id") == session_id):
                    found = event["transcript"]
    except OSError:
        return None
    return found


def check_session_context(cwd=".", session_id=None, transcript=None):
    try:
        with open(os.path.join(PLUGIN_ROOT, "metrics", "tripwires.json")) as fh:
            limit_k = json.load(fh)["tripwires"]["orchestrator_ctx_start_k_max"]["value"]
    except (OSError, ValueError, KeyError):
        limit_k = 150
    transcript = transcript or session_transcript(cwd, session_id)
    samples = close_run.context_samples(transcript)
    if not samples:
        return {"id": "context", "status": "ok", "context_k": None,
                "detail": "sesión nueva (sin llamadas previas medidas)"}
    context_k = round(max(samples)[1] / 1000)
    if context_k > limit_k:
        return {
            "id": "context",
            "status": "warn",
            "context_k": context_k,
            "detail": (f"la sesión ya lleva {context_k}k tokens de contexto (umbral {limit_k}k) y cada llamada los relee; "
                       "propón al usuario `/clear` o una sesión nueva y repetir el preflight allí "
                       "(o `--keep-session` si decide seguir en esta)"),
        }
    return {"id": "context", "status": "ok", "context_k": context_k,
            "detail": f"{context_k}k tokens de contexto (umbral {limit_k}k)"}


def format_markdown(checks):
    badge = {"ok": "OK", "warn": "AVISO", "fail": "FALLO"}
    labels = {
        "session_model": "1. Modelo de la sesión",
        "version": "2. Versión del playbook",
        "config": "3. Configuración del repo",
        "tools": "4. Herramientas y permisos",
        "git_state": "5. Estado del clon principal",
        "hooks": "6. Hooks y corrida activa",
        "context": "7. Contexto de la sesión",
    }
    return "\n".join(
        f"- {labels.get(c['id'], c['id'])}: **{badge[c['status']]}** — {c['detail']}"
        for c in checks
    )


def run_preflight(session_model, cwd=".", override_model=None, open_run=None, session_id=None,
                  do_fetch=True, remote_version=True, keep_session=False):
    cfg_check = check_config(cwd=cwd)
    cfg = cfg_check.get("config") or {}
    profile = cfg.get("profile", "reduced")
    tracker_type = (cfg.get("tracker") or {}).get("type", "github")

    model_check = check_session_model(session_model, profile=profile, override_reason=override_model)
    tools_check = check_tools(cwd=cwd, tracker_type=tracker_type)
    gh_prefix = tuple(tools_check.get("gh_env_prefix", "").split())
    version_check = check_version(cwd=cwd, remote_check=remote_version, gh_prefix=gh_prefix)
    git_check = check_git_state(cwd=cwd, do_fetch=do_fetch)

    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("AGY_SESSION_ID")
    context_check = check_session_context(cwd=cwd, session_id=sid)
    if keep_session and context_check["status"] == "warn":
        context_check["detail"] += " · el usuario decidió seguir en esta sesión"
    preliminary = [model_check, version_check, cfg_check, tools_check, git_check]
    # The run belongs to the session that opens it, and /clear starts another one:
    # with a heavy context, leave it closed until the user decides.
    can_open = not any(c["status"] == "fail" for c in preliminary) and (
        context_check["status"] == "ok" or keep_session)
    hooks_check = check_hooks_and_active_run(
        cwd=cwd, open_ticket=open_run, session_id=session_id, can_open=can_open
    )

    checks = [*preliminary, hooks_check, context_check]
    ok = not any(c["status"] == "fail" for c in checks)
    return {
        "ok": ok,
        "profile": profile,
        "config_path": cfg_check.get("path"),
        "tracker_type": tracker_type,
        "base_branch": git_check.get("base_branch"),
        "origin_sha": git_check.get("origin_sha"),
        "gh_env_prefix": tools_check.get("gh_env_prefix", ""),
        "checks": checks,
        "markdown": format_markdown(checks),
    }


def main():
    parser = argparse.ArgumentParser(description="Ejecuta todos los controles de preflight en una sola llamada.")
    parser.add_argument("--session-model", required=True, help="ID o alias del modelo de la sesión actual")
    parser.add_argument("--override-model", help="Motivo si el usuario autorizó otro modelo de sesión")
    parser.add_argument("--open-run", help="Abre .agent-playbook/active-run para este ticket si el preflight pasa")
    parser.add_argument("--session-id", help="ID de la sesión (por defecto CLAUDE_CODE_SESSION_ID)")
    parser.add_argument("--keep-session", action="store_true",
                        help="Abre la corrida aunque la sesión ya traiga mucho contexto (el usuario lo decidió)")
    parser.add_argument("--no-fetch", action="store_true", help="Omitir git fetch origin")
    parser.add_argument("--no-remote-version", action="store_true", help="Omitir consulta remota de versión")
    args = parser.parse_args()

    result = run_preflight(
        session_model=args.session_model,
        override_model=args.override_model,
        open_run=args.open_run,
        session_id=args.session_id,
        do_fetch=not args.no_fetch,
        remote_version=not args.no_remote_version,
        keep_session=args.keep_session,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
