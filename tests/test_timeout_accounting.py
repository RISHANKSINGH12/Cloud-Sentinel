import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

from eval.evaluate_test import MANIFEST, evaluate_run


class TimeoutAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = pd.read_csv(MANIFEST, dtype=str).fillna("")
        cls.faults = pd.read_csv(
            ROOT / "eval" / "faults.csv",
            parse_dates=["start", "end"],
        )

    def evaluate_recording(self, filename):
        matches = self.manifest[
            (self.manifest["file"] == filename)
            & (self.manifest["role"] == "test")
        ]
        self.assertEqual(len(matches), 1)
        return evaluate_run(matches.iloc[0], self.faults)

    def test_frontend_timeout_sentinels_are_not_scored_as_latency(self):
        result = self.evaluate_recording("data_cpu_hog_frontend_1.csv")

        self.assertFalse(result["v2_latency_detected"])
        self.assertEqual(result["v2_latency_false_rows"], 0)
        self.assertEqual(result["timeouts_during_fault"]["latency_s"], 4)
        self.assertEqual(result["timeouts_after_fault"]["latency_s"], 14)

    def test_successful_cartservice_delay_is_still_detected(self):
        result = self.evaluate_recording("data_net_delay_cartservice_2.csv")

        self.assertTrue(result["page_latency"]["latency_s"]["detected"])
        self.assertEqual(result["page_latency"]["latency_s"]["delay_s"], 23.0)
        self.assertEqual(result["timeouts_during_fault"]["latency_s"], 0)
        self.assertEqual(result["timeouts_after_fault"]["latency_s"], 0)


if __name__ == "__main__":
    unittest.main()
