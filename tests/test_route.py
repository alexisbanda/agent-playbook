import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import route  # noqa: E402

ROUTING = route.load_routing()


def decide(prompt, model=None, profile="reduced"):
    return route.decide(prompt, model, profile, ROUTING)


class HeaderTest(unittest.TestCase):
    def test_parses_role_class_and_override(self):
        role, klass, override = route.parse_header("ROLE: coder · CLASS: money\nOVERRIDE: hotfix urgente\nresto")
        self.assertEqual((role, klass, override), ("coder", "money", "hotfix urgente"))

    def test_accepts_pipe_separator(self):
        self.assertEqual(route.parse_header("ROLE: reader | CLASS: reader")[:2], ("reader", "reader"))

    def test_header_must_be_near_the_top(self):
        self.assertIsNone(route.parse_header("a\nb\nc\nROLE: coder · CLASS: standard")[0])


class DecisionTest(unittest.TestCase):
    def test_missing_header_blocks(self):
        self.assertEqual(decide("haz el fix", "sonnet")["decision"], "block")

    def test_unknown_class_blocks(self):
        self.assertEqual(decide("ROLE: coder · CLASS: whatever")["decision"], "block")

    def test_no_model_injects_class_default(self):
        result = decide("ROLE: reader · CLASS: reader")
        self.assertEqual((result["decision"], result["model"]), ("inject", "haiku"))

    def test_allowed_model_passes(self):
        self.assertEqual(decide("ROLE: coder · CLASS: standard", "opus")["decision"], "allow")

    def test_disallowed_model_blocks(self):
        result = decide("ROLE: coder · CLASS: critical", "sonnet")
        self.assertEqual(result["decision"], "block")
        self.assertIn("opus", result["reason"])

    def test_override_lets_disallowed_model_pass_and_records_reason(self):
        result = decide("ROLE: reader · CLASS: reader\nOVERRIDE: repo enorme", "opus")
        self.assertEqual((result["decision"], result["override"]), ("allow", "repo enorme"))

    def test_flagship_never_writes_code_even_with_override(self):
        for role in ("coder", "patriot"):
            result = decide(f"ROLE: {role} · CLASS: critical\nOVERRIDE: lo necesito", "fable")
            self.assertEqual(result["decision"], "block", role)

    def test_flagship_can_review_or_read_when_class_allows(self):
        self.assertEqual(decide("ROLE: reviewer · CLASS: review\nOVERRIDE: segunda opinión", "fable")["decision"], "allow")

    def test_full_model_id_maps_to_tier(self):
        self.assertEqual(decide("ROLE: coder · CLASS: standard", "claude-sonnet-5")["tier"], "standard")

    def test_unknown_model_blocks(self):
        self.assertEqual(decide("ROLE: coder · CLASS: standard", "gpt-9")["decision"], "block")

    def test_unknown_profile_blocks(self):
        self.assertEqual(decide("ROLE: coder · CLASS: standard", "sonnet", "huge")["decision"], "block")


class ProfileTest(unittest.TestCase):
    def test_reduced_maps_full_classes(self):
        result = decide("ROLE: coder · CLASS: money")
        self.assertEqual((result["class"], result["model"]), ("critical", "opus"))

    def test_full_keeps_specific_classes(self):
        self.assertEqual(decide("ROLE: coder · CLASS: mechanical", "opus", "full")["decision"], "block")

    def test_full_accepts_reduced_critical(self):
        result = decide("ROLE: coder · CLASS: critical", None, "full")
        self.assertEqual((result["class"], result["model"]), ("critical", "opus"))

    def test_every_class_default_is_allowed(self):
        for name, profile in ROUTING["profiles"].items():
            for klass, rule in profile["classes"].items():
                self.assertIn(rule["default"], rule["allowed"], f"{name}/{klass}")

    def test_every_alias_points_to_an_existing_class(self):
        for name, profile in ROUTING["profiles"].items():
            for alias, target in profile["class_aliases"].items():
                self.assertIn(target, profile["classes"], f"{name}: {alias} -> {target}")

    def test_high_risk_classes_stay_premium_only_in_both_profiles(self):
        for klass in ("contract", "money", "security"):
            for profile in ("reduced", "full"):
                result = decide(f"ROLE: coder · CLASS: {klass}", "sonnet", profile)
                self.assertEqual(result["decision"], "block", f"{profile}/{klass}")


class SessionTest(unittest.TestCase):
    def test_accepts_standard_and_above(self):
        for model in ("claude-sonnet-5", "claude-opus-5-5", "claude-fable-5-1", "opus"):
            self.assertEqual(route.check_session(model, ROUTING)["decision"], "allow", model)

    def test_rejects_economy(self):
        self.assertEqual(route.check_session("claude-haiku-4-5", ROUTING)["decision"], "block")


class PinsTest(unittest.TestCase):
    def test_reports_missing_pins(self):
        self.assertEqual(len(route.missing_pins(ROUTING, env={})), 4)
        env = {t["pin_env"]: t["model_id"] for t in ROUTING["tiers"].values()}
        self.assertEqual(route.missing_pins(ROUTING, env=env), [])


class AgyRuntimeTest(unittest.TestCase):
    def test_recognizes_agy_aliases_and_gemini_models(self):
        self.assertEqual(route.tier_of("flash", ROUTING), "economy")
        self.assertEqual(route.tier_of("inherit", ROUTING), "standard")
        self.assertEqual(route.tier_of("pro", ROUTING), "premium")
        self.assertEqual(route.tier_of("gemini-2.5-pro", ROUTING), "premium")

    def test_injects_agy_model_alias_when_runtime_is_agy(self):
        reader = route.decide("ROLE: reader · CLASS: reader", None, "reduced", ROUTING, runtime="agy")
        self.assertEqual((reader["decision"], reader["model"]), ("inject", "flash"))
        coder = route.decide("ROLE: coder · CLASS: standard", None, "reduced", ROUTING, runtime="agy")
        self.assertEqual((coder["decision"], coder["model"]), ("inject", "inherit"))
        crit = route.decide("ROLE: coder · CLASS: critical", None, "reduced", ROUTING, runtime="agy")
        self.assertEqual((crit["decision"], crit["model"]), ("inject", "pro"))


if __name__ == "__main__":
    unittest.main()
