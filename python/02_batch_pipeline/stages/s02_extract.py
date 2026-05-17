"""
s02_extract.py - Text extraction from PDFs and JSON files (Stage S02).

For JSON files: reads the file and extracts text from known fields
(tries "text", "content", "body", "extracted_text", "ocr_text" in order).

For PDF files: uses pdfplumber as primary extractor. If pdfplumber returns
fewer than min_text_length characters, falls back to pytesseract OCR.

Cost: $0 (no API calls).

Error Sources and Handling:
    - Corrupted PDFs: logged, extraction_status="failed", auto-escalated later.
    - Password-protected PDFs: logged as failed.
    - Image-only PDFs where OCR fails: logged, extraction_status="failed".
    - JSON files with no recognized text field: logged, extraction_status="failed".
    - OCR quality is variable. Short OCR output (<100 chars) is flagged as
      ocr_status="partial" to signal low confidence.

Usage:
    from stages.s02_extract import run_extraction
    records = run_extraction(config, inventory_records, logger, error_logger)
"""

import json
import os
from utils.logging_utils import now_iso
from utils.schemas import ExtractedRecord, ExtractionMethod, ExtractionStatus, OcrStatus


# Fields to check in JSON files, in priority order.
JSON_TEXT_FIELDS = ["text", "content", "body", "extracted_text", "ocr_text",
                    "full_text", "raw_text", "document_text"]


def _extract_from_json(filepath: str) -> tuple[str | None, ExtractionMethod, str | None]:
    """
    Try to extract text from a JSON file by checking known field names.

    Returns: (text, method, error_message)
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception as e:
        return None, ExtractionMethod.NONE, f"JSON parse error: {e}"

    if isinstance(data, str):
        # Entire file is a text string
        return data, ExtractionMethod.JSON_FIELD, None

    if isinstance(data, dict):
        for field_name in JSON_TEXT_FIELDS:
            if field_name in data and isinstance(data[field_name], str):
                return data[field_name], ExtractionMethod.JSON_FIELD, None

        # Try concatenating all string values
        texts = [v for v in data.values() if isinstance(v, str) and len(v) > 50]
        if texts:
            return "\n\n".join(texts), ExtractionMethod.JSON_FIELD, None

    return None, ExtractionMethod.NONE, "No recognized text field in JSON"


def _extract_from_pdf(filepath: str, config: dict) -> tuple[str | None, ExtractionMethod, OcrStatus, int | None, str | None]:
    """
    Extract text from PDF using pdfplumber, with pytesseract fallback.

    Returns: (text, method, ocr_status, page_count, error_message)
    """
    import pdfplumber

    min_length = config.get("extraction", {}).get("min_text_length", 100)
    page_count = None

    # Try pdfplumber first
    try:
        with pdfplumber.open(filepath) as pdf:
            page_count = len(pdf.pages)
            texts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    texts.append(page_text)
            full_text = "\n\n".join(texts)

            if len(full_text.strip()) >= min_length:
                return full_text, ExtractionMethod.PDFPLUMBER, OcrStatus.NOT_NEEDED, page_count, None
    except Exception as e:
        # pdfplumber failed entirely; try OCR
        pass

    # Fallback to OCR
    try:
        import pytesseract
        from pdf2image import convert_from_path

        dpi = config.get("extraction", {}).get("ocr_dpi", 200)
        lang = config.get("extraction", {}).get("ocr_language", "eng")

        images = convert_from_path(filepath, dpi=dpi)
        if page_count is None:
            page_count = len(images)

        ocr_texts = []
        for img in images:
            ocr_texts.append(pytesseract.image_to_string(img, lang=lang))
        full_text = "\n\n".join(ocr_texts)

        if len(full_text.strip()) >= min_length:
            return full_text, ExtractionMethod.PYTESSERACT, OcrStatus.SUCCESS, page_count, None
        elif len(full_text.strip()) > 0:
            return full_text, ExtractionMethod.PYTESSERACT, OcrStatus.PARTIAL, page_count, None
        else:
            return None, ExtractionMethod.NONE, OcrStatus.FAILED, page_count, "OCR returned empty text"

    except Exception as e:
        return None, ExtractionMethod.NONE, OcrStatus.FAILED, page_count, f"OCR failed: {e}"


def run_extraction(config: dict, inventory: list[dict], logger, error_logger) -> list[dict]:
    """
    Extract text from all inventoried files.

    Args:
        config: Parsed pipeline_config.yaml.
        inventory: List of InventoryRecord dicts from S01.
        logger: Pipeline logger.
        error_logger: Error logger.

    Returns:
        List of ExtractedRecord dicts.
        Writes outputs/s02_extracted.jsonl.
    """
    output_dir = config.get("outputs", {}).get("base_dir", "./outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "s02_extracted.jsonl")

    records = []
    success_count = 0
    fail_count = 0

    for i, inv in enumerate(inventory):
        filepath = inv["original_path"]
        file_type = inv["file_type"]

        if (i + 1) % 500 == 0:
            logger.info(f"S02_EXTRACT | Progress: {i + 1}/{len(inventory)}")

        text = None
        method = ExtractionMethod.NONE
        ext_status = ExtractionStatus.FAILED
        ocr_status = OcrStatus.NOT_ATTEMPTED
        page_count = None
        error_msg = None

        if file_type == "json":
            text, method, error_msg = _extract_from_json(filepath)
            ocr_status = OcrStatus.NOT_NEEDED
            if text:
                ext_status = ExtractionStatus.SUCCESS
            else:
                ext_status = ExtractionStatus.FAILED

        elif file_type == "pdf":
            text, method, ocr_status, page_count, error_msg = _extract_from_pdf(filepath, config)
            if text and method != ExtractionMethod.NONE:
                ext_status = ExtractionStatus.SUCCESS
                if ocr_status == OcrStatus.PARTIAL:
                    ext_status = ExtractionStatus.PARTIAL
            else:
                ext_status = ExtractionStatus.FAILED

        else:
            error_msg = f"Unsupported file type: {file_type}"
            ext_status = ExtractionStatus.SKIPPED

        if ext_status == ExtractionStatus.FAILED:
            fail_count += 1
            error_logger.warning(
                f"S02_EXTRACT | doc_id={inv['doc_id'][:12]} | "
                f"file={inv['filename']} | {error_msg}"
            )
        else:
            success_count += 1

        record = ExtractedRecord(
            doc_id=inv["doc_id"],
            filename=inv["filename"],
            source_folder=inv["source_folder"],
            original_path=inv["original_path"],
            file_type=inv["file_type"],
            file_size_bytes=inv["file_size_bytes"],
            discovery_timestamp=inv["discovery_timestamp"],
            extraction_method=method,
            extraction_status=ext_status,
            ocr_status=ocr_status,
            raw_text=text,
            text_length=len(text) if text else 0,
            extraction_error=error_msg,
            page_count=page_count,
            extraction_timestamp=now_iso(),
        )
        records.append(record.model_dump())

    # Write output
    with open(output_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    logger.info(
        f"S02_EXTRACT | COMPLETE | "
        f"Success: {success_count}, Failed: {fail_count} | "
        f"Output: {output_path}"
    )

    return records
