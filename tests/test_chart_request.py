import unittest
from datetime import date, time, timedelta

from pydantic import ValidationError

from schemas.chart import ChartRequest


VALID_REQUEST = {
    "user_name": "test_user_9",
    "user_email": "test9@example.com",
    "pet_name": "Nabi",
    "pet_type": "cat",
    "pet_gender": "female",
    "pet_breed": "Korean Shorthair",
    "pet_birth_date": "2023-09-21",
    "pet_birth_time": "08:35:00",
    "city": "Busan",
}


class ChartRequestTests(unittest.TestCase):
    def test_valid_request_preserves_calculator_types(self):
        payload = ChartRequest.model_validate(VALID_REQUEST)
        self.assertEqual(payload.pet_birth_date, date(2023, 9, 21))
        self.assertEqual(payload.pet_birth_time, time(8, 35))
        self.assertEqual(payload.model_dump(mode="json"), VALID_REQUEST)

    def test_invalid_inputs(self):
        cases = [
            ("user_name", ""), ("user_name", "     "),
            ("user_email", "abc"), ("user_email", ""),
            ("pet_name", ""), ("pet_name", "     "),
            ("pet_type", "dragon"), ("pet_gender", "unknown"),
            ("pet_birth_date", (date.today() + timedelta(days=1)).isoformat()),
            ("pet_birth_date", "2023-02-29"),
            ("pet_birth_time", "25:00:00"), ("pet_birth_time", "invalid"),
            ("city", ""), ("city", "     "),
            ("user_name", "x" * 101), ("pet_name", "x" * 101),
            ("pet_breed", "x" * 101), ("city", "x" * 256),
            ("user_email", "x" * 244 + "@example.com"),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError) as error:
                    ChartRequest.model_validate({**VALID_REQUEST, field: value})
                self.assertIn(field, [item["loc"][0] for item in error.exception.errors()])

    def test_required_fields_and_null_values(self):
        for field in VALID_REQUEST.keys() - {"pet_birth_time"}:
            with self.subTest(field=field):
                payload = dict(VALID_REQUEST)
                del payload[field]
                with self.assertRaises(ValidationError):
                    ChartRequest.model_validate(payload)
                with self.assertRaises(ValidationError):
                    ChartRequest.model_validate({**VALID_REQUEST, field: None})

    def test_trims_text_fields(self):
        fields = ("user_name", "user_email", "pet_name", "pet_breed", "city")
        payload = dict(VALID_REQUEST)
        for field in fields:
            payload[field] = "  " + payload[field] + "  "
        self.assertEqual(ChartRequest.model_validate(payload).model_dump(mode="json"), VALID_REQUEST)

    def test_length_boundaries(self):
        for field, limit in (("user_name", 100), ("pet_name", 100), ("pet_breed", 100), ("city", 255)):
            with self.subTest(field=field):
                payload = ChartRequest.model_validate({**VALID_REQUEST, field: "x" * limit})
                self.assertEqual(len(getattr(payload, field)), limit)

    def test_unknown_birth_time(self):
        payload = dict(VALID_REQUEST)
        del payload["pet_birth_time"]
        self.assertIsNone(ChartRequest.model_validate(payload).pet_birth_time)
        self.assertIsNone(ChartRequest.model_validate({**payload, "pet_birth_time": None}).pet_birth_time)

    def test_today_and_leap_day(self):
        for value in (date.today().isoformat(), "2024-02-29"):
            with self.subTest(value=value):
                self.assertEqual(ChartRequest.model_validate({**VALID_REQUEST, "pet_birth_date": value}).pet_birth_date, date.fromisoformat(value))

    def test_existing_empty_breed_contract(self):
        self.assertEqual(ChartRequest.model_validate({**VALID_REQUEST, "pet_breed": "  "}).pet_breed, "")

    def test_allowed_pet_values(self):
        for pet_type in ("dog", "cat"):
            for pet_gender in ("male", "female"):
                with self.subTest(pet_type=pet_type, pet_gender=pet_gender):
                    ChartRequest.model_validate({**VALID_REQUEST, "pet_type": pet_type, "pet_gender": pet_gender})


if __name__ == "__main__":
    unittest.main()
