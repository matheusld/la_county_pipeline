import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Any, List


def load_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def try_parse_json(text: str):
    text = (text or '').strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None
    return None


def extract_text_from_response_body(body: Dict[str, Any]) -> str:
    output = body.get('output', [])
    for item in output:
        content = item.get('content', [])
        for part in content:
            if part.get('type') in {'output_text', 'text'} and part.get('text'):
                return part['text']
            if part.get('type') == 'json_schema' and part.get('json'):
                return json.dumps(part['json'], ensure_ascii=False)
    if isinstance(body.get('output_text'), str):
        return body['output_text']
    if isinstance(body.get('response'), dict):
        return extract_text_from_response_body(body['response'])
    return ''


def to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def parse_json_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def has_nonempty(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return 1 if value.strip() and value.strip().lower() != 'null' else 0
    if isinstance(value, list):
        return 1 if len(value) > 0 else 0
    return 1


def final_priority(row: Dict[str, Any]) -> int:
    relevance = to_int(row.get('relevance'), 0)
    confidence = to_int(row.get('confidence'), 1)
    connection_strength = to_int(row.get('connection_strength'), 0)
    needs_second_pass = 1 if str(row.get('needs_second_pass', '')).lower() == 'true' else 0

    care_struct_bonus = 4 if parse_json_list(row.get('care_first_structures')) else 0
    ai_struct_bonus = 4 if parse_json_list(row.get('ai_governance_structures')) else 0
    tech_bonus = 2 if parse_json_list(row.get('tech_systems_or_vendors')) else 0
    actor_bonus = 2 if parse_json_list(row.get('main_actors')) else 0
    money_bonus = 2 if has_nonempty(row.get('money')) else 0
    decision_bonus = 3 if has_nonempty(row.get('decision_or_event')) else 0
    evidence_bonus = 4 if len(parse_json_list(row.get('evidence_quotes'))) >= 1 else 0
    direct_link_bonus = 3 if str(row.get('connection_type', '')).lower() == 'direct institutional link' else 0

    return (
        relevance * 12
        + confidence * 4
        + connection_strength * 8
        + needs_second_pass * 6
        + care_struct_bonus + ai_struct_bonus + tech_bonus + actor_bonus
        + money_bonus + decision_bonus + evidence_bonus + direct_link_bonus
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch-output-jsonl', required=True)
    ap.add_argument('--manifest-csv', required=True)
    ap.add_argument('--output-csv', default='./batch_triage_results.csv')
    ap.add_argument('--second-pass-csv', default='./second_pass_candidates.csv')
    ap.add_argument('--second-pass-n', type=int, default=180)
    args = ap.parse_args()

    manifest = {row['custom_id']: row for row in load_csv(Path(args.manifest_csv))}
    merged_rows = []
    parsed = 0
    errors = 0

    with open(args.batch_output_jsonl, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            custom_id = record.get('custom_id', '')
            body = (record.get('response') or {}).get('body', {})
            text = extract_text_from_response_body(body)
            payload = try_parse_json(text)
            if payload is None:
                errors += 1
                payload = {}
            else:
                parsed += 1

            base = manifest.get(custom_id, {}).copy()
            row = {
                **base,
                'relevance': payload.get('relevance'),
                'confidence': payload.get('confidence'),
                'doc_type_llm': payload.get('doc_type'),
                'care_first_structures': json.dumps(payload.get('care_first_structures', []), ensure_ascii=False),
                'ai_governance_structures': json.dumps(payload.get('ai_governance_structures', []), ensure_ascii=False),
                'care_domains': json.dumps(payload.get('care_domains', []), ensure_ascii=False),
                'tech_systems_or_vendors': json.dumps(payload.get('tech_systems_or_vendors', []), ensure_ascii=False),
                'main_actors': json.dumps(payload.get('main_actors', []), ensure_ascii=False),
                'money': payload.get('money'),
                'decision_or_event': payload.get('decision_or_event'),
                'connection_type': payload.get('connection_type'),
                'connection_strength': payload.get('connection_strength'),
                'why_it_matters': payload.get('why_it_matters'),
                'evidence_quotes': json.dumps(payload.get('evidence_quotes', []), ensure_ascii=False),
                'evidence_labels': json.dumps(payload.get('evidence_labels', []), ensure_ascii=False),
                'needs_second_pass': payload.get('needs_second_pass'),
            }
            row['final_priority'] = final_priority(row)
            merged_rows.append(row)

    merged_rows.sort(
        key=lambda r: (
            to_int(r.get('final_priority'), 0),
            to_int(r.get('connection_strength'), 0),
            to_int(r.get('relevance'), 0),
            to_int(r.get('confidence'), 0),
        ),
        reverse=True,
    )

    preferred_fields = [
        'custom_id', 'filename', 'meeting_date', 'doc_type', 'char_count',
        'path', 'original_path', 'source_bucket', 'source_format', 'extraction_method',
        'api_score', 'care_score', 'tech_score', 'top_hits', 'money_hits', 'vendors_found',
        'relevance', 'confidence', 'doc_type_llm', 'care_first_structures', 'ai_governance_structures',
        'care_domains', 'tech_systems_or_vendors', 'main_actors', 'money', 'decision_or_event',
        'connection_type', 'connection_strength', 'why_it_matters', 'evidence_quotes', 'evidence_labels',
        'needs_second_pass', 'final_priority'
    ]

    # Robust to manifest/schema drift: include all unexpected keys instead of crashing.
    discovered_fields = []
    seen = set(preferred_fields)
    for row in merged_rows:
        for key in row.keys():
            if key not in seen:
                discovered_fields.append(key)
                seen.add(key)

    out_fields = preferred_fields + discovered_fields

    with open(args.output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(merged_rows)

    second_pass = [
        r for r in merged_rows
        if to_int(r.get('relevance'), 0) >= 2
        and to_int(r.get('connection_strength'), 0) >= 1
        and str(r.get('needs_second_pass', '')).lower() == 'true'
    ][: args.second_pass_n]

    with open(args.second_pass_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(second_pass)

    print(f'Parsed OK      : {parsed:,}')
    print(f'Parse failures : {errors:,}')
    print(f'Merged rows    : {len(merged_rows):,}')
    print(f'Second pass    : {len(second_pass):,}')
    print(f'Wrote          : {args.output_csv}')
    print(f'Wrote          : {args.second_pass_csv}')


if __name__ == '__main__':
    main()
