import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.codex_scoring_guardrails import (  # noqa: E402
    apply_keyword_floors,
    format_documents_for_prompt,
    sanitize_score,
)


class CodexScoringGuardrailTests(unittest.TestCase):
    def test_unrelated_public_comment_cannot_become_bridge_document(self):
        text = (
            "PUBLIC REQUEST TO ADDRESS THE BOARD OF SUPERVISORS. "
            "Residents submitted comments about saving the Royal Vista golf course, "
            "traffic, air quality, open space, and a housing appeal. "
            "Agenda #4 was heard on 9/18/2024. The comments mention a vendor email "
            "footer and a risk assessment in an environmental report, but no county "
            "care-first program and no technology governance system."
        )
        model_score = {
            "doc_id": "abc",
            "score_carefirst": 10,
            "score_ai_governance": 10,
            "score_intersection": 8,
            "score_evidentiary": 9,
            "rationale": "Strong bridge between care-first and tech governance.",
        }

        clean = sanitize_score(model_score, text)

        self.assertEqual(clean["score_carefirst"], 0)
        self.assertEqual(clean["score_ai_governance"], 0)
        self.assertEqual(clean["score_intersection"], 0)
        self.assertLessEqual(clean["score_evidentiary"], 3)
        self.assertIn("codex_guardrails", clean)

    def test_actual_bridge_scores_survive_intersection_cap(self):
        text = (
            "The Board directed CFCI and Measure J implementation staff to coordinate "
            "with the Chief Information Officer Peter Loo and the GenAI Governance Board "
            "on oversight, procurement, and accountability for automated eligibility "
            "tools used in diversion and reentry services. The motion authorizes a "
            "$2,000,000 implementation plan and shall report back on July 1, 2025."
        )
        model_score = {
            "doc_id": "def",
            "score_carefirst": 8,
            "score_ai_governance": 8,
            "score_intersection": 9,
            "score_evidentiary": 8,
            "rationale": "Connects Measure J/CFCI and AI governance oversight.",
        }

        clean = sanitize_score(model_score, text)

        self.assertEqual(clean["score_carefirst"], 8)
        self.assertEqual(clean["score_ai_governance"], 8)
        self.assertEqual(clean["score_intersection"], 9)
        self.assertGreaterEqual(clean["score_evidentiary"], 5)

    def test_broad_service_and_tech_procurement_records_are_not_zeroed(self):
        text = (
            "The Department of Mental Health and Probation will execute a contract "
            "for a case management system supporting diversion program services. "
            "The agreement includes security audits, privacy controls, vendor "
            "oversight, and reporting to the Board on March 3, 2025."
        )
        model_score = {
            "doc_id": "ghi",
            "score_carefirst": 5,
            "score_ai_governance": 5,
            "score_intersection": 5,
            "score_evidentiary": 5,
            "rationale": "Care-service delivery and technology procurement overlap.",
        }

        clean = sanitize_score(model_score, text)

        self.assertEqual(clean["score_carefirst"], 5)
        self.assertEqual(clean["score_ai_governance"], 5)
        self.assertEqual(clean["score_intersection"], 5)

    def test_prompt_documents_do_not_include_keyword_metadata(self):
        batch = [
            {
                "doc_id": "abc",
                "filename": "example.pdf",
                "keyword_score": 12.0,
                "keyword_matches": ["ai_governance", "care_first"],
            }
        ]
        text_by_id = {"abc": "Measure J and GenAI Governance Board text."}

        prompt_docs = format_documents_for_prompt(batch, text_by_id)

        self.assertIn("doc_id: abc", prompt_docs)
        self.assertIn("filename: example.pdf", prompt_docs)
        self.assertIn("Measure J and GenAI Governance Board text.", prompt_docs)
        self.assertNotIn("keyword_score", prompt_docs)
        self.assertNotIn("keyword_matches", prompt_docs)

    def test_ai_keyword_match_sets_incidental_floor_only(self):
        score = {
            "doc_id": "jkl",
            "score_carefirst": 0,
            "score_ai_governance": 0,
            "score_intersection": 0,
            "score_evidentiary": 2,
            "rationale": "Routine record.",
        }

        clean = apply_keyword_floors(score, ["ai_governance"])

        self.assertEqual(clean["score_ai_governance"], 2)
        self.assertEqual(clean["score_carefirst"], 0)
        self.assertEqual(clean["score_intersection"], 0)


if __name__ == "__main__":
    unittest.main()
