import threading
import unittest
from unittest.mock import Mock, patch

from openai import APIError
from starlette.requests import Request

from api import charts
from schemas.chart import CompatibilityChartRequest, HumanChartRequest


class CompatibilityParallelTests(unittest.TestCase):
    def setUp(self):
        self.payload = CompatibilityChartRequest(
            user_name='Private', user_email='private@example.com',
            user_birth_date='1990-01-01', user_city='Seoul',
            pet_name='Pet', pet_type='cat', pet_gender='male',
            pet_breed='mixed', pet_birth_date='2020-01-01', pet_city='Busan',
        )
        self.request = Request({'type': 'http', 'headers': []})
        self.owner = threading.get_ident()
        self.db = Mock()
        self.db.add.side_effect = self.add
        for method in ('flush', 'commit', 'rollback'):
            getattr(self.db, method).side_effect = self.assert_db_thread

    def assert_db_thread(self):
        self.assertEqual(threading.get_ident(), self.owner)

    def add(self, row):
        self.assert_db_thread()
        if hasattr(row, 'user_name'):
            row.user_id = 1
        else:
            row.pet_id = 2
            self.assertEqual(row.user_id, 1)

    def exercise(self, failure=None, api_error=False):
        barrier = threading.Barrier(3)
        finished = []
        worker_ids = set()
        lock = threading.Lock()
        error = APIError('private error', Mock(), body=None) if api_error else RuntimeError('private error')

        def worker(name):
            def call(**kwargs):
                self.assertNotIn('db', kwargs)
                self.assertNotEqual(threading.get_ident(), self.owner)
                if name == 'compatibility':
                    self.assertEqual(kwargs['compatibility_analysis'], {'aspects': []})
                    self.assertNotIn('interpretation', kwargs['human'])
                    self.assertNotIn('interpretation', kwargs['pet'])
                    self.assertEqual(kwargs['human']['analysis'], {'prepared': True})
                with lock:
                    worker_ids.add(threading.get_ident())
                # All three calls must start before any is allowed to finish.
                barrier.wait(timeout=3)
                with lock:
                    finished.append(name)
                if failure == name:
                    raise error
                return name
            return call

        mocks = {
            'calculate_chart': Mock(return_value={'planets': {}}),
            'analyze_chart': Mock(return_value={'individual': True}),
            'analyze_compatibility': Mock(return_value={'aspects': []}),
            'prepare_chart_for_ai': Mock(return_value={'chart': {}, 'analysis': {'prepared': True}}),
            'interpret_human': worker('human'),
            'interpret_pet': worker('pet'),
            'interpret_compatibility': worker('compatibility'),
        }
        records = []
        with patch.multiple(charts, **mocks), patch.object(charts.timing_logger, 'info', side_effect=lambda fmt, *args: records.append(fmt % args)), patch.object(charts.logger, 'error'), patch.object(charts.logger, 'warning'):
            if failure:
                with self.assertRaises(charts.HTTPException) as caught:
                    charts.create_compatibility_chart.__wrapped__(self.request, self.payload, self.db)
                self.assertEqual(caught.exception.status_code, 503 if api_error else 500)
                self.db.rollback.assert_called_once()
                self.db.commit.assert_not_called()
            else:
                result = charts.create_compatibility_chart.__wrapped__(self.request, self.payload, self.db)
                self.assertEqual(result, {
                    'user_id': 1, 'pet_id': 2,
                    'human': {'interpretation': 'human', 'analysis': {'individual': True}, 'chart': {'planets': {}}},
                    'pet': {'interpretation': 'pet', 'analysis': {'individual': True}, 'chart': {'planets': {}}},
                    'compatibility': {'interpretation': 'compatibility', 'analysis': {'aspects': []}},
                })
                self.assertEqual(list(result['human']), ['interpretation', 'analysis', 'chart'])
                self.db.commit.assert_called_once()
                self.db.rollback.assert_not_called()
        self.assertEqual(len(worker_ids), 3)
        self.assertEqual(set(finished), {'human', 'pet', 'compatibility'})
        self.assertEqual(len(records), 8)
        self.assertIn('step=api_total', records[-1])
        self.assertTrue(all('private' not in record.lower() for record in records))

    def test_parallel_calls_preserve_response_and_db_thread(self):
        self.exercise()

    def test_openai_failure_in_each_worker_returns_503(self):
        for name in ('human', 'pet', 'compatibility'):
            with self.subTest(worker=name):
                self.setUp()
                self.exercise(name, api_error=True)

    def test_internal_failure_rolls_back_after_workers_finish(self):
        self.exercise('pet')

    def test_human_endpoint_remains_serial(self):
        payload = HumanChartRequest(**self.payload.model_dump())
        def interpret(**kwargs):
            self.assert_db_thread()
            return 'human'
        with patch.multiple(charts, calculate_chart=Mock(return_value={}), analyze_chart=Mock(return_value={}), interpret_human=interpret), patch.object(charts, 'ThreadPoolExecutor') as pool:
            result = charts.create_human_chart.__wrapped__(self.request, payload, self.db)
            self.assertEqual(result['interpretation'], 'human')
            pool.assert_not_called()
            self.db.commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
