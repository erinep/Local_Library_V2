import unittest

from fastapi import HTTPException

from app.providers.llm_provider import LlmProvider


class LlmProviderParsingTests(unittest.TestCase):
    def setUp(self):
        self.provider = LlmProvider(base_url="http://example", model="fake-model")

    def test_parse_tag_mapping_skips_reasoning(self):
        parsed = {
            "Mode": "mystery",
            "reasoning": "ignore me",
            "Setting": "historical",
        }
        tags = self.provider._parse_tag_mapping(parsed)
        self.assertEqual(sorted(tags), ["Mode:mystery", "Setting:historical"])

    def test_parse_tag_mapping_list_values(self):
        parsed = {"Genre": ["Epic", "Adventure"]}
        tags = self.provider._parse_tag_mapping(parsed)
        self.assertEqual(sorted(tags), ["Genre:Adventure", "Genre:Epic"])

    def test_parse_json_content_string(self):
        parsed = self.provider._parse_json_content('{"Mode":"mystery"}', "empty")
        self.assertEqual(parsed, {"Mode": "mystery"})

    def test_parse_json_content_invalid(self):
        with self.assertRaises(HTTPException):
            self.provider._parse_json_content("not json", "empty")

    def test_coerce_tag_value_romance(self):
        value = self.provider._coerce_tag_value("Romance", "0.7")
        self.assertEqual(value, 0.7)

    def test_coerce_tag_value_romance_clamps(self):
        value = self.provider._coerce_tag_value("Romance", 2.5)
        self.assertEqual(value, 1.0)

    def test_coerce_tag_value_empty_string(self):
        with self.assertRaises(HTTPException):
            self.provider._coerce_tag_value("Mode", " ")

    def test_extract_reasoning_from_message(self):
        choice = {
            "message": {
                "reasoning": "Because it fits.",
            }
        }
        reasoning = self.provider._extract_reasoning(choice)
        self.assertEqual(reasoning, "Because it fits.")

    def test_extract_reasoning_from_content_list(self):
        choice = {
            "content": [
                {"reasoning": "Step one."},
                {"reasoning": "Step two."},
            ]
        }
        reasoning = self.provider._extract_reasoning(choice)
        self.assertEqual(reasoning, "Step one.")


if __name__ == "__main__":
    unittest.main()
