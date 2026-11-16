import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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

    def start_run(self, run="1", session="s1"):
        os.makedirs(os.path.join(self.repo, ".agent-playbook"), exist_ok=True)
        with open(os.path.join(self.repo, ".agent-playbook", "active-run"), "w") as fh:
            fh.write(f"{run} {session}\n" if session else run)

    def hook(self, name, payload, cwd=None):
        payload = {"session_id": "s1", "cwd": cwd or self.repo, **payload}
        # Hermetic: the developer's own pinned model aliases must not leak in.
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_DEFAULT_")}
        out = subprocess.run(
            [sys.executable, os.path.join(HOOKS, name)],
            input=json.dumps(payload), capture_output=True, text=True, cwd=cwd or self.repo, env=env,
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

    def test_gate_ignores_sessions_that_do_not_own_the_run(self):
        self.start_run(session="owner")
        self.assertIsNone(self.hook("model_gate.py", {
            "hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "observer",
            "tool_input": {"prompt": "sin encabezado", "model": "fable"},
        }))

    def test_subagents_of_the_owner_session_are_gated(self):
        self.start_run(session="owner")
        out = self.hook("model_gate.py", {
            "hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "owner", "agent_id": "a1",
            "tool_input": {"prompt": "sin encabezado", "model": "sonnet"},
        })
        self.assertEqual(self.decision(out), "deny")

    def test_legacy_marker_without_session_still_gates(self):
        self.start_run(session=None)
        self.assertEqual(self.decision(self.agent("sin encabezado", "sonnet")), "deny")

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

    def test_commands_behind_variables_or_git_dash_c_are_caught(self):
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.assertEqual(self.decision(self.bash('$GH pr merge 4 -R o/r --squash')), "deny")
        self.assertEqual(self.decision(self.bash('${GH} pr ready 4', agent_id="a1")), "deny")
        self.assertEqual(self.decision(self.bash("env -u GITHUB_TOKEN gh pr merge 4")), "deny")
        self.assertEqual(self.decision(self.bash("git -C . push origin main")), "deny")
        self.assertEqual(self.decision(self.bash("$GIT push --force origin feat/x")), "deny")

    def test_bare_push_with_dash_c_uses_that_checkout(self):
        worktree = self.repo + ".worktrees/1-x"
        git(self.repo, "worktree", "add", "-q", "-b", "feat/1-x", worktree)
        self.assertIsNone(self.bash(f"git -C {worktree} push"))
        self.assertEqual(self.decision(self.bash(f"git -C {self.repo} push", cwd=worktree)), "deny")

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
        self.hook("telemetry.py", {
            "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": "gh pr create --draft --title x"},
            "tool_response": {"stdout": "https://github.com/o/r/pull/12\n", "stderr": ""},
        })
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["user_prompt", "pr_opened"])
        self.assertEqual(events[-1]["pr"], "12")
        self.assertTrue(all(e["run"] == "7" for e in events))
        self.assertNotIn("secreto", json.dumps(events))

    def bash_done(self, command, stdout="", session="s1"):
        self.hook("telemetry.py", {
            "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": session,
            "tool_input": {"command": command}, "tool_response": {"stdout": stdout, "stderr": ""},
        })

    def test_pr_opened_needs_the_pr_url_in_the_output(self):
        self.bash_done("gh pr create --draft --title x", stdout="pull request create failed")
        self.assertEqual(self.events(), [])

    def test_mentions_of_a_command_do_not_count(self):
        self.bash_done("grep -c 'gh pr merge' notes.md; echo 'git worktree add x'", stdout="https://github.com/o/r/pull/3")
        self.bash_done("cat > brief.md <<'EOF'\nNunca uses gh pr ready ni gh pr merge\nEOF")
        self.assertEqual(self.events(), [])

    def test_gh_behind_a_variable_or_env_prefix_counts(self):
        self.bash_done('GH="env -u GITHUB_TOKEN gh"; $GH pr ready 4 -R o/r')
        self.bash_done("env -u GITHUB_TOKEN -u GH_TOKEN gh pr merge 4 --squash --match-head-commit abc")
        self.bash_done("cd ../wt && git worktree remove ../wt")
        self.assertEqual([e["event"] for e in self.events()], ["pr_promoted", "pr_merged", "worktree_removed"])

    def test_ready_undo_is_not_a_promotion(self):
        self.bash_done("gh pr ready 4 --undo")
        self.assertEqual(self.events(), [])

    def test_other_sessions_are_not_part_of_the_run(self):
        self.start_run("5", session="owner")
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "x", "session_id": "owner"})
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "x", "session_id": "observer"})
        self.assertEqual([e["run"] for e in self.events()], ["5", None])

    def test_session_start_warns_about_missing_pins(self):
        out = self.hook("telemetry.py", {"hook_event_name": "SessionStart", "source": "startup"})
        self.assertIn("ANTHROPIC_DEFAULT_", out["hookSpecificOutput"]["additionalContext"])


