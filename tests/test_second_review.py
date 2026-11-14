import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import second_review as sr  # noqa: E402


def agy_response(verdict="APPROVE", summary="Todo correcto.", findings=None, criteria=None,
                 status="SUCCESS", duration=12.34, total_tokens=1500):
    payload = {
        "status": status,
        "duration_seconds": duration,
        "usage": {"total_tokens": total_tokens},
        "structured_output": {
            "verdict": verdict,
            "summary": summary,
            "findings": findings if findings is not None else [],
            "criteria": criteria if criteria is not None else [],
        },
    }
    return json.dumps(payload)


class SettingsTest(unittest.TestCase):
    def test_defaults_when_missing_or_empty(self):
        expected = {
            "enabled": False,
            "model": sr.DEFAULT_MODEL,
            "timeout": sr.DEFAULT_TIMEOUT,
            "min_diff_lines": sr.DEFAULT_MIN_DIFF_LINES,
            "internal_review": True,
        }
        self.assertEqual(sr.settings({}), expected)
        self.assertEqual(sr.settings({"second_reviewer": None}), expected)

    def test_reads_configured_values(self):
        cfg = {
            "second_reviewer": {
                "enabled": True,
                "model": "gemini-3.1-pro",
                "timeout_seconds": 120,
                "min_diff_lines": 0,
                "internal_review": False,
            }
        }
        self.assertEqual(
            sr.settings(cfg),
            {"enabled": True, "model": "gemini-3.1-pro", "timeout": 120, "min_diff_lines": 0, "internal_review": False},
        )
        self.assertEqual(sr.role_for("standard", {"internal_review": True}), "advisory")
        self.assertEqual(sr.role_for("critical", {"internal_review": True}), "internal")
        self.assertEqual(sr.role_for("critical", {"internal_review": False}), "advisory")

    def test_example_config_is_valid_against_schema(self):
        with open(os.path.join(ROOT, "config", "agent-playbook.example.json"), encoding="utf-8") as fh:
            example = json.load(fh)
        with open(os.path.join(ROOT, "config", "agent-playbook.schema.json"), encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertIn("second_reviewer", schema["properties"])
        self.assertEqual(example["second_reviewer"], {"enabled": False})
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.validate(example, schema)


class InputsAndSkipTest(unittest.TestCase):
    def test_gather_inputs_reads_state_pr_and_github_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = sr.run_dir(tmp, "42")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, sr.STATE_NAME), "w", encoding="utf-8") as fh:
                fh.write("| Clase | critical |\n")
            calls = []

            def fake_gh(cwd, args):
                calls.append((cwd, args))
                if args[0] == "pr":
                    return "Cuerpo del PR"
                if args[0] == "issue":
                    return "# Ticket 42\n\nCriterios"
                return ""

            ticket, plan, pr_body = sr.gather_inputs(
                "42", "/tmp/wt", tmp, {"tracker": {"type": "github"}}, gh=fake_gh
            )
            self.assertEqual(ticket, "# Ticket 42\n\nCriterios")
            self.assertEqual(plan, "| Clase | critical |")
            self.assertEqual(pr_body, "Cuerpo del PR")
            self.assertEqual([c[0] for c in calls], ["/tmp/wt", tmp])
            self.assertEqual([c[1][:3] for c in calls], [["pr", "view", "--json"], ["issue", "view", "42"]])

    def test_gather_inputs_explicit_files_win_over_state_and_gh(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = sr.run_dir(tmp, "42")
            os.makedirs(state_dir)
            with open(os.path.join(state_dir, sr.STATE_NAME), "w", encoding="utf-8") as fh:
                fh.write("plan de RUN_STATE")
            paths = {}
            for name, content in (("ticket.md", "ticket fijo"), ("plan.md", "plan fijo"), ("pr.md", "pr fijo")):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                paths[name] = path
            calls = []

            def fake_gh(cwd, args):
                calls.append((cwd, args))
                return "no debe usarse"

            ticket, plan, pr_body = sr.gather_inputs(
                "42", "/tmp/wt", tmp, {"tracker": {"type": "github"}},
                ticket_file=paths["ticket.md"],
                plan_file=paths["plan.md"],
                pr_body_file=paths["pr.md"],
                gh=fake_gh,
            )
            self.assertEqual((ticket, plan, pr_body), ("ticket fijo", "plan fijo", "pr fijo"))
            self.assertEqual(calls, [])

    def test_gather_inputs_non_github_or_non_numeric_run_skips_issue_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            for tracker_type, run_id in (("notion", "42"), ("jira", "42"), ("github", "abc123")):
                calls = []

                def fake_gh(cwd, args, log=calls):
                    log.append(args)
                    return "PR body"

                ticket, plan, pr_body = sr.gather_inputs(
                    run_id, "/tmp/wt", tmp, {"tracker": {"type": tracker_type}}, gh=fake_gh
                )
                self.assertEqual((ticket, plan, pr_body), ("", "", "PR body"))
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][0], "pr")

    def test_class_from_state(self):
        self.assertEqual(sr.class_from_state("| Clase | critical |\n"), "critical")
        self.assertEqual(sr.class_from_state("| Clase | Critical |\n"), "critical")
        self.assertEqual(sr.class_from_state("| Clase | standard |\n"), "standard")
        self.assertEqual(sr.class_from_state("sin tabla"), "standard")
        self.assertEqual(sr.class_from_state(""), "standard")

    def test_skip_reason_cases(self):
        self.assertEqual(sr.skip_reason(0, [], 50), "el diff está vacío")
        self.assertEqual(
            sr.skip_reason(200, ["README.md", "docs/a.mdx", "guide.rst", "notes.txt"], 50),
            "solo cambia documentación",
        )
        self.assertEqual(
            sr.skip_reason(49, ["README.md", "app.py"], 50),
            "el diff tiene 49 líneas, menos de 50",
        )
        self.assertIsNone(sr.skip_reason(50, ["app.py"], 50))
        self.assertIsNone(sr.skip_reason(120, ["app.py"], 50))
        self.assertIsNone(sr.skip_reason(1, ["app.py"], 0))


