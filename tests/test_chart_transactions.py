"""Exercise the real ASGI route without OpenAI, geocoding, or a database."""

import asyncio
import importlib
import json
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

import httpx2
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from sqlalchemy.orm import Session

from test_chart_request import VALID_REQUEST


def load_app():
    # Keep calculator real: analysis imports its ASPECT_ORB and PLANETS constants.
    # Importing calculator does not perform geocoding or calculate a chart.
    # Only stub interpreter to avoid its import-time OpenAI client creation.
    interpreter = ModuleType("astrology.interpreter")
    interpreter.interpret_chart = Mock()
    with patch.dict(sys.modules, {
        "astrology.interpreter": interpreter,
    }):
        app_module = importlib.import_module("main")
        charts = importlib.import_module("api.charts")
    return app_module.app, charts


async def post_json(app, payload):
    body = json.dumps(payload).encode()
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Future()

    async def send(message):
        sent.append(message)

    await app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/charts",
        "raw_path": b"/api/charts", "root_path": "", "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345), "server": ("test", 80),
    }, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    content = b"".join(item.get("body", b"") for item in sent if item["type"] == "http.response.body")
    return status, json.loads(content)


class ChartTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.charts = load_app()

    def setUp(self):
        self.charts.limiter.reset()
        self.db = Mock(spec=Session)

        def add(model):
            if isinstance(model, self.charts.Pet):
                model.pet_id = 1
            else:
                model.user_id = 2

        self.db.add.side_effect = add
        self.app.dependency_overrides[self.charts.get_db] = lambda: self.db
        self.addCleanup(self.app.dependency_overrides.clear)
        self.addCleanup(self.charts.limiter.reset)
        self.calculate = self.enterContext(patch.object(self.charts, "calculate_chart", return_value={"test_chart": True}))
        self.analyze = self.enterContext(patch.object(self.charts, "analyze_chart", return_value={"test_analysis": True}))
        self.interpret = self.enterContext(patch.object(self.charts, "interpret_chart", return_value={"test_interpretation": True}))

    def post(self, payload=None):
        return asyncio.run(post_json(self.app, VALID_REQUEST if payload is None else payload))

    def assert_failure(self, status, message):
        with self.assertLogs("api.charts", level="WARNING") as logs:
            actual_status, body = self.post()
        self.assertEqual(actual_status, status)
        self.assertEqual(body, {"detail": message})
        self.db.rollback.assert_called_once_with()
        self.assertNotIn("SECRET", " ".join(logs.output))
        self.assertTrue(all(record.exc_info is None for record in logs.records))

    def test_success(self):
        status, body = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(body, {
            "user_id": 2, "pet_id": 1,
            "chart": {"test_chart": True}, "analysis": {"test_analysis": True},
            "interpretation": {"test_interpretation": True},
        })
        self.db.commit.assert_called_once_with()
        self.db.rollback.assert_not_called()
        self.assertEqual(self.db.add.call_count, 2)
        self.assertEqual(self.db.flush.call_count, 2)
        self.assertEqual([call[0] for call in self.db.method_calls], ["add", "flush", "add", "flush", "commit"])

    def test_calculation_failure(self):
        self.calculate.side_effect = ValueError("SECRET internal details")
        self.assert_failure(500, "Unable to create chart. Please try again later.")
        self.db.commit.assert_not_called()
        self.analyze.assert_not_called()
        self.interpret.assert_not_called()

    def test_analysis_failure(self):
        self.analyze.side_effect = RuntimeError("SECRET implementation details")
        self.assert_failure(500, "Unable to create chart. Please try again later.")
        self.db.commit.assert_not_called()
        self.interpret.assert_not_called()

    def test_openai_errors(self):
        request = httpx2.Request("POST", "https://example.invalid")
        errors = [APIConnectionError(request=request), APITimeoutError(request=request)]
        for code, status in (("rate_limit_exceeded", 429), ("insufficient_quota", 429), ("credit_balance_exhausted", 402)):
            error_type = RateLimitError if status == 429 else APIStatusError
            errors.append(error_type("SECRET provider error", response=httpx2.Response(status, request=request), body={"code": code, "message": "SECRET"}))
        for error in errors:
            with self.subTest(error=type(error).__name__, code=getattr(error, "code", None)):
                self.charts.limiter.reset()
                self.db.reset_mock()
                self.interpret.side_effect = error
                self.assert_failure(503, "AI interpretation service is temporarily unavailable.")
                self.db.commit.assert_not_called()

    def test_interpretation_internal_failure(self):
        self.interpret.side_effect = RuntimeError("SECRET parsing failure")
        self.assert_failure(500, "Unable to create chart. Please try again later.")
        self.db.commit.assert_not_called()

    def test_commit_failure(self):
        self.db.commit.side_effect = RuntimeError("SECRET database details")
        self.assert_failure(500, "Unable to create chart. Please try again later.")
        self.db.commit.assert_called_once_with()

    def test_flush_failure(self):
        self.db.flush.side_effect = RuntimeError("SECRET SQL parameters")
        self.assert_failure(500, "Unable to create chart. Please try again later.")
        self.db.commit.assert_not_called()
        self.calculate.assert_not_called()

    def test_rollback_failure_still_returns_safe_response(self):
        self.calculate.side_effect = RuntimeError("SECRET")
        self.db.rollback.side_effect = RuntimeError("SECRET")
        self.assert_failure(500, "Unable to create chart. Please try again later.")

    def test_validation_422(self):
        status, body = self.post({**VALID_REQUEST, "user_name": "   "})
        self.assertEqual(status, 422)
        self.assertIsInstance(body["detail"], list)
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()
        self.calculate.assert_not_called()
        self.interpret.assert_not_called()

    def test_rate_limit_429(self):
        for _ in range(5):
            self.assertEqual(self.post()[0], 200)
        self.assertEqual(self.post()[0], 429)
        self.assertEqual(self.interpret.call_count, 5)
        self.assertEqual(self.db.commit.call_count, 5)
        self.db.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
