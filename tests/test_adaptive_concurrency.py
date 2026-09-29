import unittest

from ai_product_factory.adaptive_concurrency import ConcurrencyPressure,decide_effective_concurrency


class AdaptiveConcurrencyTests(unittest.TestCase):
    def test_healthy_independent_work_uses_profile_ceiling(self):
        out=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=5,quota_status="normal"),
        )
        self.assertEqual(out.effective_concurrency,3)

    def test_runnable_work_bounds_concurrency(self):
        out=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=1,quota_status="normal"),
        )
        self.assertEqual(out.effective_concurrency,1)

    def test_unknown_paid_cost_blocks_execution(self):
        out=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=3,unknown_paid_cost=True),
        )
        self.assertEqual(out.effective_concurrency,0)
        self.assertTrue(any("unknown paid cost" in x for x in out.reasons))

    def test_critical_or_blocked_quota_blocks_execution(self):
        for status in ("critical","blocked"):
            out=decide_effective_concurrency(
                agent_key="ui",profile_ceiling=2,
                pressure=ConcurrencyPressure(runnable_work=2,quota_status=status),
            )
            self.assertEqual(out.effective_concurrency,0)

    def test_attention_quota_caps_at_one(self):
        out=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=3,quota_status="attention"),
        )
        self.assertEqual(out.effective_concurrency,1)

    def test_high_conflict_or_repair_rate_caps_at_one(self):
        conflict=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=3,conflict_rate=.30),
        )
        repair=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=3,repair_rate=.40),
        )
        self.assertEqual(conflict.effective_concurrency,1)
        self.assertEqual(repair.effective_concurrency,1)

    def test_low_first_pass_yield_caps_at_one(self):
        out=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=3,first_pass_yield=.50),
        )
        self.assertEqual(out.effective_concurrency,1)

    def test_high_ci_queue_latency_caps_at_one(self):
        out=decide_effective_concurrency(
            agent_key="development",profile_ceiling=3,
            pressure=ConcurrencyPressure(runnable_work=3,ci_queue_minutes=25),
        )
        self.assertEqual(out.effective_concurrency,1)


if __name__=="__main__":
    unittest.main()
