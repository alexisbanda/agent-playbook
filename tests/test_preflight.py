import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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

    def write_transcript(self, context_tokens):
        path = os.path.join(self.tmp, "session.jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "timestamp": "2026-10-20T10:00:00Z", "message": {
                "id": "m1", "usage": {"input_tokens": 1, "cache_read_input_tokens": context_tokens - 1}}}) + "\n")
        return path

    def test_merge_permission_looks_in_project_local_and_user_settings(self):
        home = tempfile.mkdtemp()
        try:
            out = preflight.check_merge_permission(cwd=self.tmp, home=home)
            self.assertEqual(out["status"], "warn")
            self.assertIn("No requiere decisión", out["detail"])
            os.makedirs(os.path.join(self.tmp, ".claude"), exist_ok=True)
            with open(os.path.join(self.tmp, ".claude", "settings.local.json"), "w") as fh:
                json.dump({"permissions": {"allow": [preflight.MERGE_RULE]}}, fh)
            self.assertEqual(preflight.check_merge_permission(cwd=self.tmp, home=home)["status"], "ok")
            os.remove(os.path.join(self.tmp, ".claude", "settings.local.json"))
            os.makedirs(os.path.join(home, ".claude"))
            with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
                json.dump({"permissions": {"allow": ["Bash(env -u GITHUB_TOKEN -u GH_TOKEN gh pr merge *)"]}}, fh)
            self.assertEqual(preflight.check_merge_permission(cwd=self.tmp, home=home)["status"], "ok")
        finally:
            shutil.rmtree(home)

    def test_context_check_warns_when_the_session_carries_a_previous_ticket(self):
        heavy = preflight.check_session_context(cwd=self.tmp, transcript=self.write_transcript(400000))
        self.assertEqual((heavy["status"], heavy["context_k"]), ("warn", 400))
        self.assertIn("/clear", heavy["detail"])
        light = preflight.check_session_context(cwd=self.tmp, transcript=self.write_transcript(40000))
        self.assertEqual(light["status"], "ok")

    def test_context_check_finds_the_session_transcript_in_the_events(self):
        transcript = self.write_transcript(400000)
        os.makedirs(os.path.join(self.tmp, ".agent-playbook"), exist_ok=True)
        with open(os.path.join(self.tmp, ".agent-playbook", "events.jsonl"), "w") as fh:
            fh.write(json.dumps({"event": "user_prompt", "session_id": "other", "transcript": "/nope.jsonl"}) + "\n")
            fh.write(json.dumps({"event": "user_prompt", "session_id": "mine", "transcript": transcript}) + "\n")
        self.assertEqual(preflight.session_transcript(self.tmp, "mine"), transcript)
        self.assertEqual(preflight.check_session_context(cwd=self.tmp, session_id="other")["status"], "ok")
        self.assertEqual(preflight.check_session_context(cwd=self.tmp, session_id="mine")["status"], "warn")

    def test_heavy_context_leaves_the_run_closed_unless_the_user_keeps_the_session(self):
        self.write_config()
        ok = lambda check_id: (lambda *a, **k: {"id": check_id, "status": "ok", "detail": ""})
        heavy = {"id": "context", "status": "warn", "context_k": 400, "detail": "pesado"}
        with mock.patch.object(preflight, "check_tools", ok("tools")), \
             mock.patch.object(preflight, "check_git_state", ok("git_state")), \
             mock.patch.object(preflight, "check_session_model", ok("session_model")), \
             mock.patch.object(preflight, "check_session_context", lambda **k: dict(heavy)):
            closed = preflight.run_preflight("opus", cwd=self.tmp, open_run="42", session_id="s",
                                             do_fetch=False, remote_version=False)
            self.assertIsNone(closed["checks"][5]["opened_run"])
            kept = preflight.run_preflight("opus", cwd=self.tmp, open_run="42", session_id="s",
                                           do_fetch=False, remote_version=False, keep_session=True)
            self.assertEqual(kept["checks"][5]["opened_run"], "42")

    def test_second_reviewer_check_omitted_when_disabled_and_warns_without_agy(self):
        self.write_config()
        self.assertIsNone(preflight.check_second_reviewer(cwd=self.tmp))

        ok = lambda check_id: (lambda *a, **k: {"id": check_id, "status": "ok", "detail": ""})
        with mock.patch.object(preflight, "check_tools", ok("tools")), \
             mock.patch.object(preflight, "check_git_state", ok("git_state")), \
             mock.patch.object(preflight, "check_session_model", ok("session_model")), \
             mock.patch.object(preflight, "check_session_context", ok("context")), \
             mock.patch.object(preflight, "check_merge_permission", ok("merge_permission")):
            disabled = preflight.run_preflight("opus", cwd=self.tmp, do_fetch=False, remote_version=False)
            self.assertNotIn("second_reviewer", [c["id"] for c in disabled["checks"]])

            self.write_config({
                "version": 1,
                "profile": "reduced",
                "tracker": {"type": "github"},
                "second_reviewer": {"enabled": True, "model": "gemini-4-argon"},
            })
            with mock.patch.object(preflight.shutil, "which", return_value="/usr/local/bin/agy"):
                found = preflight.run_preflight("opus", cwd=self.tmp, do_fetch=False, remote_version=False)
                sec_ok = [c for c in found["checks"] if c["id"] == "second_reviewer"][0]
                self.assertEqual(sec_ok["status"], "ok")
                self.assertIn("gemini-4-argon", sec_ok["detail"])
                self.assertIn("9. Segundo reviewer", found["markdown"])

            with mock.patch.object(preflight.shutil, "which", return_value=None):
                missing = preflight.run_preflight("opus", cwd=self.tmp, do_fetch=False, remote_version=False)
                self.assertTrue(missing["ok"])
                sec_warn = [c for c in missing["checks"] if c["id"] == "second_reviewer"][0]
                self.assertEqual(sec_warn["status"], "warn")
                self.assertEqual(
                    sec_warn["detail"],
                    "second_reviewer.enabled pero agy no está en el PATH: la corrida seguirá sin segundo reviewer",
                )


if __name__ == "__main__":
    unittest.main()
