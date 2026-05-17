import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.consensus_metrics import consensus_kappas  # noqa: E402


class ConsensusMetricsTests(unittest.TestCase):
    def test_reports_raw_and_consensus_kappas_separately(self):
        rows = [
            {
                "tier_claude": 1,
                "tier_gpt": 1,
                "tier_avg": 1,
                "avg_score_carefirst": 7,
                "avg_score_ai_governance": 6,
                "avg_score_intersection": 6,
                "avg_score_evidentiary": 4,
            },
            {
                "tier_claude": 2,
                "tier_gpt": 3,
                "tier_avg": 2,
                "avg_score_carefirst": 4,
                "avg_score_ai_governance": 4,
                "avg_score_intersection": 4,
                "avg_score_evidentiary": 4,
            },
            {
                "tier_claude": 3,
                "tier_gpt": 4,
                "tier_avg": 3,
                "avg_score_carefirst": 1,
                "avg_score_ai_governance": 1,
                "avg_score_intersection": 1,
                "avg_score_evidentiary": 1,
            },
            {
                "tier_claude": 4,
                "tier_gpt": 3,
                "tier_avg": 4,
                "avg_score_carefirst": 0,
                "avg_score_ai_governance": 0,
                "avg_score_intersection": 0,
                "avg_score_evidentiary": 0,
            },
        ]

        metrics = consensus_kappas(rows)

        self.assertIn("claude_vs_gpt", metrics)
        self.assertIn("claude_vs_avg", metrics)
        self.assertIn("claude_vs_final", metrics)
        self.assertGreater(metrics["claude_vs_avg"]["unweighted_kappa"], 0.5)
        self.assertGreater(
            metrics["claude_vs_avg"]["unweighted_kappa"],
            metrics["claude_vs_gpt"]["unweighted_kappa"],
        )


if __name__ == "__main__":
    unittest.main()
