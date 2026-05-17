#!/usr/bin/env python3
"""
Export any pipeline JSONL file to Excel, splitting into two workbooks so file
sizes stay manageable.

Works with any stage output. Typical usage:

    # Full aggregated scores (all documents, both models)
    python jsonl_to_xlsx_v2.py \
        --input outputs/s07_aggregated.jsonl \
        --output-stem outputs/s07_aggregated

    # Final shortlist only (~167 documents)
    python jsonl_to_xlsx_v2.py \
        --input outputs/s09_shortlist.jsonl \
        --output-stem outputs/s09_shortlist

Each run produces:
    <output_stem>_part1.xlsx
    <output_stem>_part2.xlsx

Each workbook contains:
    Documents     — top-level fields as columns; nested dicts/lists flattened or JSON-serialized
    Raw_Records   — original JSON line per record, for lossless round-trip
    dict__*       — one sheet per nested dict field, flattened to columns
    list__* / items__* — one sheet per list field, one row per item
    Data_Dictionary — column inventory across all sheets
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


MAX_SHEET_NAME_LEN = 31
ILLEGAL_SHEET_CHARS = r"[:\\/?*\[\]]"


def safe_sheet_name(name: str, used: set[str]) -> str:
    name = re.sub(ILLEGAL_SHEET_CHARS, "_", name)
    name = name[:MAX_SHEET_NAME_LEN] or "Sheet"
    base = name
    i = 1
    while name in used:
        suffix = f"_{i}"
        name = (base[: MAX_SHEET_NAME_LEN - len(suffix)] + suffix)[:MAX_SHEET_NAME_LEN]
        i += 1
    used.add(name)
    return name


def clean_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=False)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


def flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    items: dict[str, Any] = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("Top-level JSON line is not an object")
                rows.append(obj)
            except Exception as e:
                raise ValueError(f"Failed parsing line {line_num}: {e}") from e
    return rows


def build_tables(records: list[dict[str, Any]], global_start_index: int = 0) -> dict[str, pd.DataFrame]:
    documents_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []

    dict_tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    list_scalar_tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    list_dict_tables: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for local_idx, rec in enumerate(records):
        global_idx = global_start_index + local_idx
        doc_id = rec.get("doc_id")
        filename = rec.get("filename")
        analysis = rec.get("analysis")

        raw_rows.append(
            {
                "global_record_index": global_idx,
                "part_record_index": local_idx,
                "doc_id": doc_id,
                "filename": filename,
                "raw_json": json.dumps(rec, ensure_ascii=False, sort_keys=False),
            }
        )

        doc_row: dict[str, Any] = {
            "global_record_index": global_idx,
            "part_record_index": local_idx,
            "doc_id": doc_id,
            "filename": filename,
        }

        for k, v in rec.items():
            if k == "analysis":
                continue
            if k in {"doc_id", "filename"}:
                continue
            doc_row[k] = clean_cell(v)

        if isinstance(analysis, dict):
            doc_row["analysis_json"] = json.dumps(analysis, ensure_ascii=False, sort_keys=False)

            scalar_analysis = {}
            for akey, aval in analysis.items():
                if isinstance(aval, dict):
                    flat = flatten_dict(aval, parent_key=akey)
                    scalar_part = {k: clean_cell(v) for k, v in flat.items() if not isinstance(v, (dict, list))}
                    doc_row.update(scalar_part)

                    dict_tables[akey].append(
                        {
                            "global_record_index": global_idx,
                            "part_record_index": local_idx,
                            "doc_id": doc_id,
                            "filename": filename,
                            **{k: clean_cell(v) for k, v in flat.items()},
                            "_json": json.dumps(aval, ensure_ascii=False, sort_keys=False),
                        }
                    )

                elif isinstance(aval, list):
                    if len(aval) == 0:
                        list_scalar_tables[akey].append(
                            {
                                "global_record_index": global_idx,
                                "part_record_index": local_idx,
                                "doc_id": doc_id,
                                "filename": filename,
                                "item_index": None,
                                "value": None,
                            }
                        )
                    else:
                        first_non_null = next((x for x in aval if x is not None), None)

                        if isinstance(first_non_null, dict):
                            for item_idx, item in enumerate(aval):
                                if item is None:
                                    list_dict_tables[akey].append(
                                        {
                                            "global_record_index": global_idx,
                                            "part_record_index": local_idx,
                                            "doc_id": doc_id,
                                            "filename": filename,
                                            "item_index": item_idx,
                                            "_json": None,
                                        }
                                    )
                                else:
                                    flat_item = flatten_dict(item)
                                    list_dict_tables[akey].append(
                                        {
                                            "global_record_index": global_idx,
                                            "part_record_index": local_idx,
                                            "doc_id": doc_id,
                                            "filename": filename,
                                            "item_index": item_idx,
                                            **{k: clean_cell(v) for k, v in flat_item.items()},
                                            "_json": json.dumps(item, ensure_ascii=False, sort_keys=False),
                                        }
                                    )
                        else:
                            for item_idx, item in enumerate(aval):
                                list_scalar_tables[akey].append(
                                    {
                                        "global_record_index": global_idx,
                                        "part_record_index": local_idx,
                                        "doc_id": doc_id,
                                        "filename": filename,
                                        "item_index": item_idx,
                                        "value": clean_cell(item),
                                    }
                                )

                        doc_row[f"{akey}_json"] = json.dumps(aval, ensure_ascii=False, sort_keys=False)

                else:
                    scalar_analysis[akey] = clean_cell(aval)

            doc_row.update(scalar_analysis)

        else:
            doc_row["analysis_json"] = clean_cell(analysis)

        documents_rows.append(doc_row)

    tables: dict[str, pd.DataFrame] = {
        "Documents": pd.DataFrame(documents_rows),
        "Raw_Records": pd.DataFrame(raw_rows),
    }

    for name, rows in dict_tables.items():
        tables[f"dict__{name}"] = pd.DataFrame(rows)

    for name, rows in list_scalar_tables.items():
        tables[f"list__{name}"] = pd.DataFrame(rows)

    for name, rows in list_dict_tables.items():
        tables[f"items__{name}"] = pd.DataFrame(rows)

    for tname, df in tables.items():
        if df.empty:
            continue
        preferred = [
            c for c in [
                "global_record_index", "part_record_index", "doc_id", "filename",
                "item_index", "value", "_json", "raw_json"
            ] if c in df.columns
        ]
        remaining = sorted([c for c in df.columns if c not in preferred])
        tables[tname] = df[preferred + remaining]

    return tables


def autosize_columns(writer: pd.ExcelWriter, df: pd.DataFrame, sheet_name: str, max_width: int = 60) -> None:
    ws = writer.sheets[sheet_name]
    for idx, col in enumerate(df.columns):
        values = [str(col)] + ["" if pd.isna(v) else str(v) for v in df[col].head(1000)]
        width = min(max(len(v) for v in values) + 2, max_width)
        ws.set_column(idx, idx, width)


def write_workbook(
    tables: dict[str, pd.DataFrame],
    output_path: Path,
    part_label: str,
    total_records: int,
    start_idx: int,
    end_idx: int,
) -> None:
    used_names: set[str] = set()

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook = writer.book

        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        wrap_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})
        text_fmt = workbook.add_format({"valign": "top"})

        readme_name = safe_sheet_name("README", used_names)
        pd.DataFrame(
            [
                {"field": "part_label", "value": part_label},
                {"field": "source_total_records", "value": total_records},
                {"field": "included_global_start_index", "value": start_idx},
                {"field": "included_global_end_index", "value": end_idx - 1},
                {"field": "included_record_count", "value": end_idx - start_idx},
                {"field": "split_method", "value": "Exact split by row order, no overlap, no skipped rows"},
                {"field": "Documents", "value": "Top-level record metadata plus flattened scalar analysis fields"},
                {"field": "Raw_Records", "value": "Exact original JSON line for every record in this part"},
                {"field": "dict__*", "value": "Nested dict fields from analysis, flattened to columns"},
                {"field": "list__*", "value": "List-of-scalars fields from analysis, one row per item"},
                {"field": "items__*", "value": "List-of-dicts fields from analysis, one row per item"},
            ]
        ).to_excel(writer, sheet_name=readme_name, index=False)

        for sheet_name, df in tables.items():
            safe_name = safe_sheet_name(sheet_name, used_names)
            out_df = df.copy()

            for col in out_df.columns:
                out_df[col] = out_df[col].map(clean_cell)

            out_df.to_excel(writer, sheet_name=safe_name, index=False)

            ws = writer.sheets[safe_name]
            ws.freeze_panes(1, 0)

            for col_idx, col_name in enumerate(out_df.columns):
                ws.write(0, col_idx, col_name, header_fmt)

            if len(out_df.columns) > 0 and len(out_df) > 0:
                ws.set_column(0, len(out_df.columns) - 1, None, text_fmt)

            for col_idx, col_name in enumerate(out_df.columns):
                if col_name.endswith("_json") or col_name in {"raw_json", "analysis_json", "_json", "value"}:
                    ws.set_column(col_idx, col_idx, 50, wrap_fmt)

            autosize_columns(writer, out_df, safe_name)
            ws.autofilter(0, 0, max(len(out_df), 1), max(len(out_df.columns) - 1, 0))

        dict_name = safe_sheet_name("Data_Dictionary", used_names)
        dd_rows = []
        for tname, df in tables.items():
            for col in df.columns:
                dd_rows.append({"sheet": tname, "column": col})
        pd.DataFrame(dd_rows).to_excel(writer, sheet_name=dict_name, index=False)


def split_records_exact(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    n = len(records)
    midpoint = (n + 1) // 2  # first half gets the extra row if odd
    return records[:midpoint], records[midpoint:]


def validate_split(
    all_records: list[dict[str, Any]],
    part1: list[dict[str, Any]],
    part2: list[dict[str, Any]]
) -> None:
    if len(part1) + len(part2) != len(all_records):
        raise ValueError("Split validation failed: combined part sizes do not match total")

    original_json = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in all_records]
    split_json = (
        [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in part1] +
        [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in part2]
    )

    if original_json != split_json:
        raise ValueError("Split validation failed: row order/content changed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to any pipeline JSONL output file")
    parser.add_argument("--output-stem", required=True, help="Output stem, without extension")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_stem = Path(args.output_stem)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    records = read_jsonl(input_path)
    part1, part2 = split_records_exact(records)
    validate_split(records, part1, part2)

    part1_path = output_stem.parent / f"{output_stem.name}_part1.xlsx"
    part2_path = output_stem.parent / f"{output_stem.name}_part2.xlsx"

    tables1 = build_tables(part1, global_start_index=0)
    tables2 = build_tables(part2, global_start_index=len(part1))

    write_workbook(
        tables=tables1,
        output_path=part1_path,
        part_label="part1",
        total_records=len(records),
        start_idx=0,
        end_idx=len(part1),
    )
    write_workbook(
        tables=tables2,
        output_path=part2_path,
        part_label="part2",
        total_records=len(records),
        start_idx=len(part1),
        end_idx=len(records),
    )

    print(f"Done:")
    print(f"  {part1_path}")
    print(f"  {part2_path}")
    print(f"Total records: {len(records)}")
    print(f"Part 1: {len(part1)}")
    print(f"Part 2: {len(part2)}")
    print("Validation passed: no skipped rows, no overlap, original order preserved.")


if __name__ == "__main__":
    main()