class PacketAndCommandTest(unittest.TestCase):
    def test_build_packet_includes_all_sections_and_diff(self):
        packet = sr.build_packet(
            ticket="Implementar login",
            plan="1. Añadir endpoint",
            pr_body="Resumen del PR",
            stat=" app.py | 2 +\n",
            diff="diff --git a/app.py b/app.py\n+ok = True\n",
            base="origin/main",
            head="abc1234",
        )
        self.assertIn("Implementar login", packet)
        self.assertIn("1. Añadir endpoint", packet)
        self.assertIn("Resumen del PR", packet)
        self.assertIn("```diff\ndiff --git a/app.py b/app.py", packet)

    def test_build_packet_omits_oversized_diff_with_git_diff_hint(self):
        huge_diff = "x" * (sr.MAX_DIFF_BYTES + 1)
        packet = sr.build_packet(
            ticket="Ticket grande",
            plan="",
            pr_body="",
            stat=" big.txt | 1000 +\n",
            diff=huge_diff,
            base="origin/main",
            head="def5678",
        )
        self.assertNotIn(huge_diff, packet)
        self.assertIn("git diff origin/main...HEAD -- <archivo>", packet)

    def test_build_command_enforces_sandbox_plan_and_allow_list(self):
        cmd = sr.build_command(
            model="gemini-4-argon",
            effort="medium",
            timeout=300,
            packet_path="/tmp/run/second-review-input.md",
            add_dir="/tmp/run",
        )
        self.assertNotIn("--dangerously-skip-permissions", cmd)
        self.assertEqual(cmd[cmd.index("--mode") + 1], "plan")
        self.assertIn("--sandbox", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")
        self.assertIn("--json-schema", cmd)
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], "/tmp/run")
        settings_json = json.loads(cmd[cmd.index("--settings") + 1])
        self.assertEqual(
            settings_json,
            {"permissions": {"allow": [f"command({c})" for c in sr.ALLOWED_COMMANDS]}},
        )


class ParseResultTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "x.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_valid_response_normalizes_paths_severities_and_verdict(self):
        abs_x = os.path.join(self.tmp, "x.py")
        stdout = agy_response(
            verdict="APPROVE",
            summary="Falta validar entrada.",
            findings=[
                {
                    "file": f"file://{abs_x}#L3",
                    "line": 3,
                    "severity": "blocker",
                    "summary": "Falta check",
                    "evidence": "linea 3",
                },
                {
                    "file": "ghost.py",
                    "severity": "major",
                    "summary": "Archivo inventado",
                },
                {
                    "file": abs_x,
                    "severity": "critical",
                    "summary": "Severidad desconocida",
                },
                {
                    "file": abs_x,
                    "severity": "minor",
                    "summary": "Sugerencia de estilo",
                },
            ],
            criteria=[{"criterion": "C1", "status": "covered", "test": "tests/test_x.py::test_1"}],
            duration=4.56,
            total_tokens=2048,
        )
        status, payload = sr.parse_result(stdout, "", self.tmp)
        self.assertEqual(status, "ok")
        # An APPROVE with a blocker or major finding must be corrected to CHANGES_REQUESTED.
        self.assertEqual(payload["verdict"], "CHANGES_REQUESTED")
        self.assertEqual(payload["seconds"], 4.6)
        self.assertEqual(payload["tokens"], 2048)

        self.assertEqual(len(payload["findings"]), 2)
        f0, f1 = payload["findings"]
        self.assertEqual((f0["file"], f0["severity"], f0["file_exists"]), ("x.py", "blocker", True))
        self.assertEqual((f1["file"], f1["severity"], f1["file_exists"]), ("ghost.py", "major", False))
        self.assertEqual(payload["criteria"], [{"criterion": "C1", "status": "covered", "test": "tests/test_x.py::test_1"}])

    def test_discards_minor_and_invalid_severity_findings_and_approves(self):
        stdout = agy_response(
            verdict="CHANGES_REQUESTED",
            summary="Solo detalles.",
            findings=[
                {"file": "x.py", "severity": "minor", "summary": "Nombre mejorable"},
                {"file": "x.py", "severity": "critical", "summary": "Severidad fuera de esquema"},
            ],
        )
        status, payload = sr.parse_result(stdout, "", self.tmp)
        self.assertEqual(status, "ok")
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["verdict"], "APPROVE")

    def test_auto_denied_in_stderr_returns_denied(self):
        status, _ = sr.parse_result("", "command auto-denied by sandbox", self.tmp)
        self.assertEqual(status, "denied")

    def test_non_json_stdout_returns_invalid(self):
        status, _ = sr.parse_result("not json at all", "", self.tmp)
        self.assertEqual(status, "invalid")

    def test_non_success_status_returns_invalid(self):
        status, _ = sr.parse_result(agy_response(status="ERROR"), "", self.tmp)
        self.assertEqual(status, "invalid")

    def test_missing_or_unknown_verdict_returns_invalid(self):
        status, _ = sr.parse_result(agy_response(verdict="MAYBE"), "", self.tmp)
        self.assertEqual(status, "invalid")
        no_verdict = json.dumps({"status": "SUCCESS", "structured_output": {"findings": [], "criteria": []}})
        status2, _ = sr.parse_result(no_verdict, "", self.tmp)
        self.assertEqual(status2, "invalid")


class ReviewWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "dev@example.com")
        self._git("config", "user.name", "Dev")
        with open(os.path.join(self.repo, "app.py"), "w", encoding="utf-8") as fh:
            fh.write("v = 1\n")
        self._git("add", "app.py")
        self._git("commit", "-q", "-m", "initial")

        self._git("checkout", "-q", "-b", "feat/ticket-7")
        with open(os.path.join(self.repo, "app.py"), "w", encoding="utf-8") as fh:
            fh.write("v = 2\n")
        self._git("add", "app.py")
        self._git("commit", "-q", "-m", "feat: update v")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _git(self, *args):
        subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True)

    def test_review_writes_artifacts_and_retries_once_on_invalid(self):
        responses = iter([
            ("not json", "", None),
            (agy_response(verdict="APPROVE", summary="Bien.", total_tokens=900, duration=3.2), "", None),
        ])
        calls = []

        def fake_runner(command, cwd, timeout):
            calls.append((command, cwd, timeout))
            return next(responses)

        res = sr.review(
            "7",
            self.repo,
            ticket="Criterio: v vale 2",
            plan="Cambiar v a 2",
            pr_body="PR body",
            base="main",
            root=self.repo,
            runner=fake_runner,
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["attempts"], 2)
        self.assertEqual(len(calls), 2)

        run_dir = sr.run_dir(self.repo, "7")
        self.assertTrue(os.path.isfile(os.path.join(run_dir, sr.INPUT_NAME)))
        self.assertTrue(os.path.isfile(os.path.join(run_dir, sr.RESULT_NAME)))
        with open(os.path.join(run_dir, sr.INPUT_NAME), encoding="utf-8") as fh:
            packet = fh.read()
        self.assertIn("Criterio: v vale 2", packet)
        self.assertIn("+v = 2", packet)

        with open(os.path.join(run_dir, sr.LOG_NAME), encoding="utf-8") as fh:
            lines = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual((lines[0]["event"], lines[0]["attempts"], lines[0]["status"]), ("review", 2, "ok"))
        self.assertNotIn("blocking", lines[0])

    def test_diff_size_counts_changed_lines_and_files(self):
        with open(os.path.join(self.repo, "extra.py"), "w", encoding="utf-8") as fh:
            fh.write("a = 1\nb = 2\nc = 3\n")
        self._git("add", "extra.py")
        self._git("commit", "-q", "-m", "feat: add extra")
        lines, files = sr.diff_size(self.repo, "main")
        self.assertEqual(lines, 5)
        self.assertEqual(files, ["app.py", "extra.py"])

    def test_review_does_not_retry_on_missing_or_timeout(self):
        for err in ("missing", "timeout"):
            calls = []

            def fake_runner(command, cwd, timeout, code=err):
                calls.append(code)
                return "", "", code

            res = sr.review(f"run-{err}", self.repo, ticket="t", base="main", root=self.repo, runner=fake_runner)
            self.assertEqual(res["status"], err)
            self.assertEqual(res["attempts"], 1)
            self.assertEqual(len(calls), 1)
            self.assertIn("error", res)


