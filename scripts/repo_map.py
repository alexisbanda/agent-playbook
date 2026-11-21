#!/usr/bin/env python3
# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
"""Generates a persistent, compact repository architecture map (.agent-playbook/repo-map.md).

Saves reader subagents from re-exploring the repository cold on every ticket in
medium/large projects. Standard library only.

Usage:
  repo_map.py [--root .] [--output .agent-playbook/repo-map.md] [--max-depth 3] [--json]
"""
import argparse
import json
import os
import subprocess
import sys

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".claude", ".agent-playbook", ".gemini", ".idea", ".vscode",
    "node_modules", "vendor", "dist", "build", "target", "coverage", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", ".nuxt", ".venv", "venv", "env",
}

MANIFESTS = (
    "package.json", "composer.json", "pyproject.toml", "requirements.txt",
    "Cargo.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle", "Makefile",
    "docker-compose.yml", "compose.yaml", "Dockerfile",
)

KEY_DOCS = (
    "README.md", "CLAUDE.md", "AGENTS.md",
    "docs/product/BRIEF.md", "docs/product/TECH.md",
    ".agent-playbook.json", ".claude/agent-playbook.json", ".ticket-studio.json",
)


def git_head(root):
    out = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def scan_tree(root, max_depth=3):
    """Returns a compact directory summary with file counts and primary extensions."""
    directories = []
    entrypoints = []

    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not d.endswith(".worktrees"))
        rel = os.path.relpath(current, root)
        depth = 0 if rel == "." else len(rel.split(os.sep))
        if depth > max_depth:
            dirs[:] = []
            continue

        visible_files = sorted(f for f in files if not f.startswith(".") or f in (".agent-playbook.json", ".ticket-studio.json"))
        for f in visible_files:
            rel_file = f if rel == "." else os.path.join(rel, f)
            if f in ("main.py", "app.py", "index.ts", "index.js", "server.ts", "server.js", "main.go", "main.rs", "artisan", "manage.py"):
                entrypoints.append(rel_file)

        if rel != ".":
            exts = {}
            for f in visible_files:
                _, ext = os.path.splitext(f)
                if ext:
                    exts[ext] = exts.get(ext, 0) + 1
            top_exts = ", ".join(f"{ext} ({cnt})" for ext, cnt in sorted(exts.items(), key=lambda x: (-x[1], x[0]))[:3])
            directories.append({
                "path": rel.replace(os.sep, "/"),
                "files": len(visible_files),
                "subdirs": len(dirs),
                "extensions": top_exts,
            })

    return {
        "head_sha": git_head(root),
        "manifests": [m for m in MANIFESTS if os.path.exists(os.path.join(root, m))],
        "key_docs": [d for d in KEY_DOCS if os.path.exists(os.path.join(root, d))],
        "entrypoints": sorted(entrypoints),
        "directories": directories,
    }


def render_markdown(data):
    lines = [
        "# Mapa del repositorio (`repo-map.md`)",
        "",
        f"- **HEAD SHA:** `{data.get('head_sha') or 'sin commits'}`",
        f"- **Manifiestos detectados:** {', '.join(f'`{m}`' for m in data['manifests']) or 'ninguno'}",
        f"- **Documentos clave:** {', '.join(f'`{d}`' for d in data['key_docs']) or 'ninguno'}",
        f"- **Entrypoints:** {', '.join(f'`{e}`' for e in data['entrypoints']) or 'ninguno'}",
        "",
        "## Estructura de directorios",
        "",
        "| Directorio | Archivos | Subdirectorios | Extensiones principales |",
        "| --- | --- | --- | --- |",
    ]
    if data["directories"]:
        for d in data["directories"]:
            lines.append(f"| `{d['path']}/` | {d['files']} | {d['subdirs']} | {d['extensions'] or '—'} |")
    else:
        lines.append("| `.` | 0 | 0 | — |")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Genera .agent-playbook/repo-map.md")
    parser.add_argument("--root", default=".", help="Raíz del repositorio")
    parser.add_argument("--output", help="Ruta del archivo de salida (por defecto <root>/.agent-playbook/repo-map.md)")
    parser.add_argument("--max-depth", type=int, default=3, help="Profundidad máxima de directorios")
    parser.add_argument("--json", action="store_true", help="Imprime el mapa en JSON en lugar de escribir Markdown")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    data = scan_tree(root, max_depth=args.max_depth)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    out_path = args.output or os.path.join(root, ".agent-playbook", "repo-map.md")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    md = render_markdown(data)
    with open(out_path, "w") as fh:
        fh.write(md)
    print(json.dumps({"ok": True, "output": out_path, "head_sha": data["head_sha"], "directories": len(data["directories"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
