import unittest
from datetime import datetime, timedelta

from detector.online import OnlineDetector, latency_cutoff

T0 = datetime(2026, 10, 4, 12, 0, 0)


def feed(detector, seconds, cpu, mem=100.0, start=0, service="cartservice"):
    flags = []
    for i in range(start, start + seconds, 5):
        reading = detector.update(T0 + timedelta(seconds=i), service, mem + (i % 3) * 0.1, cpu)
        flags.append(reading.flag if reading else None)
    return flags


class OnlineDetectorTests(unittest.TestCase):
    def test_steady_service_is_never_flagged(self):
        flags = feed(OnlineDetector(), 300, cpu=0.02)
        self.assertNotIn(True, flags)

    def test_cpu_jump_is_flagged_after_three_readings(self):
        d = OnlineDetector()
        feed(d, 60, cpu=0.02)
        flags = feed(d, 30, cpu=0.9, start=60)
        self.assertEqual(flags.index(True), 2)  # 3rd abnormal reading

    def test_no_flags_while_learning_first_baseline(self):
        flags = feed(OnlineDetector(), 45, cpu=5.0)
        self.assertEqual(set(flags), {None})

    def test_restart_suppresses_flags_during_warmup(self):
        d = OnlineDetector()
        feed(d, 60, cpu=0.02)
        d.reset_service("cartservice", T0 + timedelta(seconds=60))
        flags = feed(d, 100, cpu=0.9, start=60)
        self.assertNotIn(True, flags)

    def test_latency_cutoff_ignores_timeouts(self):
        cutoff = latency_cutoff([0.1, 0.11, 0.1, 5.0, 0.12, 5.0])
        self.assertLess(cutoff, 1.0)
        self.assertIsNone(latency_cutoff([5.0, 5.0]))


if __name__ == "__main__":
    unittest.main()
