"""Transaction regression tests; no network, MySQL, or OpenAI calls required."""
import asyncio
import json
import threading
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from openai import APIError
from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api import charts
from db.database import Base, get_db
from db.models import Pet, User
from main import app


# SQLite needs INTEGER for generated primary keys. Production types stay unchanged.
@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kwargs):
    return "INTEGER"


HUMAN = dict(user_name="Visitor", user_email="visitor@example.com",
             user_birth_date="1990-01-02", user_birth_time="12:30:00", user_city="Seoul")
PET = dict(pet_name="Luna", pet_type="cat", pet_gender="female", pet_breed="Mix",
           pet_birth_date="2020-01-02", pet_city="Seoul")
CHART = {"positions": [1, 2], "city": "Seoul"}
ANALYSIS = {"elements": {"fire": 2}}
COMPATIBILITY = {"score": 80}


async def post(path, payload):
    """Exercise the real ASGI route and validation without adding a test client library."""
    messages = []
    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
               "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
               "query_string": b"", "headers": [(b"content-type", b"application/json")],
               "client": ("127.0.0.1", 1234), "server": ("test", 80), "root_path": ""},
              receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(data)


class ChartTransactionsTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, "connect", lambda connection, record:
                     connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.events = []
        event.listen(self.engine, "checkout", lambda *args: self.events.append("checkout"))
        event.listen(self.engine, "checkin", lambda *args: self.events.append("checkin"))
        event.listen(self.engine, "before_cursor_execute", lambda *args: self.events.append("sql"))
        self.sessions = []

        def dependency():
            with Session(self.engine) as session:
                self.sessions.append(session)
                owner_thread = threading.get_ident()
                def record(operation):
                    def listener(*args):
                        self.assertEqual(threading.get_ident(), owner_thread)
                        self.events.append(operation)
                    return listener
                event.listen(session, "before_flush", record("flush"))
                event.listen(session, "before_commit", record("commit"))
                yield session

        app.dependency_overrides[get_db] = dependency
        self.addCleanup(app.dependency_overrides.clear)
        self.stack.enter_context(patch.object(app.state.limiter, "enabled", False))
        self.stack.enter_context(patch.object(charts, "calculate_chart", return_value=CHART))
        self.stack.enter_context(patch.object(charts, "analyze_chart", return_value=ANALYSIS))
        self.stack.enter_context(patch.object(charts, "analyze_compatibility", return_value=COMPATIBILITY))
        self.stack.enter_context(patch.object(charts, "prepare_chart_for_ai",
                                             return_value={"chart": CHART, "analysis": ANALYSIS}))
        self.barrier = None
        self.worker_threads = set()
        for name in ("human", "pet", "compatibility"):
            self.stack.enter_context(patch.object(charts, "interpret_" + name,
                                                  side_effect=self.interpret(name)))

    def interpret(self, name):
        def run(**kwargs):
            # Inspect pool events, never hand a SQLAlchemy Session to a GPT worker.
            self.assertNotIn("checkout", self.events)
            self.assertNotIn("sql", self.events)
            self.assertNotIn("flush", self.events)
            self.assertNotIn("commit", self.events)
            self.worker_threads.add(threading.get_ident())
            self.events.append("gpt_" + name)
            if self.barrier:
                self.barrier.wait(timeout=5)
            return {"text": name}
        return run

    def call(self, compatibility=False, payload=None):
        path = "/api/charts/compatibility" if compatibility else "/api/charts/humans"
        return asyncio.run(post(path, payload if payload is not None else
                                ({**HUMAN, **PET} if compatibility else HUMAN)))

    def counts(self):
        with Session(self.engine) as session:
            return tuple(session.scalar(select(func.count()).select_from(model))
                         for model in (User, Pet))

    def test_human_success_contract_and_order(self):
        status, result = self.call()
        self.assertEqual(status, 200)
        self.assertEqual(result, {"user_id": 1, "interpretation": {"text": "human"},
                                  "analysis": ANALYSIS, "chart": CHART})
        self.assertIs(type(result["user_id"]), int)
        self.assertLess(self.events.index("gpt_human"), self.events.index("checkout"))
        self.assertFalse(self.sessions[0].in_transaction())
        self.assertEqual(self.events.count("checkout"), self.events.count("checkin"))
        self.assertEqual(self.counts(), (1, 0))
        with Session(self.engine) as session:
            self.assertEqual(session.get(User, 1).user_name, HUMAN["user_name"])

    def test_compatibility_success_contract_fk_parallel_and_order(self):
        self.barrier = threading.Barrier(3)
        status, result = self.call(True)
        self.assertEqual(status, 200)
        self.assertEqual(result, {"user_id": 1, "pet_id": 1,
            "human": {"interpretation": {"text": "human"}, "analysis": ANALYSIS, "chart": CHART},
            "pet": {"interpretation": {"text": "pet"}, "analysis": ANALYSIS, "chart": CHART},
            "compatibility": {"interpretation": {"text": "compatibility"}, "analysis": COMPATIBILITY}})
        self.assertEqual(len(self.worker_threads), 3)
        self.assertEqual(sum(e.startswith("gpt_") for e in self.events), 3)
        self.assertEqual(set(self.events[:3]), {"gpt_human", "gpt_pet", "gpt_compatibility"})
        self.assertFalse(self.sessions[0].in_transaction())
        self.assertEqual(self.events.count("checkout"), self.events.count("checkin"))
        self.assertEqual(self.counts(), (1, 1))
        with Session(self.engine) as session:
            pet = session.get(Pet, result["pet_id"])
            self.assertEqual(pet.user_id, result["user_id"])
            self.assertEqual(pet.user.user_name, HUMAN["user_name"])

    def test_gpt_failures_do_not_save(self):
        for compatibility, name in ((False, "human"), (True, "human"),
                                    (True, "pet"), (True, "compatibility")):
            with self.subTest(compatibility=compatibility, name=name):
                self.events.clear()
                with patch.object(charts, "interpret_" + name,
                                  side_effect=APIError("unavailable", request=None, body=None)):
                    status, result = self.call(compatibility)
                self.assertEqual((status, result), (503, {"detail":
                    "AI interpretation service is temporarily unavailable."}))
                self.assertNotIn("checkout", self.events)
                self.assertEqual(self.counts(), (0, 0))

    def test_internal_gpt_failure_contract(self):
        with patch.object(charts, "interpret_human", side_effect=ValueError("invalid")):
            self.assertEqual(self.call(), (500, {"detail":
                "Unable to create chart. Please try again later."}))
        self.assertNotIn("checkout", self.events)
        self.assertEqual(self.counts(), (0, 0))

    def test_commit_failures_roll_back_all_inserts(self):
        for compatibility in (False, True):
            with self.subTest(compatibility=compatibility):
                self.events.clear()
                def fail_commit(session):
                    # Both inserts have really executed before the simulated failure.
                    self.assertEqual(len(session.identity_map), 2 if compatibility else 1)
                    raise RuntimeError("commit failed")
                with patch.object(Session, "commit", fail_commit):
                    status, result = self.call(compatibility)
                self.assertEqual((status, result), (500, {"detail":
                    "Unable to create chart. Please try again later."}))
                self.assertFalse(self.sessions[-1].in_transaction())
                self.assertEqual(self.counts(), (0, 0))

    def test_pet_insert_failure_rolls_back_user(self):
        def fail_pet_insert(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO pets"):
                raise RuntimeError("pet insert failed")
        event.listen(self.engine, "before_cursor_execute", fail_pet_insert)
        status, result = self.call(True)
        self.assertEqual(status, 500)
        self.assertEqual(result, {"detail": "Unable to create chart. Please try again later."})
        self.assertEqual(self.counts(), (0, 0))

    def test_validation_contract(self):
        status, result = self.call(payload={**HUMAN, "user_email": "invalid"})
        self.assertEqual(status, 422)
        self.assertEqual(result["detail"][0]["loc"], ["body", "user_email"])
        self.assertEqual(self.counts(), (0, 0))

    def test_timing_logs_retained(self):
        for compatibility, prefix in ((False, "human_timing"), (True, "compatibility_timing")):
            self.events.clear()
            with self.assertLogs(charts.timing_logger, level="INFO") as logs:
                self.assertEqual(self.call(compatibility)[0], 200)
            for step in ("db_save_commit", "api_total", "human_gpt_interpretation"):
                self.assertTrue(any(prefix + " step=" + step in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
