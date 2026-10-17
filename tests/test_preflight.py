import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import preflight  # noqa: E402


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-b", "main"], cwd=self.tmp, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=self.tmp, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Dev"], cwd=self.tmp, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/o/r.git"], cwd=self.tmp, capture_output=True, check=True)
        with open(os.path.join(self.tmp, "README.md"), "w") as fh:
            fh.write("# repo\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.tmp, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.tmp, capture_output=True, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_config(self, cfg=None, rel_path=os.path.join(".claude", "agent-playbook.json")):
        full = os.path.join(self.tmp, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            json.dump(cfg or {"version": 1, "profile": "reduced", "tracker": {"type": "github"}}, fh)

    def test_session_model_blocks_haiku_unless_overridden(self):
        blocked = preflight.check_session_model("haiku")
        self.assertEqual(blocked["status"], "fail")
        overridden = preflight.check_session_model("haiku", override_reason="prueba rápida")
        self.assertEqual(overridden["status"], "warn")
        self.assertIn("override", overridden["detail"])

    def test_version_check_uses_24h_cache_and_warns_when_outdated(self):
        cache_dir = os.path.join(self.tmp, ".agent-playbook", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "version-check.json"), "w") as fh:
            json.dump({"latest": "99.0.0", "checked_at": 1000.0}, fh)
        res = preflight.check_version(cwd=self.tmp, remote_check=True, now=1500.0)
        self.assertEqual(res["status"], "warn")
        self.assertTrue(res["cached"])
        self.assertEqual(res["latest"], "99.0.0")

    def test_config_check_supports_both_root_and_claude_paths(self):
        missing = preflight.check_config(cwd=self.tmp)
        self.assertEqual(missing["status"], "fail")
        self.write_config(rel_path=".agent-playbook.json")
        ok = preflight.check_config(cwd=self.tmp)
        self.assertEqual(ok["status"], "ok")
        self.assertEqual(ok["path"], ".agent-playbook.json")

    def test_hooks_check_opens_active_run_and_warns_on_other_ticket_or_hook_errors(self):
        res = preflight.check_hooks_and_active_run(cwd=self.tmp, open_ticket="42", session_id="sess-1", can_open=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["opened_run"], "42")
        with open(os.path.join(self.tmp, ".agent-playbook", "active-run")) as fh:
            self.assertEqual(fh.read().strip(), "42 sess-1")

        # Another ticket finds existing active-run and warns without overwriting
        other = preflight.check_hooks_and_active_run(cwd=self.tmp, open_ticket="99", session_id="sess-2", can_open=True)
        self.assertEqual(other["status"], "warn")
        self.assertIsNone(other["opened_run"])
        self.assertIn("42 sess-1", other["detail"])

        # Hook errors log triggers warning
        with open(os.path.join(self.tmp, ".agent-playbook", "hook-errors.log"), "w") as fh:
            fh.write("2026-10-17 model_gate timeout\n")
        with_err = preflight.check_hooks_and_active_run(cwd=self.tmp, open_ticket="42", session_id="sess-1", can_open=True)
        self.assertEqual(with_err["status"], "warn")
        self.assertIn("model_gate timeout", with_err["detail"])


if __name__ == "__main__":
    unittest.main()
