import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import metrics_report as mr  # noqa: E402
import run_journeys as rj  # noqa: E402

PRICES = mr.load_json(mr.PRICES)["models"]
TRIPWIRES = mr.load_json(mr.TRIPWIRES)


def run(n, **over):
    base = {
        "run": str(n), "playbook_version": "0.6.0", "closed_at": f"2026-10-0{n}T10:00:00+00:00",
        "wall_minutes": 10, "human_wait_minutes": 2, "subagents": 3, "prs_merged": 1, "compactions": 0,
        "e2e_first_pass": "yes", "overrides": [], "gate_events": {}, "tokens_measured": True,
        "tokens_by_model": {"claude-sonnet-5": {"input_tokens": 0, "output_tokens": 1000, "cache_read_input_tokens": 100000, "cache_creation_input_tokens": 10000}},
    }
    base.update(over)
    return base


def wires(runs):
    result, note = mr.check_tripwires(mr.summarise(runs, PRICES), TRIPWIRES)
    return {w["name"]: w["tripped"] for w in result}, note


class CostTest(unittest.TestCase):
    def test_estimates_cost_from_tokens_and_prices(self):
        cost, unpriced = mr.run_cost(run(1), PRICES)
        # 1000 out × $10 + 100k cache read × $0.20 + 10k cache write × $2.50, per million
        self.assertEqual((cost, unpriced), (round(0.01 + 0.02 + 0.025, 2), []))

    def test_dated_model_ids_use_the_base_price(self):
        self.assertEqual(mr.price_for("claude-haiku-4-5-20251001", PRICES)["input"], 1.0)

    def test_unknown_models_are_reported_not_guessed(self):
        _, unpriced = mr.run_cost(run(1, tokens_by_model={"claude-x-9": {"output_tokens": 5}}), PRICES)
        self.assertEqual(unpriced, ["claude-x-9"])


class TripwireTest(unittest.TestCase):
    def test_needs_a_minimum_of_runs(self):
        result, note = wires([run(1), run(2)])
        self.assertEqual(result, {})
        self.assertIn("mínimo", note)

    def test_healthy_runs_trip_nothing(self):
        result, _ = wires([run(i) for i in range(1, 5)])
        self.assertFalse(any(result.values()), result)

    def test_absences_do_not_count_as_waiting(self):
        # 100 min run, 70 of them away: 6 active minutes over 30 effective is not friction.
        runs = [run(i, wall_minutes=100, human_wait_minutes=76, human_wait_active_minutes=6,
                    human_absence_minutes=70, human_stops=4) for i in range(1, 4)]
        result, _ = wires(runs)
        self.assertFalse(result["human_wait_share_max"])
        self.assertFalse(result["human_stops_per_run_max"])
        result, _ = wires([run(i, human_stops=9, human_wait_active_minutes=2, human_absence_minutes=0) for i in range(1, 4)])
        self.assertTrue(result["human_stops_per_run_max"])

    def test_long_coders_trip(self):
        result, _ = wires([run(i, coder_calls_max=150, coder_ctx_peak_k=320.0) for i in range(1, 4)])
        self.assertTrue(result["coder_calls_max"])
        self.assertTrue(result["coder_ctx_peak_k_max"])
        result, _ = wires([run(i, coder_calls_max=40, coder_ctx_peak_k=120.0) for i in range(1, 4)])
        self.assertFalse(result["coder_calls_max"] or result["coder_ctx_peak_k_max"])

    def test_report_shows_the_orchestrator_model(self):
        rows = mr.summarise([run(1, orchestrator_model="claude-sonnet-5"), run(2)], PRICES)
        table = mr.markdown(rows, [], "nota", 10)
        self.assertIn("| sonnet |", table)
        self.assertEqual(mr.short_model("gemini-3.1-pro"), "gemini-3.1-pro")

    def test_runs_without_coder_metrics_skip_those_wires(self):
        result, _ = wires([run(i) for i in range(1, 4)])
        self.assertNotIn("coder_calls_max", result)

    def test_e2e_failures_trip(self):
        result, _ = wires([run(1), run(2, e2e_first_pass="no"), run(3, e2e_first_pass="no"), run(4)])
        self.assertTrue(result["e2e_first_pass_rate_min"])

    def test_waiting_for_the_human_trips(self):
        result, _ = wires([run(i, human_wait_minutes=8) for i in range(1, 4)])
        self.assertTrue(result["human_wait_share_max"])

    def test_untracked_tokens_trip(self):
        result, _ = wires([run(1), run(2), run(3, tokens_measured=False, tokens_by_model={})])
        self.assertTrue(result["untracked_runs_max"])

    def test_overrides_and_blocks_trip(self):
        runs = [run(i, overrides=["a", "b"], gate_events={"model_block": 3}) for i in range(1, 4)]
        result, _ = wires(runs)
        self.assertTrue(result["overrides_per_run_max"] and result["model_blocks_per_run_max"])

    def test_inherited_session_context_trips(self):
        result, _ = wires([run(i, orchestrator_ctx_start_k=420.0) for i in range(1, 4)])
        self.assertTrue(result["orchestrator_ctx_start_k_max"])

    def test_runs_without_start_context_are_not_judged_on_it(self):
        result, _ = wires([run(i) for i in range(1, 4)])
        self.assertNotIn("orchestrator_ctx_start_k_max", result)

    def test_report_renders(self):
        rows = mr.summarise([run(i) for i in range(1, 4)], PRICES)
        result, note = mr.check_tripwires(rows, TRIPWIRES)
        text = mr.markdown(rows, result, note, 10)
        self.assertIn("| 3 |", text)
        self.assertIn("🟢 ok", text)

    def test_export_sanitized_redacts_ids_and_overrides(self):
        raw = [run("CLIENTE-SECRET-42", overrides=["motivo interno confidencial"], _source="/privado/metrics.jsonl")]
        clean = mr.sanitize_runs(raw)
        self.assertEqual(clean[0]["run"], "run-1")
        self.assertEqual(clean[0]["overrides"], ["redacted"])
        self.assertNotIn("_source", clean[0])


class JourneysTest(unittest.TestCase):
    def test_runs_each_journey_and_keeps_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = rj.run_journeys(
                [{"name": "Pasa", "command": "echo bien"}, {"name": "Falla ya", "command": "echo mal; exit 3"}],
                tmp, timeout=30,
            )
            self.assertEqual([(r["ok"], r["exit"]) for r in results], [(True, 0), (False, 3)])
            with open(results[1]["log"]) as fh:
                self.assertIn("mal", fh.read())
            self.assertIn("❌ falla (exit 3)", rj.table(results))

    def test_timeout_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            [result] = rj.run_journeys([{"name": "lento", "command": "sleep 5"}], tmp, timeout=1)
            self.assertFalse(result["ok"])
            self.assertIn("timeout", rj.table([result]))

    def test_cli_without_journeys_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".claude"))
            with open(os.path.join(tmp, ".claude", "agent-playbook.json"), "w") as fh:
                json.dump({"journeys": []}, fh)
            out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_journeys.py"), "1"],
                                 cwd=tmp, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertIn("LÍMITES", out.stdout)


if __name__ == "__main__":
    unittest.main()