class TriageSummarizeAndReportTest(unittest.TestCase):
    def test_triage_from_state_reads_rows_and_ignores_other_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sr.triage_from_state(tmp), (0, 0))
            with open(os.path.join(tmp, sr.STATE_NAME), "w", encoding="utf-8") as fh:
                fh.write(
                    "# Corrida 7\n\n"
                    "## PRs\n\n"
                    "| Repo | PR | HEAD revisado | promoted_at | Review | Checks | Mergeado |\n"
                    "| --- | --- | --- | --- | --- | --- | --- |\n"
                    "| app | 1 | aaa | 10 | 99 | ok | si |\n\n"
                    "## Segundo reviewer\n\n"
                    "| HEAD | Veredicto | Hallazgos | Aceptados | Descartados (motivo) |\n"
                    "| --- | --- | --- | --- | --- |\n"
                    "| abc1111 | CHANGES_REQUESTED | 3 | 2 | 1 (falso positivo) |\n"
                    "| def2222 | APPROVE | 0 | | |\n"
                    "| 9876543 | CHANGES_REQUESTED | 2 | 1 (aplicado) | 1 (fuera de alcance) |\n\n"
                    "## Fallas preexistentes\n\n"
                    "| A | B | C | D | E |\n"
                    "| --- | --- | --- | --- | --- |\n"
                    "| x | y | z | 5 | 6 |\n"
                )
            self.assertEqual(sr.triage_from_state(tmp), (3, 2))

    def test_already_reviewed_only_true_after_ok_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(sr.already_reviewed(tmp))
            sr.append_log(tmp, {"event": "review", "status": "skipped", "reason": "el diff está vacío"})
            sr.append_log(tmp, {"event": "review", "status": "timeout"})
            self.assertFalse(sr.already_reviewed(tmp))
            sr.append_log(tmp, {"event": "review", "status": "ok", "verdict": "APPROVE"})
            self.assertTrue(sr.already_reviewed(tmp))

    def test_summarize_none_without_log_and_aggregates_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(sr.summarize(tmp))
            sr.append_log(tmp, {"event": "review", "status": "skipped", "reason": "solo cambia documentación"})
            self.assertEqual(
                sr.summarize(tmp),
                {
                    "calls": 0,
                    "degraded": 0,
                    "skipped": 1,
                    "changes_requested": 0,
                    "findings": 0,
                    "accepted": 0,
                    "discarded": 0,
                    "tokens": 0,
                    "seconds": 0.0,
                    "internal": 0,
                },
            )
            sr.append_log(tmp, {"event": "review", "role": "internal", "status": "ok", "verdict": "CHANGES_REQUESTED", "findings": 3, "tokens": 1000, "seconds": 10.2})
            sr.append_log(tmp, {"event": "review", "status": "timeout"})
            sr.append_log(tmp, {"event": "review", "status": "ok", "verdict": "APPROVE", "findings": 1, "tokens": 500, "seconds": 5.3})
            with open(os.path.join(tmp, sr.STATE_NAME), "w", encoding="utf-8") as fh:
                fh.write(
                    "## Segundo reviewer\n\n"
                    "| HEAD | Veredicto | Hallazgos | Aceptados | Descartados (motivo) |\n"
                    "| --- | --- | --- | --- | --- |\n"
                    "| abc1234 | CHANGES_REQUESTED | 3 | 2 | 1 (ya cubierto) |\n"
                    "| def5678 | APPROVE | 1 | 0 | 1 (estilo) |\n"
                )
            self.assertEqual(
                sr.summarize(tmp),
                {
                    "calls": 3,
                    "degraded": 1,
                    "skipped": 1,
                    "changes_requested": 1,
                    "findings": 4,
                    "accepted": 2,
                    "discarded": 2,
                    "tokens": 1500,
                    "seconds": 15.5,
                    "internal": 1,
                },
            )

    def test_report_degraded_mentions_limits_and_ok_includes_tables(self):
        degraded = sr.report({"status": "timeout", "error": "agy no respondió en 300 s"})
        self.assertIn("LÍMITES", degraded)

        ok = sr.report({
            "status": "ok",
            "model": "gemini-4-argon",
            "verdict": "CHANGES_REQUESTED",
            "head": "1234567890",
            "seconds": 8.4,
            "tokens": 1200,
            "summary": "Un defecto.",
            "findings": [
                {
                    "file": "a.py",
                    "line": 10,
                    "severity": "major",
                    "summary": "Falta nulo",
                    "evidence": "sin if",
                    "file_exists": False,
                }
            ],
            "criteria": [{"criterion": "C1", "status": "partial", "test": "test_a"}],
        })
        self.assertIn("| # | Severidad | Dónde | Hallazgo | Evidencia |", ok)
        self.assertIn("a.py:10 (no existe en el worktree)", ok)
        self.assertIn("| Criterio | Cobertura | Test |", ok)
        self.assertIn("| C1 | partial | test_a |", ok)
        self.assertIn("Fila para «Segundo reviewer» de RUN_STATE.md (completa aceptados y descartados):", ok)
        self.assertIn("| 1234567 | CHANGES_REQUESTED | 1 | | |", ok)

        internal_ok = sr.report({
            "status": "ok",
            "role": "internal",
            "model": "gemini-4-argon",
            "verdict": "APPROVE",
            "head": "1234567890",
            "seconds": 5.0,
            "tokens": 900,
            "summary": "Listo.",
            "findings": [],
            "criteria": [],
        })
        self.assertIn("reviewer interno, obligatorio", internal_ok)
        self.assertIn("Su APPROVE sobre el HEAD actual es el del reviewer interno", internal_ok)
        internal_fail = sr.report({"status": "timeout", "role": "internal", "error": "agy no respondió"})
        self.assertIn("ROLE: reviewer · CLASS: review", internal_fail)


class MainHelpersTest(unittest.TestCase):
    def test_null_min_diff_lines_falls_back_to_default_and_zero_is_kept(self):
        self.assertEqual(sr.settings({"second_reviewer": {"min_diff_lines": None}})["min_diff_lines"],
                         sr.DEFAULT_MIN_DIFF_LINES)
        self.assertEqual(sr.settings({"second_reviewer": {"min_diff_lines": 0}})["min_diff_lines"], 0)

    def test_state_class_reads_run_state_and_defaults_to_standard(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sr.state_class(tmp, "7"), "standard")
            directory = sr.run_dir(tmp, "7")
            os.makedirs(directory)
            with open(os.path.join(directory, sr.STATE_NAME), "w", encoding="utf-8") as fh:
                fh.write("| Campo | Valor |\n| --- | --- |\n| Clase | critical |\n")
            self.assertEqual(sr.state_class(tmp, "7"), "critical")

    def test_no_review_is_logged_and_counts_as_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sr.no_review(tmp, "missing", "agy no está instalado"), 1)
            self.assertFalse(sr.already_reviewed(tmp))
            self.assertTrue(sr.already_reviewed(tmp, "missing"))
            totals = sr.summarize(tmp)
            self.assertEqual((totals["calls"], totals["degraded"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
