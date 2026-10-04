import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOOKS = os.path.join(ROOT, "hooks")


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True)


class HookTestCase(unittest.TestCase):
    """A throwaway repo with the playbook configured, on branch main."""

    mode = "block"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "app")
        os.makedirs(os.path.join(self.repo, ".claude"))
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
        self.write_config()

    def tearDown(self):
        errors = os.path.join(self.repo, ".agent-playbook", "hook-errors.log")
        try:
            # Hooks fail open, so an internal error would otherwise pass silently.
            self.assertFalse(os.path.exists(errors), open(errors).read() if os.path.exists(errors) else "")
        finally:
            shutil.rmtree(self.tmp)

    def write_config(self, **hooks):
        config = {"version": 1, "profile": "reduced", "tracker": {"type": "github"}, "hooks": {"mode": self.mode, **hooks}}
        with open(os.path.join(self.repo, ".claude", "agent-playbook.json"), "w") as fh:
            json.dump(config, fh)

    def start_run(self, run="1"):
        os.makedirs(os.path.join(self.repo, ".agent-playbook"), exist_ok=True)
        with open(os.path.join(self.repo, ".agent-playbook", "active-run"), "w") as fh:
            fh.write(run)

    def hook(self, name, payload, cwd=None):
        payload = {"session_id": "s1", "cwd": cwd or self.repo, **payload}
        out = subprocess.run(
            [sys.executable, os.path.join(HOOKS, name)],
            input=json.dumps(payload), capture_output=True, text=True, cwd=cwd or self.repo,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout) if out.stdout.strip() else None

    def events(self):
        path = os.path.join(self.repo, ".agent-playbook", "events.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return [json.loads(line) for line in fh]

    def decision(self, output):
        return (output or {}).get("hookSpecificOutput", {}).get("permissionDecision")


class ModelGateTest(HookTestCase):
    def agent(self, prompt, model=None):
        tool_input = {"description": "x", "prompt": prompt, "subagent_type": "general-purpose"}
        if model:
            tool_input["model"] = model
        return self.hook("model_gate.py", {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": tool_input})

    def test_outside_a_run_only_logs(self):
        self.assertIsNone(self.agent("sin encabezado", "fable"))
        self.assertEqual(self.events()[-1]["event"], "subagent_launch")

    def test_injects_default_model_keeping_the_rest_of_the_input(self):
        self.start_run()
        out = self.agent("ROLE: reader · CLASS: reader\nlee el repo")
        updated = out["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["model"], "haiku")
        self.assertEqual(updated["subagent_type"], "general-purpose")
        self.assertNotIn("permissionDecision", out["hookSpecificOutput"])

    def test_blocks_forbidden_model(self):
        self.start_run()
        self.assertEqual(self.decision(self.agent("ROLE: coder · CLASS: critical", "sonnet")), "deny")
        self.assertEqual(self.events()[-1]["decision"], "block")

    def test_blocks_missing_header(self):
        self.start_run()
        self.assertEqual(self.decision(self.agent("haz algo", "sonnet")), "deny")

    def test_allows_valid_launch_silently(self):
        self.start_run()
        self.assertIsNone(self.agent("ROLE: coder · CLASS: standard", "sonnet"))

    def test_override_is_recorded(self):
        self.start_run()
        self.assertIsNone(self.agent("ROLE: reader · CLASS: reader\nOVERRIDE: monorepo enorme", "opus"))
        self.assertEqual(self.events()[-1]["override"], "monorepo enorme")

    def test_inactive_without_config(self):
        os.remove(os.path.join(self.repo, ".claude", "agent-playbook.json"))
        self.start_run()
        self.assertIsNone(self.agent("haz algo", "fable"))
        self.assertEqual(self.events(), [])


class ModelGateWarnTest(HookTestCase):
    mode = "warn"

    def test_warn_mode_lets_it_through_with_context(self):
        self.start_run()
        out = self.hook("model_gate.py", {
            "hook_event_name": "PreToolUse", "tool_name": "Agent",
            "tool_input": {"prompt": "ROLE: coder · CLASS: critical", "model": "sonnet"},
        })
        self.assertIsNone(self.decision(out))
        self.assertIn("AVISO", out["hookSpecificOutput"]["additionalContext"])


class SafetyGateTest(HookTestCase):
    def bash(self, command, cwd=None, **extra):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, **extra}
        return self.hook("safety_gate.py", payload, cwd=cwd)

    def test_blocks_push_to_main_explicit(self):
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.assertEqual(self.decision(self.bash("git push origin main")), "deny")
        self.assertEqual(self.decision(self.bash("git push origin HEAD:refs/heads/main")), "deny")

    def test_blocks_bare_push_while_on_main(self):
        self.assertEqual(self.decision(self.bash("git push")), "deny")

    def test_allows_push_of_feature_branch(self):
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.assertIsNone(self.bash("git push -u origin feat/x"))

    def test_blocks_force_push(self):
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.assertEqual(self.decision(self.bash("git push --force origin feat/x")), "deny")
        self.assertEqual(self.decision(self.bash("git push origin +feat/x")), "deny")

    def test_force_flag_elsewhere_is_not_a_force_push(self):
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.assertIsNone(self.bash("git push origin feat/x && rm -f tmp.txt"))

    def test_subagent_cannot_merge_or_promote(self):
        self.assertEqual(self.decision(self.bash("gh pr merge 3 --squash --match-head-commit abc", agent_id="a1")), "deny")
        self.assertEqual(self.decision(self.bash("gh pr ready 3", agent_id="a1")), "deny")

    def test_main_thread_merge_needs_match_head_commit(self):
        self.assertEqual(self.decision(self.bash("gh pr merge 3 --squash")), "deny")
        self.assertIsNone(self.bash("gh pr merge 3 --squash --match-head-commit abc123"))

    def test_rm_rf_only_inside_repo_or_worktrees(self):
        self.assertIsNone(self.bash("rm -rf vendor/cache"))
        self.assertIsNone(self.bash(f"rm -rf {self.repo}.worktrees/1-x"))
        self.assertEqual(self.decision(self.bash("rm -rf /tmp")), "deny")
        self.assertEqual(self.decision(self.bash("rm -rf ~")), "deny")
        self.assertEqual(self.decision(self.bash("rm -rf ../other")), "deny")
        self.assertIsNone(self.bash("rm -f ../other/file"))

    def test_rm_rf_relative_to_a_worktree(self):
        worktree = self.repo + ".worktrees/1-x"
        git(self.repo, "worktree", "add", "-q", "-b", "feat/1-x", worktree)
        self.assertIsNone(self.bash("rm -rf node_modules", cwd=worktree))
        self.assertEqual(self.decision(self.bash("rm -rf ../../app", cwd=worktree)), "deny")

    def test_production_patterns_from_config(self):
        self.write_config(production_patterns=[r"--env=production"])
        self.assertEqual(self.decision(self.bash("php artisan migrate --env=production")), "deny")

    def test_harmless_commands_pass(self):
        self.assertIsNone(self.bash("git status && ls -la"))


class SafetyGateWarnTest(HookTestCase):
    mode = "warn"

    def test_warn_mode_asks_the_human(self):
        out = self.hook("safety_gate.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
        self.assertEqual(self.decision(out), "ask")


class TelemetryTest(HookTestCase):
    def test_records_facts_without_contents(self):
        self.start_run("7")
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "secreto 123"})
        self.hook("telemetry.py", {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "gh pr create --draft --title x"}})
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["user_prompt", "pr_opened"])
        self.assertTrue(all(e["run"] == "7" for e in events))
        self.assertNotIn("secreto", json.dumps(events))

    def test_session_start_warns_about_missing_pins(self):
        out = self.hook("telemetry.py", {"hook_event_name": "SessionStart", "source": "startup"})
        self.assertIn("ANTHROPIC_DEFAULT_", out["hookSpecificOutput"]["additionalContext"])


