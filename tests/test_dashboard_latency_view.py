import unittest

from dashboard.latency_view import (
    build_page_latency_frame,
    find_largest_slowdown,
    find_unavailable_pages,
)


class DashboardLatencyViewTests(unittest.TestCase):
    def test_home_only_recording_discloses_missing_pages_and_not_slowdown(self):
        report = {
            "latency_s": {
                "before_seconds": 0.09,
                "during_seconds": 0.075,
                "increase_seconds": -0.015,
                "timeouts": 0,
                "timeouts_after_fault": 0,
            }
        }

        page_frame = build_page_latency_frame(report)

        self.assertEqual(page_frame["Page"].tolist(), ["Home"])
        self.assertEqual(find_unavailable_pages(page_frame), ["Product", "Cart"])
        self.assertIsNone(find_largest_slowdown(page_frame))

    def test_three_page_run_reports_the_largest_positive_slowdown(self):
        report = {
            "latency_s": {
                "before_seconds": 0.1,
                "during_seconds": 0.3,
                "increase_seconds": 0.2,
                "timeouts": 0,
                "timeouts_after_fault": 0,
            },
            "latency_product_s": {
                "before_seconds": 0.05,
                "during_seconds": 0.65,
                "increase_seconds": 0.6,
                "timeouts": 0,
                "timeouts_after_fault": 0,
            },
            "latency_cart_s": {
                "before_seconds": 0.05,
                "during_seconds": 0.64,
                "increase_seconds": 0.59,
                "timeouts": 0,
                "timeouts_after_fault": 0,
            },
        }

        page_frame = build_page_latency_frame(report)

        self.assertEqual(
            find_largest_slowdown(page_frame),
            ("Product", 0.6),
        )
        self.assertEqual(find_unavailable_pages(page_frame), [])

    def test_empty_recording_has_no_page_data_or_slowdown(self):
        page_frame = build_page_latency_frame({})

        self.assertIsNone(find_largest_slowdown(page_frame))
        self.assertEqual(
            find_unavailable_pages(page_frame),
            ["Home", "Product", "Cart"],
        )


if __name__ == "__main__":
    unittest.main()
