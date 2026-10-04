import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import merge_gate as mg  # noqa: E402

HEAD = "a" * 40
PROMOTED = datetime.datetime(2026, 10, 4, 16, 0, tzinfo=datetime.timezone.utc)


def pr(**over):
    base = {"number": 4, "state": "OPEN", "isDraft": False, "headRefOid": HEAD, "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN", "statusCheckRollup": [
                {"__typename": "CheckRun", "name": "tests", "status": "COMPLETED", "conclusion": "SUCCESS"}]}
    base.update(over)
    return base


def review(**over):
    base = {"head_sha": HEAD, "status": "completed", "conclusion": "success", "completed_at": "2026-10-04T16:05:00Z"}
    base.update(over)
    return base


def evaluate(p=None, r="default", enabled=True, deploy_ok=None, active=()):
    r = review() if r == "default" else r
    return mg.evaluate(p or pr(), r, PROMOTED, enabled, "claude-review", deploy_ok, list(active))


def state(result, row):
    return result[1][row - 1][1]


class VerdictTest(unittest.TestCase):
    def test_all_green_is_ready(self):
        self.assertEqual(evaluate()[0], mg.OK)

    def test_verdict_on_an_old_commit_is_not_anchored(self):
        self.assertEqual(state(evaluate(r=review(head_sha="b" * 40)), 1), mg.WAIT)

    def test_verdict_before_promotion_is_stale(self):
        self.assertEqual(state(evaluate(r=review(completed_at="2026-10-04T15:59:00Z")), 1), mg.WAIT)

    def test_changes_requested_stops_the_run(self):
        result = evaluate(r=review(conclusion="failure"))
        self.assertEqual((state(result, 1), result[0]), (mg.FAIL, mg.FAIL))

    def test_skipped_review_asks_for_a_draft_cycle(self):
        result = evaluate(r=review(conclusion="skipped"))
        self.assertEqual(state(result, 1), mg.WAIT)
        self.assertIn("borrador", result[1][0][2])

    def test_missing_or_running_review_waits(self):
        self.assertEqual(state(evaluate(r=None), 1), mg.WAIT)
        self.assertEqual(state(evaluate(r=review(status="in_progress")), 1), mg.WAIT)

    def test_without_review_bot_the_internal_review_counts(self):
        self.assertEqual(state(evaluate(r=None, enabled=False), 1), mg.OK)


class ChecksTest(unittest.TestCase):
    def test_failed_check_stops(self):
        p = pr(statusCheckRollup=[{"__typename": "CheckRun", "name": "tests", "status": "COMPLETED", "conclusion": "FAILURE"}])
        self.assertEqual(state(evaluate(p), 2), mg.FAIL)

    def test_pending_check_waits(self):
        p = pr(statusCheckRollup=[{"__typename": "CheckRun", "name": "tests", "status": "IN_PROGRESS"}])
        self.assertEqual(state(evaluate(p), 2), mg.WAIT)

    def test_review_check_is_judged_only_as_the_verdict(self):
        p = pr(statusCheckRollup=[{"__typename": "CheckRun", "name": "claude-review", "status": "COMPLETED", "conclusion": "FAILURE"}])
        self.assertEqual(state(evaluate(p), 2), mg.OK)

    def test_no_checks_passes_but_says_so(self):
        result = evaluate(pr(statusCheckRollup=[]))
        self.assertEqual(state(result, 2), mg.OK)
        self.assertIn("LÍMITES", result[1][1][2])

    def test_status_contexts_count(self):
        p = pr(statusCheckRollup=[{"__typename": "StatusContext", "context": "ci/legacy", "state": "PENDING"}])
        self.assertEqual(state(evaluate(p), 2), mg.WAIT)


class MergeableTest(unittest.TestCase):
    def test_conflicts_stop(self):
        self.assertEqual(state(evaluate(pr(mergeable="CONFLICTING", mergeStateStatus="DIRTY")), 3), mg.FAIL)

    def test_behind_or_unknown_waits(self):
        self.assertEqual(state(evaluate(pr(mergeStateStatus="BEHIND")), 3), mg.WAIT)
        self.assertEqual(state(evaluate(pr(mergeable="UNKNOWN")), 3), mg.WAIT)

    def test_draft_waits_and_closed_stops(self):
        self.assertEqual(state(evaluate(pr(isDraft=True)), 3), mg.WAIT)
        self.assertEqual(state(evaluate(pr(state="CLOSED")), 3), mg.FAIL)


class DeployTest(unittest.TestCase):
    def test_deploy_check_command_decides(self):
        self.assertEqual(state(evaluate(deploy_ok=False), 4), mg.WAIT)
        self.assertEqual(state(evaluate(deploy_ok=True, active=["deploy"]), 4), mg.OK)

    def test_runs_in_progress_on_base_wait(self):
        self.assertEqual(state(evaluate(active=["deploy"]), 4), mg.WAIT)


if __name__ == "__main__":
    unittest.main()