class CloseRunTest(HookTestCase):
    def test_builds_a_valid_metrics_line_and_clears_the_marker(self):
        self.start_run("9")
        transcript = os.path.join(self.tmp, "t.jsonl")
        with open(transcript, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "timestamp": "2099-01-01T00:00:00Z", "message": {"id": "m1", "model": "claude-opus-5-5", "usage": {"input_tokens": 10, "output_tokens": 5}}}) + "\n")
        self.hook("telemetry.py", {"hook_event_name": "SessionStart", "source": "startup", "transcript_path": transcript})
        self.hook("telemetry.py", {"hook_event_name": "Stop"})
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "ok"})
        self.hook("telemetry.py", {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "gh pr merge 1 --match-head-commit a"}})
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "close_run.py"), "9", "--e2e-first-pass", "yes", "--root", self.repo],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        metrics = json.loads(out.stdout)
        self.assertEqual((metrics["prs_merged"], metrics["human_waits"], metrics["e2e_first_pass"]), (1, 1, "yes"))
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".agent-playbook", "active-run")))
        with open(os.path.join(self.repo, ".agent-playbook", "metrics.jsonl")) as fh:
            self.assertEqual(len(fh.readlines()), 1)


class TranscriptUsageTest(unittest.TestCase):
    def test_sums_usage_by_model_once_per_message(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import close_run
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            line = {"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5", "usage": {"input_tokens": 10, "output_tokens": 4, "cache_read_input_tokens": 100}}}
            fh.write(json.dumps(line) + "\n" + json.dumps(line) + "\n")
            fh.write(json.dumps({"type": "user", "message": {"content": "hola"}}) + "\n")
        try:
            usage = close_run.usage_from_transcript(fh.name)
        finally:
            os.remove(fh.name)
        self.assertEqual(dict(usage["claude-sonnet-5"]), {"input_tokens": 10, "output_tokens": 4, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0})


if __name__ == "__main__":
    unittest.main()
