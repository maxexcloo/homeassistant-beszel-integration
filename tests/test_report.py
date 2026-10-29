"""Dependency-free tests; also run directly with python tests/test_report.py."""

import importlib.util
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "beszel_report",
    Path(__file__).parents[1] / "custom_components" / "beszel" / "report.py",
)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
NOW = datetime(2026, 10, 28, tzinfo=UTC)


class ReportTests(unittest.TestCase):
    """Validate actual production normalization without Home Assistant stubs."""

    def test_timestamp_roundtrip_and_old_diagnostic(self):
        for age in (0, 300, 301, 600, 86400):
            with self.subTest(age=age):
                old = NOW - timedelta(seconds=age)
                self.assertEqual(
                    report.container_timestamp(old.timestamp() * 1000, NOW), old
                )
                self.assertEqual(report.statistics_timestamp(old.isoformat(), NOW), old)

    def test_bad_container_timestamp(self):
        for value in (
            None,
            True,
            False,
            "1793145600000",
            -1,
            0,
            float("nan"),
            float("inf"),
            10**400,
            (NOW.timestamp() + 1) * 1000,
        ):
            with self.subTest(value=value):
                self.assertIsNone(report.container_timestamp(value, NOW))

    def test_seconds_are_never_treated_as_current_milliseconds(self):
        timestamp = report.container_timestamp(NOW.timestamp(), NOW)
        self.assertGreater((NOW - timestamp).total_seconds(), 300)

    def test_bad_statistics_timestamp(self):
        for value in (
            None,
            1234,
            "bad",
            "2026-10-28T00:00:00",
            (NOW + timedelta(seconds=1)).isoformat(),
        ):
            with self.subTest(value=value):
                self.assertIsNone(report.statistics_timestamp(value, NOW))
        self.assertEqual(
            report.statistics_timestamp("2026-10-28T01:00:00+01:00", NOW), NOW
        )
        self.assertEqual(report.statistics_timestamp("2026-10-28T00:00:00Z", NOW), NOW)

    def test_every_health_state(self):
        for value, expected in (
            (0, "no_health_data"),
            (1, "starting"),
            (2, "healthy"),
            (3, "unhealthy"),
            (None, "unknown"),
            (False, "unknown"),
            (True, "unknown"),
            ("2", "unknown"),
            (4, "unknown"),
            (1.5, "unknown"),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    report.container_value({"health": value}, "health", NOW), expected
                )

    def test_metrics_missing_not_zero(self):
        for key in ("cpu", "memory", "net"):
            for value in (None, True, "12", -1, float("nan"), float("inf"), 10**400):
                with self.subTest(key=key, value=value):
                    self.assertIsNone(report.container_value({key: value}, key, NOW))
            self.assertIsNone(report.container_value({}, key, NOW))
            self.assertEqual(report.container_value({key: 0}, key, NOW), 0)

    def test_units_and_cpu_range(self):
        self.assertEqual(report.container_value({"memory": 100}, "memory", NOW), 104.86)
        self.assertEqual(
            report.container_value({"net": 1_000_000}, "net", NOW), 1_000_000
        )
        self.assertEqual(report.container_value({"cpu": 100}, "cpu", NOW), 100)
        self.assertIsNone(report.container_value({"cpu": 101}, "cpu", NOW))


if __name__ == "__main__":
    unittest.main()
