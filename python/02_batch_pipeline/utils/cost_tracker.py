"""
cost_tracker.py - Token and cost accounting for the triage pipeline.

Tracks cumulative token usage and estimated cost across all API calls.
Writes a running cost log to outputs/cost_log.jsonl for audit.
Raises warnings when approaching budget thresholds.

Usage:
    from utils.cost_tracker import CostTracker
    tracker = CostTracker(config, output_dir="./outputs")
    tracker.log_call(model="gpt-4.1-nano", input_tokens=900, output_tokens=150)
    tracker.summary()  # prints cumulative cost

Design Decisions:
    - Uses Batch API pricing by default (50% of standard).
    - Cost estimates are conservative (round up).
    - Budget warnings are logged, not exceptions. The pipeline continues
      but the researcher is alerted to review spend.
"""

import json
import os
from dataclasses import dataclass, field
from utils.logging_utils import now_iso


@dataclass
class CostTracker:
    """
    Accumulates token usage and estimated cost across API calls.

    Args:
        config: Parsed pipeline_config.yaml dict.
        output_dir: Directory for cost_log.jsonl.
    """
    config: dict
    output_dir: str = "./outputs"

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    _log_path: str = field(init=False, default="")

    def __post_init__(self):
        os.makedirs(self.output_dir, exist_ok=True)
        self._log_path = os.path.join(self.output_dir, "cost_log.jsonl")

    def _get_pricing(self, model: str) -> dict:
        """Look up per-1M-token pricing for a model from config."""
        pricing = self.config.get("cost", {}).get("batch_pricing", {})
        if model in pricing:
            return pricing[model]
        # Fallback: try matching partial model name
        for key, val in pricing.items():
            if key in model:
                return val
        # Default to nano pricing as conservative estimate
        return {"input_per_1m": 0.05, "output_per_1m": 0.20}

    def log_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        doc_id: str = "",
        stage: str = "",
        batch_id: str = "",
    ) -> float:
        """
        Record a single API call's token usage and cost.

        Returns estimated cost of this call in USD.
        """
        pricing = self._get_pricing(model)
        cost = (
            (input_tokens / 1_000_000) * pricing["input_per_1m"]
            + (output_tokens / 1_000_000) * pricing["output_per_1m"]
        )

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost
        self.call_count += 1

        # Write to cost log
        entry = {
            "timestamp": now_iso(),
            "stage": stage,
            "doc_id": doc_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "call_cost_usd": round(cost, 6),
            "cumulative_cost_usd": round(self.total_cost_usd, 4),
            "batch_id": batch_id,
        }
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Budget warnings
        budget_warn = self.config.get("cost", {}).get("budget_warn_usd", 15.0)
        budget_ceil = self.config.get("cost", {}).get("budget_ceiling_usd", 20.0)
        if self.total_cost_usd >= budget_ceil:
            print(f"BUDGET CEILING REACHED: ${self.total_cost_usd:.2f} >= ${budget_ceil:.2f}")
        elif self.total_cost_usd >= budget_warn:
            print(f"BUDGET WARNING: ${self.total_cost_usd:.2f} >= ${budget_warn:.2f}")

        return cost

    def log_batch(
        self,
        model: str,
        total_input_tokens: int,
        total_output_tokens: int,
        doc_count: int,
        batch_id: str = "",
        stage: str = "",
    ) -> float:
        """
        Record a Batch API submission's total token usage.
        Use this when you get aggregate token counts from the batch result.
        """
        pricing = self._get_pricing(model)
        cost = (
            (total_input_tokens / 1_000_000) * pricing["input_per_1m"]
            + (total_output_tokens / 1_000_000) * pricing["output_per_1m"]
        )

        self.total_input_tokens += total_input_tokens
        self.total_output_tokens += total_output_tokens
        self.total_cost_usd += cost
        self.call_count += doc_count

        entry = {
            "timestamp": now_iso(),
            "stage": stage,
            "type": "batch_aggregate",
            "model": model,
            "doc_count": doc_count,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "batch_cost_usd": round(cost, 6),
            "cumulative_cost_usd": round(self.total_cost_usd, 4),
            "batch_id": batch_id,
        }
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return cost

    def summary(self) -> dict:
        """Print and return a cost summary."""
        s = {
            "total_calls": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "budget_ceiling_usd": self.config.get("cost", {}).get("budget_ceiling_usd", 20.0),
            "budget_remaining_usd": round(
                self.config.get("cost", {}).get("budget_ceiling_usd", 20.0) - self.total_cost_usd, 4
            ),
        }
        print(f"Cost Summary: {self.call_count} calls, "
              f"${s['total_cost_usd']:.4f} spent, "
              f"${s['budget_remaining_usd']:.4f} remaining")
        return s
