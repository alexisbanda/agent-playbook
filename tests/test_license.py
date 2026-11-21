# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
"""Keeps the licensing documents and copyright notices in place.

Every code and prompt file the plugin ships must carry the copyright notice, and
the manifests must point at LICENSE. A new file without the notice fails CI.
"""
import glob
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTICE = "Copyright (c) 2026 Alexis Banda. Todos los derechos reservados."
LICENSE_FIELD = "SEE LICENSE IN LICENSE"
DOCUMENTS = ("LICENSE", "NOTICE", "THIRD_PARTY.md", "PRIVACY.md")
COVERED = (
    "hooks/*.py",
    "scripts/*.py",
    "tests/*.py",
    "skills/*/SKILL.md",
    "agents/*.md",
    "references/**/*.md",
    "routing/*.md",
    "docs/*.md",
)


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


class LicenseTest(unittest.TestCase):
    def test_documents_exist(self):
        for name in DOCUMENTS:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, name)), f"falta {name}")
        self.assertIn(NOTICE, read("LICENSE"))
        self.assertIn(NOTICE, read("NOTICE"))

    def test_manifests_point_at_license(self):
        for path in ("plugin.json", ".claude-plugin/plugin.json"):
            self.assertEqual(json.loads(read(path)).get("license"), LICENSE_FIELD, path)
        plugin = json.loads(read(".claude-plugin/plugin.json"))["name"]
        entry = [p for p in json.loads(read(".claude-plugin/marketplace.json"))["plugins"] if p["name"] == plugin]
        self.assertEqual(entry[0].get("license"), LICENSE_FIELD, "marketplace.json")

    def test_files_carry_notice(self):
        missing = []
        for pattern in COVERED:
            for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
                head = "".join(read(path).splitlines(keepends=True)[:12])
                if NOTICE not in head:
                    missing.append(os.path.relpath(path, ROOT))
        self.assertEqual(missing, [], "archivos sin aviso de copyright: " + ", ".join(sorted(missing)))


if __name__ == "__main__":
    unittest.main()
