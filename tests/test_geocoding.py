"""Places V2 tests: AWS credential discovery and HTTP are always mocked."""
from concurrent.futures import ThreadPoolExecutor
import inspect
import threading
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import (ClientError, NoCredentialsError, PartialCredentialsError,
    CredentialRetrievalError, ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError)
from botocore.session import Session
from botocore.validate import validate_parameters

from api import charts
from astrology import calculator
from services import geocoding as geo
from tests import test_chart_transactions as transactions


def result(city="San Francisco", position=None, country="USA", region="CA", score=1.0):
    return {"Position": position if position is not None else [-122.4194, 37.7749],
            "PlaceType": "Locality", "Title": city,
            "Address": {"Locality": city, "Country": {"Code3": country},
                        "Region": {"Code": region}}, "MatchScores": {"Overall": score}}


class GeocodingTest(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.geocode.return_value = {"ResultItems": [result()]}
        patcher = patch.object(geo, "get_places_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_worldwide_coordinates_and_query_contract(self):
        model = Session().get_service_model("geo-places").operation_model("Geocode")
        for query, coords, country, region in (
            ("San Francisco, California, USA", [-122.4194, 37.7749], "USA", "CA"),
            ("서울, 대한민국", [126.978, 37.5665], "KOR", "Seoul"),
            ("Tokyo, Japan", [139.6917, 35.6895], "JPN", "Tokyo"),
            ("London, United Kingdom", [-0.1276, 51.5072], "GBR", "England"),
        ):
            with self.subTest(query=query):
                self.client.geocode.return_value = {"ResultItems": [result(query, coords, country, region)]}
                place = geo.geocode_place(query)
                self.assertEqual((place.longitude, place.latitude), tuple(coords))
                self.assertEqual((place.country_code, place.region_code), (country, region))
                self.client.geocode.assert_called_with(QueryText=query, MaxResults=2)
                validate_parameters(self.client.geocode.call_args.kwargs, model.input_shape)

    def test_no_results(self):
        self.client.geocode.return_value = {"ResultItems": []}
        with self.assertRaises(geo.GeocodingNotFoundError):
            geo.geocode_place("PRIVATE city")

    def test_client_error_categories_and_privacy(self):
        for code, expected in (
            ("AccessDeniedException", geo.GeocodingPermissionError),
            ("UnrecognizedClientException", geo.GeocodingAuthenticationError),
            ("ExpiredTokenException", geo.GeocodingAuthenticationError),
            ("ThrottlingException", geo.GeocodingRateLimitError),
            ("InternalServerException", geo.GeocodingServiceError),
        ):
            with self.subTest(code=code):
                self.client.geocode.side_effect = ClientError(
                    {"Error": {"Code": code, "Message": "PRIVATE provider body/key/query"}}, "Geocode")
                with self.assertRaises(expected) as captured:
                    geo.geocode_place("PRIVATE city")
                self.assertNotIn("PRIVATE", str(captured.exception))
                self.assertTrue(captured.exception.__suppress_context__)

    def test_credentials_timeout_and_transport_errors(self):
        for error, expected in (
            (NoCredentialsError(), geo.GeocodingAuthenticationError),
            (PartialCredentialsError(provider="mock", cred_var="secret"), geo.GeocodingAuthenticationError),
            (CredentialRetrievalError(provider="mock", error_msg="PRIVATE"), geo.GeocodingAuthenticationError),
            (ConnectTimeoutError(endpoint_url="PRIVATE"), geo.GeocodingTimeoutError),
            (ReadTimeoutError(endpoint_url="PRIVATE"), geo.GeocodingTimeoutError),
            (EndpointConnectionError(endpoint_url="PRIVATE"), geo.GeocodingServiceError),
        ):
            with self.subTest(error=type(error).__name__):
                self.client.geocode.side_effect = error
                with self.assertRaises(expected):
                    geo.geocode_place("PRIVATE")

    def test_malformed_positions(self):
        for coords in ([37], [181, 30], [30, 91], [float("nan"), 0], [True, 0], ["bad", 0]):
            with self.subTest(coords=coords):
                self.client.geocode.return_value = {"ResultItems": [result(position=coords)]}
                with self.assertRaises(geo.GeocodingServiceError):
                    geo.geocode_place("city")

    def test_ambiguity_and_qualified_city(self):
        first = result("Springfield", [-89.65, 39.78], region="IL")
        second = result("Springfield", [-72.59, 42.10], region="MA")
        self.client.geocode.return_value = {"ResultItems": [first, second]}
        with self.assertRaises(geo.GeocodingAmbiguousError):
            geo.geocode_place("Springfield")
        with self.assertRaises(geo.GeocodingAmbiguousError):
            geo.geocode_place("Springfield, USA")
        second["MatchScores"]["Overall"] = .5
        self.assertEqual(geo.geocode_place("Springfield, Illinois, USA").region_code, "IL")

    def test_failed_request_does_not_poison_client(self):
        self.client.geocode.side_effect = [ReadTimeoutError(endpoint_url="PRIVATE"),
                                           {"ResultItems": [result()]}]
        with self.assertRaises(geo.GeocodingTimeoutError):
            geo.geocode_place("city")
        self.assertEqual(geo.geocode_place("city").latitude, 37.7749)

    def test_concurrent_failure_is_isolated(self):
        barrier = threading.Barrier(20)
        def call(**kwargs):
            barrier.wait(timeout=5)
            if kwargs["QueryText"] == "failed":
                raise ReadTimeoutError(endpoint_url="PRIVATE")
            return {"ResultItems": [result()]}
        self.client.geocode.side_effect = call
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(geo.geocode_place, query)
                       for query in ["failed"] + ["city"] * 19]
            with self.assertRaises(geo.GeocodingTimeoutError):
                futures[0].result()
            self.assertTrue(all(f.result().latitude == 37.7749 for f in futures[1:]))

    def test_malformed_responses_are_service_errors(self):
        for response in (None, {}, {"ResultItems": None}, {"ResultItems": [None]},
                         {"ResultItems": [{"Address": None}]},
                         {"ResultItems": [{"Position": [0, 0], "Address": {"Country": None}}]}):
            with self.subTest(response=response):
                self.client.geocode.return_value = response
                with self.assertRaises(geo.GeocodingServiceError):
                    geo.geocode_place("city")

    def test_no_runtime_nominatim_and_sync_routes(self):
        self.assertNotIn("Nominatim", inspect.getsource(calculator))
        self.assertNotIn("geopy", inspect.getsource(calculator))
        self.assertFalse(inspect.iscoroutinefunction(charts.create_human_chart))
        self.assertFalse(inspect.iscoroutinefunction(charts.create_compatibility_chart))


class ClientReuseTest(unittest.TestCase):
    def test_single_creation_and_parallel_network_calls(self):
        client = Mock()
        barrier = threading.Barrier(20)
        def geocode(**kwargs):
            barrier.wait(timeout=5)
            return {"ResultItems": [result()]}
        client.geocode.side_effect = geocode
        with patch.object(geo, "_client", None), patch.object(geo.boto3.session, "Session") as factory:
            factory.return_value.client.return_value = client
            with ThreadPoolExecutor(max_workers=20) as executor:
                places = list(executor.map(geo.geocode_place, ["city"] * 20))
            self.assertEqual(len(places), 20)
            factory.assert_called_once_with()
            factory.return_value.client.assert_called_once()
            args, kwargs = factory.return_value.client.call_args
            self.assertEqual(args, ("geo-places",))
            self.assertEqual(set(kwargs), {"region_name", "config"})
            self.assertEqual(kwargs["region_name"], "us-west-2")
            config = kwargs["config"]
            self.assertEqual((config.connect_timeout, config.read_timeout), (3, 5))
            self.assertEqual(config.retries, {"mode": "standard", "total_max_attempts": 2})
            self.assertGreaterEqual(config.max_pool_connections, 20)

    def test_creation_failure_can_recover(self):
        with patch.object(geo, "_client", None), patch.object(geo.boto3.session, "Session") as factory:
            factory.return_value.client.side_effect = [NoCredentialsError(), Mock()]
            with self.assertRaises(geo.GeocodingAuthenticationError):
                geo.geocode_place("city")
            self.assertIsNone(geo._client)
            self.assertIsNotNone(geo.get_places_client())


class GeocodingApiIntegrationTest(unittest.TestCase):
    setUp = transactions.ChartTransactionsTest.setUp
    interpret = transactions.ChartTransactionsTest.interpret
    call = transactions.ChartTransactionsTest.call
    counts = transactions.ChartTransactionsTest.counts

    def test_both_routes_use_shared_aws_geocoder(self):
        client = Mock()
        client.geocode.return_value = {"ResultItems": [result("Seoul", [126.978, 37.5665], "KOR", "Seoul")]}
        for compatibility in (False, True):
            with self.subTest(compatibility=compatibility):
                self.events.clear()
                client.geocode.reset_mock()
                with patch.object(charts, "calculate_chart", side_effect=calculator.calculate_chart), patch.object(geo, "get_places_client", return_value=client), patch.object(calculator, "TimezoneFinder") as finder:
                    finder.return_value.timezone_at.return_value = "Asia/Seoul"
                    status, response = self.call(compatibility)
                self.assertEqual(status, 200)
                self.assertEqual(client.geocode.call_count, 2 if compatibility else 1)
                birth = response["human"]["chart"]["birth"] if compatibility else response["chart"]["birth"]
                self.assertEqual(set(birth), {"latitude", "longitude", "timezone", "birth_time_known",
                                              "local_datetime", "utc_datetime"})
                self.assertEqual((birth["longitude"], birth["latitude"]), (126.978, 37.5665))

    def test_service_errors_do_not_reach_gpt_or_db(self):
        for compatibility in (False, True):
            for error_type, expected in ((geo.GeocodingRateLimitError, 503),
                    (geo.GeocodingTimeoutError, 503), (geo.GeocodingServiceError, 503),
                    (geo.GeocodingAuthenticationError, 500), (geo.GeocodingPermissionError, 500),
                    (geo.GeocodingNotFoundError, 500), (geo.GeocodingAmbiguousError, 500)):
                with self.subTest(compatibility=compatibility, error=error_type):
                    self.events.clear()
                    with patch.object(charts, "calculate_chart", side_effect=error_type("PRIVATE")):
                        status, response = self.call(compatibility)
                    self.assertEqual(status, expected)
                    self.assertEqual(set(response), {"detail"})
                    self.assertNotIn("PRIVATE", response["detail"])
                    self.assertNotIn("checkout", self.events)
                    self.assertFalse(any(e.startswith("gpt_") for e in self.events))
                    self.assertEqual(self.counts(), (0, 0))
