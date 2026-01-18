import unittest

from app.services import metadata_scoring


class MetadataScoringTests(unittest.TestCase):
    def test_author_similarity_exact_match(self):
        score = metadata_scoring.author_similarity("Jane Doe", "Jane Doe")
        self.assertEqual(score, 1.0)

    def test_author_similarity_partial_match(self):
        score = metadata_scoring.author_similarity("Jane Doe", "Jane A. Doe")
        self.assertGreater(score, 0.0)

    def test_title_overlap(self):
        score = metadata_scoring.title_token_overlap("The Divine Comedy", "the divine comedy")
        self.assertEqual(score, 1.0)

    def test_desc_score_caps_at_one(self):
        score = metadata_scoring.desc_score("a" * 2000)
        self.assertEqual(score, 1.0)

    def test_confidence_score_combines(self):
        score, desc_score, identity_score = metadata_scoring.confidence_score(
            query_title="Great Book",
            query_author="Jane Doe",
            candidate_title="Great Book",
            candidate_author="Jane Doe",
            description="a" * 800,
        )
        self.assertEqual(desc_score, 1.0)
        self.assertEqual(identity_score, 1.0)
        self.assertEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
