"""Safe calculation diagnostics without external geocoding calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.geocoding import (GeocodingPermissionError, GeocodingTimeoutError,
                                GeocodingRateLimitError, GeocodingNotFoundError)

from astrology import calculator
from tests import test_chart_transactions as transaction_tests


class CalculationDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.geocoder_patch = patch.object(calculator, "geocode_place")
        self.geocoder = self.geocoder_patch.start()
        self.addCleanup(self.geocoder_patch.stop)
        self.geocoder.return_value = SimpleNamespace(latitude=37.5665, longitude=126.978)
        self.finder_patch = patch.object(calculator, "TimezoneFinder")
        self.finder = self.finder_patch.start()
        self.addCleanup(self.finder_patch.stop)
        self.finder.return_value.timezone_at.return_value = "Asia/Seoul"

    def call(self, birth_time=time(12)):
        return calculator.calculate_chart(date(1990, 1, 15), birth_time, "PRIVATE-CITY")

    def check_failure(self, step, exc, target, **options):
        with patch.object(target[0], target[1], **options):
            with self.assertLogs(calculator.logger, level="ERROR") as captured:
                with self.assertRaises(type(exc)) as raised:
                    self.call()
        if "side_effect" in options:
            self.assertIs(raised.exception, exc)
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertIn("internal_step=" + step, record.getMessage())
        self.assertIn("exception_type=" + type(exc).__name__, record.getMessage())
        self.assertNotIn("PRIVATE", record.getMessage())
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.stack_info)

    def test_geocoder_errors_are_safe_and_preserved(self):
        for error_type in (GeocodingRateLimitError, GeocodingTimeoutError, GeocodingPermissionError):
            with self.subTest(error=error_type):
                exc = error_type("PRIVATE-CITY PRIVATE-KEY PRIVATE-RESPONSE")
                self.check_failure("geocoding", exc,
                    (calculator, "geocode_place"), side_effect=exc)

    def test_missing_city(self):
        exc = GeocodingNotFoundError()
        self.check_failure("geocoding", exc,
                           (calculator, "geocode_place"), side_effect=exc)

    def test_missing_timezone(self):
        self.check_failure("timezone_lookup", ValueError(),
                           (self.finder.return_value, "timezone_at"), return_value=None)

    def test_timezone_initialization_failure(self):
        exc = OSError("PRIVATE-file")
        self.check_failure("timezone_finder_initialization", exc,
                           (calculator, "TimezoneFinder"), side_effect=exc)

    def test_planet_and_house_failures(self):
        for name, step in (("calculate_planets", "planet_calculation"),
                           ("calculate_houses", "house_calculation")):
            exc = RuntimeError("PRIVATE-DETAIL")
            self.check_failure(step, exc, (calculator, name), side_effect=exc)

    def test_repeated_city_is_currently_not_cached(self):
        self.call()
        self.call()
        self.assertEqual(self.geocoder.call_count, 2)
        self.assertEqual(self.finder.call_count, 2)

    def test_parallel_calculations_match_sequential_results(self):
        # Actual Swiss Ephemeris calculations; only external lookup objects are mocked.
        for birth_time in (None, time(12)):
            expected = self.call(birth_time)
            with ThreadPoolExecutor(max_workers=20) as executor:
                results = list(executor.map(lambda _: self.call(birth_time), range(20)))
            self.assertTrue(all(result == expected for result in results))


class ApiCalculationDiagnosticsTest(unittest.TestCase):
    setUp = transaction_tests.ChartTransactionsTest.setUp
    interpret = transaction_tests.ChartTransactionsTest.interpret
    call = transaction_tests.ChartTransactionsTest.call
    counts = transaction_tests.ChartTransactionsTest.counts

    def test_api_safe_exception_type_and_unchanged_error(self):
        for compatibility in (False, True):
            with self.subTest(compatibility=compatibility):
                self.events.clear()
                with patch("api.charts.calculate_chart", side_effect=GeocodingTimeoutError("PRIVATE-URL")):
                    with self.assertLogs("api.charts", level="WARNING") as captured:
                        status, result = self.call(compatibility)
                self.assertEqual(status, 503)
                self.assertEqual(result, {"detail": "Location lookup service is temporarily unavailable."})
                self.assertIn("stage=geocoding category=timeout exception_type=GeocodingTimeoutError", captured.output[0])
                self.assertNotIn("PRIVATE", captured.output[0])
                self.assertIsNone(captured.records[0].exc_info)
                self.assertNotIn("checkout", self.events)
                self.assertEqual(self.counts(), (0, 0))
