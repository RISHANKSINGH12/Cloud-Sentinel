import unittest

from remediator.recovery_simulation import simulate_recovery


class RecoverySimulationTests(unittest.TestCase):
    def test_allowlisted_scenarios_detect_act_and_pass_health_check(self):
        for fault_kind in ("cpu_hog", "mem_leak", "net_delay"):
            with self.subTest(fault_kind=fault_kind):
                result = simulate_recovery(fault_kind, "demo-service")

                self.assertEqual(result.fault_kind, fault_kind)
                self.assertEqual(result.target_service, "demo-service")
                self.assertTrue(result.detected_signal)
                self.assertTrue(result.action)
                self.assertFalse(result.before.healthy)
                self.assertTrue(result.after.healthy)
                self.assertTrue(result.recovered)

    def test_unknown_fault_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "No sandbox recovery scenario"):
            simulate_recovery("unknown", "demo-service")

    def test_empty_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "target service is required"):
            simulate_recovery("cpu_hog", " ")


if __name__ == "__main__":
    unittest.main()
