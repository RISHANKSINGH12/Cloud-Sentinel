import unittest
from pathlib import Path

from eval.evaluate_healthy_latency import score_recording


ROOT = Path(__file__).resolve().parents[1]
HEALTHY_RECORDINGS = (
    "data_healthy_pages.csv",
    "data_healthy_pages_2_complete.csv",
)
PAGE_COLUMNS = ("latency_s", "latency_product_s", "latency_cart_s")


class HealthyLatencyEvaluationTests(unittest.TestCase):
    def test_complete_healthy_recordings_have_no_latency_alerts_or_timeouts(self):
        for filename in HEALTHY_RECORDINGS:
            with self.subTest(recording=filename):
                results = score_recording(ROOT / "data" / filename)

                self.assertEqual(set(results), set(PAGE_COLUMNS))
                for result in results.values():
                    self.assertGreater(result["scored_probes"], 0)
                    self.assertEqual(result["alerts"], 0)
                    self.assertEqual(result["flagged_samples"], 0)
                    self.assertEqual(result["timeouts"], 0)


if __name__ == "__main__":
    unittest.main()
