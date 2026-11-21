# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import repo_map  # noqa: E402


class RepoMapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        subprocess.run(["git", "-C", self.tmp, "init", "-q", "-b", "main"], check=True)
        os.makedirs(os.path.join(self.tmp, "src", "api"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "tests"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "node_modules", "pkg"), exist_ok=True)
        with open(os.path.join(self.tmp, "package.json"), "w") as fh:
            fh.write("{}")
        with open(os.path.join(self.tmp, "README.md"), "w") as fh:
            fh.write("# App\n")
        with open(os.path.join(self.tmp, "src", "index.ts"), "w") as fh:
            fh.write("export const app = 1;\n")
        with open(os.path.join(self.tmp, "src", "api", "routes.ts"), "w") as fh:
            fh.write("export const routes = [];\n")
        with open(os.path.join(self.tmp, "tests", "app.test.ts"), "w") as fh:
            fh.write("test('ok', () => {});\n")
        with open(os.path.join(self.tmp, "node_modules", "pkg", "index.js"), "w") as fh:
            fh.write("module.exports = {};\n")
        subprocess.run(["git", "-C", self.tmp, "-c", "user.email=t@t", "-c", "user.name=t", "add", "."], check=True)
        subprocess.run(["git", "-C", self.tmp, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_scans_tree_and_ignores_node_modules(self):
        data = repo_map.scan_tree(self.tmp)
        self.assertTrue(data["head_sha"])
        self.assertIn("package.json", data["manifests"])
        self.assertIn("README.md", data["key_docs"])
        self.assertIn("src/index.ts", data["entrypoints"])
        paths = [d["path"] for d in data["directories"]]
        self.assertIn("src", paths)
        self.assertIn("src/api", paths)
        self.assertIn("tests", paths)
        self.assertNotIn("node_modules", paths)

    def test_cli_writes_markdown_file(self):
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "repo_map.py"), "--root", self.tmp],
            capture_output=True, text=True, check=True,
        )
        info = json.loads(out.stdout)
        self.assertTrue(info["ok"])
        map_path = os.path.join(self.tmp, ".agent-playbook", "repo-map.md")
        self.assertTrue(os.path.exists(map_path))
        with open(map_path) as fh:
            content = fh.read()
        self.assertIn("`src/index.ts`", content)
        self.assertIn("`src/api/`", content)


if __name__ == "__main__":
    unittest.main()