class ContextGuardTest(HookTestCase):
    def write_agent(self, role, calls, ctx, agent="c1"):
        session = os.path.join(self.tmp, "s1")
        os.makedirs(os.path.join(session, "subagents"), exist_ok=True)
        path = os.path.join(session, "subagents", f"agent-{agent}.jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": f"ROLE: {role} · CLASS: standard\nbrief"}}) + "\n")
            for i in range(calls):
                usage = {"input_tokens": 1, "cache_read_input_tokens": ctx * (i + 1) // calls, "cache_creation_input_tokens": 0, "output_tokens": 5}
                fh.write(json.dumps({"type": "assistant", "message": {"id": f"m{i}", "model": "claude-sonnet-5", "usage": usage}}) + "\n")
        return session + ".jsonl"

    def guard(self, transcript, agent="c1"):
        return self.hook("context_guard.py", {"hook_event_name": "PostToolUse", "tool_name": "Bash", "agent_id": agent,
                                              "transcript_path": transcript, "tool_input": {"command": "ls"}})

    def test_warns_a_coder_past_the_limit_once_per_step(self):
        self.start_run()
        transcript = self.write_agent("coder", 20, 160_000)
        out = self.guard(transcript)
        self.assertIn("HANDBACK.md", out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.guard(transcript))  # same level: no repeated warning
        self.write_agent("coder", 21, 215_000)
        self.assertIsNotNone(self.guard(transcript))  # 50k further: warns again
        self.assertEqual([e["ctx_k"] for e in self.events() if e["event"] == "context_guard"], [160, 215])

    def test_warns_on_too_many_calls(self):
        self.start_run()
        self.assertIsNotNone(self.guard(self.write_agent("coder", 85, 90_000)))

    def test_silent_below_limits_for_other_roles_and_outside_a_run(self):
        transcript = self.write_agent("coder", 20, 300_000)
        self.assertIsNone(self.guard(transcript))  # no run open
        self.start_run()
        self.assertIsNone(self.guard(self.write_agent("reader", 90, 300_000, agent="r1"), agent="r1"))
        self.assertIsNone(self.guard(self.write_agent("coder", 10, 100_000, agent="c2"), agent="c2"))
        self.assertIsNone(self.hook("context_guard.py", {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                                         "transcript_path": transcript}))  # main thread

    def test_limit_comes_from_the_config(self):
        self.write_config(coder_ctx_handback_k=300)
        self.start_run()
        self.assertIsNone(self.guard(self.write_agent("coder", 20, 250_000)))


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


    def test_counts_the_orchestrator_without_a_session_start(self):
        # The session started before the repo's hooks saw it: its transcript is found next to its subagents'.
        self.start_run("13", "sid")
        session_dir = os.path.join(self.tmp, "sid")
        os.makedirs(os.path.join(session_dir, "subagents"))
        def assistant(model, ts, out):
            return json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": f"{model}{ts}", "model": model, "usage": {"input_tokens": 1, "output_tokens": out}}}) + "\n"
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "ok", "session_id": "sid"})
        time.sleep(1.1)
        inside = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(session_dir + ".jsonl", "w") as fh:
            fh.write(assistant("claude-opus-5-5", "2000-01-01T00:00:00Z", 999))  # before the run: not counted
            fh.write(assistant("claude-opus-5-5", inside, 7))
        agent = os.path.join(session_dir, "subagents", "agent-x.jsonl")
        with open(agent, "w") as fh:
            fh.write(assistant("claude-sonnet-5", inside, 30))
        time.sleep(1.1)
        self.hook("telemetry.py", {"hook_event_name": "SubagentStop", "agent_id": "x", "agent_type": "general-purpose",
                                   "agent_transcript_path": agent, "session_id": "sid"})
        self.hook("telemetry.py", {"hook_event_name": "Stop", "session_id": "sid"})
        metrics = self.close_with_fake_gh("13", 'import sys\nsys.exit(1)\n')
        self.assertEqual(metrics["tokens_by_model"]["claude-opus-5-5"]["output_tokens"], 7)
        self.assertEqual(metrics["tokens_by_model"]["claude-sonnet-5"]["output_tokens"], 30)
        self.assertEqual(metrics["orchestrator_ctx_start_k"], 0.0)  # the call before the run is not its start
        self.assertEqual(metrics["orchestrator_model"], "claude-opus-5-5")

    def test_measures_the_longest_coder(self):
        self.start_run("14", "sid")
        session_dir = os.path.join(self.tmp, "sid")
        os.makedirs(os.path.join(session_dir, "subagents"))
        def agent(name, role, ctxs):
            path = os.path.join(session_dir, "subagents", f"agent-{name}.jsonl")
            with open(path, "w") as fh:
                fh.write(json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": f"ROLE: {role} · CLASS: standard"}]}}) + "\n")
                for i, ctx in enumerate(ctxs):
                    fh.write(json.dumps({"type": "assistant", "message": {"id": f"{name}{i}", "model": "claude-sonnet-5",
                                         "usage": {"input_tokens": 0, "cache_read_input_tokens": ctx, "output_tokens": 1}}}) + "\n")
            self.hook("telemetry.py", {"hook_event_name": "SubagentStop", "agent_id": name, "agent_transcript_path": path, "session_id": "sid"})
        agent("r", "reader", [10_000] * 50)  # readers do not count
        agent("a", "coder", [40_000, 120_000, 90_000])
        agent("b", "coder", [40_000, 60_000, 70_000, 80_000])
        self.hook("telemetry.py", {"hook_event_name": "Stop", "session_id": "sid"})
        metrics = self.close_with_fake_gh("14", 'import sys\nsys.exit(1)\n')
        self.assertEqual((metrics["coder_calls_max"], metrics["coder_ctx_peak_k"], metrics["context_guard_warnings"]), (4, 120.0, 0))

    def test_separates_human_stops_absences_and_automatic_wakeups(self):
        self.start_run("15", "sid")
        events = os.path.join(self.repo, ".agent-playbook", "events.jsonl")
        def ev(ts, event, **kw):
            with open(events, "a") as fh:
                fh.write(json.dumps({"ts": ts, "event": event, "session_id": "sid", "agent_id": None, "run": "15", **kw}) + "\n")
        ev("2026-11-01T10:00:00+00:00", "turn_end")
        ev("2026-11-01T10:05:00+00:00", "user_prompt", chars=5)                 # 5 min: a stop
        ev("2026-11-01T10:10:00+00:00", "turn_end")
        ev("2026-11-01T10:20:00+00:00", "user_prompt", chars=300, automatic=True)  # task notification
        ev("2026-11-01T10:30:00+00:00", "turn_end")
        ev("2026-11-01T12:30:00+00:00", "user_prompt", chars=8)                 # 120 min: away
        metrics = self.close_with_fake_gh("15", 'import sys\nsys.exit(1)\n')
        self.assertEqual((metrics["human_waits"], metrics["human_stops"]), (3, 2))
        self.assertEqual((metrics["human_wait_active_minutes"], metrics["human_absence_minutes"]), (5.0, 120.0))
        self.assertEqual(metrics["human_wait_minutes"], 135.0)  # unchanged meaning: every wait

    def test_marks_prompts_injected_by_the_harness(self):
        self.start_run("16")
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "<task-notification>done</task-notification>"})
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "ok"})
        prompts = [e for e in self.events() if e["event"] == "user_prompt"]
        self.assertEqual([e.get("automatic") for e in prompts], [True, None])

    def close_with_fake_gh(self, run, gh_script):
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        gh = os.path.join(bin_dir, "gh")
        with open(gh, "w") as fh:
            fh.write(f"#!{sys.executable}\n{gh_script}")
        os.chmod(gh, 0o755)
        env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"])
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "close_run.py"), run, "--root", self.repo, "--dry-run"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def open_pr(self, number):
        self.hook("telemetry.py", {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                                   "tool_input": {"command": "gh pr create --draft --title t --body-file b.md"},
                                   "tool_response": {"stdout": f"https://github.com/o/r/pull/{number}\n", "stderr": ""}})

    def test_counts_a_pr_the_user_merged_outside_the_session(self):
        self.start_run("10")
        self.open_pr(7)
        metrics = self.close_with_fake_gh("10", 'import sys, json\nassert sys.argv[1:4] == ["pr", "view", "7"]\nprint(json.dumps({"state": "MERGED"}))\n')
        self.assertEqual((metrics["prs_opened"], metrics["prs_merged"], metrics["prs_merged_outside"]), (1, 1, 1))

    def test_a_merge_seen_by_the_hooks_is_not_counted_twice(self):
        self.start_run("11")
        self.open_pr(8)
        self.hook("telemetry.py", {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "gh pr merge 8 --match-head-commit a"}})
        metrics = self.close_with_fake_gh("11", 'import json\nprint(json.dumps({"state": "MERGED"}))\n')
        self.assertEqual((metrics["prs_merged"], metrics["prs_merged_outside"]), (1, 0))

    def test_without_github_only_the_events_count(self):
        self.start_run("12")
        self.open_pr(9)
        metrics = self.close_with_fake_gh("12", 'import sys\nsys.stderr.write("network down")\nsys.exit(1)\n')
        self.assertEqual((metrics["prs_merged"], metrics["prs_merged_outside"]), (0, 0))

    def test_records_second_review_summary_or_null(self):
        self.start_run("17")
        self.hook("telemetry.py", {"hook_event_name": "UserPromptSubmit", "prompt": "hola"})
        no_sr = self.close_with_fake_gh("17", 'import sys\nsys.exit(1)\n')
        self.assertIsNone(no_sr["second_review"])

        run_dir = os.path.join(self.repo, ".agent-playbook", "runs", "17")
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "second-review.jsonl"), "w") as fh:
            fh.write(json.dumps({
                "ts": "2026-11-14T10:00:00Z", "event": "review", "head": "abc", "model": "gemini-4-argon",
                "status": "ok", "attempts": 1, "verdict": "CHANGES_REQUESTED", "findings": 2,
                "seconds": 9.4, "tokens": 1100,
            }) + "\n")
        with open(os.path.join(run_dir, "RUN_STATE.md"), "w") as fh:
            fh.write(
                "# Corrida 17\n\n"
                "## Segundo reviewer\n\n"
                "| HEAD | Veredicto | Hallazgos | Aceptados | Descartados (motivo) |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| abc | CHANGES_REQUESTED | 2 | 1 | 1 (falso positivo) |\n"
            )
        with_sr = self.close_with_fake_gh("17", 'import sys\nsys.exit(1)\n')
        self.assertEqual(
            with_sr["second_review"],
            {
                "calls": 1, "degraded": 0, "skipped": 0, "changes_requested": 1, "findings": 2,
                "accepted": 1, "discarded": 1, "tokens": 1100, "seconds": 9.4, "internal": 0,
            },
        )
        self.assertIsNone(with_sr["gemini_readers"])
        with open(os.path.join(run_dir, "gemini-readers.jsonl"), "w") as fh:
            fh.write(json.dumps({
                "ts": "2026-11-14T10:00:00Z", "event": "reader", "question": "q1",
                "model": "gemini-3.8-flash", "status": "ok", "attempts": 1,
                "files": 2, "risks": 1, "tests": 1, "seconds": 3.2, "tokens": 800,
            }) + "\n")
        with_sr = self.close_with_fake_gh("17", 'import sys\nsys.exit(1)\n')
        self.assertEqual(
            with_sr["gemini_readers"],
            {"calls": 1, "degraded": 0, "recovered": 0, "tokens": 800, "seconds": 3.2},
        )
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import close_run  # noqa: E402
        try:
            import jsonschema
        except ImportError:
            jsonschema = None
        if jsonschema is not None:
            self.assertIsNone(close_run.validate(with_sr))
            self.assertIsNone(close_run.validate(no_sr))
        self.assertIsNone(close_run.build_metrics("17", self.events(), "na", root=None)["second_review"])


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

    def test_a_streamed_message_counts_its_final_usage(self):
        # Claude Code writes one record per content block; only the last one has the final output_tokens.
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import close_run
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            for out in (4, 4, 391):
                fh.write(json.dumps({"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5", "usage": {"input_tokens": 2, "output_tokens": out, "cache_read_input_tokens": 50}}}) + "\n")
        try:
            usage = close_run.usage_from_transcript(fh.name)
        finally:
            os.remove(fh.name)
        self.assertEqual((usage["claude-sonnet-5"]["output_tokens"], usage["claude-sonnet-5"]["cache_read_input_tokens"]), (391, 50))

    def test_context_samples_add_input_and_cache_inside_the_window(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import close_run
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            for ts, read in (("2026-10-17T09:00:00Z", 900000), ("2026-10-17T10:00:00Z", 160000), ("2026-10-17T10:05:00Z", 170000)):
                fh.write(json.dumps({"type": "assistant", "timestamp": ts, "message": {"id": ts, "usage": {
                    "input_tokens": 5, "cache_read_input_tokens": read, "cache_creation_input_tokens": 1000}}}) + "\n")
        try:
            start = close_run.parse_ts("2026-10-17T09:30:00Z")
            samples = close_run.context_samples(fh.name, start)
        finally:
            os.remove(fh.name)
        self.assertEqual([tokens for _, tokens in samples], [161005, 171005])

    def test_parses_agy_planner_response_usage(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import close_run
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps({
                "step_index": 3,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-10-17T10:00:00Z",
                "model": "gemini-2.5-pro",
                "usage": {"input_tokens": 120, "output_tokens": 45},
            }) + "\n")
        try:
            usage = close_run.usage_from_transcript(fh.name)
        finally:
            os.remove(fh.name)
        self.assertEqual((usage["gemini-2.5-pro"]["input_tokens"], usage["gemini-2.5-pro"]["output_tokens"]), (120, 45))


class AgyDualRuntimeHooksTest(HookTestCase):
    def test_agy_invoke_subagent_injects_and_gates_models(self):
        self.start_run()
        out = self.hook("model_gate.py", {
            "hookEventName": "PreToolUse",
            "toolName": "invoke_subagent",
            "toolInput": {
                "Subagents": [
                    {"TypeName": "research", "Role": "Reader", "Prompt": "ROLE: reader · CLASS: reader\nExplora"}
                ]
            },
        })
        updated = out["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["Subagents"][0]["Model"], "flash")

        blocked = self.hook("model_gate.py", {
            "hookEventName": "PreToolUse",
            "toolName": "invoke_subagent",
            "toolInput": {
                "Subagents": [
                    {"TypeName": "self", "Role": "Coder", "Model": "inherit", "Prompt": "ROLE: coder · CLASS: critical\nFix"}
                ]
            },
        })
        self.assertEqual(self.decision(blocked), "deny")

    def test_agy_run_command_is_checked_by_safety_gate(self):
        out = self.hook("safety_gate.py", {
            "hookEventName": "PreToolUse",
            "toolName": "run_command",
            "toolInput": {"CommandLine": "git push origin main", "Cwd": self.repo},
        })
        self.assertEqual(self.decision(out), "deny")

    def test_root_config_file_is_loaded_when_dot_claude_is_absent(self):
        os.remove(os.path.join(self.repo, ".claude", "agent-playbook.json"))
        with open(os.path.join(self.repo, ".agent-playbook.json"), "w") as fh:
            json.dump({"version": 1, "profile": "reduced", "tracker": {"type": "github"}, "hooks": {"mode": "block"}}, fh)
        self.start_run()
        out = self.hook("model_gate.py", {
            "hookEventName": "PreToolUse",
            "toolName": "invoke_subagent",
            "toolInput": {
                "Subagents": [{"TypeName": "self", "Role": "Coder", "Prompt": "sin header", "Model": "inherit"}]
            },
        })
        self.assertEqual(self.decision(out), "deny")


if __name__ == "__main__":
    unittest.main()
