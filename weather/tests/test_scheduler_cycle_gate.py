"""Regression guard for GitHub reusable-workflow scheduler semantics.

GitHub carries the CALLER event into the reusable workflow. A caller triggered
by push remains event_name='push'; it does not become 'workflow_call'.
"""
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/weather-lab-tests.yml"

class SchedulerCycleGateTests(unittest.TestCase):
    def test_scheduled_watch_skips_unnecessary_heavy_jobs(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        expected = ("github.event_name != 'pull_request' && "
                    "(!inputs.scheduled_watch || needs.cycle-watch.outputs.run_heavy == 'true')")
        self.assertEqual(source.count(expected), 4)
        self.assertNotIn("github.event_name != 'workflow_call' || !inputs.scheduled_watch", source)

    def test_scheduled_watch_does_not_run_unit_tests_repeatedly(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  test:\n    # Reusable workflows retain the caller's event", source)
        self.assertIn("    if: ${{ !inputs.scheduled_watch }}", source)

if __name__ == "__main__":
    unittest.main()
