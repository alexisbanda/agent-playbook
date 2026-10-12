import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import close_run  # noqa: E402
import metrics_report  # noqa: E402
import ticket_check as tc  # noqa: E402

CONTRACT_BODY = """## Historia
### Problema
Los jugadores no saben qué tal le va a cada Pokémon.
### Resultado esperado
Cada Pokémon muestra ganados, perdidos y porcentaje.

## Especificación
### Criterios de aceptación
- [ ] [http] `GET /api/my-pokemon/{id}/record` devuelve 200 con wins, losses y win_rate
- [ ] [test] Con 3 victorias y 2 derrotas devuelve win_rate=60
### Fuera de alcance
- Ranking global
"""
LABELS = ["type:feature", "risk:ninguno", "size:M", "ready"]


class MinimalCheckTest(unittest.TestCase):
    def test_contract_ticket_marked_ready_passes(self):
        result = tc.minimal_check(CONTRACT_BODY, LABELS)
        self.assertEqual((result["contract_ok"], result["ready"], result["typed_criteria"], result["missing"]), (True, True, 2, []))

    def test_missing_ready_is_reported_but_the_contract_is_met(self):
        result = tc.minimal_check(CONTRACT_BODY, [l for l in LABELS if l != "ready"])
        self.assertTrue(result["contract_ok"])
        self.assertFalse(result["ready"])
        self.assertTrue(any("ready" in m for m in result["missing"]))

    def test_custom_ready_label(self):
        self.assertTrue(tc.minimal_check(CONTRACT_BODY, LABELS[:-1] + ["listo"], ready_name="listo")["ready"])

    def test_handwritten_issue_explains_what_is_missing(self):
        body = "## Criterios de aceptación\n- [ ] Devuelve 404 si no existe\n"
        missing = " ".join(tc.minimal_check(body, [])["missing"])
        self.assertIn("tipo de prueba", missing)
        self.assertIn("risk:*", missing)
        self.assertIn("size:*", missing)

    def test_no_criteria_at_all(self):
        self.assertIn("criterios de aceptación", tc.minimal_check("Arreglar la cosa", [])["missing"])

    def test_unknown_check_types_do_not_count(self):
        self.assertEqual(tc.minimal_check("- [ ] [ux] queda bonito\n", [])["typed_criteria"], 0)

    def test_improvement_and_task_follow_the_same_minimum(self):
        for kind in ("improvement", "task"):
            labels = [f"type:{kind}"] + LABELS[1:]
            self.assertTrue(tc.minimal_check(CONTRACT_BODY, labels)["contract_ok"], kind)
            self.assertFalse(tc.minimal_check(CONTRACT_BODY, [f"type:{kind}", "ready"])["contract_ok"], kind)

    def test_epic_only_needs_ready(self):
        result = tc.check({"title": "Épica", "body": "## Historia", "labels": [{"name": "type:epic"}]})
        self.assertTrue(result["epic"])
        self.assertTrue(result["contract_ok"])


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "scripts"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_core(self, code):
        path = os.path.join(self.tmp, "scripts", "ticket_core.py")
        with open(path, "w") as fh:
            fh.write(code)
        return path

    def test_uses_ticket_studio_score_when_installed(self):
        path = self.write_core(
            "def parse_github(t, b, l):\n    return {'title': t}\n"
            "def lint(ticket):\n    return {'score': 85, 'errors': 0, 'warnings': 3, 'findings': []}\n")
        result = tc.check({"title": "x", "body": CONTRACT_BODY, "labels": LABELS}, studio_path=path)
        self.assertEqual((result["source"], result["score"], result["warnings"]), ("ticket-studio", 85, 3))

    def test_a_broken_ticket_studio_falls_back_to_minimal(self):
        path = self.write_core("def parse_github(*a):\n    raise ValueError('incompatible')\ndef lint(t):\n    pass\n")
        result = tc.check({"title": "x", "body": CONTRACT_BODY, "labels": LABELS}, studio_path=path)
        self.assertEqual(result["source"], "minimal")
        self.assertIn("incompatible", result["studio_error"])
        self.assertTrue(result["contract_ok"])

    def test_override_path_is_found(self):
        self.write_core("")
        os.environ["TICKET_STUDIO_ROOT"] = self.tmp
        try:
            self.assertEqual(tc.find_ticket_studio(), os.path.join(self.tmp, "scripts", "ticket_core.py"))
        finally:
            del os.environ["TICKET_STUDIO_ROOT"]


class OptInTest(unittest.TestCase):
    def test_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".claude"))
            with open(os.path.join(tmp, ".claude", "agent-playbook.json"), "w") as fh:
                json.dump({"version": 1, "profile": "reduced", "tracker": {"type": "github"}}, fh)
            save = os.path.join(tmp, ".agent-playbook", "runs", "7", "ticket_check.json")
            out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "ticket_check.py"), "7", "--save", save],
                                 cwd=tmp, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertFalse(json.loads(out.stdout)["enabled"])
            with open(save) as fh:
                self.assertFalse(json.load(fh)["enabled"])

    def test_enabled_flag(self):
        self.assertTrue(tc.contract_enabled({"tickets": {"contract": True}}))
        self.assertFalse(tc.contract_enabled({"tickets": {}}))
        self.assertEqual(tc.ready_label({}), "ready")


class MetricsTest(unittest.TestCase):
    def test_close_run_records_ticket_quality_only_when_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, ".agent-playbook", "runs", "9")
            os.makedirs(run_dir)
            self.assertIsNone(close_run.ticket_quality(tmp, "9"))
            with open(os.path.join(run_dir, "ticket_check.json"), "w") as fh:
                json.dump({"enabled": True, "source": "ticket-studio", "score": 90, "contract_ok": True, "ready": True}, fh)
            self.assertEqual(close_run.ticket_quality(tmp, "9"),
                             {"source": "ticket-studio", "score": 90, "contract_ok": True, "ready": True})
            with open(os.path.join(run_dir, "ticket_check.json"), "w") as fh:
                json.dump({"enabled": False}, fh)
            self.assertIsNone(close_run.ticket_quality(tmp, "9"))

    def test_report_shows_ticket_quality(self):
        self.assertEqual(metrics_report.ticket_cell(None), "—")
        self.assertEqual(metrics_report.ticket_cell({"score": 90, "contract_ok": True, "ready": True}), "90/100")
        self.assertEqual(metrics_report.ticket_cell({"score": None, "contract_ok": False, "ready": False}), "incompleto (sin ready)")


if __name__ == "__main__":
    unittest.main()
