# Copyright (c) 2026 Alexis Banda. Todos los derechos reservados.
# Software propietario: uso sujeto a LICENSE, prohibida su redistribución.
import json
import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gemini_reader as gr  # noqa: E402


def agy_reader_response(summary="Encontrado.", files=None, risks=None, tests=None,
                        status="SUCCESS", duration=3.4, total_tokens=900):
    return json.dumps({
        "status": status,
        "duration_seconds": duration,
        "usage": {"total_tokens": total_tokens},
        "structured_output": {
            "summary": summary,
            "files": files if files is not None else [{"path": "app.py", "why": "Punto de entrada"}],
            "risks": risks if risks is not None else ["Contrato compartido"],
            "tests": tests if tests is not None else [{"path": "tests/test_app.py", "covers": "Ruta principal"}],
        },
    })


class GeminiReaderTest(unittest.TestCase):
    def test_settings_defaults_and_configured_values(self):
        self.assertEqual(
            gr.settings({}),
            {
                "enabled": False,
                "model": gr.DEFAULT_MODEL,
                "effort": gr.DEFAULT_EFFORT,
                "timeout": gr.DEFAULT_TIMEOUT,
            },
        )
        self.assertEqual(
            gr.settings({
                "gemini_readers": {
                    "enabled": True,
                    "model": "gemini-4-argon",
                    "effort": "medium",
                    "timeout_seconds": 90,
                }
            }),
            {"enabled": True, "model": "gemini-4-argon", "effort": "medium", "timeout": 90},
        )

    def test_read_repo_logs_and_summarizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "app.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")

            def fake_runner(command, cwd, timeout):
                return agy_reader_response(
                    files=[
                        {"path": f"file://{tmp}/app.py#L1", "why": "Existe"},
                        {"path": "missing.py", "why": "No existe"},
                    ]
                ), "", None

            res = gr.read_repo("42", "Explora app", ticket="# Ticket 42", root=tmp, runner=fake_runner)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["files"][0], {"path": "app.py", "why": "Existe", "exists": True})
            self.assertEqual(res["files"][1], {"path": "missing.py", "why": "No existe", "exists": False})
            text = gr.report(res)
            self.assertIn("| app.py | Existe |", text)
            self.assertIn("missing.py (no existe en el repo)", text)
            self.assertIn("Contrato compartido", text)

            directory = gr.run_dir(tmp, "42")
            gr.no_reader(directory, "timeout", "agy no respondió", "Otra pregunta")
            self.assertEqual(
                gr.summarize(directory),
                {"calls": 2, "degraded": 1, "recovered": 0, "tokens": 900, "seconds": 3.4},
            )

    def test_build_command_permissions_and_avoid(self):
        cmd = gr.build_command("gemini-3.8-flash", "low", 180, "/tmp/p.md", "/tmp/dir")
        settings = json.loads(cmd[cmd.index("--settings") + 1])
        allow = settings["permissions"]["allow"]
        deny = settings["permissions"]["deny"]
        self.assertIn("command(head)", allow)
        for name in ("find", "sed -n", "git grep", "git status", "git branch"):
            self.assertIn(f"command({name})", allow)
        self.assertIn("command(git branch -D)", deny)
        self.assertNotIn("command(git branch)", deny)
        self.assertNotIn("command(sed)", allow)
        # deny gana a allow por prefijo: sed y find enteros no pueden estar en deny
        self.assertNotIn("command(sed)", deny)
        self.assertNotIn("command(find)", deny)
        self.assertIn("command(sed -i)", deny)
        self.assertIn("command(node)", deny)
        self.assertIn("-exec", cmd[-1])
        self.assertEqual(cmd[-2], "-p")
        self.assertNotIn("Un intento anterior", cmd[-1])
        self.assertIn("-- 'docs/08*'", cmd[-1])
        self.assertEqual(cmd[-1].count(gr.SHAPE_RULES), 1)

        retry_cmd = gr.build_command("gemini-3.8-flash", "low", 180, "/tmp/p.md", "/tmp/dir", avoid="node -v")
        self.assertEqual(retry_cmd[-2], "-p")
        self.assertIn("`node -v`", retry_cmd[-1])

        glob_cmd = gr.build_command("gemini-3.8-flash", "low", 180, "/tmp/p.md", "/tmp/dir",
                                    avoid="git grep -n X docs/08*")
        self.assertIn("`git grep -n X docs/08*`", glob_cmd[-1])
        self.assertIn("sin comodines sin comillas", glob_cmd[-1])
        self.assertIn("Un intento anterior se abortó por usar un comando no permitido", glob_cmd[-1])

    def test_parallel_read_repo_gets_distinct_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            barrier = threading.Barrier(2)

            def fake_runner(command, cwd, timeout):
                barrier.wait(timeout=5)
                marker = "Lee el encargo en: "
                line = next(l for l in command[-1].splitlines() if marker in l)
                packet = line.split(marker, 1)[1].strip()
                with open(packet, encoding="utf-8") as fh:
                    return agy_reader_response(summary=fh.read()), "", None

            questions = ["Pregunta alfa sobre auth", "Pregunta beta sobre pagos"]
            results = {}
            errors = []

            def worker(question):
                try:
                    results[question] = gr.read_repo("epic-9", question, root=tmp, runner=fake_runner)
                except Exception as error:  # pragma: no cover - se informa abajo
                    errors.append(error)

            threads = [threading.Thread(target=worker, args=(q,)) for q in questions]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertEqual(errors, [])

            directory = gr.run_dir(tmp, "epic-9")
            contents = []
            for index in (1, 2):
                path = os.path.join(directory, f"gemini-reader-{index}-input.md")
                self.assertTrue(os.path.isfile(path), path)
                with open(path, encoding="utf-8") as fh:
                    contents.append(fh.read())
            for question in questions:
                self.assertEqual(sum(question in c for c in contents), 1)
                self.assertEqual(results[question]["status"], "ok")
                self.assertIn(question, results[question]["summary"])
            other = {questions[0]: questions[1], questions[1]: questions[0]}
            for question in questions:
                self.assertNotIn(other[question], results[question]["summary"])
            self.assertEqual(len(gr.log_entries(directory)), 2)

    def test_reserve_packet_skips_existing_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = os.path.join(tmp, "gemini-reader-1-input.md")
            with open(existing, "w", encoding="utf-8") as fh:
                fh.write("original")
            index, path = gr.reserve_packet(tmp, "nuevo")
            self.assertEqual(index, 2)
            self.assertEqual(path, os.path.join(tmp, "gemini-reader-2-input.md"))
            with open(existing, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "original")
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "nuevo")

    def test_parse_result_detects_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, _ = gr.parse_result("", "jetski: auto-denied command", tmp)
            self.assertEqual(status, "denied")

            stdout = json.dumps({
                "conversation_id": "c1",
                "status": "SUCCESS",
                "response": "",
                "denied_actions": [{"action": "command", "display_name": "Bash"}],
            })
            status, _ = gr.parse_result(stdout, "", tmp)
            self.assertEqual(status, "denied")

    def test_denied_command_reads_last_run_command_and_handles_errors(self):
        with tempfile.TemporaryDirectory() as brain:
            logs_dir = os.path.join(brain, "conv-1", ".system_generated", "logs")
            os.makedirs(logs_dir)
            transcript = os.path.join(logs_dir, "transcript.jsonl")
            step1 = json.dumps({
                "type": "PLANNER_RESPONSE",
                "tool_calls": [{"name": "run_command", "args": {"CommandLine": '"ls -la"'}}],
            })
            step2 = (
                '{"type": "PLANNER_RESPONSE", "tool_calls": ['
                '{"name": "run_command", "args": {"CommandLine": "\\"node -e \\\\\\"x\\\\\\"\\""}}'
                ']}'
            )
            with open(transcript, "w", encoding="utf-8") as fh:
                fh.write(step1 + "\n" + step2 + "\n")

            stdout = json.dumps({"conversation_id": "conv-1"})
            self.assertEqual(gr.denied_command(stdout, brain_dir=brain), 'node -e "x"')
            self.assertIsNone(gr.denied_command("not-json", brain_dir=brain))
            self.assertIsNone(gr.denied_command(json.dumps({"conversation_id": "missing"}), brain_dir=brain))

    def _write_transcript(self, brain, conv_id, cmd_line):
        logs_dir = os.path.join(brain, conv_id, ".system_generated", "logs")
        os.makedirs(logs_dir, exist_ok=True)
        step = {
            "type": "PLANNER_RESPONSE",
            "tool_calls": [{"name": "run_command", "args": {"CommandLine": json.dumps(cmd_line)}}],
        }
        with open(os.path.join(logs_dir, "transcript.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(step) + "\n")

    def test_read_repo_retries_once_on_denied_and_recovers(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as brain:
            with open(os.path.join(tmp, "app.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            self._write_transcript(brain, "conv-denied", 'node -e "x"')
            denied_out = json.dumps({
                "conversation_id": "conv-denied",
                "status": "SUCCESS",
                "response": "",
                "denied_actions": [{"action": "command", "display_name": "Bash"}],
            })
            responses = iter([
                (denied_out, "auto-denied detail", None),
                (agy_reader_response(), "", None),
            ])
            commands = []

            def fake_runner(command, cwd, timeout):
                commands.append(command)
                return next(responses)

            res = gr.read_repo("42", "Explora app", root=tmp, runner=fake_runner, brain_dir=brain)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["attempts"], 2)
            self.assertEqual(res["denied"], ['node -e "x"'])
            self.assertEqual(len(commands), 2)
            self.assertEqual(commands[1][-2], "-p")
            self.assertIn('node -e "x"', commands[1][-1])

            directory = gr.run_dir(tmp, "42")
            stderr_log = os.path.join(directory, "gemini-reader-1-stderr.log")
            self.assertTrue(os.path.isfile(stderr_log))
            with open(stderr_log, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "auto-denied detail")

            entries = gr.log_entries(directory)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["denied"], ['node -e "x"'])
            self.assertIn('Reintento tras denegar: `node -e "x"`', gr.report(res))

    def test_read_repo_denied_twice_fails_with_command_in_error(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as brain:
            self._write_transcript(brain, "conv-1", "python3 -V")
            self._write_transcript(brain, "conv-2", "ruby -v")
            out1 = json.dumps({
                "conversation_id": "conv-1",
                "status": "SUCCESS",
                "denied_actions": [{"action": "command"}],
            })
            out2 = json.dumps({
                "conversation_id": "conv-2",
                "status": "SUCCESS",
                "denied_actions": [{"action": "command"}],
            })
            responses = iter([(out1, "err1", None), (out2, "err2", None)])

            def fake_runner(command, cwd, timeout):
                return next(responses)

            res = gr.read_repo("42", "Explora app", root=tmp, runner=fake_runner, brain_dir=brain)
            self.assertEqual(res["status"], "denied")
            self.assertEqual(res["attempts"], 2)
            self.assertEqual(res["denied"], ["python3 -V", "ruby -v"])
            self.assertIn("ruby -v", res["error"])
            entries = gr.log_entries(gr.run_dir(tmp, "42"))
            self.assertEqual(entries[0]["denied"], ["python3 -V", "ruby -v"])

    def test_summarize_counts_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            gr.append_log(tmp, {
                "event": "reader", "status": "ok", "denied": ["node -v"], "tokens": 500, "seconds": 2.0,
            })
            gr.append_log(tmp, {
                "event": "reader", "status": "ok", "tokens": 300, "seconds": 1.0,
            })
            gr.append_log(tmp, {
                "event": "reader", "status": "denied", "denied": ["python3 -V", "ruby -v"],
            })
            self.assertEqual(
                gr.summarize(tmp),
                {"calls": 3, "degraded": 1, "recovered": 1, "tokens": 800, "seconds": 3.0},
            )


if __name__ == "__main__":
    unittest.main()
