import unittest

from remediator.live_heal import check_guard, is_recovered

PARAMS = {"cpu_cores": (0.02, 0.01), "memory_mb": (100.0, 10.0)}
OK = dict(last_action={}, locked=set(), actions_done=0, max_actions=3,
          cooldown_s=300, now=1000.0)


def guard(**over):
    args = {**OK, **over}
    return check_guard(args.pop("context", "kind-aiops"),
                       args.pop("namespace", "default"),
                       args.pop("service", "cartservice"), **args)


class GuardTests(unittest.TestCase):
    def test_allowlisted_target_is_allowed(self):
        self.assertIsNone(guard())

    def test_wrong_context_is_refused(self):
        self.assertIn("context", guard(context="prod-cluster"))

    def test_wrong_namespace_is_refused(self):
        self.assertIn("namespace", guard(namespace="kube-system"))

    def test_non_allowlisted_service_is_refused(self):
        self.assertIn("allowlisted", guard(service="redis-cart"))

    def test_cooldown_lock_and_budget(self):
        self.assertIn("cooldown", guard(last_action={"cartservice": 900.0}))
        self.assertIn("locked", guard(locked={"cartservice"}))
        self.assertIn("budget", guard(actions_done=3))


class VerifyTests(unittest.TestCase):
    good = [{"cpu_cores": 0.03, "memory_mb": 105.0}] * 4

    def test_recovered_when_back_in_baseline(self):
        ok, _ = is_recovered(PARAMS, self.good, 0.5, [0.1, 0.12, 0.11])
        self.assertTrue(ok)

    def test_still_hot_cpu_fails(self):
        bad = [{"cpu_cores": 0.9, "memory_mb": 105.0}] * 4
        ok, why = is_recovered(PARAMS, bad, 0.5, [0.1])
        self.assertFalse(ok)
        self.assertIn("cpu_cores", why)

    def test_timeout_during_verification_fails(self):
        ok, _ = is_recovered(PARAMS, self.good, 0.5, [0.1, 5.0, 0.1])
        self.assertFalse(ok)

    def test_too_few_samples_fails(self):
        ok, _ = is_recovered(PARAMS, self.good[:2], 0.5, [0.1])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
