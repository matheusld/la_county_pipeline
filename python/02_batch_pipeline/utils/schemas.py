"""
schemas.py - Data models for every stage of the document triage pipeline.

This module defines Pydantic models that serve as both runtime validation
and a living data dictionary. Each field includes a description suitable
for inclusion in a research methods appendix.

Methodology note (Stages S06–S09):
    Two cost-efficient models score every document independently using the
    same prompt. S07 aggregates the two scores, flags disagreements, and
    assigns a final priority tier. S08 draws a random 10% spot-check from
    low-priority documents to validate false-negative rates. S09 produces
    the final shortlist for full human review.

Usage:
    from utils.schemas import FilteredRecord, ScoredRecord, AggregateRecord
    record = AggregateRecord(doc_id="abc123", ...)
    record.model_dump()  # -> dict for JSONL serialization

Design decisions:
    - All timestamps are ISO 8601 strings for cross-platform compatibility.
    - Optional fields default to None so missing data is distinguishable
      from empty data in downstream analysis.
    - doc_id is a SHA-256 hash of file content, stable across renames.
    - Composite scores are always calculated locally by ranker.py; model
      self-reported composites are never stored or trusted.

Known limitations:
    - Pydantic V2 syntax. Requires pydantic >= 2.0.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExtractionMethod(str, Enum):
    JSON_FIELD   = "json_field"
    PDFPLUMBER   = "pdfplumber"
    PYTESSERACT  = "pytesseract"
    MANUAL       = "manual"
    NONE         = "none"


class ExtractionStatus(str, Enum):
    SUCCESS  = "success"
    PARTIAL  = "partial"
    FAILED   = "failed"
    SKIPPED  = "skipped"


class OcrStatus(str, Enum):
    NOT_NEEDED    = "not_needed"
    SUCCESS       = "success"
    PARTIAL       = "partial"
    FAILED        = "failed"
    NOT_ATTEMPTED = "not_attempted"


class PriorityTier(int, Enum):
    """
    Final tier assigned to each document after cross-model aggregation.

    Cutoffs are defined in pipeline_config.yaml under aggregate.tier_thresholds
    and applied locally by s07_aggregate.py using the weighted composite formula.
    """
    TIER_1 = 1  # Cite in paper: composite >= 6.0 AND (carefirst >= 5 OR ai_gov >= 5)
    TIER_2 = 2  # Useful background: composite >= 3.5 OR intersection >= 4
    TIER_3 = 3  # Skim only: composite >= 1.0
    TIER_4 = 4  # Irrelevant: composite < 1.0


class ReviewStatus(str, Enum):
    """Outcome of the human spot-check review."""
    CONFIRMED_LOW    = "confirmed_low"     # reviewer agrees: low priority
    ESCALATE         = "escalate"          # reviewer disagrees: should be higher priority
    UNCERTAIN        = "uncertain"         # reviewer cannot determine from preview
    NOT_REVIEWED     = "not_reviewed"      # not yet reviewed by human


# ---------------------------------------------------------------------------
# Stage S01: Discovery
# ---------------------------------------------------------------------------

class InventoryRecord(BaseModel):
    """One record per file found during discovery (Stage S01)."""
    doc_id: str = Field(
        description="SHA-256 hash of file content. Stable identifier across renames."
    )
    filename: str = Field(
        description="Original filename including extension."
    )
    source_folder: str = Field(
        description="Which source collection this file came from."
    )
    original_path: str = Field(
        description="Full filesystem path at discovery time."
    )
    file_type: str = Field(
        description="File extension: json | pdf"
    )
    file_size_bytes: int = Field(
        description="File size in bytes at discovery time."
    )
    discovery_timestamp: str = Field(
        description="ISO 8601 timestamp when the file was inventoried."
    )


# ---------------------------------------------------------------------------
# Stage S02: Extraction
# ---------------------------------------------------------------------------

class ExtractedRecord(BaseModel):
    """Record after text extraction (Stage S02). Extends inventory."""
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    file_type: str
    file_size_bytes: int
    discovery_timestamp: str

    extraction_method: ExtractionMethod = Field(
        description="Method used to obtain text from this document."
    )
    extraction_status: ExtractionStatus = Field(
        description="Whether extraction succeeded, partially succeeded, or failed."
    )
    ocr_status: OcrStatus = Field(
        description="Whether OCR was attempted and its outcome."
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Full extracted text before normalization. None if extraction failed."
    )
    text_length: int = Field(
        default=0,
        description="Character count of raw_text. 0 if extraction failed."
    )
    extraction_error: Optional[str] = Field(
        default=None,
        description="Error message if extraction failed. None on success."
    )
    page_count: Optional[int] = Field(
        default=None,
        description="Number of pages (PDFs only). None for JSON sources."
    )
    extraction_timestamp: str = Field(
        description="ISO 8601 timestamp when extraction completed."
    )


# ---------------------------------------------------------------------------
# Stage S03: Normalization
# ---------------------------------------------------------------------------

class NormalizedRecord(BaseModel):
    """Record after text normalization (Stage S03)."""
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    file_type: str
    file_size_bytes: int
    extraction_method: ExtractionMethod
    extraction_status: ExtractionStatus
    ocr_status: OcrStatus
    text_length: int
    page_count: Optional[int] = None

    normalized_text: Optional[str] = Field(
        default=None,
        description="Cleaned text after normalization. None if no usable text."
    )
    normalized_length: int = Field(
        default=0,
        description="Character count after normalization."
    )
    was_truncated: bool = Field(
        default=False,
        description="True if text exceeded max_text_length and was truncated."
    )
    truncation_point: Optional[int] = Field(
        default=None,
        description="Character index where truncation occurred. None if not truncated."
    )
    normalization_timestamp: str = Field(
        description="ISO 8601 timestamp."
    )


# ---------------------------------------------------------------------------
# Stage S04: Deduplication
# ---------------------------------------------------------------------------

class DedupRecord(BaseModel):
    """
    Record after near-duplicate detection (Stage S04).

    Documents flagged as near-duplicates are marked but NOT removed; this
    preserves the audit trail and avoids silent data loss. Duplicates are
    excluded from LLM scoring stages to avoid wasting API budget.
    """
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    extraction_status: ExtractionStatus
    ocr_status: OcrStatus
    normalized_length: int

    is_duplicate: bool = Field(
        default=False,
        description="True if this document is a near-duplicate of another."
    )
    duplicate_of: Optional[str] = Field(
        default=None,
        description="doc_id of the canonical document this is a duplicate of."
    )
    jaccard_similarity: Optional[float] = Field(
        default=None,
        description="Jaccard similarity score with the canonical document (0–1)."
    )
    dedup_timestamp: str = Field(
        description="ISO 8601 timestamp."
    )


# ---------------------------------------------------------------------------
# Stage S05: Keyword Filtering
# ---------------------------------------------------------------------------

class FilteredRecord(BaseModel):
    """
    Record after keyword/regex filtering (Stage S05).

    keyword_score is an additive signal only. No documents are discarded
    at this stage; the score is passed to later stages as a feature.
    """
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    extraction_status: ExtractionStatus
    normalized_length: int
    is_duplicate: bool

    keyword_matches: list[str] = Field(
        default_factory=list,
        description="Keyword domains matched (e.g., 'ai_governance', 'care_first')."
    )
    keyword_terms_matched: list[str] = Field(
        default_factory=list,
        description="Specific terms or patterns that matched."
    )
    keyword_score: float = Field(
        default=0.0,
        description="Additive score from keyword matches. Higher = more likely relevant."
    )
    filter_timestamp: str = Field(
        description="ISO 8601 timestamp."
    )


# ---------------------------------------------------------------------------
# Stages S06a / S06b: Per-model Scoring
# ---------------------------------------------------------------------------

class ScoredRecord(BaseModel):
    """
    Record after one model scores a document (Stages S06a and S06b).

    Each model scores independently using the same prompt (scoring_v1).
    Composite and tier are computed locally from the four raw dimension
    scores; the model's own composite calculation is never trusted.

    Two files are produced:
        outputs/s06_gpt_scored.jsonl    — GPT-5.4-mini scores
        outputs/s06_claude_scored.jsonl — Claude Haiku scores

    These are joined in Stage S07 to produce AggregateRecord.
    """
    # --- Document identity (carried forward from FilteredRecord) ---
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    extraction_status: ExtractionStatus
    normalized_length: int
    is_duplicate: bool
    keyword_score: float
    keyword_matches: list[str] = Field(default_factory=list)

    # --- Four scoring dimensions (0–10 each, assigned by the model) ---
    score_carefirst: float = Field(
        description=(
            "How much does the document address Measure J, CFCI, ODR, DYD, "
            "ATI, care-first governance, or related care-first structures? "
            "0 = no care-first content; 10 = entirely about care-first governance."
        )
    )
    score_ai_governance: float = Field(
        description=(
            "How much does the document address TD 24-04, the GenAI Governance Board, "
            "ISD procurement, algorithmic systems, or AI policy in county contexts? "
            "0 = no AI/tech content; 10 = entirely about AI governance."
        )
    )
    score_intersection: float = Field(
        description=(
            "Does the document explicitly connect the care-first and AI governance "
            "systems? 0 = neither system; 1–2 = one system only; 3–4 = both present "
            "but unconnected; 5–6 = both in proximity; 7–8 = gap explicitly discussed; "
            "9–10 = bridging the two systems is the central subject."
        )
    )
    score_evidentiary: float = Field(
        description=(
            "Concrete evidence quality for citation. Counts named actors (+1 each, "
            "max 3), dollar amounts (+1 each, max 2), contract IDs (+1 each, max 2), "
            "verbatim-quotable language (+1 each, max 2), specific dates (+1)."
        )
    )

    # --- Locally computed fields (not from model output) ---
    composite: float = Field(
        description=(
            "Weighted composite: carefirst×0.25 + ai_governance×0.25 + "
            "intersection×0.35 + evidentiary×0.15. Computed locally."
        )
    )
    tier: PriorityTier = Field(
        description="Priority tier assigned locally from composite and dimension scores."
    )

    # --- Model metadata ---
    rationale: str = Field(
        description="Model's one-sentence explanation of the scores."
    )
    model_used: str = Field(
        description="Model identifier (e.g., 'gpt-5.4-mini', 'claude-haiku-4-5')."
    )
    model_version: str = Field(
        description="Specific model version string for reproducibility."
    )
    prompt_version: str = Field(
        description="Prompt template version (e.g., '1.0')."
    )
    prompt_hash: str = Field(
        description="SHA-256 of the prompt template, for reproducibility verification."
    )

    # --- Cost and traceability ---
    input_tokens: int = Field(
        default=0,
        description="Input tokens consumed by this request."
    )
    output_tokens: int = Field(
        default=0,
        description="Output tokens consumed by this request."
    )
    scoring_timestamp: str = Field(
        description="ISO 8601 timestamp when scoring completed."
    )
    api_request_id: Optional[str] = Field(
        default=None,
        description="Provider API request ID, for traceability."
    )
    batch_id: Optional[str] = Field(
        default=None,
        description="Batch job ID (OpenAI or Anthropic) if submitted via Batch API."
    )
    score_error: Optional[str] = Field(
        default=None,
        description=(
            "If the model failed to return a valid score, a description of the error. "
            "Scores default to 0.0 when this field is set."
        )
    )


# ---------------------------------------------------------------------------
# Stage S07: Cross-model Aggregation
# ---------------------------------------------------------------------------

class AggregateRecord(BaseModel):
    """
    Record after cross-model score aggregation (Stage S07).

    Both models' scores are preserved alongside the averaged final scores.
    Disagreement is flagged when the two composites diverge by more than
    the threshold defined in pipeline_config.yaml (default: 2.0 points on
    a 10-point scale).

    Priority routing:
        - priority_review=True if final_tier is Tier 1 or Tier 2.
        - priority_review=True also if flagged_disagreement=True, regardless
          of tier, because disagreement indicates the document may be
          underscored by the lower model.

    Documents with priority_review=False and final_tier in {3, 4} are
    candidates for the 10% spot-check in Stage S08.
    """
    # --- Document identity ---
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    extraction_status: ExtractionStatus
    normalized_length: int
    is_duplicate: bool
    keyword_score: float
    keyword_matches: list[str] = Field(default_factory=list)

    # --- GPT model raw scores ---
    gpt_score_carefirst: Optional[float] = Field(
        default=None,
        description="GPT dimension score for care-first (0–10). None if scoring failed."
    )
    gpt_score_ai_governance: Optional[float] = Field(default=None)
    gpt_score_intersection: Optional[float] = Field(default=None)
    gpt_score_evidentiary: Optional[float] = Field(default=None)
    gpt_composite: Optional[float] = Field(
        default=None,
        description="GPT weighted composite, computed locally."
    )
    gpt_tier: Optional[PriorityTier] = Field(default=None)
    gpt_rationale: Optional[str] = Field(default=None)
    gpt_model_version: str = Field(
        description="GPT model version string."
    )
    gpt_prompt_hash: str = Field(
        description="SHA-256 of the prompt used for GPT scoring."
    )
    gpt_score_error: Optional[str] = Field(
        default=None,
        description="Error message if GPT scoring failed for this document."
    )

    # --- Claude model raw scores ---
    claude_score_carefirst: Optional[float] = Field(
        default=None,
        description="Claude dimension score for care-first (0–10). None if scoring failed."
    )
    claude_score_ai_governance: Optional[float] = Field(default=None)
    claude_score_intersection: Optional[float] = Field(default=None)
    claude_score_evidentiary: Optional[float] = Field(default=None)
    claude_composite: Optional[float] = Field(
        default=None,
        description="Claude weighted composite, computed locally."
    )
    claude_tier: Optional[PriorityTier] = Field(default=None)
    claude_rationale: Optional[str] = Field(default=None)
    claude_model_version: str = Field(
        description="Claude model version string."
    )
    claude_prompt_hash: str = Field(
        description="SHA-256 of the prompt used for Claude scoring."
    )
    claude_score_error: Optional[str] = Field(
        default=None,
        description="Error message if Claude scoring failed for this document."
    )

    # --- Aggregated final scores (computed locally in S07) ---
    final_score_carefirst: float = Field(
        description="Average care-first score across models."
    )
    final_score_ai_governance: float = Field(
        description="Average AI governance score across models."
    )
    final_score_intersection: float = Field(
        description="Average intersection score across models."
    )
    final_score_evidentiary: float = Field(
        description="Average evidentiary score across models."
    )
    final_composite: float = Field(
        description=(
            "Final weighted composite from averaged dimension scores. Formula: "
            "carefirst×0.25 + ai_governance×0.25 + intersection×0.35 + evidentiary×0.15."
        )
    )
    final_tier: PriorityTier = Field(
        description="Final priority tier derived from final_composite."
    )

    # --- Disagreement detection ---
    composite_delta: float = Field(
        description=(
            "Absolute difference between gpt_composite and claude_composite. "
            "High values indicate model disagreement on this document."
        )
    )
    flagged_disagreement: bool = Field(
        description=(
            "True if composite_delta >= aggregate.disagreement_threshold in config. "
            "Disagreement documents are always included in the shortlist regardless "
            "of final_tier, because the lower-scoring model may be wrong."
        )
    )

    # --- Routing ---
    priority_review: bool = Field(
        description=(
            "True if this document should be included in the shortlist. "
            "Set True when final_tier <= 2 or flagged_disagreement is True."
        )
    )
    text_preview: str = Field(
        default="",
        description="First N characters of normalized text, for human spot-check review."
    )

    aggregation_timestamp: str = Field(
        description="ISO 8601 timestamp when aggregation completed."
    )


# ---------------------------------------------------------------------------
# Stage S08: Spot-check Sampling
# ---------------------------------------------------------------------------

class SpotCheckRecord(BaseModel):
    """
    Record for a document sampled in the 10% spot-check (Stage S08).

    The spot-check draws a stratified random sample from documents where
    priority_review=False (Tier 3/4, no disagreement flag). This validates
    that the pipeline's low-priority classification is accurate and estimates
    the false-negative rate.

    Sampling is seeded (random_seed in config) for reproducibility.
    Results are written to outputs/s08_spotcheck.csv for human review.
    """
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    extraction_status: ExtractionStatus
    normalized_length: int
    keyword_score: float
    keyword_matches: list[str] = Field(default_factory=list)

    # Scores that led to low-priority classification
    final_composite: float
    final_tier: PriorityTier
    gpt_composite: Optional[float] = None
    claude_composite: Optional[float] = None
    gpt_rationale: Optional[str] = None
    claude_rationale: Optional[str] = None

    # Sampling metadata
    sample_index: int = Field(
        description="Position in the random sample (1-indexed)."
    )
    sample_pool_size: int = Field(
        description="Total number of low-priority documents eligible for sampling."
    )
    sample_rate: float = Field(
        description="Configured sampling rate (e.g., 0.10 for 10%)."
    )
    random_seed: int = Field(
        description="Random seed used for reproducible sampling."
    )
    text_preview: str = Field(
        default="",
        description="Text excerpt shown to reviewer."
    )

    # Human review fields (filled in after spot-check)
    reviewer_id: Optional[str] = Field(
        default=None,
        description="Identifier of the human reviewer."
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Free-text notes from the reviewer."
    )
    review_status: ReviewStatus = Field(
        default=ReviewStatus.NOT_REVIEWED,
        description="Outcome of spot-check review."
    )
    review_timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp of human review."
    )


# ---------------------------------------------------------------------------
# Stage S09: Final Shortlist
# ---------------------------------------------------------------------------

class ShortlistRecord(BaseModel):
    """
    Record in the final shortlist produced by Stage S09.

    The shortlist is the pipeline's primary output for manual qualitative
    analysis. It includes all Tier 1 documents, all Tier 2 documents, and
    all disagreement-flagged documents, ranked by final_composite descending
    and truncated to the target_size configured in pipeline_config.yaml.

    The shortlist CSV and JSONL are the handoff artifacts for the researcher.
    See Appendix A of the paper for full details on inclusion rules and
    validation metrics.
    """
    # Rank within shortlist (1 = highest composite)
    rank: int = Field(
        description="Position in the final shortlist, sorted by final_composite descending."
    )

    # Document identity
    doc_id: str
    filename: str
    source_folder: str
    original_path: str
    extraction_status: ExtractionStatus
    normalized_length: int
    keyword_score: float
    keyword_matches: list[str] = Field(default_factory=list)

    # Final scores
    final_composite: float
    final_tier: PriorityTier
    final_score_carefirst: float
    final_score_ai_governance: float
    final_score_intersection: float
    final_score_evidentiary: float

    # Per-model composites (for reader transparency)
    gpt_composite: Optional[float] = None
    claude_composite: Optional[float] = None
    composite_delta: float = Field(
        description="Absolute difference between model composites."
    )
    flagged_disagreement: bool

    # Inclusion reason (for methods appendix)
    inclusion_reason: str = Field(
        description=(
            "Why this document is on the shortlist: "
            "'tier_1', 'tier_2', or 'disagreement'."
        )
    )

    # Human-readable summary
    gpt_rationale: Optional[str] = None
    claude_rationale: Optional[str] = None
    text_preview: str = Field(
        default="",
        description="Text excerpt for the reviewer."
    )

    shortlist_timestamp: str = Field(
        description="ISO 8601 timestamp when shortlist was generated."
    )
