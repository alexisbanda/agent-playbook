#!/usr/bin/env python3
# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
"""Checks that plugin.json and marketplace.json agree on the version and,
when a base ref is given, that the version was bumped against it.

Usage: check-version.py [BASE_REF]
"""
import json
import subprocess
import sys

PLUGIN = ".claude-plugin/plugin.json"
ROOT_PLUGIN = "plugin.json"
MARKETPLACE = ".claude-plugin/marketplace.json"


def parse(version):
    return tuple(int(part) for part in version.split("."))


def load(path, ref=None):
    if ref is None:
        with open(path) as fh:
            return json.load(fh)
    out = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


def main():
    plugin = load(PLUGIN)
    root_plugin = load(ROOT_PLUGIN)
    if root_plugin.get("version") != plugin["version"]:
        sys.exit(f"version mismatch: {PLUGIN} {plugin['version']} vs {ROOT_PLUGIN} {root_plugin.get('version')}")
    entries = [p for p in load(MARKETPLACE)["plugins"] if p["name"] == plugin["name"]]
    if len(entries) != 1:
        sys.exit(f"marketplace.json must list '{plugin['name']}' exactly once")
    if entries[0].get("version") != plugin["version"]:
        sys.exit(f"version mismatch: plugin.json {plugin['version']} vs marketplace.json {entries[0].get('version')}")

    if len(sys.argv) > 1:
        base = load(PLUGIN, sys.argv[1])
        if base is None:
            print(f"no {PLUGIN} on {sys.argv[1]}; skipping bump check")
        elif parse(plugin["version"]) <= parse(base["version"]):
            sys.exit(f"version not bumped: {base['version']} -> {plugin['version']}. Every merge must bump the version.")

    print(f"version ok: {plugin['version']}")


if __name__ == "__main__":
    main()
