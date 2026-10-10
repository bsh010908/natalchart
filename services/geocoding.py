"""Amazon Location Places V2 adapter; no explicit credentials or Nominatim fallback."""
from dataclasses import dataclass
import math
from threading import Lock

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError, ClientError, ConnectTimeoutError, ReadTimeoutError,
    NoCredentialsError, PartialCredentialsError, CredentialRetrievalError,
)


class GeocodingServiceError(RuntimeError):
    category = "service"


class GeocodingAuthenticationError(GeocodingServiceError):
    category = "authentication"


class GeocodingPermissionError(GeocodingServiceError):
    category = "permission"


class GeocodingRateLimitError(GeocodingServiceError):
    category = "rate_limit"


class GeocodingTimeoutError(GeocodingServiceError):
    category = "timeout"


class GeocodingNotFoundError(ValueError):
    pass


class GeocodingAmbiguousError(ValueError):
    pass


@dataclass(frozen=True)
class GeocodedPlace:
    latitude: float
    longitude: float
    # Internal inspection only: never added to API responses or routine logs.
    country_code: str | None
    country_name: str | None
    region_code: str | None
    region_name: str | None


_client = None
_client_initialization_lock = Lock()


def get_places_client():
    global _client
    if _client is None:
        # Only the first creation is serialized. Network requests never hold this lock.
        with _client_initialization_lock:
            if _client is None:
                _client = boto3.session.Session().client(
                    "geo-places", region_name="us-west-2",
                    config=Config(connect_timeout=3, read_timeout=5,
                                  max_pool_connections=40,
                                  retries={"mode": "standard", "total_max_attempts": 2}),
                )
    return _client


def _administrative_identity(item):
    address = item.get("Address", {})
    country = address.get("Country", {})
    region = address.get("Region", {})
    return (country.get("Code3") or country.get("Code2") or country.get("Name"),
            region.get("Code") or region.get("Name"))


def _is_ambiguous(query, first, second):
    first_city = first.get("Address", {}).get("Locality", "").casefold()
    second_city = second.get("Address", {}).get("Locality", "").casefold()
    if not first_city or first_city != second_city:
        return False
    first_identity = _administrative_identity(first)
    second_identity = _administrative_identity(second)
    if not any(first_identity) or not any(second_identity) or first_identity == second_identity:
        return False
    first_score = first.get("MatchScores", {}).get("Overall")
    second_score = second.get("MatchScores", {}).get("Overall")
    # Reject bare identical city names or equally ranked matches in different regions.
    # This is conservative detection, not a worldwide ambiguity guarantee.
    return (query.strip().casefold() == first_city or
            (first_score is not None and first_score == second_score))


def geocode_place(query: str) -> GeocodedPlace:
    try:
        response = get_places_client().geocode(QueryText=query, MaxResults=2)
    except (NoCredentialsError, PartialCredentialsError, CredentialRetrievalError):
        raise GeocodingAuthenticationError("Geocoding authentication failed") from None
    except (ConnectTimeoutError, ReadTimeoutError):
        raise GeocodingTimeoutError("Geocoding request timed out") from None
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"UnrecognizedClientException", "InvalidClientTokenId", "ExpiredToken",
                    "ExpiredTokenException", "InvalidSignatureException", "SignatureDoesNotMatch",
                    "MissingAuthenticationTokenException", "AuthFailure"}:
            error = GeocodingAuthenticationError
        elif code in {"AccessDeniedException", "AccessDenied", "UnauthorizedException"}:
            error = GeocodingPermissionError
        elif code in {"ThrottlingException", "Throttling", "TooManyRequestsException",
                      "RequestLimitExceeded"}:
            error = GeocodingRateLimitError
        else:
            error = GeocodingServiceError
        # Do not propagate provider messages, response bodies, or the query.
        raise error("Geocoding service request failed") from None
    except BotoCoreError:
        raise GeocodingServiceError("Geocoding service unavailable") from None

    if not isinstance(response, dict):
        raise GeocodingServiceError("Invalid geocoding response")
    items = response.get("ResultItems")
    if items == []:
        raise GeocodingNotFoundError("Birth place not found")
    if not isinstance(items, list) or not items:
        raise GeocodingServiceError("Invalid geocoding response")
    for candidate in items[:2]:
        if not isinstance(candidate, dict):
            raise GeocodingServiceError("Invalid geocoding response")
        address = candidate.get("Address", {})
        scores = candidate.get("MatchScores", {})
        if (not isinstance(address, dict) or not isinstance(scores, dict)
                or not isinstance(address.get("Country", {}), dict)
                or not isinstance(address.get("Region", {}), dict)
                or not isinstance(address.get("Locality", ""), str)):
            raise GeocodingServiceError("Invalid geocoding response")
    item = items[0]
    if len(items) > 1 and _is_ambiguous(query, item, items[1]):
        raise GeocodingAmbiguousError("Birth place is ambiguous; include country and region")
    try:
        longitude, latitude = item["Position"]
        if (isinstance(longitude, bool) or isinstance(latitude, bool)
                or not math.isfinite(longitude) or not math.isfinite(latitude)
                or not -180 <= longitude <= 180 or not -90 <= latitude <= 90):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise GeocodingServiceError("Invalid geocoding coordinates") from None
    address = item.get("Address", {})
    country = address.get("Country", {})
    region = address.get("Region", {})
    return GeocodedPlace(latitude=latitude, longitude=longitude,
                         country_code=country.get("Code3") or country.get("Code2"),
                         country_name=country.get("Name"), region_code=region.get("Code"),
                         region_name=region.get("Name"))
