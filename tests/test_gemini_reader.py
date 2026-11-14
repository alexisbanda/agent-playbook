import json
import os
import sys
import tempfile
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
                {"calls": 2, "degraded": 1, "tokens": 900, "seconds": 3.4},
            )


if __name__ == "__main__":
    unittest.main()
